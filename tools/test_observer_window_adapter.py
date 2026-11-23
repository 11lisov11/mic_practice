"""Real adapter OFF qualification, torn snapshots, raw trips and input epochs."""
import json,subprocess
import prepare_observer_current_window as p
from test_foc_estimate_publish_fix import native_source
from test_observer_current_window import compile_case
from analyze_observer_nis import write
def main():
    out=p.OUT/'verification'
    pre=p.read(p.BASE/'model_verification/plant_observer_candidate.cpp').split('#define MIC_NATIVE_BUILD',1)[0]
    pre=pre[:pre.index('static void host_publication_irq();')]
    pre='#include "observer_current_window.h"\n#include "observer_forecast.h"\n'+pre
    pre+='\nstatic void host_publication_irq(){}\nstatic bool inject_torn;\n'
    native=native_source(p.OUT)
    native=native.replace('sample=bin_current;ow_bin window=bin_window;',
        'sample=bin_current;ow_bin window=bin_window;if(inject_torn){++telemetry_seq;inject_torn=false;}')
    tail=r'''
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
int main(){
 unsigned checks=0;
 // Execute all64 real OFF qualification cases, including the completed mean
 // accumulator in TIM1 work and center->endpoint forecast in foreground.
 selected=MA_FOC;sample.zero=sample.valid=1;fake_bus=0;
 for(unsigned i=0;i<2000U&&!fe_complete&&!fe_fault;++i)ma_native_service();
 assert(fe_complete&&fe_case==64U&&!fe_fault&&fe_fast_cycles==100U);++checks;
 assert(FE_FAST_BUDGET==4000U&&FE_OBSERVER_BUDGET==85000U);++checks;
 timer.BDTR=0;cycle.CYCCNT=1000000;assert(ma_native_prepare());timer.BDTR=1;fake_bus=323;
 uint32_t now=1000000;
 // First sample after MOE is not yet valid. Original bounded neutral prime.
 sample.valid=0;sample.cycles=now-4000;assert(!ma_native_fast(5));
 sample.valid=1;
 for(unsigned i=1;i<=16;++i){
  now+=10624;cycle.CYCCNT=now;sample.cycles=now-4000;sample.sequence=i*2;
  sample.counts[0]=20;sample.counts[1]=-10;sample.counts[2]=-10;
  sample.arr=5312;sample.bus_v=323;sample.ccr[0]=sample.ccr[1]=sample.ccr[2]=2656;
  assert(!ma_native_fast(5));++checks;
 }
 const auto w=bin_window;assert(w.count==16&&w.end==sample.cycles&&w.center==w.end-79680U);
 assert(fabsf(w.ia-ma_amps(20))<1e-6f);++checks;
 // A later ADC sample must not enter the completed window, nor move its epoch.
 sample.sequence+=2;sample.cycles+=10624;sample.counts[0]=100;
 inject_torn=true;ma_native_service();assert(observer.steps==0);++telemetry_seq;++checks;
 ma_native_service();assert(observer.steps==1&&!run_fault&&estimate_cycles==w.end);
 assert(observer_center_cycles==w.center);++checks;
 float endpoint[6];assert(!ow_forecast(&model,observer.x,w.tail_va,w.tail_vb,
   (float)(w.end-w.center)/SystemCoreClock,endpoint));
 float published[6];assert(ma_estimate_read(published)==w.end&&!memcmp(published,endpoint,sizeof(endpoint)));++checks;
 ma_native_service();assert(observer.steps==1);++checks;
 // Same completed measurement must not be integrated a second time.
 // Any repeat ADC timestamp is rejected, without padding/filtering it.
 ow_state snapshot=observer_window;ow_bin discard;
 assert(ow_push(&observer_window,snapshot.last,31875,0,0,0,0,&discard)==-1);++checks;
 // Foreground skipped an entire voltage bin. Never integrate the last1ms
 // voltage over a barely-under2ms observer interval.
 bin_window.previous_center+=10624U;bin_window.end+=170000U;
 bin_cycles=bin_window.end;bin_current.cycles=bin_cycles;
 ma_native_service();assert(run_fault==MA_STALE&&observer.steps==1);++checks;
 printf("{\"checks\":%u,\"OFF_cases\":%u,\"fake_clock_cycles_not_target_timing\":true}\n",checks,fe_case);
}
'''
    exe=compile_case(out,'window_adapter',pre+native+'\n'+tail,p.OUT)
    r=subprocess.run([str(exe)],capture_output=True,text=True)
    (out/'window_adapter_run.log').write_text(r.stdout+r.stderr,encoding='utf8');r.check_returncode()
    write(out/'adapter_report.json',dict(passed=True,**json.loads(r.stdout),hardware_commands=0))
    print(r.stdout)
if __name__=='__main__':main()
