#include "C:/mic_practice/artifacts/live_bench_20261122/foc_handover_feedback_filter_sweep_r2/IIR_0.0625/nucleo/Inc/motor_control.h"
#include "observer_start_history.h"
#define PAIR_NOISE_CANDIDATE 1
#include "observer_current_window.h"
#include "observer_forecast.h"
static void mic_current_request_observer_capture(uint32_t,uint32_t,uint32_t){}
#include "irq_breakdown.h"
#include "observer_applied_voltage.h"
#include "observer_trace_core.h"
#include "observer_trace_wire.h"
#include <cstdlib>

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



#include <cstdio>
#include <algorithm>
struct Plant {
  double x[5]={};ma_motor m;double load=0;
  void current(const double*z,double&ia,double&ib)const{
    const double det=(double)m.ls*m.lr-(double)m.lm*m.lm;
    ia=(m.lr*z[0]-m.lm*z[2])/det;ib=(m.lr*z[1]-m.lm*z[3])/det;
  }
  void deriv(const double*z,double va,double vb,double*f)const{
    double ia,ib;current(z,ia,ib);
    const double det=(double)m.ls*m.lr-(double)m.lm*m.lm;
    const double ra=(-m.lm*z[0]+m.ls*z[2])/det,rb=(-m.lm*z[1]+m.ls*z[3])/det;
    f[0]=va-m.rs*ia;f[1]=vb-m.rs*ib;
    f[2]=-m.rr*ra-m.poles*z[4]*z[3];f[3]=-m.rr*rb+m.poles*z[4]*z[2];
    const double torque=1.5*m.poles*(z[0]*ib-z[1]*ia);
    f[4]=(torque-load-m.b*z[4])/m.j;
  }
  void step(double va,double vb,double dt){
    double k[4][5],z[5];deriv(x,va,vb,k[0]);
    for(int i=0;i<5;i++)z[i]=x[i]+dt*.5*k[0][i];deriv(z,va,vb,k[1]);
    for(int i=0;i<5;i++)z[i]=x[i]+dt*.5*k[1][i];deriv(z,va,vb,k[2]);
    for(int i=0;i<5;i++)z[i]=x[i]+dt*k[2][i];deriv(z,va,vb,k[3]);
    for(int i=0;i<5;i++)x[i]+=dt*(k[0][i]+2*k[1][i]+2*k[2][i]+k[3][i])/6;
  }
};
static void host_publication_irq();
static int host_observe(ma_observer*,const ma_motor*,float,float,float,float,float);
#define ma_observe host_observe





static int host_observe_noise(ma_observer*,const ma_motor*,float,float,float,float,float,const ma_noise*);
#define ma_observe_noise host_observe_noise


static float max_prequalification_iq;


static bool force_unavailable;
#define MIC_NATIVE_BUILD 2026112112U
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
/* Only used after the unchanged per-frame fe_profile_allowed/fe_model_exact
 * check. Constant propagation removes repeated motor-parameter divisions;
 * this is the SAME model, not a guessed replacement or cached validation. */
static const ma_motor fe_control_model=FE_ESTIMATED_MOTOR;
static uint16_t stage_mask;
static volatile uint8_t selected=MA_VF,profile_ready=1,qualification=FE_ESTIMATED,running,first_fault,run_fault;
/* Stable pointer ABI for exact offline replay of actual ARM/FMA code.
 * No hardware access, no inlining/cloning to a different hidden ABI. */
__attribute__((noinline,noclone,used)) int mic_observer_noise(uint32_t counts,ma_noise*r){
 return ma_pair_noise(counts,r);
}
__attribute__((noinline,noclone,used)) int mic_observer_step(ma_observer*o,
 const ma_motor*m,const float*input,const ma_noise*noise){
 return ma_observe_noise(o,m,input[0],input[1],input[2],input[3],input[4],noise);
}
static ma_observer observer;
static ma_controller controller;
/* Single foreground writer; highest-priority TIM1 reader cannot be preempted
 * by that writer. Only a complete inactive slot is published, in one store. */
