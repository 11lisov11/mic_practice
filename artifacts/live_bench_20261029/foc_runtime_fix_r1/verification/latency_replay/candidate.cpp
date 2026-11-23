#include <cstdio>

#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include "multi_native.h"
#include "motor_control.h"
#include "uart_v3_transport.h"
#include "research_wire.h"
#include "multi_command.h"
struct Timer{uint32_t ARR=5312,CCR1=100,CCR2=200,CCR3=300,BDTR=0;};
static Timer timer;static Timer*TIM1=&timer;
struct Cycle{uint32_t CYCCNT=1000;};static Cycle cycle;static Cycle*DWT=&cycle;
static uint32_t SystemCoreClock=170000000;
static int motor_state=0;enum{IDLE=0,MC_NO_ERROR=0,MC_SW_ERROR=128,MC_DURATION=1};
static int MC_GetSTMStateMotor1(){return motor_state;}
static int LL_TIM_IsEnabledAllOutputs(Timer*t){return t->BDTR!=0;}
struct Bus{int _Super;};static Bus BusVoltageSensor_M1;
static uint16_t fake_bus=0;
static uint16_t VBS_GetAvBusVoltage_V(int*){return fake_bus;}
static void __DMB(){}
#define TW_AFTER 484
#define TNOISE 255
#define DEADTIME_NS 1350
#define ADV_TIM_CLK_MHz 170
#define ADC_REFERENCE_VOLTAGE 3.3f
#define RSHUNT .04f
#define AMPLIFICATION_GAIN 2.1f
static ma_current_sample sample={};
static int sample_coherent=1;
int mic_current_fast(ma_current_sample*out){*out=sample;return sample_coherent;}

#include "identify_core.h"
#include "identify_wire.h"
#include "foc_experiment.h"
#include <initializer_list>
static int PWM_ParamsM1,off_calls;
static void PWM_SwitchOffPWM(int*){timer.BDTR=0;++off_calls;}
static uint32_t ticks;static uint32_t host_profile_clock(){return ticks+=100;}
enum{TIM1_UP_TIM16_IRQn=25};static unsigned kicks;
static void NVIC_SetPendingIRQ(int);

static const int replay_counts[][3]={{-32,4,28},{-26,10,16},{-32,9,23},{-17,21,-4},{-29,5,24},{-16,-11,27},{-30,8,22},{-28,2,26},{-28,7,21},{-19,13,6},{-15,13,2}};
static int host_observe(ma_observer*,const ma_motor*,float,float,float,float,float);
#define ma_observe host_observe

#define MIC_NATIVE_BUILD 2026102972U
static mi_state id_state;
static mi_config id_config,id_staged;
static uint16_t id_stage_mask;
static uint8_t id_configured,id_prepared,id_profile_attempted;
static uint32_t id_profile_cycles;
static volatile uint8_t id_profile_running;
static void mi_native_profile_off(void);
static int mi_native_prepare(void),mi_native_config(const uint8_t*),mi_native_service(void);
static uint16_t mi_native_fast(void);

/* Motor model must arrive by stopped-only stage/CRC commit. No guessed motor
 * constants are installed as physical identification. Qualification bits assert
 * motor identification, physical amp scale, and target timing evidence separately.
 * Nothing here modifies native SD/Break, watchdog, bus or thermal thresholds.
 */
