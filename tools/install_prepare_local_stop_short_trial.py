"""Install the tested admission-only HMI and accept one non-actuating preparation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.request import ProxyHandler,build_opener

from collect_wifi_telemetry import get_status,read_token
from prepare_local_stop_fixture_trial import ROOT,HERE,BASE_SHA,audit
from run_wifi_nucleo_pwm_bench import WifiHmi,wait_status

REMOTE='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py'
CAL='/home/arduino/.config/mic-ai/vbus_calibration.json'
CAL_SHA='a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();candidate=a.candidate.resolve();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    images,evidence=audit();manifest=json.loads((candidate/'manifest.json').read_text())
    source=candidate/'web_hmi/server.py';digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest==manifest['hmi_sha256'] and evidence==manifest['evidence_sha256']
    for name in ('short_trial_selftest_r1/report.json','short_trial_guards_r1/report.json'):
        assert json.loads((HERE/name).read_text())['pass'] is True
    ssh=['ssh','-p','2222','-i',str(ROOT/'.unoq_ssh/id_ed25519'),'-o','UserKnownHostsFile='+str(ROOT/'.unoq_ssh/known_hosts'),'-o','StrictHostKeyChecking=yes','arduino@192.168.1.138']
    scp=['scp','-P','2222','-i',str(ROOT/'.unoq_ssh/id_ed25519'),'-o','UserKnownHostsFile='+str(ROOT/'.unoq_ssh/known_hosts'),'-o','StrictHostKeyChecking=yes']
    report={'schema':'mic_ai.local_stop_short_trial_install.v1','pass':False,'hmi_sha256':digest,
            'mcu_flash_commands':0,'arm_commands':0,'start_commands':0,'clear_commands':0,
            'calibration_modified':False,'hardware_commands':[],'operations':[]}
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(cmd,label,source=None):
        r=subprocess.run(cmd,input=source,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        (out/(label+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        report['operations'].append({'label':label,'exit_code':r.returncode});save()
        if r.returncode:raise RuntimeError(label+' failed')
        return r.stdout
    def py(code,label):return run(ssh+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -'],label,code)
    opener=build_opener(ProxyHandler({}))
    def idle():
        s=get_status(opener,'http://192.168.1.138:8080')
        assert (s['fw_build'],s['mc_fw_build'])==(2026101205,2026101204)
        assert s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==s['hmi_local_stop_latched']==0
        assert s['vdc']==0 and 0<=s['bp_vbus_raw']<=20 and not(s['bp_status']&0x22)
        assert s['bp_transport_fault']==s['bp_bad_cnt']==0 and s['bp_age_ms']<300
        assert s['hmi_vbus_hv_calibrated']==1 and s['hmi_powered_trial_enabled']==0
        assert s['bp_fault'] in (0,5)
        return s
    try:
        before=idle();(out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
        config=f"REMOTE={REMOTE!r}\nOLD={BASE_SHA!r}\nNEW={digest!r}\nCAL={CAL!r}\nCAL_SHA={CAL_SHA!r}\n"
        code='''from pathlib import Path
import hashlib
p=Path(REMOTE);c=Path(CAL)
assert hashlib.sha256(p.read_bytes()).hexdigest()==OLD
assert hashlib.sha256(c.read_bytes()).hexdigest()==CAL_SHA
assert not p.with_name('server.py.short-trial-staged').exists()
assert not p.with_name('server.py.before_short_trial_fixture_delta').exists()
print('Pinned HMI/calibration verified')
'''
        py(config+code,'remote_before')
        run(scp+[str(source),'arduino@192.168.1.138:'+str(Path(REMOTE).with_name('server.py.short-trial-staged')).replace('\\','/')],'stage_hmi')
        idle()
        code='''from pathlib import Path
import hashlib,subprocess,os,signal,shutil
p=Path(REMOTE);c=Path(CAL);q=p.with_name('server.py.short-trial-staged')
assert hashlib.sha256(p.read_bytes()).hexdigest()==OLD
assert hashlib.sha256(q.read_bytes()).hexdigest()==NEW
assert hashlib.sha256(c.read_bytes()).hexdigest()==CAL_SHA
compile(q.read_text(),str(q),'exec')
pid=int(subprocess.check_output(['systemctl','show','unoq-hmi.service','-p','MainPID','--value'],text=True))
proc=Path('/proc')/str(pid)
assert proc.stat().st_uid==os.getuid() and (proc/'cwd').resolve()==p.parent
assert b'server.py' in (proc/'cmdline').read_bytes().split(b'\\x00')
shutil.copy2(p,p.with_name('server.py.before_short_trial_fixture_delta'));q.chmod(p.stat().st_mode);q.replace(p)
os.kill(pid,signal.SIGTERM)
print('Admission-only HMI installed and owned process restarted')
'''
        py(config+code,'install_restart_hmi')
        token=read_token(str(ROOT/'.unoq_ssh/control_token'))
        h=WifiHmi('http://192.168.1.138:8080',token,report['hardware_commands'],via_wsl=False)
        s=wait_status(h,lambda s:(s.get('fw_build'),s.get('mc_fw_build'))==(2026101205,2026101204) and s.get('pwm')==s.get('hmi_hv_armed')==0,25,'HMI recovered without MCU restart')
        report['after_hmi_restart']=s
        # Server time avoids clock-skew rejection; proof lifetime is checked at acceptance.
        now=float(py('import time\nprint(time.time())\n','server_time').strip())
        proof=json.loads((candidate/'qualification_seed.json').read_text())
        proof.update(issued_at=now-1,expires_at=now+599,idle_tx_max_gap_us=s['uno_tx_all_max_gap_us'])
        (out/'qualification.json').write_text(json.dumps(proof,indent=2)+'\n')
        h.command('MODE VF');h.command('SET FREQ 5')
        h.post('/api/powered-trial',{'action':'prepare','confirm':'PREPARE UARTV3 TRIAL 3S','qualification':proof},'prepare one bounded trial; NO ARM/START')
        after=h.status();h.close()
        assert after['hmi_powered_trial_enabled']==1 and after['hmi_hv_armed']==after['pwm']==0
        assert after['hmi_powered_trial_wait_limited']==0 and after['hmi_powered_trial_remaining_s'] is None
        (out/'after.json').write_text(json.dumps(after,indent=2)+'\n')
        code='''from pathlib import Path
import hashlib
assert hashlib.sha256(Path(REMOTE).read_bytes()).hexdigest()==NEW
assert hashlib.sha256(Path(CAL).read_bytes()).hexdigest()==CAL_SHA
print('Installed HMI and unchanged calibration verified')
'''
        py(config+code,'remote_after')
        report.update({'pass':True,'prepared_not_armed':True,'accepted_wait_has_no_deadline':True,
                       'live_motor_identity':[after['fw_build'],after['mc_fw_build']],
                       'calibration_sha256':CAL_SHA,'limits_unchanged':True})
    except Exception as exc:report['error']=str(exc);raise
    finally:save()
    print(json.dumps({k:v for k,v in report.items() if k not in ('after_hmi_restart','hardware_commands')},indent=2))


if __name__=='__main__':main()