typedef struct {float x[6];uint32_t stamp;uint8_t speed_ready;} ma_estimate_slot;
static ma_estimate_slot estimate_slot[2];
static uint32_t estimate_index;
static volatile uint32_t estimate_cycles;
enum {EP_IDLE=0,EP_COMPUTE=1,EP_COPY=2,EP_COMMITTED=3,EP_ACCOUNTING=4,EP_ABORTED=5};
static volatile uint32_t ma_observer_stage,ma_observer_done_cycles,ma_commit_mark_cycles,ma_input_bin;
static void ma_estimate_reset(uint32_t stamp){
 memset(estimate_slot,0,sizeof(estimate_slot));
 estimate_slot[0].stamp=estimate_slot[1].stamp=stamp;
 __atomic_store_n(&estimate_index,0,__ATOMIC_RELEASE);estimate_cycles=stamp;
 ma_observer_stage=EP_IDLE;ma_observer_done_cycles=ma_commit_mark_cycles=ma_input_bin=0;
}
static int ma_estimate_publish(const float*x,uint32_t stamp,uint8_t speed_ready){
 if(run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return 0;
 unsigned next=__atomic_load_n(&estimate_index,__ATOMIC_RELAXED)^1U;
 ma_observer_stage=EP_COPY;
 for(unsigned i=0;i<6;++i)estimate_slot[next].x[i]=x[i];
 estimate_slot[next].stamp=stamp;
 estimate_slot[next].speed_ready=speed_ready;
 __DMB();if(run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return 0;
 ma_commit_mark_cycles=DWT->CYCCNT;
 __atomic_store_n(&estimate_index,next,__ATOMIC_RELEASE);
 estimate_cycles=stamp;ma_observer_stage=EP_COMMITTED;return 1;
}
static uint32_t ma_estimate_read(float*x,uint8_t*speed_ready){
 unsigned index=__atomic_load_n(&estimate_index,__ATOMIC_ACQUIRE);
 for(unsigned i=0;i<6;++i)x[i]=estimate_slot[index].x[i];
 *speed_ready=force_unavailable?0U:estimate_slot[index].speed_ready;
 return estimate_slot[index].stamp;
}

static volatile uint32_t telemetry_seq,bin_cycles;
static volatile float bin_va,bin_vb;
/* Published by the SAME sequence as voltage and time. Never substitute the
 * newest foreground ADC sample for the endpoint of an older completed bin. */
static ma_current_sample bin_current;
/* Experimental 5Hz profile: supervision of actual commanded dq-axis rate.
 * Measure over 16 observer windows, outside the PWM IRQ. A biased speed
 * estimate can otherwise be plausible at handover and later accelerate the
 * electrical field above the requested band even while NIS remains low. */
typedef struct {float alpha,beta,elapsed,angle_limit;uint8_t count,ready;} ma_field_rate;
static ma_field_rate field_rate;
static void ma_field_rate_update(ma_field_rate *rate,const float*x,float reference,float dt){
 if(!rate->count){
  rate->alpha=x[2];rate->beta=x[3];
  rate->elapsed=rate->angle_limit=0.f;rate->count=1U;return;
 }
 rate->elapsed+=dt;
 rate->angle_limit+=6.2831853072f*(reference+.75f)*dt;
 if(++rate->count<17U)return;
 const float cross=rate->alpha*x[3]-rate->beta*x[2];
 const float dot=rate->alpha*x[2]+rate->beta*x[3];
 const float angle=fabsf(atan2f(cross,dot));
 rate->ready=(uint8_t)(rate->elapsed>.010f&&rate->elapsed<.030f&&angle<=rate->angle_limit);
 rate->alpha=x[2];rate->beta=x[3];
 rate->elapsed=rate->angle_limit=0.f;rate->count=1U;
}
static ow_state observer_window;
static ow_bin bin_window;
static uint32_t observer_center_cycles;
static uint32_t start_cycles;
static ma_current_sample cached_sample;

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
ib_meter mic_foc_irq_detail;
static ib_snapshot ma_irq_begin;
static uint32_t ma_irq_last[21],ma_irq_first[21];
static ft_perf ma_perf;
static uint8_t ma_perf_off=1;
static ft_first_fault ma_first_runtime;
static uint32_t ma_observer_begin;
static volatile uint8_t ma_observer_active;
static void ma_freeze_publication(uint32_t*w){
 unsigned index=__atomic_load_n(&estimate_index,__ATOMIC_ACQUIRE);
 w[0]=1;w[1]=ma_observer_stage;w[2]=ma_observer_done_cycles;w[3]=ma_commit_mark_cycles;
 w[4]=index;w[5]=estimate_slot[0].stamp;w[6]=estimate_slot[1].stamp;
 w[7]=ma_input_bin;w[8]=estimate_cycles;w[9]=ma_perf.steps;
 w[10]=observer.steps;w[11]=bin_cycles;w[12]=telemetry_seq;
 w[13]=__atomic_load_n(&estimate_index,__ATOMIC_ACQUIRE);
}
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
 w[11]=(s?((uint32_t)s->valid|((uint32_t)s->zero<<1)):0)|((uint32_t)running<<2)|((uint32_t)ma_observer_active<<3);
 w[12]=elapsed;w[13]=observer.steps;
 ma_freeze_publication(w+14);
 if(ma_observer_active)ib_delta(&mic_foc_irq_detail,&ma_irq_begin,at,ma_irq_first);
 else memcpy(ma_irq_first,ma_irq_last,sizeof(ma_irq_first));
 __DMB();__atomic_store_n(&ma_first_runtime.state,2,__ATOMIC_RELEASE);
}
/* First regular-ADC safety failure survives STOP/CLEAR and later faults.
 * RCM latches MC_SW_ERROR independently before calling this recorder. */
void ma_native_regular_fault(const uint32_t*words){
 uint32_t expected=0;
 if(!__atomic_compare_exchange_n(&ma_first_runtime.state,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return;
 for(unsigned i=0;i<14;++i)ma_first_runtime.word[i]=words[i];
  ma_freeze_publication(ma_first_runtime.word+14);
  if(ma_observer_active)ib_delta(&mic_foc_irq_detail,&ma_irq_begin,DWT->CYCCNT,ma_irq_first);
  else memcpy(ma_irq_first,ma_irq_last,sizeof(ma_irq_first));
 __DMB();__atomic_store_n(&ma_first_runtime.state,2,__ATOMIC_RELEASE);
}

/* Observational writer in foreground only; no diagnostic DMA/serial during RUN. */
static od_capture observer_trace;
static nh_capture observer_history;
int ma_history_packet(uint8_t*p,int off){return nh_packet(&observer_history,p,off);}
void ma_history_sent(void){nh_sent(&observer_history);}
static volatile float bin_id,bin_iq,bin_idref,bin_iqref,bin_reference;
static volatile uint32_t bin_control_sequence,bin_control_adc_cycles;
static void ma_observer_record(const ma_current_sample*s,uint32_t stamp,uint32_t seq,uint32_t adc,
 float id,float iq,float idref,float iqref,float reference,float va,float vb,float dt,int fault,int published,const ow_bin*w){
 if(observer_trace.frozen||(!fault&&(!running||!LL_TIM_IsEnabledAllOutputs(TIM1))))return;
 od_sample r;
 r.cycles=DWT->CYCCNT;r.steps=observer.steps;
 r.reasons=od_reasons(running,fe_profile_allowed(selected),observer.steps,run_fault||fault,
   hypotf(observer.x[2],observer.x[3]),model.flux,observer.nis);
 r.control_sequence=seq;r.control_adc_cycles=adc;
 r.observer_sequence=s->sequence;r.observer_adc_cycles=s->cycles;r.bin_cycles=stamp;
 r.rpm=observer.x[4]*9.549296586f;r.flux_alpha=observer.x[2];r.flux_beta=observer.x[3];r.nis=observer.nis;
 r.id=id;r.iq=iq;r.id_ref=idref;r.iq_ref=iqref;r.reference_hz=reference;
 r.ia=w->ia;r.ib=w->ib;
 r.observation_cycles=w->center;r.window_first_cycles=w->first;r.window_count=w->count|(w->pair_counts<<8);
 r.forecast_dt=(float)(w->end-w->center)/SystemCoreClock;
 r.va=va;r.vb=vb;r.dt=dt;
 for(unsigned i=0;i<2;++i){r.predicted_i[i]=observer.predicted_i[i];r.innovation[i]=observer.innovation[i];r.innovation_variance[i]=observer.innovation_variance[i];}
 for(unsigned i=0;i<3;++i)r.active_ccr[i]=s->ccr[i];
 r.bus_arr=(uint32_t)s->bus_v|((uint32_t)s->arr<<16);r.observer_fault=(uint32_t)fault;r.published=(uint32_t)published;
 od_push(&observer_trace,&r);
 /* Raw source capture is requested at first replay latch, above publication. */
}
int ma_observer_trace_packet(uint8_t*p,uint32_t build,unsigned page){
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||!observer_trace.frozen||page>=OD_PAGES)return 0;
 if(!observer_trace.sealed){
  observer_trace.blob.header.firmware=build;observer_trace.blob.header.crc=0;
  observer_trace.blob.header.crc=uv3_crc32c((const uint8_t*)&observer_trace.blob,OD_BYTES);
  observer_trace.sealed=1;
 }
 memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=OD_WIRE;p[3]=5;p[4]=1;p[5]=(uint8_t)page;
 p[6]=OD_PAGES;unsigned len=page==OD_PAGES-1U?28U:(unsigned)OD_PAYLOAD;p[7]=(uint8_t)len;
 memcpy(p+8,((const uint8_t*)&observer_trace.blob)+OD_PAYLOAD*page,len);p[38]=1;uv3_seal(p);return 1;
}

void ma_timing_diag(uint8_t*p,uint32_t build,unsigned page){
 uint32_t words[7]={0};page%=9;
 unsigned complete=__atomic_load_n(&ma_first_runtime.state,__ATOMIC_ACQUIRE)==2;
 if(page==0){
  words[0]=ma_perf.wall;words[1]=ma_perf.irq;words[2]=ma_perf.cpu_upper;words[3]=ma_perf.roots;
  words[4]=ma_perf.max_wall;words[5]=ma_perf.max_irq;words[6]=ma_perf.max_cpu;
 }else if(page==1){
  words[0]=ma_perf.queue;words[1]=ma_perf.adc_age;words[2]=ma_perf.result_age;
  words[3]=ma_perf.max_queue;words[4]=ma_perf.max_result;words[5]=ma_perf.steps;words[6]=ma_perf.errors;
 }else if(page<6){if(complete)memcpy(words,ma_first_runtime.word+(page-2)*7,sizeof(words));}
 else memcpy(words,(complete?ma_irq_first:ma_irq_last)+(page-6)*7,sizeof(words));
 memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xE8;p[3]=3;
 p[4]=(uint8_t)page;p[5]=(uint8_t)(complete|(ma_perf_off?2U:0U));ma_put(p+6,build);
 for(unsigned i=0;i<7;++i)ma_put(p+10+4*i,words[i]);
 uv3_seal(p);
}

int ma_native_prepare(void){
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||MC_GetSTMStateMotor1()!=IDLE)return 0;
  if(selected==MA_VF)return 1;
  if(selected==4)return mi_native_prepare();
  if(!fe_profile_allowed(selected))return 0;
  running=0;run_fault=0;fe_trial_done=0;memset(&ma_perf,0,sizeof(ma_perf));
  memset(ma_irq_last,0,sizeof(ma_irq_last));ma_perf_off=0;ma_reset(&observer,&controller);
  memset(&field_rate,0,sizeof(field_rate));
  if(qualification==FE_ESTIMATED&&selected==MA_FOC){
    /* This bounded test starts the unloaded bench motor from rest. The old
     * generic prior allowed hundreds of rpm before a rotating field existed.
     * Use initial uncertainties of 1 rad/s and 5 mN m. The electrical part
     * of x/P, process/measurement noise and NIS tests remain unchanged.
     * nh_begin below records this initial P for exact future replay. */
    observer.p[4][4]=1.0f;
    observer.p[5][5]=0.000025f;
  }
  ma_estimate_reset(DWT->CYCCNT);
  od_begin(&observer_trace,MIC_NATIVE_BUILD);
  nh_begin(&observer_history,&observer,&model,MIC_NATIVE_BUILD,DWT->CYCCNT,od_fpscr());
  bin_id=bin_iq=bin_idref=bin_iqref=bin_reference=0;bin_control_sequence=bin_control_adc_cycles=0;
  ow_reset(&observer_window,estimate_cycles);observer_center_cycles=estimate_cycles;memset(&bin_window,0,sizeof(bin_window));bin_cycles=estimate_cycles;
  memset(&bin_current,0,sizeof(bin_current));
  memset(&cached_sample,0,sizeof(cached_sample));return 1;
}
int ma_native_request(unsigned algorithm){
  if(algorithm<MA_VF||algorithm>4)return 0;
  if(LL_TIM_IsEnabledAllOutputs(TIM1))return algorithm==selected;
  if(algorithm==4)return id_configured&&!id_state.ready&&!id_state.done&&id_profile_cycles>0&&id_profile_cycles<=4800U;
  if(algorithm!=MA_VF&&!fe_profile_allowed(algorithm))return 0;
  if(algorithm!=selected){
    if(MC_GetSTMStateMotor1()!=IDLE)return 0;
    selected=(uint8_t)algorithm;ma_reset(&observer,&controller);
    ma_estimate_reset(DWT->CYCCNT);
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
    od_freeze(&observer_trace,run_fault);
    nh_freeze(&observer_history,&observer,NH_STOP);
    running=0;return;
  }
  if(selected==MA_VF||!running||run_fault)return;
  /* Completed16-sample bins define cadence; service immediately when ready. */
  ma_current_sample sample;
  /* Snapshot completed voltage accumulator without blocking the PWM interrupt.
   * A torn snapshot is retried on a later service turn, never spun on in IRQ. */
  uint32_t seq=telemetry_seq,stamp=bin_cycles;float va=bin_va,vb=bin_vb;
  sample=bin_current;ow_bin window=bin_window;
  float trace_id=bin_id,trace_iq=bin_iq,trace_idref=bin_idref,trace_iqref=bin_iqref,trace_ref=bin_reference;
  uint32_t trace_seq=bin_control_sequence,trace_adc=bin_control_adc_cycles;
  __DMB();if(seq!=telemetry_seq||(seq&1)||stamp==estimate_cycles)return;
  if(!sample.valid||!sample.zero||sample.cycles!=stamp||window.end!=stamp||window.count!=16U)return;
  /* A skipped completed window has lost its voltage history. Do not stretch
     the last1ms input over2ms, even when timestamp jitter falls below2ms. */
  if(window.previous_center!=observer_center_cycles){
    ma_fail_at(MA_STALE,FT_OBSERVER_DT,DWT->CYCCNT,&sample,estimate_cycles,stamp,0);return;}
  const float dt=(float)(window.center-observer_center_cycles)/SystemCoreClock;
  if(dt<.0001f)return;
  if(dt>.002f){ma_fail_at(MA_STALE,FT_OBSERVER_DT,DWT->CYCCNT,&sample,estimate_cycles,stamp,0);return;}
  ft_clock clock_begin=ma_clock_snapshot();ma_observer_begin=clock_begin.now;
  ma_perf.queue=clock_begin.now-stamp;ma_perf.adc_age=clock_begin.now-sample.cycles;
  if(ma_perf.queue>ma_perf.max_queue)ma_perf.max_queue=ma_perf.queue;
  ib_read(&mic_foc_irq_detail,&ma_irq_begin,clock_begin.now);
  ma_observer_active=1;ma_observer_stage=EP_COMPUTE;ma_input_bin=stamp;
  ma_noise noise;
  if(!mic_observer_noise(window.pair_counts,&noise)){
    ma_fail_at(MA_INVALID,FT_OBSERVER,DWT->CYCCNT,&sample,estimate_cycles,stamp,0);return;}
  const float input[5]={window.ia,window.ib,va,vb,dt};
  int replay_staged=od_replay_stage_pairs(&observer_trace,&observer,&model,window.ia,window.ib,va,vb,dt,window.pair_counts);
  const uint32_t history_fpscr=od_fpscr();
  int fault=mic_observer_step(&observer,&model,input,&noise);
  nh_step(&observer_history,&observer,input,window.pair_counts,history_fpscr,fault,window.center,stamp);
  const int replay_was_latched=observer_trace.replay_latched;
  od_replay_commit(&observer_trace,&observer,fault,replay_staged);
  /* The startup journal retains early crossings. Reserve the raw NIS
   * request for the same post-warmup event as the full x/P replay. */
  if(!replay_was_latched&&observer_trace.replay_latched)
    mic_current_request_observer_capture(window.first,window.end,observer.steps);
  /* A numerically successful EKF step can still fail the existing NIS
   * criterion. Latch the usual observer fault before TIM can consume
   * this state. Preserve x/P and the rejected sample for replay. */
  if(!fault&&observer.steps>=500U&&!(observer.nis<25.f)){
    fault=MA_OBSERVER;
    ma_fail(MA_OBSERVER);
    ma_observer_record(&sample,stamp,trace_seq,trace_adc,trace_id,trace_iq,
      trace_idref,trace_iqref,trace_ref,va,vb,dt,fault,0,&window);
  }
  if(!fault&&qualification==FE_ESTIMATED){
    ma_field_rate_update(&field_rate,observer.x,trace_ref,dt);
    if(__atomic_load_n(&controller.preflux,__ATOMIC_RELAXED)==2U&&!field_rate.ready){
      fault=MA_OBSERVER;
      ma_fail(MA_OBSERVER);
      ma_observer_record(&sample,stamp,trace_seq,trace_adc,trace_id,trace_iq,
        trace_idref,trace_iqref,trace_ref,va,vb,dt,fault,0,&window);
    }
  }
  float endpoint_estimate[6];
  if(!fault)fault=ow_forecast(&model,observer.x,window.tail_va,window.tail_vb,
    (float)(stamp-window.center)/SystemCoreClock,endpoint_estimate);
  const uint8_t speed_ready=(uint8_t)(!fault&&observer.steps>=500U&&observer.nis<25.f&&
    hypotf(observer.x[2],observer.x[3])>model.flux*.5f&&
    (qualification!=FE_ESTIMATED||field_rate.ready));
  ma_observer_done_cycles=DWT->CYCCNT;
  /* Publish a successfully calculated state before IRQ/performance bookkeeping.
   * Its age remains anchored to the measured input bin, never to this instant. */
  int published=!fault&&ma_estimate_publish(endpoint_estimate,stamp,speed_ready);
  if(!fault)observer_center_cycles=window.center;
  ma_observer_stage=published?EP_ACCOUNTING:EP_ABORTED;
  ft_clock clock_end=ma_clock_snapshot();ft_measure(&ma_perf,clock_begin,clock_end);
  ib_delta(&mic_foc_irq_detail,&ma_irq_begin,clock_end.now,ma_irq_last);
  ma_observer_active=0;host_publication_irq();
  ma_perf.steps=observer.steps;
  if(ma_perf.wall>max_observer_cycles)max_observer_cycles=ma_perf.wall;
  if(fault){ma_fail_at((unsigned)fault,FT_OBSERVER,clock_end.now,&sample,estimate_cycles,stamp,ma_perf.wall);return;}
  if(!published||run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return;
  ma_perf.result_age=clock_end.now-stamp;
  if(ma_perf.result_age>ma_perf.max_result)ma_perf.max_result=ma_perf.result_age;
  ma_observer_stage=EP_IDLE;
  ma_observer_record(&sample,stamp,trace_seq,trace_adc,trace_id,trace_iq,trace_idref,trace_iqref,trace_ref,va,vb,dt,fault,published,&window);
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
    estimate_slot[__atomic_load_n(&estimate_index,__ATOMIC_RELAXED)].stamp=begin;
    /* Start one coherent voltage/observer epoch after real PWM becomes active.
     * Do not interpret the earlier OFF/prepare timestamp as a completed bin. */
    ++telemetry_seq;__DMB();bin_cycles=begin;bin_va=bin_vb=0;
    ow_reset(&observer_window,estimate_cycles);observer_center_cycles=estimate_cycles;memset(&bin_window,0,sizeof(bin_window));__DMB();++telemetry_seq;
  }
  ma_current_sample sample;int got=mic_current_fast(&sample);
  /* If TIM preempts an ADC publication, use only the preceding coherent REAL
   * sample, bounded by the same age limit. Invalid completed samples still stop. */
  if(got&&sample.valid&&sample.zero)cached_sample=sample;
  else if(!got&&cached_sample.valid){sample=cached_sample;got=1;}
  float x[6];uint8_t speed_ready;uint32_t est_cycles=ma_estimate_read(x,&speed_ready);
  const int coherent=1; /* whole published slot, no odd-sequence fallback */
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
    ma_fail_at(MA_STALE,why,begin,got?&sample:NULL,est_cycles,bin_cycles,0);return MC_SW_ERROR;
  }
  ma_geometry g={TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,112U,240U,
    (uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
  ma_output out;
  float applied_a=0,applied_b=0;
  const float actual_ia=ma_amps(sample.counts[0]);
  const float actual_ib=(actual_ia+2.f*ma_amps(sample.counts[1]))*.5773502692f;
  int voltage_fault=ma_applied_voltage(&g,sample.ccr,sample.arr,sample.bus_v,
    actual_ia,actual_ib,&applied_a,&applied_b);
  /* fe_profile_allowed has just validated the exact calculated model.
   * TIM1 has the highest configurable IRQ priority; no foreground profile write
   * can occur here. Other qualifications retain their own per-frame validation. */
  const int model_ok=qualification==FE_ESTIMATED||ma_motor_valid(&model);
  int fault;
  if(qualification==FE_ESTIMATED){
    fault=ma_control_with_speed_admission(&controller,&fe_control_model,x,&g,selected,ma_amps(sample.counts[0]),
    (ma_amps(sample.counts[0])+2.f*ma_amps(sample.counts[1]))*.5773502692f,
    reference_hz,VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super),1.f/16000U,fresh,&out,model_ok,speed_ready);
  }else{
    fault=ma_control_checked(&controller,&model,x,&g,selected,ma_amps(sample.counts[0]),
    (ma_amps(sample.counts[0])+2.f*ma_amps(sample.counts[1]))*.5773502692f,
    reference_hz,VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super),1.f/16000U,fresh,&out,model_ok);
  }
  if(!fault && voltage_fault)fault=voltage_fault;
  ow_bin completed_window;int window_ready=0;
  /* Raw1.35A check above is never filtered. Include accumulator in deadline. */
  if(!fault){window_ready=ow_push_pair(&observer_window,sample.cycles,SystemCoreClock*3U/16000U,
    actual_ia,actual_ib,applied_a,applied_b,&completed_window,sample.pair);
    if(window_ready<0)fault=MA_STALE;}
  const uint32_t elapsed=DWT->CYCCNT-begin;
  if(elapsed>max_fast_cycles)max_fast_cycles=elapsed;
  /* Publishing too near the ADC epoch deadline is a duration fault, not a late
   * partial update. Preload remains enabled; all three next compares form a set. */
  if(fault||elapsed>SystemCoreClock/16000U/2U){
    ma_fail_at((unsigned)(fault?fault:MA_STALE),fault?FT_CONTROL:FT_FAST_DURATION,
      begin,&sample,est_cycles,bin_cycles,elapsed);return MC_DURATION;
  }
  TIM1->CCR1=out.ccr[0];TIM1->CCR2=out.ccr[1];TIM1->CCR3=out.ccr[2];
  /* ADC context contains ACTIVE compares, not the CCR preload just written.
   * Retain the same dead-time model; do not invent measured terminal voltage. */
  if(window_ready){
    ++telemetry_seq;__DMB();bin_window=completed_window;
    bin_va=completed_window.va;bin_vb=completed_window.vb;
    bin_current=sample;bin_cycles=sample.cycles;
    bin_id=out.id_measured;bin_iq=out.iq_measured;bin_idref=out.id_ref;bin_iqref=out.iq_ref;bin_reference=reference_hz;
    bin_control_sequence=sample.sequence;bin_control_adc_cycles=sample.cycles;
    __DMB();++telemetry_seq;
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
static volatile float fe_applied_a,fe_applied_b;
static ow_state fe_window_seed;
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
 const uint16_t cc[3]={(uint16_t)(fe_test_geometry.arr/2U),(uint16_t)(fe_test_geometry.arr/2U),(uint16_t)(fe_test_geometry.arr/2U)};
 float av,bv;int avrc=ma_applied_voltage(&fe_test_geometry,cc,(uint16_t)fe_test_geometry.arr,
   (uint16_t)fe_test_bus,fe_test_ia,fe_test_ib,&av,&bv);
 fe_applied_a=av;fe_applied_b=bv;
 const int model_ok=fe_model_exact(&model);
 volatile uint8_t speed_ready=(uint8_t)(fe_case&1U);
 fe_rc=avrc?avrc:ma_control_with_speed_admission(&fe_test_controller,&fe_control_model,fe_test_x,&fe_test_geometry,MA_FOC,
   fe_test_ia,fe_test_ib,fe_test_ref,fe_test_bus,1.f/16000U,1,&fe_test_out,model_ok,speed_ready);
 ow_state window_probe=fe_window_seed;ow_bin window_result={0};
 const int wrc=ow_push_pair(&window_probe,16U*10624U,31875U,
   fe_test_ia,fe_test_ib,av,bv,&window_result,(uint8_t)(fe_case%3U));
 if(wrc!=1&&!fe_rc)fe_rc=MA_STALE;
 fe_applied_a=window_result.va;fe_applied_b=window_result.vb;
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
   ft_clock split_begin=ma_clock_snapshot();
   const uint32_t begin=host_profile_clock();
   fe_test_observer.steps=499U;
   const int probe_capture=!observer_trace.blob.header.total&&!observer_trace.frozen&&!observer_trace.replay_latched;
   uint32_t probe_pairs=16U<<(5U*(fe_case%3U));ma_noise noise;
   int good_noise=mic_observer_noise(probe_pairs,&noise);
   int probe_stage=probe_capture?od_replay_stage_pairs(&observer_trace,&fe_test_observer,&model,
      fe_test_ia,fe_test_ib,fe_test_out.va,fe_test_out.vb,.001f,probe_pairs):0;
   const float input[5]={fe_test_ia,fe_test_ib,fe_test_out.va,fe_test_out.vb,.001f};
   int rc=good_noise?mic_observer_step(&fe_test_observer,&model,input,&noise):MA_INVALID;
   /* Exercise the copy's worst branch without changing actual observer NIS,
    * its result, or any qualification/protection threshold. No IRQ reads it. */
   float measured_nis=fe_test_observer.nis;fe_test_observer.nis=25.f;
   od_replay_commit(&observer_trace,&fe_test_observer,rc,probe_stage);
   fe_test_observer.nis=measured_nis;
   ma_field_rate rate_probe={fe_test_x[2],fe_test_x[3],.015f,.50f,16U,0U};
   ma_field_rate_update(&rate_probe,fe_test_observer.x,5.f,.001f);
   if(!rc&&rate_probe.count!=1U)rc=MA_OBSERVER;
   float probe_forecast[6]={0};
   if(!rc)rc=ow_forecast(&model,fe_test_observer.x,fe_test_out.va,fe_test_out.vb,.0005f,probe_forecast);
   fe_applied_a=probe_forecast[0];
   fe_applied_b=rate_probe.ready?1.f:0.f;
   uint32_t cycles=host_profile_clock()-begin;
   if(probe_capture){memset(&observer_trace,0,sizeof(observer_trace));}
   ft_clock split_end=ma_clock_snapshot();ft_measure(&ma_perf,split_begin,split_end);
   ma_perf_off=1;++ma_perf.steps;
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
  ow_reset(&fe_window_seed,0);ow_bin discard;
  for(unsigned n=1;n<16U;++n)(void)ow_push_pair(&fe_window_seed,n*10624U,31875U,
    fe_test_ia,fe_test_ib,0,0,&discard,(uint8_t)(fe_case%3U));
  /* Cover entry, sustained preflux, and dq handover in the OFF budget. */
  /* Include the open-loop and qualified handover branches in OFF DWT.
   * Synthetic inputs only. No output-enable, timer or protection writes. */
  fe_test_controller.preflux=(uint8_t)(fe_n%3U);
  if(!fe_n){fe_test_controller.last_ia=fe_test_ia;fe_test_controller.last_ib=fe_test_ib;}
  fe_test_controller.start_cos=cosf((fe_case%16U)*.3926990817f);
  fe_test_controller.start_sin=sinf((fe_case%16U)*.3926990817f);
  if(fe_test_controller.preflux==1U&&(fe_case&9U)==9U)
    fe_test_x[4]=ma_min2(fe_test_ref,5.f)*6.2831853072f;
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
#undef ma_observe_noise
#undef ma_observe
static Plant plant;
static uint64_t sim_now,next_irq,origin,stop_tick;
static uint32_t wall_cycles=116656,queue_cycles=17000,account_cycles=0;
static unsigned frames,observer_calls,late_n,valid_n,step_before;
static double ramp_delay_s,reference_max,last_iq,peak_hold_speed_error;
static unsigned first_torque_step,handover_step;
static double maximum_plant_rpm;
static const int captured[48][2]={{-3,-2},{0,-8},{-2,-1},{9,10},{10,12},{1,-4},{-8,-3},{-4,-2},{4,4},{6,4},{-10,-5},{7,10},{-2,-2},{2,3},{-5,-4},{2,-5},{9,7},{10,9},{-12,-7},{-6,-10},{-6,2},{-1,-9},{4,3},{4,4},{6,5},{2,6},{-5,-6},{-1,-9},{3,5},{-6,-3},{9,12},{-7,-5},{-2,8},{7,0},{-5,2},{4,4},{-5,2},{-1,0},{-6,0},{10,8},{-8,-6},{2,-6},{-3,-8},{9,4},{1,6},{-4,-6},{-8,-6},{5,-4}};
static double prior_va,prior_vb,handover_delta,voltage_delta_sum;
static unsigned voltage_samples;
static double error_sum,peak_nis,min_flux=100;static int scenario;
static bool observing,sim_stopped;static double peak;
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
static void frame(){
 cycle.CYCCNT=(uint32_t)next_irq;
 double a,b;plant.current(plant.x,a,b);

 float amp=(float)(ADC_REFERENCE_VOLTAGE/(4095.0*RSHUNT*AMPLIFICATION_GAIN));
 unsigned pair=timer.CCR1>=timer.CCR2&&timer.CCR1>=timer.CCR3?2:timer.CCR2>=timer.CCR3?1:0;
 unsigned first=pair==2?1:0,second=pair==0?1:2,third=3-first-second;
 double sensed_phases[3]={a,-.5*a+.8660254037844386*b,-.5*a-.8660254037844386*b};
 sample={};sample.zero=1;sample.valid=frames>0;sample.cycles=cycle.CYCCNT-4000;sample.sequence=++frames;
 double gain=scenario==18?.9:scenario==19?1.1:1.;
 int n0=0,n1=0;
 if(scenario==4){n0=(int)(frames%3)-1;n1=(int)((frames+1)%3)-1;}
 if(scenario==5){n0=(int)(((frames*1103515245U+12345U)>>16)%33)-16;n1=(int)(((frames*1664525U+1013904223U)>>16)%33)-16;}
 if(scenario==16)n0+=8;
 if((scenario==24||scenario==25||scenario==26)&&controller.preflux==2U){
  const unsigned index=(frames-1U)%48U;
  const int gain=scenario==25?2:1;
  n0+=gain*captured[index][0];n1+=gain*captured[index][1];
  if(scenario==26)n1+=2;
 }
 sample.counts[first]=(int16_t)(lround(sensed_phases[first]*gain/amp)+n0);
 sample.counts[second]=(int16_t)(lround(sensed_phases[second]*gain/amp)+n1);
 sample.counts[third]=-sample.counts[first]-sample.counts[second];
 if(scenario==17&&frames==4800U){sample.counts[0]=150;sample.counts[1]=-75;sample.counts[2]=-75;}
 sample.arr=timer.ARR;sample.bus_v=fake_bus;
 sample.ccr[0]=timer.CCR1;sample.ccr[1]=timer.CCR2;sample.ccr[2]=timer.CCR3;
#ifdef PAIR_NOISE_CANDIDATE
 sample.pair=(uint8_t)pair;
#endif
 float reference=(float)fmin(5.,5.*fmax(0.,(next_irq-origin)/170000000.-ramp_delay_s));
 reference_max=fmax(reference_max,reference);
 if(reference==5.f)peak_hold_speed_error=fmax(peak_hold_speed_error,
   fabs(plant.x[4]*9.5492965855-300.));
 int rc=ma_native_fast(reference);
 if(observer.steps<500U)max_prequalification_iq=fmaxf(max_prequalification_iq,fabsf(bin_iqref));
 if(bin_iqref!=0.f&&last_iq==0.&&first_torque_step==0U)first_torque_step=observer.steps;
 last_iq=bin_iqref;
 if(controller.preflux==2U&&!handover_step)handover_step=observer.steps;
 maximum_plant_rpm=fmax(maximum_plant_rpm,plant.x[4]*9.5492965855);
 if(rc||!timer.BDTR){timer.BDTR=0;stop_tick=next_irq-origin;sim_stopped=true;return;}

 double dticks=229.,drop=0.,ron=0.;
 if(scenario>=8&&scenario<=11)drop=(scenario-7)*.5;
 if(scenario==12)dticks+=42.5; // additional0.25us
 if(scenario==13)dticks+=85.;  // additional0.50us
 if(scenario==14)dticks-=42.5;
 if(scenario==15)ron=1.;
 const double iph[3]={a,-.5*a+.8660254037844386*b,-.5*a-.8660254037844386*b};
 const double cc[3]={(double)timer.CCR1,(double)timer.CCR2,(double)timer.CCR3};
 double legs[3];
 for(int i=0;i<3;++i){
  double polarity=std::max(-1.,std::min(1.,iph[i]/.05));
  legs[i]=fake_bus*cc[i]/timer.ARR-(fake_bus*dticks/(2.*timer.ARR)+drop)*polarity-ron*iph[i];
 }
 const double av=(legs[0]+legs[1]+legs[2])/3.;
 const double alpha=legs[0]-av,beta=(legs[1]-legs[2])/sqrt(3.);
 const double jump=hypot(alpha-prior_va,beta-prior_vb);
 if(handover_step&&!handover_delta)handover_delta=jump;
 if(handover_step&&observer.steps<handover_step+120U){
  voltage_delta_sum+=jump*jump;++voltage_samples;
 }
 prior_va=alpha;prior_vb=beta;
 plant.step(alpha,beta,10624./170000000.);
 peak=fmax(peak,hypot(a,b));
}
static void advance(uint64_t target){
 while(next_irq<=target&&!sim_stopped){sim_now=next_irq;frame();next_irq+=10624;}
 sim_now=target;cycle.CYCCNT=(uint32_t)sim_now;
}
static int host_observe(ma_observer*o,const ma_motor*m,float a,float b,float va,float vb,float dt){
 assert(!observing);observing=true;
 int rc=ma_observe(o,m,a,b,va,vb,dt);++observer_calls;
 advance(sim_now+wall_cycles);observing=false;return rc;
}

static int host_observe_noise(ma_observer*o,const ma_motor*m,float a,float b,float va,float vb,float dt,const ma_noise*n){
 assert(!observing);observing=true;int rc=ma_observe_noise(o,m,a,b,va,vb,dt,n);++observer_calls;
 if(!rc&&scenario>=20&&scenario<=22&&o->steps==571U){
  o->nis=scenario==20?27.091480255126953f:scenario==21?25.f:nextafterf(25.f,0.f);
 }
 advance(sim_now+wall_cycles);observing=false;return rc;
}
static void host_publication_irq(){advance(sim_now+account_cycles);}
static void setup(){
 sim_now=origin=1000000;cycle.CYCCNT=(uint32_t)origin;next_irq=origin;
 fe_complete=1;fe_started=1;fe_fault=0;fe_case=64;id_profile_attempted=1;
 selected=MA_FOC;sample={};sample.valid=sample.zero=1;sample_coherent=1;fake_bus=323;
 assert(ma_native_prepare());timer.CCR1=timer.CCR2=timer.CCR3=timer.ARR/2;timer.BDTR=1;plant.m=model;
}
int main(int argc,char**argv){

 if(argc>=3){wall_cycles=(uint32_t)strtoul(argv[1],nullptr,10);queue_cycles=(uint32_t)strtoul(argv[2],nullptr,10);}
 account_cycles=0;
 scenario=argc>=4?atoi(argv[3]):0;
 ramp_delay_s=argc>=6?atof(argv[5]):0.;
 force_unavailable=scenario==23;
 setup();
 if(scenario==1)plant.m.rs*=1.2f;
 if(scenario==2)plant.m.rr*=1.2f;
 if(scenario==3)plant.m.lm*=.95f;
 while(!sim_stopped&&sim_now-origin<170000000ULL*6){
  if(running&&bin_cycles!=estimate_cycles){
   uint64_t target=sim_now+(uint32_t)((uint32_t)(bin_cycles+queue_cycles)-(uint32_t)sim_now);
   if((int32_t)((uint32_t)target-(uint32_t)sim_now)<0)target=sim_now;
   advance(target);if(sim_stopped)break;
   step_before=observer.steps;ma_native_service();
   if(observer.steps!=step_before){
     peak_nis=fmax(peak_nis,observer.nis);min_flux=fmin(min_flux,hypot(observer.x[2],observer.x[3]));
     if(running&&!run_fault&&timer.BDTR&&sim_now-origin>=170000000ULL){double e=(observer.x[4]-plant.x[4])*9.5492965855;error_sum+=e*e;++late_n;
       if(od_reasons(running,fe_profile_allowed(selected),observer.steps,run_fault,hypotf(observer.x[2],observer.x[3]),model.flux,observer.nis)==0)++valid_n;}
   }
   if(run_fault){timer.BDTR=0;stop_tick=sim_now-origin;sim_stopped=true;}
  }else advance(next_irq);
 }
 bool completed=fe_trial_done&&!run_fault&&!timer.BDTR;
 unsigned reason=ma_first_runtime.state==2?ma_first_runtime.word[0]:0;

 
 ma_native_service();
 if(observer_trace.frozen){
  od_receiver rx={};uint8_t packet[43];
  for(unsigned page=0;page<OD_PAGES;++page){assert(ma_observer_trace_packet(packet,MIC_NATIVE_BUILD,page));assert(odw_receive(&rx,packet,MIC_NATIVE_BUILD,MIC_NATIVE_BUILD,true));}
  assert(rx.complete);
  const char*path=argc>=5?argv[4]:"C:/mic_practice/artifacts/live_bench_20261116/clear_recovery_r1/model_verification/model_default_trace.bin";FILE*f=fopen(path,"wb");assert(f);assert(fwrite(rx.data,1,OD_BYTES,f)==OD_BYTES);fclose(f);
 }

 printf("{\"completed_5s\":%s,\"PWM_duration_s\":%.9g,\"frames\":%u,\"observer_calls\":%u,\"fault\":%u,\"reason\":%u,\"peak_plant_A\":%.9g,\"rpm_true_end\":%.9g,\"rpm_est_end\":%.9g,\"speed_RMSE_after1s_rpm\":%.9g,\"native_valid_fraction_after1s\":%.9g,\"peak_NIS\":%.9g,\"prequalification_Iq_ref_max_A\":%.9g,\"first_torque_step\":%u,\"maximum_reference_Hz\":%.9g,\"peak_hold_speed_error_rpm\":%.9g,\"handover_step\":%u,\"maximum_plant_rpm\":%.9g,\"handover_voltage_delta_V\":%.9g,\"post_handover_voltage_delta_rms_V\":%.9g}\n",
  completed?"true":"false",stop_tick/170000000.,frames,observer_calls,run_fault,reason,peak,
  plant.x[4]*9.5492965855,observer.x[4]*9.5492965855,late_n?sqrt(error_sum/late_n):0.,late_n?(double)valid_n/late_n:0.,peak_nis,max_prequalification_iq,first_torque_step,reference_max,peak_hold_speed_error,handover_step,maximum_plant_rpm,handover_delta,voltage_samples?sqrt(voltage_delta_sum/voltage_samples):0.);
}
