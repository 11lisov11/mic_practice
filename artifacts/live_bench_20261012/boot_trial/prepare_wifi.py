"""Assemble retained evidence and prepare one conditional trial; never ARM/START/CLEAR."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_unoq_boot_trial import HMI, UNO, NUCLEO, images, sha, source_hashes, server
from uart_update_regression import source_hashes as release_hashes
from unoq_boot_trial_selftest import proof as proof_template
from ipm_break_wifi_selftest import load_module
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token
from unoq_wifi_hmi_deploy import scp_base

here=Path(__file__).parent
candidate=here/'candidate_r1'
out=here/'prepare_r1';out.mkdir(exist_ok=False)
rep=dict(pass_=False,start_commands=0,arm_commands=0,clear_commands=0,mcu_flash_commands=0,
         general_hv_release=False,physical_idle_registers_current=False)
h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),[],False)


def status():
    s=h.status()
    if ((s['fw_build'],s['mc_fw_build'])!=(2026101108,2026101102)
            or s['state']!='SAFE' or s['pwm']!=0 or s['hmi_hv_armed']!=0
            or s['bp_status']&0x22 or s['estop']!=0 or s['bp_fault'] not in (0,5)
            or any(s[k]!=0 for k in ('bp_bad','bp_bad_cnt','mc_bad_integrity','mc_bad_sequence',
                                     'uno_rx_dropped','uno_rx_hw_errors','mc_transport_fault'))
            or not 0<=s['vdc']<=10 or not 0<=s['bp_vdc']<=10
            or not 0<=s['bp_age_ms']<300 or s['hmi_vbus_hv_calibrated']!=1):
        raise RuntimeError('Prepared auxiliary/off-only live state required')
    return s


try:
    regression=here/'regression_r2/report.json'
    reg=json.loads(regression.read_text())
    assert reg['pass'] and reg['sources_unchanged_during_tests']
    assert reg['source_sha256']==release_hashes(ROOT)
    assert any(x['test']=='unoq_boot_trial_selftest' and x['pass'] for x in reg['tests'])
    assert (candidate/'web_hmi/server.py').read_text()==server(HMI.read_text())
    mod=load_module(candidate/'web_hmi/server.py')
    audit_path=candidate/'manifest.json';audit=json.loads(audit_path.read_text())
    assert audit['pass'] and audit['calibration_contract_pass'] and audit['nucleo_pwm_equivalence_pass']
    assert audit['source_nucleo_sha256']==source_hashes(NUCLEO)
    assert audit['source_uno_sha256']==source_hashes(UNO/'UNOQ_MOTOR')
    assert audit['images']==images()==mod.BOOT_TRIAL_IMAGES
    assert sha(NUCLEO/'STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin')==images()['production_nucleo']
    pwm_path=ROOT/'artifacts/live_bench_20261010/uart_v3_candidate/active_pwm_r5/report.json'
    pwm=json.loads(pwm_path.read_text())
    assert pwm['pass'] and pwm['restored'] and pwm['code_equivalence']['pass']
    assert pwm['restore_uno_byte_verified'] and pwm['restore_nucleo_byte_verified']
    assert all(pwm['images'].get(k)==v for k,v in mod.UART_V3_TRIAL_IMAGES.items())
    assert set(pwm['cases'])==set(mod.UART_V3_TRIAL_CASES)
    assert all(x['pass'] for x in pwm['cases'].values())
    uno_install=ROOT/'artifacts/live_bench_20261012/llext_fix/install_r1/report.json'
    nuc_install=ROOT/'artifacts/live_bench_20261011/ipm_break_wifi/install_r7/report.json'
    assert json.loads(uno_install.read_text())['uno_flash_verified']
    assert json.loads(nuc_install.read_text())['nucleo_flash_verified']
    # Retain the predecessor's partial-install report as such, never promote its overall pass.
    idle_path=ROOT/'artifacts/live_bench_20261012/fault_context_fix/autonomous_wifi_r1/summary.json'
    idle=json.loads(idle_path.read_text())
    assert idle['pass'] and idle['duration_requested_s']>=120
    assert idle['first_builds']=={'fw_build':2026101108,'mc_fw_build':2026101102}
    auton_path=ROOT/'artifacts/live_bench_20261012/fault_context_fix/autonomous_result.json'
    auton=json.loads(auton_path.read_text())
    assert auton['pass'] and auton['linux_boot_id_changed'] and auton['operator_reported_powerbank']
    sd_path=ROOT/'artifacts/live_bench_20261012/j4_passive_r1/sd_measurement.json'
    sd=json.loads(sd_path.read_text());assert sd['source']=='operator multimeter report'
    assert sd['measurement']=='TP23 SD relative to J4 minus' and 2.52<sd['volts']<=3.6
    rep['before']=s=status()
    records=s['mc_break_snapshots']
    assert len(records)==2 and all(x['available'] for x in records)
    assert records[1]['captured'] is False
    raw=records[0]['raw'];event=records[0]['event']
    assert records[0]['captured'] and raw['start_window']==raw['reference_speed_unit']==raw['vbus_v']==0
    assert raw['tim_ccr1']==raw['tim_ccr2']==raw['tim_ccr3']==0
    assert event['bif'] and event['bke_at_irq'] and not event['moe_at_irq']
    assert raw['tim_dier']&0x80
    scp=scp_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
    cal=out/'calibration_original.json'
    proc=subprocess.run(scp+['arduino@192.168.1.138:/home/arduino/.config/mic-ai/vbus_calibration.json',str(cal)],
                        capture_output=True,timeout=30)
    (out/'calibration_read.log').write_bytes(proc.stdout+proc.stderr)
    assert proc.returncode==0 and sha(cal)=='a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17'
    store=mod.VbusCalibrationStore(str(cal));assert store.is_valid(s)
    files=dict(pwm=pwm_path,source_audit=audit_path,uno_install=uno_install,nucleo_install=nuc_install,
               offline=regression,idle_wifi=idle_path,autonomous=auton_path,sd_sample=sd_path,calibration=cal)
    grant=proof_template(mod)
    grant.update(offline_suites=len(reg['tests']),sd_sample_v=sd['volts'],
                 idle_tx_max_gap_us=auton['max_tx_gap_us'],
                 evidence_sha256={k:sha(v) for k,v in files.items()},issued_at=time.time(),expires_at=time.time()+600)
    assert mod.validate_powered_trial_qualification(grant)[0]
    (out/'qualification.json').write_text(json.dumps(grant,indent=2)+'\n')
    h.command('MODE VF');h.command('SET FREQ 5')
    h.post('/api/powered-trial',dict(action='prepare',confirm='PREPARE UARTV3 TRIAL 3S',qualification=grant),
           'prepare limited trial, NOT ARM/START')
    rep['after']=s=status()
    assert s['hmi_powered_trial_enabled']==1 and s['hmi_powered_trial_used']==0
    assert s['hmi_powered_trial_max_run_s']==3 and s['hmi_powered_trial_max_freq_hz']==5
    assert s['hmi_powered_trial_ready']==0 and s['freq_cmd']==5
    rep['pass_']=True
except Exception as exc:
    rep['error']=f'{type(exc).__name__}: {exc}'
finally:
    rep['commands']=h.commands;h.close();rep['pass']=rep.pop('pass_')
    (out/'report.json').write_text(json.dumps(rep,indent=2)+'\n')
print(json.dumps({k:rep.get(k) for k in ('pass','arm_commands','start_commands','clear_commands','error')}))
raise SystemExit(0 if rep['pass'] else 1)
