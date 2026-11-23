#pragma GCC optimize ("O2","no-fast-math")
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

#include "identify_core.h"
#include "identify_wire.h"
#define MIC_NATIVE_BUILD 2026102936U
static mi_state id_state;
static mi_config id_config,id_staged;
static uint16_t id_stage_mask;
static uint8_t id_configured,id_prepared,id_profile_attempted;
static uint32_t id_profile_cycles;
static void mi_native_profile_off(void);
static int mi_native_prepare(void),mi_native_config(const uint8_t*),mi_native_service(void);
static uint16_t mi_native_fast(void);

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
  if(selected==4)return mi_native_prepare();
  if(!profile_ready||qualification!=7)return 0;
  running=0;run_fault=0;ma_reset(&observer,&controller);
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
  if(op>=4)return mi_native_config(f);
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
  if(op==3&&index>=MA_VF&&index<=4&&raw==0){
    /* Selection while OFF is legal even before qualification; START will reject.
     * This is a configuration action and never implicitly starts/restarts. */
    selected=(uint8_t)index;ma_reset(&observer,&controller);return 1;
  }
  return 0;
}
void ma_native_service(void){
  mi_native_profile_off();
  if(mi_native_service())return;
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
  if(selected==4)return mi_native_fast();
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
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xE4;p[3]=3;
  p[4]=15;p[5]=selected;ma_put(p+6,build);ma_put(p+10,16000);
  p[14]=qualification;p[15]=profile_ready;p[16]=first_fault;p[18]=1;
  p[17]=(uint8_t)(running&&profile_ready&&qualification==7&&observer.steps>=500&&
    !run_fault&&hypotf(observer.x[2],observer.x[3])>model.flux*.5f&&observer.nis<25);
  ma_put(p+19,max_fast_cycles);ma_put(p+23,max_observer_cycles);
  uint32_t bits;float speed=observer.x[4]*9.549296586f;
  memcpy(&bits,&speed,4);ma_put(p+27,bits);p[31]=running;
  if(profile_ready)ma_put(p+32,uv3_crc32c((const uint8_t*)&model,sizeof(model)));
  uv3_seal(p);
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
int ma_native_complete(void){return selected==4&&id_state.done;}
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
  p[5]=(id_configured?1:0)|(id_state.active?2:0)|(id_state.ready?4:0)|(id_state.done?8:0);
  id_put(p+6,build);id_put(p+10,id_configured?uv3_crc32c((uint8_t*)&id_config,sizeof(id_config)):0);
  id_put(p+14,id_state.ready?id_state.crc:0);id_put(p+18,id_config.run_id);id_put(p+22,id_config.kind);
  uint32_t raw;memcpy(&raw,&id_config.frequency,4);id_put(p+26,raw);id_put(p+30,id_config.duration_ms);
  id_put(p+34,id_profile_cycles);p[38]=id_state.fault;uv3_seal(p);
}
int ma_id_page(uint8_t*p,uint32_t build,unsigned page){
  if(!id_state.ready||LL_TIM_IsEnabledAllOutputs(TIM1)||page>=MI_PAGES)return 0;
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=ID_PAGE_WIRE;p[3]=1;p[4]=(uint8_t)page;p[5]=MI_PAGES;
  id_put(p+6,build);id_put(p+10,id_state.crc);unsigned offset=24*page,n=MI_BYTES-offset;if(n>24)n=24;
  memcpy(p+14,id_state.bytes+offset,n);uv3_seal(p);return 1;
}

/* One CPU-only timing self-check per native boot, in actual flash, while OFF.
 * Fake inputs stay inside this isolated kernel state and are never published as
 * ADC readings, physical data, or identification results. No IRQ is masked.
 * The existing hardware/current/voltage protections remain in force.
 */
static void mi_native_profile_off(void){
 if(id_profile_attempted||id_configured||id_state.active||id_state.ready||id_state.done||
    LL_TIM_IsEnabledAllOutputs(TIM1)||
    VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)>20U)return;
 ma_current_sample real_sample;
 if(!mic_current_fast(&real_sample)||!real_sample.zero)return;
 id_profile_attempted=1;uint32_t maximum=0;int okay=1;
 ma_geometry g={TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,112U,240U,
  (uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
 for(unsigned k=0;k<8;k++){
  mi_config cfg;memset(&cfg,0,sizeof(cfg));cfg.run_id=k+1;cfg.kind=k<2?MI_DC:MI_AC;
  cfg.axis=(k%3)*2.0943951024f;cfg.amplitude=.3f;cfg.rs=12.23f;cfg.duration_ms=3000;
  cfg.gain=.95f;cfg.knee=.002f;for(unsigned j=0;j<3;j++)cfg.drop[j]=15;cfg.offset[0]=2;cfg.offset[1]=-2;
  if(cfg.kind==MI_AC){cfg.frequency=k<4?1:k<6?50:200;
   cfg.duration_ms=(uint32_t)ceilf(1000*(mi_settle_cycles(&cfg)+5)/cfg.frequency)+1;cfg.calibration_crc=mi_cal_crc(&cfg);}
  memset(&id_state,0,sizeof(id_state));if(!mi_begin(&id_state,&cfg,0)){okay=0;break;}
  id_state.response=cfg.amplitude;ma_output out;
  for(unsigned n=0;n<128;n++){
   const float offset=(k&1)?(cfg.kind==MI_DC?2.6f:(mi_settle_cycles(&cfg)+.1f)/cfg.frequency):.1f;
   mi_sample input;memset(&input,0,sizeof(input));input.valid=1;input.bus=k&1?250:350;input.arr=g.arr;input.epoch=n+1;
   input.cycles=(uint32_t)(offset*SystemCoreClock)+n*(SystemCoreClock/16000U);
   float phase=6.2831853072f*cfg.frequency*input.cycles/SystemCoreClock;
   float current=cfg.kind==MI_DC?cfg.amplitude:cfg.amplitude*sinf(phase);
   input.ia=current*id_state.axis_cos;input.ib=current*id_state.axis_sin;
   for(unsigned j=0;j<3;j++)input.ccr[j]=g.arr/2;
   uint32_t begin=DWT->CYCCNT;
   int rc=mi_step(&id_state,&g,&input,input.cycles+32,SystemCoreClock,&out);
   uint32_t elapsed=DWT->CYCCNT-begin;if(elapsed>maximum)maximum=elapsed;
   if(rc!=MI_OK){okay=0;break;}
  }
  if(!okay)break;
 }
 /* Only temporary synthetic state is discarded; no real record can exist here. */
 memset(&id_state,0,sizeof(id_state));id_prepared=0;
 id_profile_cycles=okay?maximum:UINT32_MAX;
}
