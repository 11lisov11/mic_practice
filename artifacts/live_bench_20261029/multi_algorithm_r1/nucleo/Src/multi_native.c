#pragma GCC optimize ("O2")
#include "main.h"
#include "mc_config.h"
#include "mc_interface.h"
#include "mc_api.h"
#include "mc_type.h"
#include "parameters_conversion.h"
#include "stm32g4xx_ll_tim.h"
#include "uart_v3_transport.h"
#include "multi_native.h"
#include "motor_control.h"
/* Motor model must arrive by stopped-only stage/CRC commit. No guessed motor
 * constants are installed as physical identification. Qualification bits assert
 * motor identification, physical amp scale, and target timing evidence separately.
 * Nothing here modifies native SD/Break, watchdog, bus or thermal thresholds.
 */
static ma_motor model,staged;
static uint16_t stage_mask;
static volatile uint8_t selected=MA_VF,profile_ready,qualification,running,first_fault,run_fault;
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
int ma_native_prepare(void){
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||MC_GetSTMStateMotor1()!=IDLE)return 0;
  if(selected==MA_VF)return 1;
  if(!profile_ready||qualification!=7)return 0;
  running=0;run_fault=0;ma_reset(&observer,&controller);
  ++estimate_seq;__DMB();for(unsigned i=0;i<6;i++)estimate[i]=0;
  estimate_cycles=DWT->CYCCNT;__DMB();++estimate_seq;
  sum_va=sum_vb=0;voltage_n=0;bin_cycles=estimate_cycles;
  memset(&cached_sample,0,sizeof(cached_sample));memset(cached_estimate,0,sizeof(cached_estimate));
  cached_estimate_cycles=estimate_cycles;return 1;
}
int ma_native_request(unsigned algorithm){
  if(algorithm<MA_VF||algorithm>MA_ADAPTIVE)return 0;
  if(LL_TIM_IsEnabledAllOutputs(TIM1))return algorithm==selected;
  if(algorithm!=MA_VF&&(!profile_ready||qualification!=7))return 0;
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
  if(op==1){
    if(index>=13)return 0;
    memcpy((uint8_t*)&staged+4*index,&raw,4);stage_mask|=(uint16_t)(1U<<index);return 1;
  }
  if(op==2){
    if(index>7||stage_mask!=8191||uv3_crc32c((const uint8_t*)&staged,sizeof(staged))!=raw||
      !ma_motor_valid(&staged)||staged.current_limit>1.1f||staged.trip_current>1.35f)return 0;
    model=staged;qualification=(uint8_t)index;profile_ready=1;stage_mask=0;
    ma_reset(&observer,&controller);return 1;
  }
  if(op==3&&index>=MA_VF&&index<=MA_ADAPTIVE&&raw==0){
    /* Selection while OFF is legal even before qualification; START will reject.
     * This is a configuration action and never implicitly starts/restarts. */
    selected=(uint8_t)index;ma_reset(&observer,&controller);return 1;
  }
  return 0;
}
void ma_native_service(void){
  const uint32_t now=DWT->CYCCNT;
  if(!LL_TIM_IsEnabledAllOutputs(TIM1)){
    running=0;return;
  }
  if(selected==MA_VF)return;
  if((uint32_t)(now-estimate_cycles)<SystemCoreClock/1000U)return;
  ma_current_sample sample;
  if(!mic_current_fast(&sample)||!sample.valid||!sample.zero)return;
  /* Snapshot completed voltage accumulator without blocking the PWM interrupt.
   * A torn snapshot is retried on a later service turn, never spun on in IRQ. */
  uint32_t seq=telemetry_seq,stamp=bin_cycles;float va=bin_va,vb=bin_vb;
  __DMB();if(seq!=telemetry_seq||(seq&1)||stamp==estimate_cycles)return;
  const float dt=(float)(stamp-estimate_cycles)/SystemCoreClock;
  if(dt<.0001f)return;
  if(dt>.002f){ma_fail(MA_STALE);return;}
  uint32_t begin=DWT->CYCCNT;
  int fault=ma_observe(&observer,&model,ma_amps(sample.counts[0]),
    (ma_amps(sample.counts[0])+2.f*ma_amps(sample.counts[1]))*.5773502692f,va,vb,dt);
  uint32_t cycles=DWT->CYCCNT-begin;if(cycles>max_observer_cycles)max_observer_cycles=cycles;
  if(fault){ma_fail((unsigned)fault);return;}
  ++estimate_seq;__DMB();for(unsigned i=0;i<6;i++)estimate[i]=observer.x[i];
  estimate_cycles=stamp;__DMB();++estimate_seq;
}
uint16_t ma_native_fast(float reference_hz){
  const uint32_t begin=DWT->CYCCNT;
  if(selected==MA_VF)return MC_NO_ERROR;
  if(!profile_ready||qualification!=7)return MC_SW_ERROR;
  if(run_fault)return MC_SW_ERROR;
  if(!running){
    /* Main resets model state on STOP. Initial neutral vector only primes the
     * real ADC pipeline, bounded to 2 ms; no synthetic sample substitutes for it. */
    running=1;estimate_cycles=begin;start_cycles=begin;
  }
  ma_current_sample sample;int got=mic_current_fast(&sample);
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
    ma_fail(MA_STALE);return MC_SW_ERROR;
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
    ma_fail((unsigned)(fault?fault:MA_STALE));return MC_DURATION;
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
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xE4;p[3]=2;
  p[4]=7;p[5]=selected;ma_put(p+6,build);ma_put(p+10,16000);
  p[14]=qualification;p[15]=profile_ready;p[16]=first_fault;p[18]=1;
  p[17]=(uint8_t)(running&&profile_ready&&qualification==7&&observer.steps>=500&&
    !run_fault&&hypotf(observer.x[2],observer.x[3])>model.flux*.5f&&observer.nis<25);
  ma_put(p+19,max_fast_cycles);ma_put(p+23,max_observer_cycles);
  uint32_t bits;float speed=observer.x[4]*9.549296586f;
  memcpy(&bits,&speed,4);ma_put(p+27,bits);p[31]=running;
  if(profile_ready)ma_put(p+32,uv3_crc32c((const uint8_t*)&model,sizeof(model)));
  uv3_seal(p);
}
