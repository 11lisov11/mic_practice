"""Reproduce observer startup timestamp failure in actual installed native C."""
import argparse,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261029/estimated_foc_trial_r5'
OLD='running=1;estimate_cycles=begin;start_cycles=begin;'
FIX=OLD+'''
    /* Start one coherent voltage/observer epoch after real PWM becomes active.
     * Do not interpret the earlier OFF/prepare timestamp as a completed bin. */
    ++telemetry_seq;__DMB();bin_cycles=begin;bin_va=bin_vb=0;
    sum_va=sum_vb=0;voltage_n=0;__DMB();++telemetry_seq;'''

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 prefix=(BASE/'verification/native_trial.cpp').read_text(encoding='utf-8').rsplit('int main(){',1)[0]
 assert prefix.count(OLD)==1
 test=r'''
int main(){
 fe_complete=1;fe_fault=0;fe_case=64;id_profile_attempted=1;id_profile_running=0;
 selected=MA_FOC;sample.zero=1;sample.valid=0;fake_bus=320;
 cycle.CYCCNT=1000000;assert(ma_native_prepare());
 timer.BDTR=1;
 uint32_t start=cycle.CYCCNT+8500000U; // real MCSDK delay50ms after prepare
 double rejected_dt=0;
 for(unsigned n=0;n<36;n++){
  cycle.CYCCNT=start+n*10625U;sample.cycles=cycle.CYCCNT;
  sample.valid=n>=2;sample.counts[0]=sample.counts[1]=0;
  int rc=ma_native_fast(5);
  if(run_fault)break;
  assert(rc==MC_NO_ERROR);
  if(n==16){rejected_dt=(double)((uint32_t)(bin_cycles-estimate_cycles))/SystemCoreClock;}
  ma_native_service();
  if(run_fault)break;
 }
 EXPECTATION
 printf("{\"fault\":%u,\"observer_steps\":%u,\"dt_at_first_observer_service_s\":%.9f,\"bin_samples_pending\":%u}\n",
   run_fault,observer.steps,rejected_dt,voltage_n);
}
'''
 results={}
 for name,source,expect in [('installed',prefix,'assert(run_fault==MA_STALE&&observer.steps==0);'),
                            ('fixed',prefix.replace(OLD,FIX),'assert(run_fault==0&&observer.steps>=1);')]:
  cpp=out/(name+'.cpp');cpp.write_text('#include <cstdio>\n'+source+test.replace('EXPECTATION',expect),encoding='utf-8')
  exe=cpp.with_suffix('.exe')
  r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
   '-Wno-unused-function','-Wno-misleading-indentation','-I',str(BASE/'nucleo/Inc'),
   '-I',str(BASE/'UNOQ_MOTOR'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
  (out/(name+'_build.log')).write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode()
  r=subprocess.run([str(exe)],capture_output=True,text=True)
  (out/(name+'_run.log')).write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode()
  results[name]=json.loads(r.stdout)
 report=dict(passed=True,source='actual native adapter compiled on PC, synthetic clocks/samples',
  hardware_commands=0,start_commands=0,clear_commands=0,results=results,
  protections_relaxed=False,current_deadline_and_age_guards_unchanged=True,
  observed_hardware_consistency='Recorded MA_STALE3, software128,18ADC frames; observer startup epoch is a reproduced software defect. Internal stale timestamps were not directly captured on hardware.')
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report))

if __name__=='__main__':main()