static ma_motor model=FE_ESTIMATED_MOTOR,staged;
static uint16_t stage_mask;
static volatile uint8_t selected=MA_VF,profile_ready=1,qualification=FE_ESTIMATED,running,first_fault,run_fault;
static ma_observer observer;
static ma_controller controller;
static volatile uint32_t estimate_seq;
static volatile float estimate[6];
static volatile uint32_t estimate_cycles;
static volatile uint32_t telemetry_seq,bin_cycles;
static volatile float bin_va,bin_vb;
static float sum_va,sum_vb;
static uint32_t voltage_n,start_cycles;
static ma_current_sample cached_sample;
static float cached_estimate[6];
static uint32_t cached_estimate_cycles;
static uint32_t max_fast_cycles,max_observer_cycles;
static uint32_t fe_fast_cycles,fe_observer_cycles;static uint8_t fe_fault,fe_case;
static void ma_profile_kick(void);
static unsigned fe_flags(void);static int fe_profile_allowed(unsigned);
static int fe_profile_tick(void);static void fe_profile_service(void);
static volatile uint8_t fe_trial_done;
static uint32_t fe_trial_begin;
static float ma_amps(int16_t counts){
  const float amp_per_count=(float)(ADC_REFERENCE_VOLTAGE/(4095.0*RSHUNT*AMPLIFICATION_GAIN));
  return (float)counts*amp_per_count;
}
static uint32_t ma_u32(const uint8_t*p){uint32_t v;memcpy(&v,p,4);return v;}
static void ma_put(uint8_t*p,uint32_t v){memcpy(p,&v,4);}
typedef char model_layout_is_52[(sizeof(ma_motor)==52)?1:-1];
unsigned ma_native_selected(void){return selected;}
static int stopped(void){return !LL_TIM_IsEnabledAllOutputs(TIM1)&&!running;}
static void ma_fail(unsigned code){if(!first_fault)first_fault=(uint8_t)code;run_fault=(uint8_t)code;}
/* First-fault and execution timing; never a replacement for original guards. */
ft_irq_meter mic_foc_irq_meter;
static ft_perf ma_perf;
static ft_first_fault ma_first_runtime;
static uint32_t ma_observer_begin;
static ft_clock ma_clock_snapshot(void){
 ft_clock out={0};
 for(unsigned retry=0;retry<4;++retry){
  uint32_t seq=mic_foc_irq_meter.seq;__DMB();
  out.now=DWT->CYCCNT;out.irq=mic_foc_irq_meter.cycles;out.roots=mic_foc_irq_meter.roots;
  __DMB();if(!(seq&1U)&&seq==mic_foc_irq_meter.seq){out.valid=1;return out;}
 }
 out.now=DWT->CYCCNT;return out;
}
static void ma_fail_at(unsigned code,unsigned reason,uint32_t at,
 const ma_current_sample*s,uint32_t est,uint32_t bin,uint32_t elapsed){
 ma_fail(code); /* Latch the original stop immediately, even if IRQ preempts. */
 uint32_t expected=0;
 if(!__atomic_compare_exchange_n(&ma_first_runtime.state,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return;
 uint32_t*w=ma_first_runtime.word;
 w[0]=reason;w[1]=code;w[2]=at;w[3]=s?s->cycles:0;w[4]=est;w[5]=bin;w[6]=ma_observer_begin;
 w[7]=ma_perf.wall;w[8]=ma_perf.irq;w[9]=ma_perf.cpu_upper;w[10]=s?s->sequence:0;
 w[11]=(s?((uint32_t)s->valid|((uint32_t)s->zero<<1)):0)|((uint32_t)running<<2);
 w[12]=elapsed;w[13]=observer.steps;
 __DMB();__atomic_store_n(&ma_first_runtime.state,2,__ATOMIC_RELEASE);
}
void ma_timing_diag(uint8_t*p,uint32_t build,unsigned page){
 uint32_t words[7]={0};page%=4;
 unsigned complete=__atomic_load_n(&ma_first_runtime.state,__ATOMIC_ACQUIRE)==2;
 if(page==0){
  words[0]=ma_perf.wall;words[1]=ma_perf.irq;words[2]=ma_perf.cpu_upper;words[3]=ma_perf.roots;
  words[4]=ma_perf.max_wall;words[5]=ma_perf.max_irq;words[6]=ma_perf.max_cpu;
 }else if(page==1){
  words[0]=ma_perf.queue;words[1]=ma_perf.adc_age;words[2]=ma_perf.result_age;
  words[3]=ma_perf.max_queue;words[4]=ma_perf.max_result;words[5]=observer.steps;words[6]=ma_perf.errors;
 }else if(complete)memcpy(words,ma_first_runtime.word+(page-2)*7,sizeof(words));
 memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xE8;p[3]=1;
 p[4]=(uint8_t)page;p[5]=(uint8_t)complete;ma_put(p+6,build);
 for(unsigned i=0;i<7;++i)ma_put(p+10+4*i,words[i]);
 uv3_seal(p);
}

int ma_native_prepare(void){
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||MC_GetSTMStateMotor1()!=IDLE)return 0;
  if(selected==MA_VF)return 1;
  if(selected==4)return mi_native_prepare();
  if(!fe_profile_allowed(selected))return 0;
  running=0;run_fault=0;fe_trial_done=0;memset(&ma_perf,0,sizeof(ma_perf));ma_reset(&observer,&controller);
  ++estimate_seq;__DMB();for(unsigned i=0;i<6;i++)estimate[i]=0;
  estimate_cycles=DWT->CYCCNT;__DMB();++estimate_seq;
  sum_va=sum_vb=0;voltage_n=0;bin_cycles=estimate_cycles;
  memset(&cached_sample,0,sizeof(cached_sample));memset(cached_estimate,0,sizeof(cached_estimate));
  cached_estimate_cycles=estimate_cycles;return 1;
}
int ma_native_request(unsigned algorithm){
  if(algorithm<MA_VF||algorithm>4)return 0;
  if(LL_TIM_IsEnabledAllOutputs(TIM1))return algorithm==selected;
  if(algorithm==4)return id_configured&&!id_state.ready&&!id_state.done&&id_profile_cycles>0&&id_profile_cycles<=4800U;
  if(algorithm!=MA_VF&&!fe_profile_allowed(algorithm))return 0;
  if(algorithm!=selected){
    if(MC_GetSTMStateMotor1()!=IDLE)return 0;
    selected=(uint8_t)algorithm;ma_reset(&observer,&controller);
    estimate_seq++;for(unsigned i=0;i<6;i++)estimate[i]=0;
    estimate_cycles=DWT->CYCCNT;estimate_seq++;
  }
  return 1;
}
int ma_native_config(const uint8_t*f){
  if(!stopped()||f[3]||f[4]!=8||f[12]!=1||f[13]!=0xA6)return 0;
  for(unsigned i=14;i<39;i++)if(f[i])return 0;
  unsigned op=f[6],index=f[7];uint32_t raw=ma_u32(f+8);
  if(op>=4)return mi_native_config(f);
  if(op==1){
    if(index>=13)return 0;
    memcpy((uint8_t*)&staged+4*index,&raw,4);stage_mask|=(uint16_t)(1U<<index);return 1;
  }
  if(op==2){
    if((index>7&&index!=FE_ESTIMATED)||stage_mask!=8191||uv3_crc32c((const uint8_t*)&staged,sizeof(staged))!=raw||
      !ma_motor_valid(&staged)||staged.current_limit>1.1f||staged.trip_current>1.35f)return 0;
    if(index==FE_ESTIMATED&&!fe_model_exact(&staged))return 0;
    model=staged;qualification=(uint8_t)index;profile_ready=1;stage_mask=0;
    ma_reset(&observer,&controller);return 1;
  }
  if(op==3&&index>=MA_VF&&index<=4&&raw==0){
    /* Selection while OFF is legal even before qualification; START will reject.
     * This is a configuration action and never implicitly starts/restarts. */
    selected=(uint8_t)index;fe_trial_done=0;ma_reset(&observer,&controller);return 1;
  }
  return 0;
}
void ma_native_service(void){
  mi_native_profile_off();
  if(id_profile_running){ma_profile_kick();return;}
  fe_profile_service();ma_profile_kick();
  if(mi_native_service())return;
  if(!LL_TIM_IsEnabledAllOutputs(TIM1)){
    running=0;return;
  }
  if(selected==MA_VF||!running||run_fault)return;
  /* Completed16-sample bins define cadence; service immediately when ready. */
  ma_current_sample sample;
  if(!mic_current_fast(&sample)||!sample.valid||!sample.zero)return;
  /* Snapshot completed voltage accumulator without blocking the PWM interrupt.
   * A torn snapshot is retried on a later service turn, never spun on in IRQ. */
  uint32_t seq=telemetry_seq,stamp=bin_cycles;float va=bin_va,vb=bin_vb;
  __DMB();if(seq!=telemetry_seq||(seq&1)||stamp==estimate_cycles)return;
  const float dt=(float)(stamp-estimate_cycles)/SystemCoreClock;
  if(dt<.0001f)return;
  if(dt>.002f){ma_fail_at(MA_STALE,FT_OBSERVER_DT,DWT->CYCCNT,&sample,estimate_cycles,stamp,0);return;}
  ft_clock clock_begin=ma_clock_snapshot();ma_observer_begin=clock_begin.now;
  ma_perf.queue=clock_begin.now-stamp;ma_perf.adc_age=clock_begin.now-sample.cycles;
  if(ma_perf.queue>ma_perf.max_queue)ma_perf.max_queue=ma_perf.queue;
  int fault=ma_observe(&observer,&model,ma_amps(sample.counts[0]),
    (ma_amps(sample.counts[0])+2.f*ma_amps(sample.counts[1]))*.5773502692f,va,vb,dt);
  ft_clock clock_end=ma_clock_snapshot();ft_measure(&ma_perf,clock_begin,clock_end);
  if(ma_perf.wall>max_observer_cycles)max_observer_cycles=ma_perf.wall;
  if(fault){ma_fail_at((unsigned)fault,FT_OBSERVER,clock_end.now,&sample,estimate_cycles,stamp,ma_perf.wall);return;}
  /* Never publish a late estimate after an IRQ has already latched a stop. */
  if(run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return;
  ma_perf.result_age=clock_end.now-stamp;
  if(ma_perf.result_age>ma_perf.max_result)ma_perf.max_result=ma_perf.result_age;
  ++estimate_seq;__DMB();for(unsigned i=0;i<6;i++)estimate[i]=observer.x[i];
  estimate_cycles=stamp;__DMB();++estimate_seq;
}
uint16_t ma_native_fast(float reference_hz){
  const uint32_t begin=DWT->CYCCNT;
  if(selected==MA_VF)return MC_NO_ERROR;
  if(selected==4)return mi_native_fast();
  if(!fe_profile_allowed(selected))return MC_SW_ERROR;
  if(run_fault)return MC_SW_ERROR;
  if(qualification==FE_ESTIMATED){
    if(fe_trial_done){PWM_SwitchOffPWM(&PWM_ParamsM1);return MC_NO_ERROR;}
    if(!isfinite(reference_hz)||reference_hz<0||reference_hz>5.001f){ma_fail(MA_INVALID);return MC_SW_ERROR;}
    if(!running)fe_trial_begin=begin;
    if(running&&fe_time_up(begin,fe_trial_begin,SystemCoreClock)){
      fe_trial_done=1;PWM_SwitchOffPWM(&PWM_ParamsM1);running=0;return MC_NO_ERROR;
    }
  }
  if(!running){
    /* Main resets model state on STOP. Initial neutral vector only primes the
     * real ADC pipeline, bounded to 2 ms; no synthetic sample substitutes for it. */
    running=1;estimate_cycles=begin;start_cycles=begin;
    /* Start one coherent voltage/observer epoch after real PWM becomes active.
     * Do not interpret the earlier OFF/prepare timestamp as a completed bin. */
    ++telemetry_seq;__DMB();bin_cycles=begin;bin_va=bin_vb=0;
    sum_va=sum_vb=0;voltage_n=0;__DMB();++telemetry_seq;
  }
  ma_current_sample sample={0};int got=mic_current_fast(&sample);
  /* If TIM preempts an ADC publication, use only the preceding coherent REAL
   * sample, bounded by the same age limit. Invalid completed samples still stop. */
  if(got&&sample.valid&&sample.zero)cached_sample=sample;
  else if(!got&&cached_sample.valid){sample=cached_sample;got=1;}
  float x[6];uint32_t seq=estimate_seq;__DMB();
  for(unsigned i=0;i<6;i++)x[i]=estimate[i];
  __DMB();int coherent=!(seq&1)&&seq==estimate_seq;
  uint32_t est_cycles;
  if(coherent){
    for(unsigned i=0;i<6;i++)cached_estimate[i]=x[i];
    est_cycles=estimate_cycles;cached_estimate_cycles=est_cycles;
  }else{
    for(unsigned i=0;i<6;i++)x[i]=cached_estimate[i];
    est_cycles=cached_estimate_cycles;
  }
  int fresh=got&&sample.valid&&sample.zero&&
    (uint32_t)(begin-sample.cycles)<SystemCoreClock*3U/16000U&&
    (uint32_t)(begin-est_cycles)<SystemCoreClock/500U;
  if(!fresh){
    if(got&&sample.zero&&coherent&&(uint32_t)(begin-start_cycles)<SystemCoreClock/1000U){
      TIM1->CCR1=TIM1->ARR/2;TIM1->CCR2=TIM1->ARR/2;TIM1->CCR3=TIM1->ARR/2;
      return MC_NO_ERROR;
    }
    unsigned why=!got?FT_NO_SAMPLE:(!sample.valid||!sample.zero)?FT_ADC_INVALID:
      (uint32_t)(begin-sample.cycles)>=SystemCoreClock*3U/16000U?FT_ADC_AGE:FT_ESTIMATE_AGE;
    ma_fail_at(MA_STALE,why,begin,&sample,est_cycles,bin_cycles,0);return MC_SW_ERROR;
  }
  ma_geometry g={TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,112U,240U,
    (uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
  ma_output out;
  int fault=ma_control(&controller,&model,x,&g,selected,ma_amps(sample.counts[0]),
    (ma_amps(sample.counts[0])+2.f*ma_amps(sample.counts[1]))*.5773502692f,
    reference_hz,VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super),1.f/16000U,fresh,&out);
  const uint32_t elapsed=DWT->CYCCNT-begin;
  if(elapsed>max_fast_cycles)max_fast_cycles=elapsed;
  /* Publishing too near the ADC epoch deadline is a duration fault, not a late
   * partial update. Preload remains enabled; all three next compares form a set. */
  if(fault||elapsed>SystemCoreClock/16000U/2U){
    ma_fail_at((unsigned)(fault?fault:MA_STALE),fault?FT_CONTROL:FT_FAST_DURATION,
      begin,&sample,est_cycles,bin_cycles,elapsed);return MC_DURATION;
  }
  TIM1->CCR1=out.ccr[0];TIM1->CCR2=out.ccr[1];TIM1->CCR3=out.ccr[2];
  sum_va+=out.va;sum_vb+=out.vb;
  if(++voltage_n==16){
    ++telemetry_seq;__DMB();bin_va=sum_va/16;bin_vb=sum_vb/16;bin_cycles=begin;
    __DMB();++telemetry_seq;sum_va=sum_vb=0;voltage_n=0;
  }
  return MC_NO_ERROR;
}
void ma_native_diag(uint8_t*p,uint32_t build){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xE4;p[3]=4;
  p[4]=15;p[5]=selected;ma_put(p+6,build);ma_put(p+10,16000);
  p[14]=qualification;p[15]=profile_ready;p[16]=first_fault;p[18]=1;
  p[17]=(uint8_t)(running&&fe_profile_allowed(selected)&&observer.steps>=500&&
    !run_fault&&hypotf(observer.x[2],observer.x[3])>model.flux*.5f&&observer.nis<25);
  ma_put(p+19,max_fast_cycles>fe_fast_cycles?max_fast_cycles:fe_fast_cycles);
  ma_put(p+23,max_observer_cycles>fe_observer_cycles?max_observer_cycles:fe_observer_cycles);
  uint32_t bits;float speed=observer.x[4]*9.549296586f;
  memcpy(&bits,&speed,4);ma_put(p+27,bits);p[31]=running;
  if(profile_ready)ma_put(p+32,uv3_crc32c((const uint8_t*)&model,sizeof(model)));
  p[36]=(uint8_t)fe_flags();p[37]=fe_fault;p[38]=fe_case;uv3_seal(p);
}

/* Native commissioning additions; compiled in the same TU as the existing
 * native controller. No START, fault CLEAR, or protection-register writes. */
static int mi_native_prepare(void){
  ma_current_sample sample;
  if(!id_configured||id_state.active||id_state.ready||id_state.done||!mic_current_fast(&sample)||!sample.zero)return 0;
  if(!id_profile_cycles||id_profile_cycles>4800U||!mi_begin(&id_state,&id_config,0))return 0;
  id_state.active=0;id_prepared=1;
  memset(&cached_sample,0,sizeof(cached_sample));running=0;return 1;
}
static int mi_native_config(const uint8_t*f){
  uint32_t raw=ma_u32(f+8);unsigned op=f[6],index=f[7];
  if(id_state.active)return 0;
  if(op==4){
    if(index>=15||id_state.ready)return 0;
    memcpy((uint8_t*)&id_staged+4*index,&raw,4);id_stage_mask|=(uint16_t)(1U<<index);return 1;
  }
  if(op==5&&index==0){
    if(id_state.ready||id_staged.run_id==id_state.config.run_id||id_stage_mask!=32767U||uv3_crc32c((uint8_t*)&id_staged,sizeof(id_staged))!=raw||!mi_config_valid(&id_staged))return 0;
    id_config=id_staged;id_configured=1;id_prepared=0;id_stage_mask=0;return 1;
  }
  if(op==6&&index==0&&mi_ack(&id_state,raw)){id_configured=0;id_prepared=0;return 1;}
  return 0;
}
int ma_native_complete(void){return (selected==4&&id_state.done)||(qualification==FE_ESTIMATED&&selected==MA_FOC&&fe_trial_done);}
static int mi_native_service(void){
  if(!LL_TIM_IsEnabledAllOutputs(TIM1)){
    if(id_state.active)mi_stop(&id_state,MI_EXTERNAL_STOP,DWT->CYCCNT);
    if(id_state.done&&!id_state.ready)(void)mi_seal(&id_state,MIC_NATIVE_BUILD,SystemCoreClock);
  }
  if(selected==4){if(!LL_TIM_IsEnabledAllOutputs(TIM1))running=0;return 1;}
  return 0;
}
static uint16_t mi_native_fast(void){
  if(!LL_TIM_IsEnabledAllOutputs(TIM1))return MC_NO_ERROR;
  const uint32_t begin=DWT->CYCCNT;ma_current_sample sample;
  int got=mic_current_fast(&sample);
  if(got&&sample.valid&&sample.zero)cached_sample=sample;
  else if(!got&&cached_sample.valid){sample=cached_sample;got=1;}
  if(!running){running=1;start_cycles=begin;}
  if(!got||!sample.valid||!sample.zero){
    if(got&&sample.zero&&(uint32_t)(begin-start_cycles)<SystemCoreClock/1000U){
      TIM1->CCR1=TIM1->ARR/2;TIM1->CCR2=TIM1->ARR/2;TIM1->CCR3=TIM1->ARR/2;return MC_NO_ERROR;
    }
    mi_stop(&id_state,MI_STALE,begin);return MC_SW_ERROR;
  }
  if(!id_state.active){
    if(id_state.done)return MC_SW_ERROR;
    if(!id_configured||!id_prepared)return MC_SW_ERROR;
    id_state.start=sample.cycles;id_state.active=1;id_prepared=0;
  }
  mi_sample point;memset(&point,0,sizeof(point));point.cycles=sample.cycles;point.epoch=sample.epoch;
  point.ia=ma_amps(sample.counts[0]);point.ib=(ma_amps(sample.counts[0])+2*ma_amps(sample.counts[1]))*.5773502692f;
  point.bus=sample.bus_v;point.arr=sample.arr;point.valid=sample.valid;
  for(unsigned i=0;i<3;i++)point.ccr[i]=sample.ccr[i];
  ma_geometry geometry={TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,112U,240U,
    (uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
  ma_output out;int rc=mi_step(&id_state,&geometry,&point,begin,SystemCoreClock,&out);
  if(rc==MI_COMPLETE){PWM_SwitchOffPWM(&PWM_ParamsM1);return MC_NO_ERROR;}
  if(rc!=MI_OK)return MC_SW_ERROR;
  const uint32_t elapsed=DWT->CYCCNT-begin;if(elapsed>max_fast_cycles)max_fast_cycles=elapsed;
  if(elapsed>SystemCoreClock/16000U/2U){mi_stop(&id_state,MI_OVERRUN,begin);return MC_DURATION;}
  TIM1->CCR1=out.ccr[0];TIM1->CCR2=out.ccr[1];TIM1->CCR3=out.ccr[2];return MC_NO_ERROR;
}
void ma_id_status(uint8_t*p,uint32_t build){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=ID_STATUS_WIRE;p[3]=2;p[4]=4;
  p[5]=(id_configured?1:0)|(!id_profile_running&&id_state.active?2:0)|(!id_profile_running&&id_state.ready?4:0)|(!id_profile_running&&id_state.done?8:0);
  id_put(p+6,build);id_put(p+10,id_configured?uv3_crc32c((uint8_t*)&id_config,sizeof(id_config)):0);
  id_put(p+14,id_state.ready?id_state.crc:0);id_put(p+18,id_config.run_id);id_put(p+22,id_config.kind);
  uint32_t raw;memcpy(&raw,&id_config.frequency,4);id_put(p+26,raw);id_put(p+30,id_config.duration_ms);
  id_put(p+34,id_profile_cycles);p[38]=id_profile_running?0:id_state.fault;uv3_seal(p);
}
int ma_id_page(uint8_t*p,uint32_t build,unsigned page){
  if(!id_state.ready||LL_TIM_IsEnabledAllOutputs(TIM1)||page>=MI_PAGES)return 0;
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=ID_PAGE_WIRE;p[3]=1;p[4]=(uint8_t)page;p[5]=MI_PAGES;
  id_put(p+6,build);id_put(p+10,id_state.crc);unsigned offset=24*page,n=MI_BYTES-offset;if(n>24)n=24;
  memcpy(p+14,id_state.bytes+offset,n);uv3_seal(p);return 1;
}

/* Same-priority CPU qualification: main prepares synthetic work while MOE=0;
 * the normal TIM1 update IRQ measures one pure kernel call. No IRQ mask, PWM,
 * MCSDK START or protection acknowledgment is used. */
static uint8_t id_profile_case,id_profile_n;
static volatile uint8_t id_profile_pending,id_profile_done;
static volatile uint32_t id_profile_elapsed;
static volatile int id_profile_rc;
static uint32_t id_profile_maximum;
static mi_sample id_profile_input;
static ma_geometry id_profile_geometry;
static void mi_profile_finish(int okay){
 id_profile_pending=0;id_profile_running=0;id_profile_done=0;
 memset(&id_state,0,sizeof(id_state));id_prepared=0;
 id_profile_cycles=okay?id_profile_maximum:UINT32_MAX;
}
static void mi_native_profile_off(void){
 if(id_profile_attempted&&!id_profile_running)return;
 if(!id_profile_attempted){
  if(id_configured||id_state.active||id_state.ready||id_state.done||LL_TIM_IsEnabledAllOutputs(TIM1)||
    VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)>20U)return;
  ma_current_sample real_sample;if(!mic_current_fast(&real_sample)||!real_sample.zero)return;
  id_profile_attempted=1;id_profile_running=1;id_profile_case=id_profile_n=0;id_profile_maximum=0;
  id_profile_geometry=(ma_geometry){TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,112U,240U,
   (uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
 }
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)>20U){mi_profile_finish(0);return;}
 if(id_profile_pending)return;
 if(id_profile_done){
  if(id_profile_elapsed>id_profile_maximum)id_profile_maximum=id_profile_elapsed;
  if(id_profile_rc!=MI_OK){mi_profile_finish(0);return;}
  id_profile_done=0;
  if(++id_profile_n==128){id_profile_n=0;if(++id_profile_case==8){mi_profile_finish(1);return;}}
 }
 unsigned k=id_profile_case;
 if(!id_profile_n){
  mi_config cfg;memset(&cfg,0,sizeof(cfg));cfg.run_id=k+1;cfg.kind=k<2?MI_DC:MI_AC;
  cfg.axis=(k%3)*2.0943951024f;cfg.amplitude=.3f;cfg.rs=12.23f;cfg.duration_ms=3000;
  cfg.gain=.95f;cfg.knee=.002f;for(unsigned j=0;j<3;j++)cfg.drop[j]=15;cfg.offset[0]=2;cfg.offset[1]=-2;
  if(cfg.kind==MI_AC){cfg.frequency=k<4?1:k<6?50:200;
   cfg.duration_ms=(uint32_t)ceilf(1000*(mi_settle_cycles(&cfg)+5)/cfg.frequency)+1;cfg.calibration_crc=mi_cal_crc(&cfg);}
  memset(&id_state,0,sizeof(id_state));if(!mi_begin(&id_state,&cfg,0)){mi_profile_finish(0);return;}
  id_state.response=cfg.amplitude;
 }
 const mi_config* cfg=&id_state.config;
 float offset=(k&1)?(cfg->kind==MI_DC?2.6f:(id_state.settle_cycles+.1f)/cfg->frequency):.1f;
 memset(&id_profile_input,0,sizeof(id_profile_input));id_profile_input.valid=1;id_profile_input.bus=k&1?250:350;
 id_profile_input.arr=id_profile_geometry.arr;id_profile_input.epoch=id_profile_n+1;
 id_profile_input.cycles=(uint32_t)(offset*SystemCoreClock)+id_profile_n*(SystemCoreClock/16000U);
 float phase=6.2831853072f*cfg->frequency*id_profile_input.cycles/SystemCoreClock;
 float current=cfg->kind==MI_DC?cfg->amplitude:cfg->amplitude*sinf(phase);
 id_profile_input.ia=current*id_state.axis_cos;id_profile_input.ib=current*id_state.axis_sin;
 for(unsigned j=0;j<3;j++)id_profile_input.ccr[j]=id_profile_geometry.arr/2;
 __DMB();id_profile_pending=1;
}
void ma_native_profile_tick(void){
 if(fe_profile_tick())return;
 if(!id_profile_running||!id_profile_pending||LL_TIM_IsEnabledAllOutputs(TIM1))return;
 ma_output output;
 uint32_t begin=host_profile_clock();
 int rc=mi_step(&id_state,&id_profile_geometry,&id_profile_input,id_profile_input.cycles+32,SystemCoreClock,&output);
 id_profile_elapsed=host_profile_clock()-begin;id_profile_rc=rc;id_profile_done=1;
 __DMB();id_profile_pending=0;
}

/* Isolated synthetic CPU probe. Runs only with MOE=0, low bus and real zero.
 * Main prepares cases; real TIM1 IRQ measures pure FOC, main measures observer.
 * No synthetic sample enters current feedback or saved physical captures. */
static ma_controller fe_test_controller;
static ma_observer fe_test_observer;
static ma_geometry fe_test_geometry;
static float fe_test_x[6],fe_test_ia,fe_test_ib,fe_test_bus,fe_test_ref;
static ma_output fe_test_out;
static volatile uint8_t fe_pending,fe_finished;
static volatile uint32_t fe_elapsed;
static volatile int fe_rc;
static uint8_t fe_started,fe_complete,fe_n;

static unsigned fe_flags(void){
 return (fe_complete&&!fe_fault?FE_READY:0)|
  (fe_started&&!fe_complete&&!fe_fault?FE_BUSY:0)|(fe_trial_done?FE_DONE:0);
}
static int fe_profile_allowed(unsigned algorithm){
 return profile_ready&&(qualification==7||
  (qualification==FE_ESTIMATED&&algorithm==MA_FOC&&fe_model_exact(&model)&&
   (fe_flags()&FE_READY)&&!fe_fault));
}
static int fe_profile_tick(void){
 if(!fe_pending||LL_TIM_IsEnabledAllOutputs(TIM1))return 0;
 const uint32_t begin=host_profile_clock();
 fe_rc=ma_control(&fe_test_controller,&model,fe_test_x,&fe_test_geometry,MA_FOC,
   fe_test_ia,fe_test_ib,fe_test_ref,fe_test_bus,1.f/16000U,1,&fe_test_out);
 fe_elapsed=host_profile_clock()-begin;__DMB();fe_finished=1;fe_pending=0;return 1;
}
static void fe_profile_service(void){
 if(qualification!=FE_ESTIMATED||fe_complete||fe_fault)return;
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||
    VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)>20U)return;
 ma_current_sample real_sample;
 if(!mic_current_fast(&real_sample)||!real_sample.zero)return;
 if(!fe_started){
  fe_started=1;fe_case=fe_n=0;
  fe_test_geometry=(ma_geometry){TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,
   112U,240U,(uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
 }
 if(fe_pending)return;
 if(fe_finished){
  fe_finished=0;
  if(fe_elapsed>fe_fast_cycles)fe_fast_cycles=fe_elapsed;
  if(fe_rc||!fe_elapsed||fe_elapsed>FE_FAST_BUDGET){fe_fault=(uint8_t)(fe_rc?fe_rc:MA_STALE);return;}
  /* One foreground observer call per case; timer/ADC/UART interrupts stay on. */
  if(!fe_n){
   const uint32_t begin=host_profile_clock();
   int rc=ma_observe(&fe_test_observer,&model,fe_test_ia,fe_test_ib,
                    fe_test_out.va,fe_test_out.vb,.001f);
   uint32_t cycles=host_profile_clock()-begin;
   if(cycles>fe_observer_cycles)fe_observer_cycles=cycles;
   if(rc||!cycles||cycles>FE_OBSERVER_BUDGET){fe_fault=(uint8_t)(rc?rc:MA_STALE);return;}
  }
  if(++fe_n==8){fe_n=0;if(++fe_case==FE_CASES){fe_complete=1;return;}}
 }
 if(!fe_n){
  ma_reset(&fe_test_observer,&fe_test_controller);
  float angle=(fe_case%16U)*.3926990817f,c=cosf(angle),s=sinf(angle);
  float current=(fe_case&16U)?.75f:.2f;
  fe_test_ia=current*c;fe_test_ib=current*s;
  fe_test_x[0]=fe_test_ia;fe_test_x[1]=fe_test_ib;
  fe_test_x[2]=model.flux*c;fe_test_x[3]=model.flux*s;
  fe_test_x[4]=(fe_case&32U)?314.1592654f:31.41592654f;fe_test_x[5]=0;
  for(unsigned i=0;i<6;i++)fe_test_observer.x[i]=fe_test_x[i];
  fe_test_controller.time_s=(fe_case&8U)?1.f:.05f;
  fe_test_bus=(fe_case&4U)?250.f:350.f;fe_test_ref=(fe_case&2U)?50.f:5.f;
 }
 __DMB();fe_pending=1;
}

int ma_native_reference_allowed(unsigned algorithm,uint32_t millihz){
 return qualification!=FE_ESTIMATED||algorithm==MA_VF||
   (algorithm==MA_FOC&&millihz>0&&millihz<=5000U);
}

/* MCSDK may mask UPDATE at MOE0. Pend the SAME enabled NVIC vector only for
 * isolated CPU work. No DIER, BDTR, BKE/BIE, ADC or GPIO write is involved. */
static void ma_profile_kick(void){
 if(!LL_TIM_IsEnabledAllOutputs(TIM1)&&
    VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)<=20U&&
    (id_profile_pending||fe_pending))NVIC_SetPendingIRQ(TIM1_UP_TIM16_IRQn);
}

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
 ma_native_service();advance(cycle.CYCCNT+50000U);
 assert(!run_fault&&observer.steps==1);
 printf("{\"fault\":%u,\"observer_steps\":%u,\"ADC_frames_simulated\":%u}\n",run_fault,observer.steps,frame_index);
}
