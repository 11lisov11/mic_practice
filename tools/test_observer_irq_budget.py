"""Actual-handler event replay, exact controller comparison, IRQ/wire checks."""
import importlib.util,json,sys
import prepare_observer_irq_budget as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function
from test_foc_observer_schedule_fix import stripped_header


def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
 pre='''#include <cassert>\n#include <cstdio>\n#include <cmath>\n#include <cstring>\n#include <cstdint>\n#include <initializer_list>\n#include <cfloat>\n#include "current_adc_window_plan.h"\nusing std::isfinite;using std::isnan;\n'''
 old=stripped_header(p.read(p.BASE/'nucleo/Inc/motor_control.h'))
 new=stripped_header(p.read(p.OUT/'nucleo/Inc/motor_control.h'))
 code=pre+'namespace baseline{\n'+old+'\n}\nnamespace candidate{\n'+new+'\n}\n'+r'''
static uint32_t rng=0x15f02026;static uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static float value(float lo,float hi){return lo+(hi-lo)*(next()>>8)*(1.f/16777216.f);}
int main(){
 baseline::ma_motor m={12.23f,11.004422f,.52809386f,.52809386f,.4944776f,.0002f,.000147906f,1,.25f,.8f,1.35f,400,12};
 candidate::ma_motor nm;memcpy(&nm,&m,sizeof(m));
 baseline::ma_geometry g={5312,5184,771,112,240,229};candidate::ma_geometry ng;memcpy(&ng,&g,sizeof(g));
 unsigned cases=0;
 for(unsigned i=0;i<200000;++i){
  baseline::ma_controller a={};a.time_s=value(0,5);a.integral[0]=value(-2,2);a.integral[1]=value(-2,2);a.speed_integral=value(-.1f,.1f);
  if(i<100000)a.time_s=value(0,.35f);
  if(i%1000==0)a.time_s=std::nextafter(.35f,-INFINITY)-1.f/16000;
  if(i%1000==1)a.time_s=.35f-1.f/16000;
  if(i%1000==2)a.time_s=std::nextafter(.35f,INFINITY)-1.f/16000;
  if(i%1000==3)a.time_s=NAN;
  candidate::ma_controller b;memcpy(&b,&a,sizeof(b));
  float x[6]={value(-1,1),value(-1,1),value(.001f,.3f),value(-.2f,.2f),value(-10,40),0};
  float ia=value(-1.5f,1.5f),ib=value(-1.5f,1.5f),ref=value(0,5),bus=value(250,350);
  if(i%500==0)ia=NAN;if(i%500==1)ia=INFINITY;if(i%500==2)ia=-0.f;
  baseline::ma_output oa;candidate::ma_output ob;int algo=i%2?2:3;
  int ra=baseline::ma_control(&a,&m,x,&g,algo,ia,ib,ref,bus,1.f/16000,1,&oa);
 static const candidate::ma_motor fixed={12.23f,11.004422f,.52809386f,.52809386f,.4944776f,.0002f,.000147906f,1,.25f,.8f,1.35f,400,12};
 int rb=candidate::ma_control_checked(&b,&fixed,x,&ng,algo,ia,ib,ref,bus,1.f/16000,1,&ob,candidate::ma_motor_valid(&nm));
  assert(ra==rb&&memcmp(&a,&b,sizeof(a))==0&&memcmp(&oa,&ob,sizeof(oa))==0);++cases;
 }
 baseline::ma_observer ao;baseline::ma_controller ac;candidate::ma_observer bo;candidate::ma_controller bc;
 unsigned observer_cases=0;
 for(unsigned i=0;i<20000;++i){
  if(i%64==0){baseline::ma_reset(&ao,&ac);candidate::ma_reset(&bo,&bc);}
  float ia=value(-.5f,.5f),ib=value(-.5f,.5f),va=value(-5,5),vb=value(-5,5);
  int ra=baseline::ma_observe(&ao,&m,ia,ib,va,vb,.001f);
  int rb=candidate::ma_observe(&bo,&nm,ia,ib,va,vb,.001f);
  assert(ra==rb&&!memcmp(&ao,&bo,sizeof(ao)));++observer_cases;
 }
 printf("{\"bit_exact_control_cases\":%u,\"bit_exact_observer_cases\":%u,\"startup_and_active_and_boundary_cases\":true}\n",cases,observer_cases);
}
'''
 numeric=json.loads(common.compile_run(out,'controller_exact_startup',code))
 # Extract the real old/new IRQ functions into deterministic hardware stubs.
 stub=r'''
static const unsigned UV3_FRAME=43,UNO_TX_SLOTS=4,UNO_TX_TAG_DIAG=0,UNO_TX_TAG_OFF=2;
static const unsigned USART_CR1_TCIE=64,USART_CR3_DMAT=128,USART_ICR_TCCF=1,UART_FLAG_TC=64;
static const unsigned DMA_CCR_EN=1,DMA_CCR_TCIE=2,DMA_CCR_TEIE=8,HAL_ERROR=1;
struct Regs{uint32_t CR1=0,CR3=0,ICR=0,ISR=0,TDR=0;};static Regs uart;
struct HU{Regs*Instance;};static HU huart1={&uart};
struct DM{uint32_t CCR=0,CPAR=0,CMAR=0,CNDTR=0;};static DM channel,*DMA1_Channel1=&channel;
struct DC{uint32_t ISR=0,IFCR=0;};static DC dm,*DMA1=&dm;
static unsigned off_calls;static int tim;static int*TIM1=&tim;
static void LL_TIM_DisableAllOutputs(int*){++off_calls;}
static void __DMB(){}
static unsigned HAL_GetTick(){return 100;}
struct TX{uint32_t head,tail,active,started_ms,late_reported,hard_error,queued,completed,timeouts,full_errors,dma_errors,last_status,early_tc;uint8_t bytes[4][43],tags[4];};
static TX mic_uart_tx;static bool mic_last_control_reply_safe_off;
#define MIC_FOC_IRQ_SCOPE
#define MIC_FOC_IRQ_SCOPE_NAMED(a,b)
#define MIC_UART_TX_DMA_ACK(mask) do{DMA1->ISR&=~(mask);DMA1->IFCR=(mask);}while(0)
void DMA1_Channel1_IRQHandler(void);
static void reset(){mic_uart_tx={};uart={};channel={};dm={};off_calls=0;mic_last_control_reply_safe_off=false;
 mic_uart_tx.head=1;mic_uart_tx.tags[0]=UNO_TX_TAG_OFF;for(unsigned i=0;i<43;++i)mic_uart_tx.bytes[0][i]=(uint8_t)(17*i);}
'''
 src=[]
 for folder in (p.BASE,p.OUT):
  s=p.read(folder/'nucleo/Src/main.c')
  src.append(stub+'\n'+'\n'.join(function(s,n) for n in ('uno_tx_begin_locked','uno_tx_tc_isr','DMA1_Channel1_IRQHandler')))
 code='#include <cassert>\n#include <cstdio>\n#include <cstring>\n#include <cstdint>\nnamespace baseline{\n'+src[0]+'\n}\nnamespace candidate{\n'+src[1]+'\n}\n'+r'''
int main(){
 baseline::reset();baseline::uno_tx_begin_locked(100);
 baseline::uart.ISR=baseline::UART_FLAG_TC;
 for(unsigned i=0;i<100;++i)baseline::uno_tx_tc_isr();
 assert(baseline::mic_uart_tx.early_tc==100&&(baseline::uart.CR1&baseline::USART_CR1_TCIE));
 unsigned scenarios=0;
 for(unsigned delay=0;delay<1024;++delay){
  candidate::reset();candidate::uno_tx_begin_locked(100);
  auto bytes=candidate::mic_uart_tx;candidate::uart.ISR=candidate::UART_FLAG_TC;
  assert(!(candidate::uart.CR1&candidate::USART_CR1_TCIE));
  for(unsigned i=0;i<100;++i)candidate::uno_tx_tc_isr();
  assert(!candidate::mic_uart_tx.early_tc&&!candidate::mic_uart_tx.completed);
  // A spurious/legacy early TC is disabled, never acknowledged as a frame end.
  candidate::uart.CR1|=candidate::USART_CR1_TCIE;candidate::uno_tx_tc_isr();
  assert(candidate::mic_uart_tx.early_tc==1&&!(candidate::uart.CR1&candidate::USART_CR1_TCIE));
  assert(candidate::mic_uart_tx.active&&candidate::mic_uart_tx.tail==0);
  candidate::channel.CNDTR=0;candidate::dm.ISR=2;
  // Simulate DMA IRQ arriving either before or after the final UART stop bit.
  candidate::uart.ISR=delay&1?candidate::UART_FLAG_TC:0;
  candidate::DMA1_Channel1_IRQHandler();
  assert(candidate::uart.CR1&candidate::USART_CR1_TCIE);
  candidate::uno_tx_tc_isr();
  if(!(delay&1)){assert(!candidate::mic_uart_tx.completed);candidate::uart.ISR=candidate::UART_FLAG_TC;candidate::uno_tx_tc_isr();}
  assert(candidate::mic_uart_tx.completed==1&&candidate::mic_uart_tx.tail==1&&!candidate::mic_uart_tx.active);
  candidate::uno_tx_tc_isr();assert(candidate::mic_uart_tx.completed==1);
  assert(!memcmp(bytes.bytes,candidate::mic_uart_tx.bytes,sizeof(bytes.bytes))&&candidate::mic_last_control_reply_safe_off);
  // Real DMA error keeps the original hard error/output disable and no restart.
  candidate::reset();candidate::uno_tx_begin_locked(100);candidate::dm.ISR=10;
  candidate::DMA1_Channel1_IRQHandler();
  assert(candidate::mic_uart_tx.hard_error&&candidate::mic_uart_tx.dma_errors==1&&candidate::off_calls==1);
  assert(!candidate::mic_uart_tx.completed&&!(candidate::uart.CR1&candidate::USART_CR1_TCIE));
  ++scenarios;
 }
 printf("{\"old_pending_TC_reentry_reproduced\":100,\"new_TX_event_scenarios\":%u,\"CRC_payload_unchanged\":true,\"DMA_error_still_stops\":true}\n",scenarios);
}
'''
 uart=json.loads(common.compile_run(out,'UART_actual_handlers',code))
 code=r'''
#include <cassert>
#include <cstdio>
#include "irq_breakdown.h"
#include "foc_timing_wire.h"
int main(){
 ib_meter m={};ib_snapshot a;ib_read(&m,&a,0xfffffff0U);uint32_t w[21];
 ib_leave(&m,4,100);ib_leave(&m,3,50);ib_leave(&m,2,12);ib_delta(&m,&a,0x50,w);
 assert(w[8]==1&&w[9]==100&&w[6]==1&&w[7]==50&&w[20]==511);
 // The frozen timing packet uses the same CRC/peer/version checks, now9 pages.
 ft_receiver r={};uint8_t f[43];
 for(unsigned page=0;page<9;++page){memset(f,0,sizeof(f));f[0]=0x55;f[1]=0xaa;f[2]=FT_WIRE;f[3]=3;f[4]=page;
  uint32_t fw=2026111502;memcpy(f+6,&fw,4);for(unsigned i=0;i<7;++i){uint32_t v=page*7+i;memcpy(f+10+4*i,&v,4);}uv3_seal(f);
  assert(ft_receive(&r,f,fw,true,10));if(page<8)assert(!ft_fresh(&r,true,10));}
 assert(ft_fresh(&r,true,10)&&r.words[62]==62);
 f[3]=2;uv3_seal(f);assert(!ft_receive(&r,f,2026111502,true,10));
 f[3]=3;uv3_seal(f);f[12]^=1;assert(!ft_receive(&r,f,2026111502,true,10));
 // A preempted writer never spins, and it is marked invalid rather than invented.
 m.irq[3].seq=1;ib_delta(&m,&a,0x60,w);assert(!(w[20]&(1U<<3))&&w[6]==0&&w[7]==0);
 printf("{\"nine_IRQ_slots\":true,\"wire9_pages\":true,\"CRC_peer_format_guarded\":true,\"bounded_torn_snapshot\":true}\n");
}
'''
 wire=json.loads(common.compile_run(out,'IRQ_wire',code))
 # Execute the real instrumenting wrapper with nested mock Cortex-M vectors.
 scope=p.read(p.OUT/'nucleo/Inc/foc_timing_irq.h').replace('#include "main.h"','')
 code=r'''
#include <cassert>
#include <cstdio>
#include "foc_timing_core.h"
#include "irq_breakdown.h"
struct Clock{uint32_t CYCCNT;};static Clock clock_hw,*DWT=&clock_hw;
struct Scb{uint32_t ICSR;};static Scb scb,*SCB=&scb;
static const uint32_t SCB_ICSR_RETTOBASE_Msk=2048;
static uint32_t ipsr;static uint32_t __get_IPSR(){return ipsr;}static void __DMB(){}
ft_irq_meter mic_foc_irq_meter={};ib_meter mic_foc_irq_detail={};
'''+scope+r'''
static void early_return(){MIC_FOC_IRQ_SCOPE_NAMED(2,37);DWT->CYCCNT+=10;return;}
int main(){
 ipsr=53;SCB->ICSR=2048;DWT->CYCCNT=100;
 auto uart=mic_foc_irq_begin(2,37);DWT->CYCCNT=110;
 ipsr=41;SCB->ICSR=0;auto update=mic_foc_irq_begin(4,25);DWT->CYCCNT=160;mic_foc_irq_end(&update);
 ipsr=53;SCB->ICSR=2048;DWT->CYCCNT=200;mic_foc_irq_end(&uart);
 assert(mic_foc_irq_meter.cycles==100&&mic_foc_irq_meter.roots==1);
 assert(mic_foc_irq_detail.irq[2].count==1&&mic_foc_irq_detail.irq[2].cycles==100);
 assert(mic_foc_irq_detail.irq[4].count==1&&mic_foc_irq_detail.irq[4].cycles==50);
 // C call to another IRQ helper is not a second hardware exception.
 auto helper=mic_foc_irq_begin(1,11);DWT->CYCCNT=210;mic_foc_irq_end(&helper);
 assert(mic_foc_irq_detail.irq[1].count==0&&mic_foc_irq_meter.roots==1);
 early_return();assert(mic_foc_irq_detail.irq[2].count==2&&mic_foc_irq_meter.roots==2);
 puts("{\"actual_IRQ_wrapper_nested\":true,\"C_helper_not_double_counted\":true,\"early_return_cleanup\":true}");
}
'''
 scope_test=json.loads(common.compile_run(out,'IRQ_scope_actual',code))
 # Critical numerical and timing protections must be byte-identical.
 untouched=[]
 for rel in ('nucleo/Inc/foc_experiment.h','nucleo/Inc/current_adc_deadline.h','nucleo/Inc/current_adc_window_plan.h',
             'nucleo/Src/current_shunt.c','nucleo/Inc/current_core.h','nucleo/Src/regular_conversion_manager.c',
             'nucleo/Inc/observer_applied_voltage.h','nucleo/Inc/local_stop.h'):
  assert p.read(p.OUT/rel)==p.read(p.BASE/rel).replace('2026111407',str(p.NEW[0])).replace('2026111408',str(p.NEW[1])),rel
  untouched.append(rel)
 before=p.read(p.BASE/'nucleo/Src/multi_native.c');after=p.read(p.OUT/'nucleo/Src/multi_native.c')
 for name in ('fe_profile_service','ma_estimate_publish','fe_profile_allowed'):
  assert function(before,name)==function(after,name),name
 old_fast=function(before,'ma_native_fast');new_fast=function(after,'ma_native_fast')
 a=old_fast.index('  int fault=ma_control_checked(');b=old_fast.index('  if(!fault && voltage_fault)',a)
 c=new_fast.index('  int fault;');d=new_fast.index('  if(!fault && voltage_fault)',c)
 assert new_fast[:c]+old_fast[a:b]+new_fast[d:]==old_fast
 old_probe=function(before,'fe_profile_tick');new_probe=function(after,'fe_profile_tick')
 normalized=new_probe.replace('const int model_ok=fe_model_exact(&model);\n fe_rc=avrc?avrc:ma_control_checked(&fe_test_controller,&fe_control_model,',
 'fe_rc=avrc?avrc:ma_control(&fe_test_controller,&model,').replace('1,&fe_test_out,model_ok);','1,&fe_test_out);')
 assert normalized==old_probe
 import re
 for source in ('main.c','stm32g4xx_mc_it.c'):
  a=p.read(p.BASE/'nucleo/Src'/source);b=p.read(p.OUT/'nucleo/Src'/source)
  assert re.findall(r'HAL_NVIC_\w+\([^;]+;',a)==re.findall(r'HAL_NVIC_\w+\([^;]+;',b)
  assert a.count('MIC_FOC_IRQ_SCOPE;')==b.count('MIC_FOC_IRQ_SCOPE_NAMED(')
 for name in ('ma_derivative','ma_modulate'):
  assert function(p.read(p.BASE/'nucleo/Inc/motor_control.h'),name)==function(p.read(p.OUT/'nucleo/Inc/motor_control.h'),name),name
 old_observer=function(p.read(p.BASE/'nucleo/Inc/motor_control.h'),'ma_observe')
 new_observer=function(p.read(p.OUT/'nucleo/Inc/motor_control.h'),'ma_observe')
 decl='''  float a[6][6],f[6][6],tmp[6][6];
  /* The Jacobian is dead after F is built. Reuse its144-byte workspace for
     covariance; no arithmetic order changes and no shared/static scratch. */
  float (*cov)[6]=a;'''
 assert new_observer.replace(decl,'  float a[6][6],f[6][6],tmp[6][6],cov[6][6];').replace('memcpy(cov,tmp,sizeof(a));','memcpy(cov,tmp,sizeof(cov));')==old_observer
 # HMI replay of the real fault remains2028us; unknown per-vector data not fabricated.
 spec=importlib.util.spec_from_file_location('irq_candidate_HMI',p.OUT/'web_hmi/server.py')
 hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
 saved=json.loads(p.read(p.BASE/'powered_FOC_20261115_r2/observer_final_status.json'))['data']
 decoded=hmi.foc_runtime_status(saved)['foc_runtime']
 assert decoded['first_fault']['reason_code']==4 and decoded['first_fault']['estimate_age_us']>2000
 assert not decoded['IRQ_breakdown']['available']
 for i in range(42,63):saved['foc_runtime_w'+str(i)]=0
 saved.update(foc_runtime_w50=14,foc_runtime_w51=70000,foc_runtime_w60=1000,foc_runtime_w61=171000,foc_runtime_w62=511)
 decoded=hmi.foc_runtime_status(saved)['foc_runtime'];assert decoded['IRQ_breakdown']['handlers'][4]['completed_calls']==14
 report=dict(passed=True,hardware_commands=0,numeric=numeric,UART=uart,IRQ_wire=wire,IRQ_wrapper=scope_test,
   IRQ_priorities_and_enables_unchanged=True,
   unchanged_protection_sources=untouched,fast_loop_guards_unchanged=True,
   OFF_probe_same_control_path_with_stricter_exact_model_check_inside_timing=True,
   captured_fault_replayed_without_changing_2ms=True,physical5s_run_proven=False,
   target_cycles_measured=False,limitation='Original capture has aggregate IRQ time only. UART storm is reproduced from the actual handlers, but its occurrence in that powered run is not proven. Named IRQ timings are inclusive and cannot be summed.')
 p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
