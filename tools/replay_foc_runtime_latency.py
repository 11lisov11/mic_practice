"""Reproduce starvation with real C, retained current values and explicit delay."""
import json
import prepare_foc_runtime_fix as p
from test_foc_runtime_fix import compile_run
from audit_production_pwm_filters import function

def main():
 out=p.OUT/'verification/latency_replay_r2';out.mkdir(parents=True,exist_ok=False)
 saved=p.BASE/'powered_FOC_5Hz_5s_r1/ADC_peak_decoded.json'
 trace=json.loads(p.read(saved));rows=[x['counts_uvw'] for x in trace['samples'] if x['accepted_by_monitor']]
 status=json.loads(p.read(p.BASE/'powered_FOC_5Hz_5s_r1/post_STOP_status.json'))['data']
 wall=status['algorithm_observer_cycles'];assert wall==148155
 pre=p.read(p.BASE/'verification/native_epoch.cpp').split('#define MIC_NATIVE_BUILD',1)[0]
 table='static const int replay_counts[][3]={'+','.join('{'+','.join(map(str,r))+'}' for r in rows)+'};\n'
 proto='static int host_observe(ma_observer*,const ma_motor*,float,float,float,float,float);\n#define ma_observe host_observe\n'
 body=r'''
#undef ma_observe
static uint32_t origin,next_irq;static unsigned frame_index;static bool replay_active;
static void frame(){
 cycle.CYCCNT=next_irq;next_irq+=10625U;
 sample.cycles=cycle.CYCCNT-4000U;sample.zero=1;sample.valid=frame_index>=2;
 for(unsigned j=0;j<3;j++)sample.counts[j]=replay_counts[frame_index%11][j];
 ++frame_index;
 auto token=ft_irq_enter(&mic_foc_irq_meter,cycle.CYCCNT,1);
 if(timer.BDTR&&ma_native_fast(5)!=MC_NO_ERROR)timer.BDTR=0;
 cycle.CYCCNT+=1000; // SYNTHETIC IRQ body cost, not a measured CPU split
 ft_irq_leave(&mic_foc_irq_meter,token,cycle.CYCCNT);
}
static void advance(uint32_t target){
 while((int32_t)(target-next_irq)>=0)frame();
 if((int32_t)(target-cycle.CYCCNT)>0)cycle.CYCCNT=target;
}
static int host_observe(ma_observer*o,const ma_motor*m,float ia,float ib,float va,float vb,float dt){
 int rc=ma_observe(o,m,ia,ib,va,vb,dt);
 if(replay_active)advance(cycle.CYCCNT+148155U);
 return rc;
}
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
int main(){
 fe_complete=1;fe_fault=0;fe_case=64;id_profile_attempted=1;selected=MA_FOC;
 sample.zero=1;fake_bus=320;cycle.CYCCNT=1000000;assert(ma_native_prepare());
 origin=cycle.CYCCNT+8500000U;next_irq=origin;timer.BDTR=1;
 for(unsigned n=0;n<18;++n)frame();
 replay_active=true;
 SERVICE_ORDER
 EXPECTATION
 printf("{\"fault\":%u,\"observer_steps\":%u,\"ADC_frames_simulated\":%u}\n",run_fault,observer.steps,frame_index);
}
'''
 results={}
 for label,base,order,expect in [
  ('installed',p.BASE,'advance(cycle.CYCCNT+50000U);ma_native_service();','assert(run_fault==MA_STALE);'),
  ('candidate',p.OUT,'ma_native_service();advance(cycle.CYCCNT+50000U);','assert(!run_fault&&observer.steps==1);')]:
  native=p.read(base/'nucleo/Src/multi_native.c')
  for name in ('ma_native_profile_tick','fe_profile_tick','fe_profile_service'):
   f=function(native,name);native=native.replace(f,f.replace('DWT->CYCCNT','host_profile_clock()'))
  native='\n'.join(l for l in native.splitlines() if not l.startswith(('#include','#pragma')))
  meter='ft_irq_meter mic_foc_irq_meter;\n' if label=='installed' else ''
  code='#include <cstdio>\n'+pre+table+proto+meter+native+'\n'+body.replace('SERVICE_ORDER',order).replace('EXPECTATION',expect)
  result=compile_run(out,label,code);results[label]=json.loads(result)
 report=dict(passed=True,source='actual native C; saved terminal ADC current values transferred to a synthetic startup schedule',
  measured_observer_wall_cycles=wall,foreground_delay_cycles=50000,
  foreground_delay_is_synthetic=True,IRQ_timeline_and_1000cycle_body_are_synthetic=True,
  hardware_CPU_IRQ_split_not_recoverable_from_old_capture=True,
  original_2ms_guard_unchanged=True,hardware_commands=0,new_powered_trials=0,
  not_a_five_second_hardware_validation=True,results=results)
 p.write(out/'report.json',json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
