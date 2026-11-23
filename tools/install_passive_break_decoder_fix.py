"""Install one tested passive HMI predicate on the discharged, disarmed stand."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from urllib.request import ProxyHandler, Request, build_opener

from collect_wifi_telemetry import get_status, read_token
from prepare_passive_break_decoder_fix import BASE, BASE_SHA, CAL_SHA, ROOT, control_ast, sha

REMOTE = '/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi'
FIRST_FIELDS = ('mc_fault_reason','mc_uart_error_flags','mc_fault_current_mask',
    'mc_fault_occurred_mask','mc_fault_motor_state','mc_fault_sequence','mc_fault_tx_status')
ERROR_FIELDS = ('bp_bad_cnt','bp_bad_integrity','bp_bad_sequence','bp_ne_observed','bp_ne_accepted',
    'uno_rx_hw_errors','uno_rx_hw_flags','uno_rx_dropped','uno_tx_short_writes',
    'uno_tx_gaps_over_watchdog','mc_break_rx_bad')


def validate_idle(data):
    if (any(type(data.get(k)) is not int for k in ('fw_build','mc_fw_build'))
        or (data.get('fw_build'),data.get('mc_fw_build'))!=(2026101205,2026101204)
        or data.get('state')!='SAFE' or data.get('pwm')!=0
        or data.get('hmi_hv_armed')!=0 or data.get('hmi_hv_started')!=0
        or data.get('hmi_powered_trial_enabled')!=0 or data.get('bp_transport_fault')!=0
        or data.get('mc_diag_valid')!=1):
        raise RuntimeError('Stand identity or disarmed idle state changed')
    for key, upper in (('vdc',2.000001),('bp_vdc',2.000001),('bp_age_ms',300),('bp_vbus_age_ms',300)):
        value=data.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<upper:
            raise RuntimeError('Invalid/unqualified idle field: '+key)
    if data.get('bp_vbus_valid')!=1 or type(data.get('bp_status')) is not int or data['bp_status']&0x22:
        raise RuntimeError('Bus telemetry invalid or controller outputs active')
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True,type=Path)
    parser.add_argument('--selftest',required=True,type=Path)
    parser.add_argument('--guards',required=True,type=Path)
    parser.add_argument('--outdir',required=True,type=Path)
    args=parser.parse_args(); candidate=args.candidate.resolve()
    target=candidate/'web_hmi/server.py'
    manifest=json.loads((candidate/'manifest.json').read_text())
    test=json.loads(args.selftest.read_text()); guards=json.loads(args.guards.read_text())
    if (manifest.get('schema')!='mic_ai.passive_break_decoder_fix.v1'
        or manifest.get('base_sha256')!=BASE_SHA or sha(BASE)!=BASE_SHA
        or sha(target)!=manifest.get('hmi_sha256')
        or test.get('pass') is not True or test.get('hmi_sha256')!=sha(target)
        or test.get('hardware_commands')!=0 or test.get('control_ast_identical') is not True
        or guards.get('pass') is not True or guards.get('hardware_commands')!=0
        or len(guards.get('suites',[]))!=5 or not all(s.get('pass') is True for s in guards['suites'])
        or control_ast(target.read_text())!=control_ast(BASE.read_text())):
        raise RuntimeError('Candidate or mandatory offline evidence changed/failed')
    for relative,digest in test.get('test_source_sha256',{}).items():
        if sha(ROOT/relative)!=digest: raise RuntimeError('Tested check source changed')
    out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    new=sha(target); token=read_token(str(ROOT/'.unoq_ssh/control_token'))
    opener=build_opener(ProxyHandler({}))
    ssh=['ssh','-p','2222','-i',str(ROOT/'.unoq_ssh/id_ed25519'),
        '-o','UserKnownHostsFile='+str(ROOT/'.unoq_ssh/known_hosts'),'-o','StrictHostKeyChecking=yes',
        '-o','BatchMode=yes','-o','ConnectTimeout=5','arduino@192.168.1.138']
    scp=['scp','-P','2222','-i',str(ROOT/'.unoq_ssh/id_ed25519'),
        '-o','UserKnownHostsFile='+str(ROOT/'.unoq_ssh/known_hosts'),'-o','StrictHostKeyChecking=yes',
        '-o','BatchMode=yes','-o','ConnectTimeout=5']
    report={'schema':'mic_ai.passive_break_decoder_install.v1','pass':False,
        'hmi_sha256':new,'base_sha256':BASE_SHA,'mcu_flash_commands':0,'arm_commands':0,
        'start_commands':0,'clear_commands':0,'calibration_file_modified':False,
        'hv_release_approved':False,'operations':[],
        'offline_evidence_sha256':{'selftest':sha(args.selftest),'guards':sha(args.guards)}}
    settings=f'REMOTE={REMOTE!r}\nBASE_SHA={BASE_SHA!r}\nCAL_SHA={CAL_SHA!r}\nNEW_SHA={new!r}\n'
    common="""
from pathlib import Path
import hashlib, json, os, signal, shutil, subprocess
root=Path(REMOTE)
target=root/'server.py'
stage=root/'passive_decoder_20261014.staged'
backup=root/'server.py.before_passive_decoder_20261014'
cal=Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def prop(name):
    return subprocess.check_output(['systemctl','show','unoq-hmi.service','-p',name,'--value'],text=True).strip()
def owned_pid():
    assert prop('User')=='arduino' and prop('Restart')=='always'
    pid=int(prop('MainPID')); assert pid>1
    proc=Path('/proc')/str(pid)
    assert proc.stat().st_uid==os.getuid() and (proc/'cwd').resolve()==root
    assert b'server.py' in (proc/'cmdline').read_bytes().split(bytes([0]))
    return pid
