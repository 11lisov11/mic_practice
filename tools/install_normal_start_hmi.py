"""Install the tested normal HMI only, without restarting or flashing either MCU."""
import json
import time
from pathlib import Path

import pwm_filter_hardware_session as bench
from collect_wifi_telemetry import get_status
from install_passive_break_decoder_fix import ERROR_FIELDS,FIRST_FIELDS
from prepare_normal_start_hmi import OUT,sha


def main():
    s=bench.Session(bench.ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1')
    manifest=json.loads((OUT/'manifest.json').read_text())
    test=json.loads((OUT/'selftest.json').read_text());guards=json.loads((OUT/'guards_r1/report.json').read_text())
    assert test['pass'] and test['ordinary_http_starts']==2 and test['hmi_sha256']==manifest['hmi_sha256']
    assert guards['pass'] and len(guards['suites'])==5
    assert sha(OUT/'web_hmi/server.py')==manifest['hmi_sha256']
    def stopped():
        st=get_status(s.opener,'http://192.168.1.138:8080')
        assert (st['fw_build'],st['mc_fw_build'])==bench.PROD
        assert st['state']=='SAFE' and st['pwm']==st['hmi_hv_armed']==st['hmi_hv_started']==0
        assert not(st['bp_status']&0x22) and st['bp_transport_fault']==0 and 0<=st['bp_age_ms']<300
        assert all(st.get(k)==0 for k in ERROR_FIELDS)
        assert all(st.get(k)==0 for k in ('precharge','pfc','brake','bp_ext'))
        return st
    before=stopped();s.hashes('normal_hmi_preinstall_hashes')
    out=OUT/'installation';out.mkdir(exist_ok=False)
    (out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
    common=f'''from pathlib import Path
import hashlib,subprocess,os,signal,shutil,json
root=Path({bench.HMI_ROOT!r});target=root/'server.py';stage=root/'normal_start_hmi_r1.staged';backup=root/'server.py.before_normal_start_hmi_r1'
cal=Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def pid():
 prop=lambda k:subprocess.check_output(['systemctl','show','unoq-hmi.service','-p',k,'--value'],text=True).strip()
 assert prop('User')=='arduino' and prop('Restart')=='always'
 p=int(prop('MainPID'));proc=Path('/proc')/str(p)
 assert p>1 and proc.stat().st_uid==os.getuid() and (proc/'cwd').resolve()==root
 assert b'server.py' in (proc/'cmdline').read_bytes().split(bytes([0]))
 return p
assert digest(cal)=={bench.CAL_SHA!r}
'''
    s.remote(common+f"assert digest(target)=={manifest['base_hmi_sha256']!r} and not stage.exists() and not backup.exists()\npid()\nprint('Owned stopped HMI and original calibration verified')\n",'normal_hmi_precheck')
    s.run(s.scp+[OUT/'web_hmi/server.py','arduino@192.168.1.138:'+bench.HMI_ROOT+'/normal_start_hmi_r1.staged'],'normal_hmi_stage')
    stopped()
    s.remote(common+f'''assert digest(target)=={manifest['base_hmi_sha256']!r} and digest(stage)=={manifest['hmi_sha256']!r} and not backup.exists()
compile(stage.read_text(),str(stage),'exec');p=pid();shutil.copy2(target,backup)
assert digest(backup)=={manifest['base_hmi_sha256']!r}
stage.chmod(target.stat().st_mode);stage.replace(target)
assert digest(target)=={manifest['hmi_sha256']!r} and digest(cal)=={bench.CAL_SHA!r}
os.kill(p,signal.SIGTERM)
print('HMI update installed; MCU firmware and calibration unchanged')
''','normal_hmi_install')
    s.state['normal_start_hmi_candidate']=str(OUT);s.state['normal_start_hmi_sha256']=manifest['hmi_sha256'];s.save()
    s.hmi_sha=manifest['hmi_sha256']
    deadline=time.monotonic()+30
    while True:
        try:
            after=stopped()
            if after.get('hmi_vbus_hv_calibrated')==1:break
        except Exception:
            if time.monotonic()>=deadline:raise
        if time.monotonic()>=deadline:raise RuntimeError('HMI did not resume normally; no MCU reset or automatic START')
        time.sleep(.5)
    s.hashes('normal_hmi_postinstall_hashes')
    assert all(before.get(k)==after.get(k) for k in FIRST_FIELDS+ERROR_FIELDS)
    report=dict(pass_=True,hmi_sha256=manifest['hmi_sha256'],mcu_firmware_writes=0,
       original_calibration_unchanged=True,first_fault_snapshot_preserved=True,
       regular_start_path_installed=True,powered_one_shot_required=False,
       installed_pair=list(bench.PROD),arm_commands=0,start_commands=0,clear_commands=0,after=after)
    report['pass']=report.pop('pass_');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    s.state['normal_start_hmi_installed']=True;s.state['normal_start_hmi_install_report']=str(out/'report.json');s.save()
    print(json.dumps({k:v for k,v in report.items() if k!='after'},indent=2))


if __name__=='__main__':main()
