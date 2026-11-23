"""Replay startup timing and unchanged stale-data guards in the candidate C."""
import json,shutil,subprocess
import prepare_foc_start_epoch_fix as p

def main():
 out=p.OUT/'verification'
 prefix=p.read(out/'native_epoch.cpp').rsplit('int main(){',1)[0]
 checks=r'''
int main(){
 unsigned starts=0,guard_checks=0;
 const uint32_t origins[]={1000000U,0xfff00000U};
 const uint32_t delays[]={0U,170000U,8500000U,85000000U};
 for(uint32_t origin:origins)for(uint32_t delay:delays)
 for(unsigned priming:{0U,1U,2U,8U})for(unsigned phase:{0U,1U,2U,3U}){
  timer.BDTR=0;fe_complete=1;fe_fault=0;fe_case=64;
  id_profile_attempted=1;id_profile_running=0;selected=MA_FOC;
  sample.zero=1;sample.valid=0;fake_bus=320;first_fault=0;
  telemetry_seq=0xfffffffeU;cycle.CYCCNT=origin;assert(ma_native_prepare());
  timer.BDTR=1;uint32_t start=origin+delay;
  for(unsigned n=0;n<72;n++){
   cycle.CYCCNT=start+n*10625U;sample.cycles=cycle.CYCCNT;
   sample.valid=n>=priming;sample.counts[0]=sample.counts[1]=0;
   assert(ma_native_fast(5)==MC_NO_ERROR);
   if(n%4==phase)ma_native_service();
   assert(!run_fault);
  }
  assert(observer.steps>=2);++starts;
 }
 /* Neither a missing real ADC stream nor a stopped observer is excused by
  * the epoch reset. Check the actual unchanged MA_STALE paths. */
 for(unsigned missing_adc:{0U,1U}){
  timer.BDTR=0;cycle.CYCCNT=1000000;assert(ma_native_prepare());
  timer.BDTR=1;uint32_t start=cycle.CYCCNT+8500000U;
  for(unsigned n=0;n<40&&!run_fault;n++){
   cycle.CYCCNT=start+n*10625U;sample.cycles=cycle.CYCCNT;
   sample.valid=!missing_adc;sample.counts[0]=sample.counts[1]=0;
   ma_native_fast(5); // no observer service: must expire, not continue
  }
  assert(run_fault==MA_STALE);++guard_checks;
 }
 printf("{\"startup_scenarios_passed\":%u,\"unchanged_stale_guard_checks_passed\":%u}\n",starts,guard_checks);
}
'''
 cpp=out/'native_epoch_schedule.cpp';p.write(cpp,'#include <cstdio>\n'+prefix+checks)
 exe=cpp.with_suffix('.exe')
 r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
  '-Wno-unused-function','-Wno-misleading-indentation','-I',str(p.OUT/'nucleo/Inc'),
  '-I',str(p.OUT/'UNOQ_MOTOR'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'schedule_compile.log',r.stdout+r.stderr);r.check_returncode()
 r=subprocess.run([str(exe)],capture_output=True,text=True)
 p.write(out/'schedule_run.log',r.stdout+r.stderr);r.check_returncode()
 counts=json.loads(r.stdout)
 assert counts['startup_scenarios_passed']==128
 report=dict(passed=True,source='exact candidate native C, synthetic samples and clocks',
  hardware_commands=0,includes_prepare_delay_and_DWT_wrap=True,
  includes_voltage_seqlock_wrap=True,protection_thresholds_changed=False,**counts)
 p.write(out/'startup_schedule.json',json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
