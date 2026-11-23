"""Check real recorded decoder pipeline and old/new recovery behavior."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import prepare_as5600_recovery as p
import prepare_current_shunt_monitor as u
def main():
    out=p.OUT;sk=out/'UNOQ_MOTOR';checks=[];compiler=shutil.which('g++');assert compiler
    exe=out/'build/uno/recovery_selftest.exe'
    old_core=u.read(p.BASE/'UNOQ_MOTOR/as5600_poll_reader.h')
    baseline=old_core.replace('namespace encdiag {','namespace baseline { using namespace encdiag;')
    u.write(out/'build/uno/baseline_poll_reader.h',baseline)
    subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(sk),'-I',str(out/'build/uno'),str(p.RES/'selftest.cpp'),'-o',str(exe)],check=True)
    proc=subprocess.run([str(exe)],capture_output=True,text=True,check=True);checks.append(proc.stdout.strip())
    old=u.read(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino');new=u.read(sk/'UNOQ_MOTOR.ino')
    clean=new.replace('FW_BUILD_ID = 2026102518U;','FW_BUILD_ID = 2026102517U;').replace('\n  else if (icmp(arg, "FILTER100")) mode = 5;','')
    for f in p.FIELDS:clean=clean.replace(f'\n    s += " enc_diag_{f}="; s += String((unsigned long)g_as5600.diag_{f});','')
    start=clean.index('\n    s += " enc_diag_events_hex=";');end=clean.index('\n    s += " enc_diag_sched_',start)
    clean=clean[:start]+clean[end:];assert clean==old
    for f in (p.BASE/'UNOQ_MOTOR').iterdir():
        if f.is_file() and f.name not in ('as5600_teacher.cpp','as5600_teacher.h','as5600_poll_reader.h','UNOQ_MOTOR.ino'):
            assert f.read_bytes()==(sk/f.name).read_bytes(),f.name
    checks.append('Motor sketch, MCU5s stop, UART, ADC/SD and protection headers unchanged outside identity/sensor mode/passive diagnostics')
    spec=importlib.util.spec_from_file_location('recovery_hmi',out/'web_hmi/server.py');h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
    recorded=json.loads((p.BASE/'powered_5hz_r1/report.json').read_text());s=copy.deepcopy(recorded['before']);s['fw_build']=2026102518
    decoded=h.with_zero_history(h.with_shunt_currents(copy.deepcopy(s)))
    assert decoded['mc_zero_history_valid']==1 and decoded['mc_current_zero_ready']==1
    bad=copy.deepcopy(s);raw=bytearray.fromhex(bad['mc_zero_history_hex']);raw[15]^=1;bad['mc_zero_history_hex']=raw.hex()
    assert h.with_zero_history(bad)['mc_zero_history_valid']==0
    assert h.with_zero_history(dict(s,fw_build=2026102599))['mc_zero_history_valid']==0
    peak=json.loads((ROOT/'artifacts/live_bench_20261025/as5600_software_regression_r1/legacy_powered_5hz_r1/after_diagnostics.json').read_text())
    assert h.with_adc_peak(dict(peak,fw_build=2026102518))['mc_adc_peak_valid']==1
    done=dict(s,run_id=1,run_reason=1,run_start_ms=1000,run_stop_ms=6000,run_elapsed_ms=5000,run_limit_ms=5000)
    assert h.bounded_run_complete(done,dict(run_id=0),5)
    assert not h.bounded_run_complete(dict(done,mc_fault=1),dict(run_id=0),5)
    stored=dict(fw_build=2026102517,mc_fw_build=2026102510,rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(stored,dict(stored,fw_build=2026102518))
    fields=' '.join(f'enc_diag_{name}={i+1}' for i,name in enumerate(p.FIELDS))
    d=h.RpcBridge._parse_status_string('DATA state=SAFE mode=VF pwm=0 '+fields+' enc_diag_events_hex=1234')
    assert all(d['enc_diag_'+f]==i+1 for i,f in enumerate(p.FIELDS)) and d['enc_diag_events_hex']=='1234'
    checks.append('Full real ADC/zero-history/peak/completion/calibration pipeline accepts2518; corrupted CRC and unknown firmware remain rejected')
    assert 'if(isr&BERR) return fail(BUS_ERROR,isr);' in old_core
    checks.append('Installed2517 BERR-abort path reproduced by source; candidate applies documented U585 erratum without waiving NACK/ARLO/OVR/full-frame/deadline')
    report=dict(passed=True,hardware_commands=0,hardware_validated=False,checks=checks,
        limitation='Behavioral host peripheral model, not electrical replay. Original PWM NACK/BERR/ARLO source and filtered-mode electrical timing require bench verification.')
    u.write(out/'offline-checks.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
