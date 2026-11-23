"""Actual native C + double plant with explicit captured/synthetic event timing."""
import json
import prepare_foc_estimate_publish_fix as p
import test_foc_runtime_fix as common
from test_foc_estimate_publish_fix import native_source

def main():
 out=p.OUT/'verification';common.p=p
 pre=p.read(p.ROOT/'artifacts/live_bench_20261029/foc_runtime_fix_r1/verification/native_runtime.cpp').split('#define MIC_NATIVE_BUILD',1)[0]
 plant=p.read(p.ROOT/'tools/multi_algorithm/model_test.cpp');plant=plant[plant.index('struct Plant {'):plant.index('static ma_motor prior')]
 proto='''static void host_publication_irq();
static int host_observe(ma_observer*,const ma_motor*,float,float,float,float,float);
#define ma_observe host_observe
'''
 body=r'''
#undef ma_observe
static Plant plant;
static uint64_t sim_now,next_irq,origin,stop_tick;
static uint32_t wall_cycles=117645,queue_cycles=62522,account_cycles=446;
static unsigned frames,observer_calls;
static bool observing,stopped;static double peak;
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
static void frame(){
 cycle.CYCCNT=(uint32_t)next_irq;
 double a,b;plant.current(plant.x,a,b);
 float amp=(float)(ADC_REFERENCE_VOLTAGE/(4095.0*RSHUNT*AMPLIFICATION_GAIN));
 sample={};sample.valid=sample.zero=1;sample.cycles=cycle.CYCCNT-4000;sample.sequence=++frames;
 sample.counts[0]=(int16_t)lround(a/amp);
 sample.counts[1]=(int16_t)lround((-.5*a+.8660254037844386*b)/amp);
 sample.counts[2]=(int16_t)(-sample.counts[0]-sample.counts[1]);
 float reference=(float)fmin(5.,5.*(next_irq-origin)/170000000.);
 int rc=ma_native_fast(reference);
 if(rc||!timer.BDTR){timer.BDTR=0;stop_tick=next_irq-origin;stopped=true;return;}
 plant.step(controller.last_va,controller.last_vb,10624./170000000.);
 peak=fmax(peak,hypot(a,b));
}
static void advance(uint64_t target){
 while(next_irq<=target&&!stopped){sim_now=next_irq;frame();next_irq+=10624;}
 sim_now=target;cycle.CYCCNT=(uint32_t)sim_now;
}
static int host_observe(ma_observer*o,const ma_motor*m,float a,float b,float va,float vb,float dt){
 assert(!observing);observing=true;
 int rc=ma_observe(o,m,a,b,va,vb,dt);++observer_calls;
 advance(sim_now+wall_cycles);observing=false;return rc;
}
static void host_publication_irq(){advance(sim_now+account_cycles);}
static void setup(){
 sim_now=origin=1000000;cycle.CYCCNT=(uint32_t)origin;next_irq=origin;
 fe_complete=1;fe_started=1;fe_fault=0;fe_case=64;id_profile_attempted=1;
 selected=MA_FOC;sample={};sample.valid=sample.zero=1;sample_coherent=1;fake_bus=323;
 assert(ma_native_prepare());timer.BDTR=1;plant.m=model;
}
int main(int argc,char**argv){
 if(argc>1&&strcmp(argv[1],"overload")==0)wall_cycles=357000; //2.1ms, deliberately outside deadline
 if(argc>1&&strcmp(argv[1],"adverse_unpaired_maxima")==0)wall_cycles=137634;
 setup();
 while(!stopped&&sim_now-origin<170000000ULL*6){
  if(running&&bin_cycles!=estimate_cycles){
   uint64_t target=sim_now+(uint32_t)((uint32_t)(bin_cycles+queue_cycles)-(uint32_t)sim_now);
   if((int32_t)((uint32_t)target-(uint32_t)sim_now)<0)target=sim_now;
   advance(target);if(stopped)break;
   ma_native_service();
   if(run_fault){timer.BDTR=0;stop_tick=sim_now-origin;stopped=true;}
  }else advance(next_irq);
 }
 bool completed=fe_trial_done&&!run_fault&&!timer.BDTR;
 unsigned reason=ma_first_runtime.state==2?ma_first_runtime.word[0]:0;
 printf("{\"completed_5s\":%s,\"PWM_duration_s\":%.9g,\"elapsed_with_accounting_s\":%.9g,\"frames\":%u,\"observer_calls\":%u,\"fault\":%u,\"reason\":%u,\"peak_plant_A\":%.9g,\"estimate_limit_ms\":2}\n",
  completed?"true":"false",stop_tick/170000000.,(sim_now-origin)/170000000.,frames,observer_calls,run_fault,reason,peak);
 EXPECT
}
'''
 body=body.replace('stopped','sim_stopped')
 report={}
 import subprocess
 for label,folder in [('legacy',p.BASE),('candidate',p.OUT)]:
  expectation='assert(!completed&&reason==FT_ESTIMATE_AGE);' if label=='legacy' else '''
 if(argc==1)assert(completed&&frames>=80000);
 else assert(!completed&&run_fault==MA_STALE&&reason==FT_ESTIMATE_AGE);
'''
  code=pre+'\n#include <cstdio>\n#include <algorithm>\n'+plant+proto+native_source(folder)+body.replace('EXPECT',expectation)
  first=common.compile_run(out,'plant_schedule_'+label,code)
  report[label]=json.loads(first)
  if label=='candidate':
   for scenario in ('overload','adverse_unpaired_maxima'):
    r=subprocess.run([str(out/('plant_schedule_'+label+'.exe')),scenario],capture_output=True,text=True,check=True)
    p.write(out/(scenario+'.log'),r.stdout+r.stderr);report[scenario]=json.loads(r.stdout)
 result=dict(passed=True,hardware_commands=0,source='actual native C controller/observer adapter and double precision flux plant',
  nominal_period_cycles=10624,observer_wall_cycles_from_last_capture=117645,
  queue_cycles_from_last_capture=62522,accounting_delay_cycles_injected=446,
  injected_accounting_delay_is_hypothesis=True,IRQ_events_and_main_schedule_are_simulated=True,
  ADC_is_quantized_plant_not_physical_capture=True,measured_CPU_timing_not_replaced_by_simulation=True,
  adverse_unpaired_maxima_not_a_measured_combination=True,hardware_5s_still_pending=True,
  guards_unchanged=True,results=report)
 p.write(out/'schedule_model.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
