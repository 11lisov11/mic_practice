"""Actual portable C collector on an independent stationary-rotor plant."""
import argparse,json,subprocess,sys,shutil,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from motor_identification.commissioning import decode,calibrate,impedance_capture
from motor_identification.standstill import identify
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,default=ROOT/'artifacts/live_bench_20261029/standstill_commissioning_r1/model_final')
    out=parser.parse_args().outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    exe=out/'model.exe'
    cmd=[shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
      '-I',str(ROOT/'tools/motor_commissioning'),'-I',str(ROOT/'tools/multi_algorithm'),
      '-I',str(ROOT/'artifacts/live_bench_20261029/multi_algorithm_r1/nucleo/Inc'),
      str(ROOT/'tools/motor_commissioning/model.cpp'),'-o',str(exe)]
    subprocess.run(cmd,check=True)
    def run(mode):
        r=subprocess.run([str(exe),mode,str(out).replace('\\','/')],capture_output=True,text=True)
        (out/(mode+'_runs.jsonl')).write_text(r.stdout,encoding='utf-8');r.check_returncode()
    run('dc');dc=[decode(p.read_bytes(),source_kind='synthetic') for p in sorted(out.glob('dc_*.bin'))]
    cal=calibrate(dc);assert cal['accepted'];(out/'calibration_core.bin').write_bytes(bytes.fromhex(cal['coefficient_bytes_hex']))
    (out/'calibration.json').write_text(json.dumps(cal,indent=2),encoding='utf-8')
    run('ac');ac=[decode(p.read_bytes(),source_kind='synthetic') for p in sorted(out.glob('ac_*.bin'))]
    cap=impedance_capture(ac,cal,rotor_stationary_verified=True);result=identify(cap)
    (out/'capture.json').write_text(json.dumps(cap,indent=2),encoding='utf-8')
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    assert result['accepted'],result
    m=result['equivalent_mcsdk_model']
    report=dict(passed=abs(m['RR']/9-1)<.03 and abs(m['LLS']/.012-1)<.05 and abs(m['LMS']/.3-1)<.03,
      dc_points=len(dc),ac_points=len(ac),source_kind='synthetic',hardware_commands=0,
      inferred=m,truth={'RS':12.23,'RR':9,'LLS':.012,'LLR':.012,'LMS':.3},
      independent_inverter_non_linearity=True,voltage_calibration_holdout_rms_v=cal['validation_rms_error_v'],
      fit_error=result['fit_relative_error'],validation_error=result['validation_relative_error'],eligible_for_foc_start=False,
      source_sha256={name:hashlib.sha256((ROOT/'tools/motor_commissioning'/name).read_bytes()).hexdigest() for name in ('identify_core.h','model.cpp')})
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
