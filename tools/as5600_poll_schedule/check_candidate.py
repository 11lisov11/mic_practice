"""Exercise unchanged parser guards and actual bounded scheduling scope."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import prepare_as5600_poll_schedule as p
import prepare_current_shunt_monitor as u
def main():
    out=p.OUT;sk=out/'UNOQ_MOTOR';checks=[];compiler=shutil.which('g++');assert compiler
    for name,source in [('reader',ROOT/'tools/as5600_bounded_io/selftest.cpp'),('scheduling',p.RES/'selftest.cpp')]:
        exe=out/'build/uno'/f'{name}_selftest.exe'
        subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(sk),str(source),'-o',str(exe)],check=True)
        result=subprocess.run([str(exe)],check=True,capture_output=True,text=True);checks.append(result.stdout.strip())
    old=u.read(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino');new=u.read(sk/'UNOQ_MOTOR.ino')
    clean=new.replace('FW_BUILD_ID = 2026102517U;','FW_BUILD_ID = 2026102516U;')
    for f in p.FIELDS:clean=clean.replace(f'\n    s += " enc_diag_{f}="; s += String((unsigned long)g_as5600.diag_{f});','')
    assert clean==old
    for f in (p.BASE/'UNOQ_MOTOR').iterdir():
        if f.is_file() and f.name not in ('UNOQ_MOTOR.ino','as5600_teacher.h','as5600_teacher.cpp'):
            assert f.read_bytes()==(sk/f.name).read_bytes(),f.name
    checks.append('Entire motor sketch identical outside build identity and2passive diagnostics; all timing/protection/UART/ADC/SD headers identical')
    worker=u.read(sk/'as5600_teacher.cpp')
    assert 'void wait_step() {k_busy_wait(1);}' in worker
    assert 'const auto result=encdiag::scheduled_read<PollSchedule>(poll,bytes);' in worker
    assert 'k_msleep(error == 0 ? 2 : 100);' in worker
    scope=u.read(sk/'as5600_poll_section.h')
    assert 'irq_lock(' not in scope and 'k_sleep(' not in scope and 'k_yield(' not in scope
    assert u.sha(sk/'as5600_poll_reader.h')==u.sha(p.BASE/'UNOQ_MOTOR/as5600_poll_reader.h')
    checks.append('Original3ms deadline, faults, no retry and angle/speed gates retained; IRQs not masked by scope')
    spec=importlib.util.spec_from_file_location('scheduled_hmi',out/'web_hmi/server.py')
    h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
    r=json.loads((p.BASE/'cold_boot_verify_r1/report.json').read_text());s=r['final_status']
    new_s=h.with_shunt_currents(dict(copy.deepcopy(s),fw_build=2026102517))
    old_s=h.with_shunt_currents(copy.deepcopy(s))
    assert new_s['mc_current_zero_ready']==old_s['mc_current_zero_ready']==1
    assert new_s['mc_current_offsets_adc']==old_s['mc_current_offsets_adc']
    assert h.manual_scalar_supported(new_s)
    assert not h.manual_scalar_supported(dict(new_s,fw_build=2026102599))
    stored=dict(fw_build=2026102516,mc_fw_build=2026102510,rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(stored,dict(stored,fw_build=2026102517))
    line='DATA state=SAFE mode=VF pwm=0 enc_diag_sched_sections=123 enc_diag_sched_max_hold_us=550'
    parsed=h.RpcBridge._parse_status_string(line);assert parsed['enc_diag_sched_sections']==123 and parsed['enc_diag_sched_max_hold_us']==550
    for build in (2026102516,2026102517):
        event=dict(new_s,fw_build=build,run_id=8,run_start_ms=1000,run_stop_ms=6000,run_limit_ms=5000,run_elapsed_ms=5000,run_reason=1)
        assert h.bounded_run_complete(event,dict(run_id=7),5)
        assert not h.bounded_run_complete(dict(event,fw_build=2026102599),dict(run_id=7),5)
        assert not h.bounded_run_complete(dict(event,mc_fault=1),dict(run_id=7),5)
        assert not h.bounded_run_complete(dict(event,pwm=1),dict(run_id=7),5)
    checks.append('Recorded zero/calibration accepted for2517; completed5s predicate stays narrow; unknown/fault/active rejected')
    observed=json.loads((p.BASE/'cold_boot_verify_r1/idle_status_traffic_observation.json').read_text())
    replay=dict(pause_errors=observed['pause_errors'],burst_errors=observed['burst_errors'],
        observed_last_us=observed['after_status_burst']['enc_diag_last_us'],
        observed_last_isr=observed['after_status_burst']['enc_diag_last_isr'],
        fixture_scope='Replays observed delay durations as scheduler interference, not electrical waveforms; real bench A/B still required')
    u.write(out/'recorded-scheduling-replay.json',json.dumps(replay,indent=2)+'\n')
    report=dict(passed=True,hardware_commands=0,checks=checks,hardware_validated=False,
        latency_budget='No preemptible thread handover during nominal~550us or timeout3ms transfer, plus live IRQ execution; sleep2ms after it. Actual UART and web response latency require idle stress.')
    u.write(out/'offline-checks.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