assert digest(cal)==CAL_SHA
"""
    def run(command,label,source=None):
        result=subprocess.run(command,input=source,capture_output=True,text=True,
            encoding='utf-8',errors='replace',timeout=40)
        (out/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        report['operations'].append({'label':label,'exit_code':result.returncode})
        if result.returncode: raise RuntimeError(label+' failed; inspect retained log')
        return result.stdout
    def remote(label,code): return run(ssh+[REMOTE+'/.venv/bin/python -'],label,settings+common+code)
    def idle(): return validate_idle(get_status(opener,'http://192.168.1.138:8080'))
    swapped=False
    try:
        before=idle(); (out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
        before_remote=json.loads(remote('precheck',"""
assert digest(target)==BASE_SHA and not backup.exists() and not stage.exists()
pid=owned_pid()
print(json.dumps({'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'pid':pid,'hmi_sha256':digest(target),'ui_sha256':digest(root/'static/app.js'),
    'calibration_sha256':digest(cal)}))
"""))
        run(scp+[str(target),'arduino@192.168.1.138:'+REMOTE+'/passive_decoder_20261014.staged'],'stage_candidate')
        idle()
        remote('atomic_install',"""
assert digest(target)==BASE_SHA and digest(stage)==NEW_SHA and not backup.exists()
owned_pid()
compile(stage.read_text(),str(stage),'exec')
shutil.copy2(target,backup)
assert digest(backup)==BASE_SHA
stage.chmod(target.stat().st_mode)
stage.replace(target)
assert digest(target)==NEW_SHA and digest(cal)==CAL_SHA
print('Installed only the tested passive HMI decoder; predecessor backup retained')
""")
        swapped=True
        remote('restart_owned_hmi',"""
assert digest(target)==NEW_SHA and digest(backup)==BASE_SHA
pid=owned_pid()
print('SIGTERM owned HMI process',pid,flush=True)
os.kill(pid,signal.SIGTERM)
""")
        for attempt in range(15):
            try: after=idle(); break
            except Exception:
                if attempt==14: raise
                time.sleep(1)
        assert all(before.get(k)==after.get(k) for k in FIRST_FIELDS),'First fault snapshot changed'
        after_remote=json.loads(remote('verify_install',"""
assert digest(target)==NEW_SHA and digest(backup)==BASE_SHA
print(json.dumps({'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'pid':owned_pid(),'hmi_sha256':digest(target),'ui_sha256':digest(root/'static/app.js'),
    'calibration_sha256':digest(cal)}))
"""))
        assert after_remote['boot_id']==before_remote['boot_id'],'MCU/Linux boot unexpectedly changed'
        assert after_remote['ui_sha256']==before_remote['ui_sha256'],'UI source unexpectedly changed'
        assert after_remote['pid']!=before_remote['pid'],'New HMI process not observed'
        rows=[]; started=time.monotonic()
        with (out/'status.jsonl').open('w',encoding='utf-8') as stream:
            while True:
                data=idle(); elapsed=time.monotonic()-started
                rows.append({'elapsed_s':elapsed,'status':data})
                stream.write(json.dumps(rows[-1])+'\n'); stream.flush()
                assert all(data.get(k)==before.get(k) for k in FIRST_FIELDS),'First fault snapshot changed'
                assert all(data.get(k)==before.get(k) for k in ERROR_FIELDS),'UART errors/counters changed'
                if elapsed-rows[0]['elapsed_s']>=30: break
                time.sleep(1)
        delta=rows[-1]['status']['bp_good_cnt']-rows[0]['status']['bp_good_cnt']
        assert delta>=100,'Not enough advancing UART frames'
        request=Request('http://192.168.1.138:8080/api/break-snapshot',headers={'X-UNOQ-Control-Token':token})
        with opener.open(request,timeout=8) as response: snapshot=json.load(response)
        records=snapshot.get('data',{}).get('mc_break_snapshots',[])
        assert snapshot.get('ok') is True and len(records)==2 and all(r.get('available') is True for r in records), 'Passive snapshots unavailable'
        (out/'break_snapshot.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        (out/'after.json').write_text(json.dumps(rows[-1]['status'],indent=2)+'\n')
        report.update({'pass':True,'before_remote':before_remote,'after_remote':after_remote,
            'first_fault_snapshot_preserved':True,'uart_error_counters_preserved':True,
            'samples':len(rows),'span_s':rows[-1]['elapsed_s']-rows[0]['elapsed_s'],
            'new_good_frames':delta,'snapshot_reasons':[r.get('reason') for r in records]})
    except Exception as exc:
        report['error']=str(exc)
        if swapped:
            try:
                remote('rollback_and_restart',"""
assert digest(target)==NEW_SHA and digest(backup)==BASE_SHA
pid=owned_pid()
rollback=root/'passive_decoder_20261014.rollback'
assert not rollback.exists()
shutil.copy2(backup,rollback)
rollback.replace(target)
assert digest(target)==BASE_SHA
print('Restored predecessor HMI; SIGTERM owned process',pid,flush=True)
os.kill(pid,signal.SIGTERM)
""")
                report['rolled_back']=True
            except Exception as rollback_error: report['rollback_error']=str(rollback_error)
        raise
    finally:
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report.get(key) for key in ('pass','samples','span_s','new_good_frames','snapshot_reasons','mcu_flash_commands','error')}))


if __name__=='__main__': main()
