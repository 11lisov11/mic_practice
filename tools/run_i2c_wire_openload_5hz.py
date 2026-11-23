"""One existing protected5Hz/5s trial on2813/2812, then passive wire collection.
Motor remains physically disconnected. No automatic CLEAR, reset or reflash.
"""
import argparse,json,sys,time,types
from pathlib import Path
import run_persistent_pe_as5600_5hz as prior
import prepare_i2c_wire_epoch_fix as package
from ipm_break_wifi_selftest import load_module
PAIR=package.NEW;ROOT=package.ROOT
RUN_FIELDS=('run_id','run_limit_ms','run_elapsed_ms','run_reason','run_start_ms','run_stop_ms')
def load_trial():
    source=prior.trial_source().replace('2026102709',str(PAIR[0])).replace('2026102710',str(PAIR[1]))
    m=types.ModuleType('wire_capture_existing_trial');m.__file__=str(ROOT/'tools/run_as5600_bounded_5hz.py')
    exec(compile(source,m.__file__,'exec'),m.__dict__)
    source=(ROOT/'tools/current_zero_quality.py').read_text(encoding='utf-8')
    source=prior.once(source,'(2026102703,2026102704)','(2026102703,2026102704),(2026102813,2026102812)')
    namespace={};exec(compile(source,'current_zero_quality_wire_pair','exec'),namespace)
    m.zero_ready=namespace['ready'];m.t.zero_ok=m.zero_ready;m.configure(PAIR[0],'NUCLEO')
    original_ready=m.t.ready;original_capture=m.capture_ready
    m.t.ready=lambda s:original_ready(s) and s.get('enc_errors')==0 and wire_empty(s)
    m.capture_ready=lambda s:original_capture(s) and wire_empty(s)
    return m
def wire_empty(s):
    return ((s.get('fw_build'),s.get('mc_fw_build'))==PAIR and s.get('enc_wire_state')==1
      and s.get('enc_wire_valid')==0 and s.get('enc_wire_bad')==0 and s.get('enc_wire_hex')=='-'
      and s.get('enc_wire_decode_valid')==1)
def wire_complete(s,decoder):
    try:
        q=decoder.with_i2c_first_fault(s);r=q.get('enc_wire_record')
        return ((s.get('fw_build'),s.get('mc_fw_build'))==PAIR and s.get('enc_wire_state')==3
          and s.get('enc_wire_valid')==1 and s.get('enc_wire_bad')==0
          and q.get('enc_fault_decode_valid')==q.get('enc_wire_decode_valid')==1
          and isinstance(r,dict) and r['digital_record_valid'] and not r['manual'] and not r['dma_error'])
    except (KeyError,ValueError,TypeError):return False
def boot_proof(path):
    q=json.loads(path.read_text(encoding='utf-8'));assert q['passed'] and q['AS5600_communication_passed'] and q['all_current_telemetry_fresh']
    assert q['native_zero_flags_consistently_ready'] and q['zero_history_three_stable_blocks']
    assert q['I2C_errors_total']==q['motor_commands']==q['clear_commands']==q['reset_commands']==q['flash_commands']==0
    s=q['last'];assert (s['fw_build'],s['mc_fw_build'])==PAIR and s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==0
    assert 0<=s['vdc']<20 and wire_empty(s) and all(s[k]==0 for k in RUN_FIELDS)
    return s
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--verify-only',action='store_true')
    ap.add_argument('--confirm-powered-openload-ready',action='store_true');ap.add_argument('--boot-proof',type=Path,required=True);ap.add_argument('--outdir',type=Path)
    a=ap.parse_args();boot=boot_proof(a.boot_proof);m=load_trial()
    if a.verify_only:
        print(json.dumps(dict(passed=True,pair=PAIR,mcu_limit_ms=5000,hardware_commands=0,wire_armed_before_start=True,no_guard_threshold_changes=True)));return 0
    if not a.confirm_powered_openload_ready or a.outdir is None:ap.error('Fresh powered powerbank/PC-off/motor-disconnected confirmation and outdir required')
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    package.write(out/'low_bus_proof.json',json.dumps(dict(source=str(a.boot_proof),sha256=package.sha(a.boot_proof),status=boot),indent=2)+'\n')
    h=m.WifiHmi('http://192.168.1.138:8080',m.read_token(str(ROOT/'.unoq_ssh/control_token')),[],False)
    try:
        deadline=time.monotonic()+5
        while True:
            s=h.status();package.write(out/'preflight.json',json.dumps(s,indent=2)+'\n')
            assert all(s[k]==boot[k] for k in RUN_FIELDS) and s['enc_peer_epoch']==boot['enc_peer_epoch']
            assert s['enc_reads']>=boot['enc_reads'] and wire_empty(s),'New MCU epoch/fault capture since low-bus proof'
            if m.t.ready(s) and m.setup_ok(s):break
            if not m.t.checks.off(s) or not m.t.checks.transport_clean(s) or time.monotonic()>=deadline:
                raise RuntimeError('Protected ready OFF not established. No CLEAR or START sent')
            time.sleep(.25)
    finally:h.close()
    saved=sys.argv
    sys.argv=[saved[0],'--confirm-powered-ready','--outdir',str(out/'trial'),'--uno-build',str(PAIR[0]),'--sensor-mode','NUCLEO','--collect-first-i2c-fault']
    try:code=m.main()
    finally:sys.argv=saved
    trial=json.loads(package.read(out/'trial/report.json'))
    # The existing current-window verdict is retained, even on an unloaded
    # inverter. Never repeat START merely to obtain another current window.
    result=dict(passed=False,motor_connected=False,physical_rotation_test=False,trial_exit=code,
      trial_passed=trial['passed'],outputs_off_confirmed=trial.get('outputs_off_confirmed'),
      START_commands=trial['start_commands'],CLEAR_commands=0,flash_commands=0,records_erased=False)
    if trial.get('outputs_off_confirmed'):
        h=m.WifiHmi('http://192.168.1.138:8080',m.read_token(str(ROOT/'.unoq_ssh/control_token')),[],False)
        decoder=load_module(package.OUT/'web_hmi/server.py')
        try:
            deadline=time.monotonic()+15
            while True:
                s=h.status()
                with (out/'after_wire_status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
                assert m.t.checks.off(s),'Fresh OFF changed during read-only capture collection'
                assert s['enc_peer_epoch']==boot['enc_peer_epoch'],'Peer reset during the trial'
                errors=s['enc_errors']-boot['enc_errors']
                ready=prior.extension_complete(s) and (wire_complete(s,decoder) if errors else wire_empty(s))
                if ready:break
                if time.monotonic()>=deadline:raise RuntimeError('Complete parent/release/wire record not delivered; no repeat')
                time.sleep(.25)
            package.write(out/'saved_status.json',json.dumps(s,indent=2)+'\n')
            result.update(passed=True,I2C_errors_delta=errors,wire_capture_complete=wire_complete(s,decoder),
              no_error_record_expected=errors==0,stationary_sensor_under_PWM_qualified=bool(trial['passed'] and errors==0))
        except Exception as exc:result['error']=str(exc) or type(exc).__name__
        finally:h.close()
    package.write(out/'wire_collection_report.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    return code if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
