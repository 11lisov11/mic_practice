"""Finish matching HMI deployment after verified offline rollback; no MCU writes or motor commands."""
import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

import rollback_known_good_3014 as rollback
from unoq_wifi_hmi_deploy import ssh_base, scp_base
from wifi_stop_tail_probe import parse_registers

ROOT = rollback.ROOT
BASE = ROOT/'artifacts/live_bench_20261031/rollback_3013_3014_ssh_r2'
OUT = BASE/'hmi_finish_r2'

REMOTE = r'''
import hashlib,importlib.util,json,os,pathlib,signal,subprocess,time
root=pathlib.Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
cfg=json.loads(pathlib.Path(CONFIG).read_text())
assert cfg['offline_programming_only'] and cfg['native_BKE'] and not cfg['native_MOE']
files=[]
for entry in cfg['files']:
 p=pathlib.Path(entry['remote']);data=p.read_bytes()
 assert hashlib.sha256(data).hexdigest()==entry['sha256']
 files.append((root/entry['destination'],data))
cal=pathlib.Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
before=cal.read_bytes();assert hashlib.sha256(before).hexdigest()==cfg['calibration_sha256']
spec=importlib.util.spec_from_file_location('rollback_candidate',cfg['files'][0]['remote'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
# Compatibility of the original record with the exact intended pair; no live
# reading is fabricated and no saved calibration/identity field is rewritten.
assert module.VbusCalibrationStore(str(cal)).is_valid(cfg['prospective_identity'])
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
restart=subprocess.check_output(['systemctl','show','-p','Restart','--value','unoq-hmi.service'],text=True).strip()
proc=pathlib.Path('/proc')/str(pid)
assert pid>1 and restart=='always' and proc.stat().st_uid==os.geteuid()
assert (proc/'cwd').resolve()==root
assert 'server.py' in (proc/'cmdline').read_bytes().decode().split('\0')
backup=root/'backups'/('rollback_3014_'+time.strftime('%Y%m%d_%H%M%S'))
backup.mkdir(exist_ok=False)
for target,data in files:
 (backup/target.name).write_bytes(target.read_bytes())
 pending=target.with_name(target.name+'.rollback-pending')
 pending.write_bytes(data);pending.chmod(target.stat().st_mode&0o777);os.replace(pending,target)
assert all(target.read_bytes()==data for target,data in files)
assert cal.read_bytes()==before
os.kill(pid,signal.SIGTERM)
print(json.dumps(dict(deployed=True,backup=str(backup),calibration_unchanged=True,
 runtime_verified=False,hmi_restarts=1,flash_commands=0,motor_commands=0)))
'''


def main():
    OUT.mkdir(exist_ok=False)
    r=dict(passed=False,START=0,CLEAR=0,ARM=0,flash_commands=0)
    def run(command,label,timeout=30):
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        (OUT/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        assert result.returncode==0,label
        return result.stdout
    try:
        install=json.loads((BASE/'install/report.json').read_text(encoding='utf-8'))
        assert install['uno_readback_verified'] and install['nucleo_readback_verified']
        assert rollback.digest(BASE/'install/native_flash_readback.bin')=='30232a36dccfb125afe89f4d23aab12d59a8c0d4f90b8b89c4f41be9ad1e3c18'
        raw=run([str(rollback.install.io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG',
                 'sn='+rollback.install.io.STLINK_SERIAL,'-r32','0x40012c00','104'],'native_OFF')
        words=parse_registers(raw)
        assert words[0x40012c44]&4096 and not words[0x40012c44]&32768
        ssh=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        scp=scp_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
        identity=dict(install['before'],fw_build=2026103013,mc_fw_build=2026103014)
        cfg=dict(offline_programming_only=True,native_BKE=True,native_MOE=False,
                 calibration_sha256=install['calibration_before'],prospective_identity=identity,files=[])
        prefix='/tmp/mic_finish_rollback3014_'
        for relative in ('server.py','static/app.js','static/index.html'):
            local=rollback.old.OUT/'web_hmi'/relative
            remote=prefix+local.name
            run(scp+[str(local),'arduino@192.168.1.138:'+remote],'stage_'+local.name)
            cfg['files'].append(dict(remote=remote,destination=relative,sha256=rollback.digest(local)))
        config=OUT/'config.json';config.write_text(json.dumps(cfg),encoding='utf-8')
        helper=OUT/'deploy.py';helper.write_text(REMOTE.replace('CONFIG',repr(prefix+'config.json')),encoding='utf-8')
        for local in (config,helper):
            run(scp+[str(local),'arduino@192.168.1.138:'+prefix+local.name],'stage_'+local.name)
        output=run(ssh+['python3 '+shlex.quote(prefix+'deploy.py')],'deploy')
        r['deployment']=json.loads(output)
        r['calibration_unchanged']=r['deployment']['calibration_unchanged']
        for _ in range(20):
            time.sleep(1)
            try:
                s=rollback.install.io.live_status()
                (OUT/'status.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
                assert (s['fw_build'],s['mc_fw_build'])==rollback.TARGET
                assert rollback.precheck(s)[0]
                assert s['hmi_vbus_hv_calibrated']==1
                r.update(passed=True,pair=rollback.TARGET,SD=s.get('mc_sd_live'),pwm=s['pwm'])
                break
            except Exception as exc:
                r['last_runtime_error']=str(exc)
    except Exception as exc:
        r['error']=str(exc)
    (OUT/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False))
    return 0 if r['passed'] else 1


if __name__=='__main__':
    sys.exit(main())
