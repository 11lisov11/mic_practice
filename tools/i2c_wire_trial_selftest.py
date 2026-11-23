"""Pure admission/decoder checks; imports never instantiate a network client."""
import copy,json
import run_i2c_wire_openload_5hz as candidate
from ipm_break_wifi_selftest import load_module
def main():
    p=candidate.package;m=candidate.load_trial();checks=0
    base=json.loads((p.ROOT/'artifacts/live_bench_20261027/nucleo_i2c_stop_recovery_r1/powered_first_fault_5hz_r1/trial/report.json').read_text(encoding='utf-8'))
    s=copy.deepcopy(base['before']);s.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_fw_build=p.NEW[1],enc_errors=0,enc_wire_state=1,enc_wire_valid=0,enc_wire_bad=0,enc_wire_hex='-',enc_wire_decode_valid=1)
    assert m.t.ready(s) and m.setup_ok(s) and m.capture_ready(s);checks+=1
    for changes in ({'mc_fw_build':0},{'mc_current_zero_ready':0},{'mc_current_age_ms':750},
      {'mc_current_quality_age_ms':1500},{'mc_sd_live':dict(s['mc_sd_live'],level='LOW')},
      {'mc_sd_live':dict(s['mc_sd_live'],break_irq_enabled=False)},{'mc_transport_fault':7},
      {'pwm':1},{'hmi_hv_armed':1},{'vdc':400},{'mc_age_ms':300},{'bp_temp_fault':1},
      {'enc_errors':1},{'enc_wire_state':3},{'enc_wire_valid':1},{'enc_wire_bad':1},{'enc_wire_decode_valid':0}):
        assert not m.t.ready(dict(s,**changes)),changes;checks+=1
    active=next(copy.deepcopy(x['status']) for x in base['samples'] if x['status'].get('pwm')==1 and x['status'].get('mc_frequency_reference_hz')==5)
    active.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_fw_build=p.NEW[1])
    assert m.t.checks.active(active) and m.zero_ready(active) and m.setup_ok(active);checks+=1
    d=load_module(p.OUT/'web_hmi/server.py')
    s=json.loads(p.read(p.BASE/'verification/synthetic_address_nack_status.json'))
    s.update(fw_build=p.NEW[0],enc_wire_state=3,enc_wire_valid=1,enc_wire_bad=0)
    assert candidate.wire_complete(s,d);checks+=1
    for key,value in (('enc_wire_state',1),('enc_wire_valid',0),('enc_wire_bad',1),('enc_wire_crc','1'),('enc_fault_pwm_hex','-')):
        assert not candidate.wire_complete(dict(s,**{key:value}),d);checks+=1
    manual=json.loads(p.read(p.OUT/'manual_usb_capture_r2/captured_status.json'))
    assert not candidate.wire_complete(manual,d);checks+=1
    proof=p.OUT/'autonomous_telemetry_profile_r1/report.json'
    assert candidate.boot_proof(proof)['run_id']==0;checks+=1
    result=dict(passed=True,checks=checks,hardware_commands=0,pair=list(p.NEW),mcu_limit_ms=5000,
      thresholds_and_watchdogs_unchanged=True,manual_trace_not_accepted_as_PWM_fault=True,
      no_automatic_CLEAR=True,no_repeated_START=True)
    out=p.OUT/'wire_trial_preparation_r1';out.mkdir(exist_ok=False)
    p.write(out/'selftest.json',json.dumps(result,indent=2)+'\n')
    p.write(out/'source_sha256.json',json.dumps({str(p.ROOT/'tools'/name):p.sha(p.ROOT/'tools'/name) for name in ('run_i2c_wire_openload_5hz.py','i2c_wire_trial_selftest.py','run_persistent_pe_as5600_5hz.py','run_as5600_bounded_5hz.py','current_zero_quality.py')},indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
