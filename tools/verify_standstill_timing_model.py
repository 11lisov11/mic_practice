"""Actual optimized C collector on independent plant; no board access."""
import json,subprocess,shutil,sys,hashlib
import prepare_standstill_timing as p
sys.path.insert(0,str(p.ROOT))
from motor_identification.commissioning import decode,calibrate,impedance_capture
from motor_identification.standstill import identify
def main():
 out=p.OUT/'model';out.mkdir(exist_ok=False)
 source=p.read(p.ROOT/'tools/motor_commissioning/model.cpp').replace('#include "identify_core.h"','#include <identify_core.h>').replace('2026102932',str(p.NEW[1]))
 unit=out/'model.cpp';p.write(unit,source);exe=out/'model.exe'
 r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
  '-I',str(p.OUT/'nucleo/Inc'),str(unit),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'build.log',r.stdout+r.stderr);r.check_returncode()
 def run(kind):
  r=subprocess.run([str(exe),kind,out.as_posix()],capture_output=True,text=True)
  p.write(out/(kind+'_runs.jsonl'),r.stdout);p.write(out/(kind+'_run_errors.log'),r.stderr);r.check_returncode()
 run('dc');dc=[decode(f.read_bytes(),source_kind='synthetic') for f in out.glob('dc_*.bin')]
 cal=calibrate(dc);assert cal['accepted'];(out/'calibration_core.bin').write_bytes(bytes.fromhex(cal['coefficient_bytes_hex']))
 p.write(out/'calibration.json',json.dumps(cal,indent=2))
 run('ac');ac=[decode(f.read_bytes(),source_kind='synthetic') for f in out.glob('ac_*.bin')]
 capture=impedance_capture(ac,cal,rotor_stationary_verified=True);result=identify(capture);assert result['accepted']
 p.write(out/'capture.json',json.dumps(capture,indent=2));p.write(out/'result.json',json.dumps(result,indent=2))
 m=result['equivalent_mcsdk_model']
 report=dict(passed=abs(m['RR']/9-1)<.03 and abs(m['LLS']/.012-1)<.05 and abs(m['LMS']/.3-1)<.03,
  dc_points=len(dc),ac_points=len(ac),source_kind='synthetic',hardware_commands=0,inferred=m,
  independent_inverter_non_linearity=True,validation_error=result['validation_relative_error'],
  voltage_calibration_holdout_rms_v=cal['validation_rms_error_v'],eligible_for_foc_start=False,
  kernel_sha256=hashlib.sha256((p.OUT/'nucleo/Inc/identify_core.h').read_bytes()).hexdigest())
 p.write(out/'report.json',json.dumps(report,indent=2));print(json.dumps(report));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
