"""Adversarial schema checks; existing actuator/live guards must stay unchanged."""
import argparse
import ast
import copy
import json
from pathlib import Path
import tempfile
import time

from ipm_break_wifi_selftest import load_module
from prepare_local_stop_fixture_trial import BASE, ROOT
from unoq_boot_trial_selftest import status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    path=a.candidate/'web_hmi/server.py';m=load_module(path)
    proof=json.loads((a.candidate/'qualification_seed.json').read_text())
    proof.update(issued_at=time.time()-1,expires_at=time.time()+300)
    checks=[]
    def check(ok,label):checks.append(label);assert ok,label
    check(m.validate_powered_trial_qualification(proof)[0],'valid exact retained evidence')
    for key,value in proof.items():
        if type(value) is bool:
            altered=dict(proof,**{key:not value})
            check(not m.validate_powered_trial_qualification(altered)[0],key+' required claim/limitation')
            altered=dict(proof,**{key:int(value)})
            check(not m.validate_powered_trial_qualification(altered)[0],key+' boolean type')
    for key,value in [('pair',[2026101108,2026101102]),('fixture_pair',[2026101298.0,2026101299]),
                      ('max_run_s',4),('max_run_s',3.0),('max_frequency_hz',6),('max_frequency_hz',True),
                      ('offline_suites',56),('sd_sample_v',0),('sd_sample_v',float('nan')),
                      ('idle_tx_max_gap_us',100000),('expires_at',time.time()-1),
                      ('issued_at',time.time()+1000),('expires_at',time.time()+1000),
                      ('schema',m.BOOT_TRIAL_SCHEMA),('profile','coast30'),('scope','local_stop_with_hardware_pwm_validation')]:
        check(not m.validate_powered_trial_qualification(dict(proof,**{key:value}))[0],key+' invalid '+str(value))
    for key in ('images','fixture_images','evidence_sha256'):
        for field in proof[key]:
            altered=copy.deepcopy(proof);altered[key][field]='0'*64
            check(not m.validate_powered_trial_qualification(altered)[0],key+'/'+field+' fingerprint mutation')
        altered=copy.deepcopy(proof);altered[key].pop(next(iter(altered[key])))
        check(not m.validate_powered_trial_qualification(altered)[0],key+' missing fingerprint')
    # Only a schema validator/dispatch branch and constants were added.
    old=ast.parse(BASE.read_text(encoding='utf-8'));new=ast.parse(path.read_text(encoding='utf-8'))
    before={n.name:n for n in old.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    after={n.name:n for n in new.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    for name,node in before.items():
        if name!='validate_powered_trial_qualification':
            check(ast.dump(node)==ast.dump(after[name]),name+' AST unchanged')
    s=status();s.update(fw_build=2026101205,mc_fw_build=2026101204)
    g=m.PoweredTrialGate(300,pair=m.BOOT_TRIAL_PAIR,wait_without_deadline=True)
    check((g.max_run_s,g.max_freq_hz)==(3,5),'runtime caps unchanged')
    for key,value in [('hmi_hv_armed',1),('bp_fault',5),('vdc',0),('vdc',361),
                      ('bp_age_ms',300),('bp_transport_fault',1),('freq_cmd',5.1),('bp_status',0x80)]:
        # ARM also checks the latch/output state. Test each applicable live gate.
        data=dict(s,**{key:value})
        if key=='bp_status':
            cfg=m.HvArmConfig(enabled=True,trial_gate=g)
            check(not m.hv_arm_precheck(data,cfg,True)[0],'latched STOP blocks ARM')
        elif key!='hmi_hv_armed':
            check(not g.live_check(data,idle=True,pair=m.BOOT_TRIAL_PAIR)[0],key+' live gate retained')
    check(g.expires_at is None,'accepted preparation wait remains unlimited')
    g.consume();check(not g.ready(s,True)[0],'one-shot consumed')
    # Preparation is non-actuating and preserves original calibration bytes.
    class Rpc:
        def __init__(self,data):self.data=data;self.commands=[]
        def get(self):return True,dict(self.data),''
        def cmd(self,command):self.commands.append(command);raise AssertionError(command)
    class Logs:
        def add(self,line):pass
    with tempfile.TemporaryDirectory() as d:
        cp=Path(d)/'cal.json'
        record=dict(schema=m.VbusCalibrationStore.SCHEMA,
                    identity=dict(fw_build=2026092901,mc_fw_build=2026100601,rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1),
                    points={'zero':{'meter_vdc':0,'mc_vdc_mean':0},'high':{'meter_vdc':322.7,'mc_vdc_mean':325}})
        record['integrity_sha256']=m.VbusCalibrationStore._digest(record);cp.write_text(json.dumps(record));original=cp.read_bytes()
        data=dict(s,vdc=0,bp_vdc=0,bp_vbus_raw=0,rpc_schema_version=3,bp_softstart_ready=0)
        rpc=Rpc(data);app=m.AppState(rpc,Logs(),1,hv_arm=m.HvArmState(m.HvArmConfig(enabled=True)),
            control_access=m.ControlAccessConfig(token_file='test-only'),vbus_calibration=m.VbusCalibrationStore(str(cp)))
        ok,reason=app.prepare_powered_trial(proof,'PREPARE UARTV3 TRIAL 3S')
        check(ok,'non-actuating preparation accepted: '+reason)
        check(not rpc.commands,'no hardware commands during preparation')
        check(cp.read_bytes()==original,'calibration bytes preserved')
        check(app.hv_arm.cfg.trial_gate.expires_at is None,'prepared gate has no wait deadline')
        check(app.hv_arm.cfg.ttl_sec<=10,'active ARM expiry retained')
    report={'pass':True,'checks':len(checks),'cases':checks,'hardware_commands':0,
            'actuator_and_live_gate_ast_unchanged':True,'calibration_preserved':True}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},indent=2))


if __name__=='__main__':main()
