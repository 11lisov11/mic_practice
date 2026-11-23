"""Exact adapter tests and source isolation for the startup epoch correction."""
import json,shutil,subprocess
import prepare_foc_start_epoch_fix as p
from replay_foc_start_timestamps import OLD,FIX
from audit_production_pwm_filters import function

def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True)
 old=p.read(p.BASE/'nucleo/Src/multi_native.c').replace('2026102952','2026102962')
 assert old.count(OLD)==1
 assert p.read(p.OUT/'nucleo/Src/multi_native.c')==old.replace(OLD,FIX)
 untouched=[]
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and f.suffix in ('.h','.c','.ino'):
    if f==p.OUT/'nucleo/Src/multi_native.c':continue
    before=p.read(p.BASE/f.relative_to(p.OUT)).replace('2026102951','2026102961').replace('2026102952','2026102962')
    assert p.read(f)==before,str(f)
    untouched.append(str(f.relative_to(p.OUT)))
 # Re-run full native adapter, independent clocks, bounded policy and wrap stop
 # using the exact candidate body. No real MCU/peripheral is involved here.
 source=p.read(p.BASE/'verification/native_trial.cpp')
 assert source.count(OLD)==1
 source=source.replace(OLD,FIX).replace('2026102952','2026102962')
 native='\n'.join(line for line in p.read(p.OUT/'nucleo/Src/multi_native.c').splitlines() if not line.startswith(('#include','#pragma')))
 # Fixture only replaces the DWT reads of the isolated CPU profiler.
 expected=native
 for name in ('ma_native_profile_tick','fe_profile_tick','fe_profile_service'):
  f=function(expected,name);expected=expected.replace(f,f.replace('DWT->CYCCNT','host_profile_clock()'))
 assert expected in source
 unit=out/'native_epoch.cpp';p.write(unit,source);exe=unit.with_suffix('.exe')
 r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
  '-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'compile.log',r.stdout+r.stderr);r.check_returncode()
 r=subprocess.run([str(exe)],capture_output=True,text=True);p.write(out/'run.log',r.stdout+r.stderr);r.check_returncode()
 replay=p.BASE/'first_powered_FOC_5Hz_5s_r2/startup_timestamp_replay_r2/report.json'
 assert json.loads(p.read(replay))['passed']
 report=dict(passed=True,hardware_commands=0,start_commands=0,clear_commands=0,
  exact_candidate_adapter_tested=True,startup_timestamp_regression=True,
  native5s_stop_and_wrap_checked=True,protection_and_current_files_unchanged=untouched,
  startup_replay_report=str(replay),physics_parameters_and_thresholds_changed=False)
 p.write(out/'selftest.json',json.dumps(report,indent=2));print(json.dumps({k:report[k] for k in ('passed','exact_candidate_adapter_tested','startup_timestamp_regression','native5s_stop_and_wrap_checked')}))

if __name__=='__main__':main()
