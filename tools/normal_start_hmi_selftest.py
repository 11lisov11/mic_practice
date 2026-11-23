"""Exercise repeatable authenticated START/STOP on the real HMI HTTP handlers."""
import copy
import hashlib
import json
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from ipm_break_wifi_selftest import load_module
from prepare_normal_start_hmi import OUT, ROOT, SOURCE, CAL_SHA, sha


def main():
    mod = load_module(OUT / 'web_hmi/server.py')
    manifest=json.loads((OUT / 'manifest.json').read_text());assert manifest['hmi_sha256']==sha(OUT / 'web_hmi/server.py')
    archive=ROOT / 'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/vbus_recalibration_preparation/original_vbus_calibration.json'
    original=archive.read_bytes();assert hashlib.sha256(original).hexdigest()==CAL_SHA
    store=mod.VbusCalibrationStore(str(archive))
    s=json.loads((ROOT / 'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/working_bus_on_1791997952551152700/first_status.json').read_text())
    s.update(state='SAFE',state_code=0,pwm=0,estop=0,bp_fault=0,bp_status=1,bp_softstart_ready=1,
             bp_age_ms=20,bp_rsp_age_ms=20,mc_age_ms=20,mc_rsp_age_ms=20,bp_vbus_age_ms=20,bp_temp_age_ms=20,
             vdc=319.,bp_vdc=319.,bp_vbus_raw=3190,freq_cmd=5.,freq=0.,link=True)
    def canonical(data):
        for key,value in list(data.items()):
            if key.startswith('bp_'):data['mc_'+key[3:]]=value
        return mod.with_motor_controller_aliases(data)
    s=canonical(s)
    cases=0
    def check(value,name):
        nonlocal cases
        assert value,name;cases+=1
    check(store.is_valid(s),'original points valid on audited working pair')
    cfg=mod.HvArmConfig(enabled=True,min_vdc=250,max_vdc=360)
    check(mod.hv_arm_precheck(s,cfg,store.is_valid(s))[0],'ordinary ARM without trial')
    for field,value in [('fw_build',2026101412),('mc_fw_build',2026101412),('rpc_schema_version',4),('mc_capabilities',3),('bp_mcsdk_telemetry',0)]:
        changed=dict(s,**{field:value})
        if field.startswith('bp_'):changed=canonical(changed)
        check(not store.is_valid(changed),'unreviewed measurement identity '+field)
    for uno,nuc in [(2026101492,2026101493),(2026101411,2026101493),(2026101412,2026101410)]:
        changed=dict(s,fw_build=uno,mc_fw_build=nuc)
        check(not mod.hv_arm_precheck(changed,cfg,True)[0],'fixture or mixed pair blocked')
    for field,value in [('pwm',1),('estop',1),('bp_fault',5),('bp_bad_cnt',1),('bp_temp_valid',0),('bp_temp_fault',1),('bp_temp_c',150),('bp_vbus_raw',0),('vdc',0),('vdc',400),('state','VF_RUN'),('state_code',1),('bp_status',0x80)]:
        changed=dict(s,**{field:value})
        if field=='state':changed['state_code']=1
        if field=='state_code':changed['state']='VF_RUN'
        if field=='vdc':changed['bp_vdc']=value
        changed=canonical(changed)
        check(not mod.hv_arm_precheck(changed,cfg,True)[0],'original physical guard '+field)
    stale=dict(s,bp_age_ms=99999,bp_rsp_age_ms=99999,mc_age_ms=99999,mc_rsp_age_ms=99999,last_rx_age_s=99999)
    check(not mod.hv_arm_precheck(stale,cfg,True)[0],'stale link blocked')
    check(not mod.hv_arm_precheck(s,cfg,False)[0],'invalid calibration blocked')
    class Rpc:
        def __init__(self):self.data=copy.deepcopy(s);self.commands=[]
        def get(self):return True,canonical(copy.deepcopy(self.data)),''
        def cmd(self,cmd):
            self.commands.append(cmd)
            if cmd=='START':self.data.update(state='VF_RUN',state_code=1,pwm=1,bp_status=0x23,freq=self.data['freq_cmd'])
            elif cmd in ('STOP','ESTOP'):self.data.update(state='SAFE',state_code=0,pwm=0,bp_status=1,freq=0.)
            elif cmd.startswith('SET FREQ '):self.data['freq_cmd']=float(cmd.split()[-1])
            return True,''
    rpc=Rpc();opener=build_opener(ProxyHandler({}))
    with tempfile.TemporaryDirectory() as tmp:
        token='offline-normal-start-test-credential';tokenfile=Path(tmp)/'token';tokenfile.write_text(token)
        app=mod.AppState(rpc,mod.LogStore(65536,None,65536),0,
            command_guard=mod.CommandGuardConfig(max_vdc=400,allow_hv=True,local_bench_gate=True),
            hv_arm=mod.HvArmState(cfg),start_runlimit_sec=15,
            control_access=mod.ControlAccessConfig(str(tokenfile)),vbus_calibration=store)
        server=mod.ThreadingHTTPServer(('127.0.0.1',0),mod.Handler);server.app=app
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(path,body,auth=True):
            headers={'Content-Type':'application/json'}
            if auth:headers['X-UNOQ-Control-Token']=token
            request=Request('http://127.0.0.1:'+str(server.server_port)+path,json.dumps(body).encode(),headers,method='POST')
            try:
                with opener.open(request,timeout=4) as response:return response.status,json.load(response)
            except HTTPError as exc:return exc.code,json.load(exc)
        try:
            code,result=post('/api/start-sequence',{'runlimit_s':3},False)
            check(code in (401,403) and not rpc.commands,'unauthenticated START blocked')
            for iteration in range(2):
                code,result=post('/api/hv-arm',{'action':'arm','confirm':cfg.confirm})
                check(code==200 and result.get('ok'),'ordinary authenticated ARM '+str(iteration))
                code,result=post('/api/start-sequence',{'runlimit_s':3})
                check(code==200 and result.get('ok') and rpc.data['pwm']==1,'ordinary authenticated START '+str(iteration))
                check(app.hv_arm.cfg.trial_gate is None and not app._powered_trial_spent,'no consumed one-shot '+str(iteration))
                code,result=post('/api/cmd',{'cmd':'SET FREQ 7'})
                check(code==200 and result.get('ok') and rpc.data['freq_cmd']==7,'online frequency change '+str(iteration))
                code,result=post('/api/stop-sequence',{'emergency':False})
                check(code==200 and result.get('ok') and rpc.data['pwm']==0,'ordinary STOP '+str(iteration))
            check(sum(cmd=='START' for cmd in rpc.commands)==2,'repeated START requires no new proof or firmware')
            check(sum(cmd.startswith('SET RUNLIMIT 3.') for cmd in rpc.commands)==2,'MCU runlimit sent on each START')
            check(not any(cmd=='CLEAR' for cmd in rpc.commands),'no automatic fault acknowledgement')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=4)
    check(archive.read_bytes()==original,'original calibration bytes untouched')
    # Existing safety suites use the candidate through their normal loader.
    import web_hmi_command_guard_selftest as guards
    import web_hmi_control_access_selftest as authtests
    suites=[]
    for module in (guards,authtests):
        loader='load_server_module' if hasattr(module,'load_server_module') else 'load_server'
        saved=getattr(module,loader);setattr(module,loader,lambda root:mod)
        try:result=module.main();check(result in (0,None),module.__name__);suites.append(module.__name__)
        finally:setattr(module,loader,saved)
    report=dict(pass_=True,cases=cases,ordinary_http_starts=2,online_frequency_changes=2,
                hmi_sha256=manifest['hmi_sha256'],original_calibration_unchanged=True,
                mcu_firmware_writes=0,hardware_commands=0,safety_suites=suites)
    report['pass']=report.pop('pass_');(OUT/'selftest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
