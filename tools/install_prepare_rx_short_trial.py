"""Verify output-off hardware, update HMI over Wi-Fi and prepare one trial; never ARM/START."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from prepare_rx_short_trial import ROOT, RX, BASE, server, sha, source_hashes
from clear_rx_maintenance_timeout import safe as zero_safe
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token
from unoq_wifi_hmi_deploy import ssh_base, scp_base
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL
from wifi_stop_tail_probe import parse_registers
from ipm_break_wifi_selftest import load_module
from rx_short_trial_selftest import proof as proof_template


def physical_idle(words):
    try:
        return (not words[0x40012c44]&0x8000 and bool(words[0x40012c44]&0x1000)
            and bool(words[0x40012c0c]&0x80) and bool(words[0x48000010]&0x40)
            and words[0x48000010]&0x780==0 and words[0x48000410]&3==0)
    except KeyError: return False


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--regression',type=Path,required=True)
    p.add_argument('--idle',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--confirm-mains-j4-off',action='store_true')
    a=p.parse_args()
    if not a.confirm_mains_j4_off: p.error('Confirmed deenergized state required')
    candidate=a.candidate.resolve(); out=a.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    report=dict(pass_=False,commands=[],start_commands=0,arm_commands=0,mcu_flash_commands=0)
    wifi=WifiHmi('http://192.168.1.138:8080',read_token('.unoq_ssh/control_token'),report['commands'],False)
    ssh=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
    scp=scp_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
    def run(cmd,name,timeout=60):
        r=subprocess.run([str(x) for x in cmd],capture_output=True,timeout=timeout)
        (out/(name+'.log')).write_bytes(r.stdout+r.stderr)
        if r.returncode: raise RuntimeError(name+' failed; retained log')
        return r.stdout.decode('utf-8',errors='replace')
    def read_status():
        s=wifi.status()
        if not zero_safe(s) or s['bp_transport_fault']!=0 or s['bp_bad_cnt']!=0:
            raise RuntimeError('Clean zero-bus SAFE state changed')
        return s
    try:
        regression=json.loads(a.regression.read_text())
        from uart_update_regression import source_hashes as release_hashes
        if (not regression['pass'] or not regression['sources_unchanged_during_tests']
                or regression['source_sha256']!=release_hashes(ROOT)
                or not any(x['test']=='rx_short_trial_selftest' and x['pass'] for x in regression['tests'])):
            raise RuntimeError('Current trial-aware regression required')
        text=(candidate/'web_hmi/server.py').read_text()
        if text!=server((RX/'web_hmi/server.py').read_text()): raise RuntimeError('Unexpected HMI source')
        audit=json.loads((candidate/'delta_audit.json').read_text())
        if (not audit['pass'] or not audit['pwm_core_equivalence_pass'] or not audit['calibration_contract_pass']
                or audit['source_nucleo_sha256']!=source_hashes(BASE/'nucleo')
                or audit['source_uno_sha256']!=source_hashes(RX/'UNOQ_MOTOR')):
            raise RuntimeError('Component/measurement source audit failed')
        mod=load_module(candidate/'web_hmi/server.py')
        proof=proof_template(mod)
        if audit['images']!=mod.RX_SNAPSHOT_TRIAL_IMAGES: raise RuntimeError('Unexpected component images')
        report['before']=read_status()
        old_pwm=ROOT/'artifacts/live_bench_20261010/uart_v3_candidate/active_pwm_r5/report.json'
        pwm=json.loads(old_pwm.read_text())
        if (not pwm['pass'] or not pwm['restored'] or not pwm['code_equivalence']['pass']
                or not pwm['restore_uno_byte_verified'] or not pwm['restore_nucleo_byte_verified']
                or any(pwm['images'].get(k)!=v for k,v in mod.UART_V3_TRIAL_IMAGES.items())
                or set(pwm['cases'])!=set(mod.UART_V3_TRIAL_CASES)
                or any(x['pass'] is not True for x in pwm['cases'].values())):
            raise RuntimeError('Baseline PWM measurements missing')
        idle=json.loads(a.idle.read_text())
        if (idle['pass'] is not True or idle['duration_requested_s']<30
                or idle['counters']['bp_good']['last']-idle['counters']['bp_good']['first']<100
                or idle['first_builds']!={'fw_build':2026101104,'mc_fw_build':2026101102}
                or idle['counters']['bp_bad_cnt']['first']!=0 or idle['counters']['bp_bad_cnt']['last']!=0):
            raise RuntimeError('Fresh post-CLEAR idle evidence missing')
        for line in (a.idle.parent/'status.jsonl').read_text().splitlines():
            if not zero_safe(json.loads(line)['status']): raise RuntimeError('Unclean idle sample')
        cal_file='/home/arduino/.config/mic-ai/vbus_calibration.json'
        before_cal=run(ssh+['sha256sum '+cal_file],'calibration_before').split()[0]
        words={}
        for name,address,byte_count in (('tim1',0x40012c00,80),('gpioa',0x48000010,4),('gpiob',0x48000410,4)):
            read_status()
            words.update(parse_registers(run([PROGRAMMER,'-c','port=SWD','mode=HOTPLUG','sn='+SERIAL,
                '-r32',hex(address),str(byte_count)],'read_'+name)))
        phys=dict(pass_=physical_idle(words),registers={hex(k):hex(v) for k,v in words.items()},
            scope='Passive register/GPIO sample, not an active PWM or edge-timing capture')
        phys['pass']=phys.pop('pass_'); (out/'physical_idle.json').write_text(json.dumps(phys,indent=2)+'\n')
        if not phys['pass']: raise RuntimeError('BKE/BIE/PA6/physical output-off readback failed')
        image=BASE/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin'
        readback=out/'nucleo_readback.bin'
        run([PROGRAMMER,'-c','port=SWD','mode=HOTPLUG','sn='+SERIAL,'-u','0x08000000',str(image.stat().st_size),readback],
            'nucleo_readback')
        if sha(readback)!=mod.RX_SNAPSHOT_TRIAL_IMAGES['production_nucleo']:
            raise RuntimeError('Live Nucleo image does not match source-audited image')
        uno_install=ROOT/'artifacts/live_bench_20261011/uart_rx_fix/install_r1/report.json'
        nuc_install=ROOT/'artifacts/live_bench_20261011/ipm_break_wifi/install_r7/report.json'
        if not json.loads(uno_install.read_text()).get('uno_flash_verified'):
            raise RuntimeError('Uno readback evidence missing')
        if not json.loads(nuc_install.read_text()).get('nucleo_flash_verified'):
            raise RuntimeError('Nucleo readback evidence missing')
        target='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py'
        before_hmi=run(ssh+['sha256sum '+target],'hmi_before').split()[0]
        if before_hmi!=sha(RX/'web_hmi/server.py'): raise RuntimeError('Unexpected installed HMI')
        remote='/home/arduino/rx_short_trial_server.py'; runner='/home/arduino/rx_short_trial_recovery.py'
        read_status()
        run(scp+[candidate/'web_hmi/server.py','arduino@192.168.1.138:'+remote],'copy_hmi')
        run(scp+[ROOT/'tools/recover_unoq_hmi_router_remote.py','arduino@192.168.1.138:'+runner],'copy_recovery')
        goal=sha(candidate/'web_hmi/server.py')
        report['hmi_install']=json.loads(run(ssh+[f'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python {runner} --candidate {remote} --sha256 {goal} --expected-live-sha256 {before_hmi} --confirm-mains-j4-off'],'install_hmi'))
        time.sleep(3)
        after=read_status()
        if after.get('hmi_vbus_hv_calibrated')!=1: raise RuntimeError('Audited calibration contract not accepted')
        if run(ssh+['sha256sum '+cal_file],'calibration_after').split()[0]!=before_cal:
            raise RuntimeError('Calibration file changed')
        report['calibration_bytes_unchanged']=True
        now=time.time(); proof.update(issued_at=now,expires_at=now+600,offline_suites=len(regression['tests']))
        paths=dict(pwm=old_pwm,physical_idle=out/'physical_idle.json',delta_audit=candidate/'delta_audit.json',
            uno_install=uno_install,nucleo_install=nuc_install,offline=a.regression,idle_wifi=a.idle)
        proof['evidence_sha256']={k:sha(v) for k,v in paths.items()}
        if not mod.validate_powered_trial_qualification(proof)[0]: raise RuntimeError('Trial proof rejected')
        (out/'qualification.json').write_text(json.dumps(proof,indent=2)+'\n')
        wifi.command('MODE VF'); wifi.command('SET FREQ 5')
        wifi.post('/api/powered-trial',dict(action='prepare',confirm='PREPARE UARTV3 TRIAL 3S',qualification=proof),
                  'prepare only, NOT ARM or START')
        report['after']=after=read_status()
        if after.get('hmi_powered_trial_enabled')!=1 or after.get('freq_cmd')!=5:
            raise RuntimeError('Bounded preparation not reflected in live HMI')
        report['remaining_step']='Autonomous power and operator confirmation, then powered idle observation; no START sent'
        report['pass_']=True
    except Exception as exc: report['error']=f'{type(exc).__name__}: {exc}'
    finally:
        wifi.close(); report['pass']=report.pop('pass_')
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('pass','calibration_bytes_unchanged','start_commands','arm_commands','error')}))
    return 0 if report['pass'] else 1


if __name__=='__main__': raise SystemExit(main())
