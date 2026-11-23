
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
static uint16_t VBS_GetAvBusVoltage_V(int*){return 320;}
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
static void config(uint8_t*p,unsigned op,unsigned index,uint32_t value){
 memset(p,0,UV3_FRAME);p[4]=8;p[6]=(uint8_t)op;p[7]=(uint8_t)index;
 memcpy(p+8,&value,4);p[12]=1;p[13]=0xA6;
}
int main(){
 assert(fabs(ma_amps(100)-.959358f)<.00001f);
 for(unsigned a=0;a<4;a++)assert(ma_wire_mode(a)==(a==1?3:a==2?6:a==3?7:0));
 for(unsigned mask=0;mask<32;mask++){
   assert(bool(ma_config_allowed(mask&1,mask&2,mask&4,mask&8,mask&16))==((mask&15)==0&&bool(mask&16)));
   assert(bool(ma_config_cancel(mask&1,mask&2,mask&4,mask&8,mask&16))==((mask&15)!=0||!(mask&16)));
 }
 uint8_t command[UV3_FRAME];memset(command,0xFF,sizeof(command));command[2]=3;command[5]=29;
 ma_config_encode(command,1,4,0x12345678);assert(command[2]==3&&command[3]==0&&command[4]==8&&command[5]==29);
 for(unsigned i=14;i<39;i++)assert(!command[i]);
 uint8_t p[UV3_FRAME];ma_native_diag(p,2026102922U);xp_receiver rx={};
 assert(xp_receive(&rx,p,2026102922U,true,10));assert(rx.caps==7&&rx.selected==1&&!rx.profile_ready);
 assert(!xp_fresh(&rx,true,2510));assert(!xp_receive(&rx,p,2026102912U,true,12));
 for(unsigned i=0;i<UV3_FRAME;i++){p[i]^=1;assert(!xp_receive(&rx,p,2026102922U,true,12));p[i]^=1;}
 config(p,3,2,0);assert(ma_native_config(p));assert(ma_native_selected()==2);
 assert(!ma_native_request(2));assert(ma_native_fast(5)==MC_SW_ERROR&&timer.CCR1==100);
 config(p,1,13,0);assert(!ma_native_config(p));
 ma_motor m={12.23f,10,.9f,.9f,.84f,.0003f,.00015f,1,.35f,1.1f,1.35f,400,12};
 for(unsigned i=0;i<13;i++){uint32_t v;memcpy(&v,(uint8_t*)&m+4*i,4);config(p,1,i,v);assert(ma_native_config(p));}
 config(p,2,0,123);assert(!ma_native_config(p));
 config(p,2,0,uv3_crc32c((uint8_t*)&m,sizeof(m)));assert(ma_native_config(p));assert(!ma_native_request(2));
 // Qualification=7 here is a HOST FIXTURE assertion, not hardware evidence.
 for(unsigned i=0;i<13;i++){uint32_t v;memcpy(&v,(uint8_t*)&m+4*i,4);config(p,1,i,v);assert(ma_native_config(p));}
 config(p,2,7,uv3_crc32c((uint8_t*)&m,sizeof(m)));assert(ma_native_config(p));
 assert(ma_native_request(2));assert(ma_native_prepare());
 timer.BDTR=1;sample.zero=1;sample.valid=0;sample.cycles=cycle.CYCCNT;
 assert(ma_native_fast(5)==MC_NO_ERROR&&timer.CCR1==timer.ARR/2);
 assert(!ma_native_request(3));config(p,3,3,0);assert(!ma_native_config(p));
 sample.valid=1;sample.counts[0]=20;sample.counts[1]=-10;cycle.CYCCNT+=10625;sample.cycles=cycle.CYCCNT;
 assert(ma_native_fast(5)==MC_NO_ERROR);
 estimate_seq|=1;sample_coherent=0;cycle.CYCCNT+=10625;
 assert(ma_native_fast(5)==MC_NO_ERROR); // preempted writers never cause a spin or false fault
 estimate_seq++;sample_coherent=1;
 const auto ccr=timer.CCR1;
 cycle.CYCCNT+=1700000;assert(ma_native_fast(5)!=MC_NO_ERROR&&timer.CCR1==ccr);
 assert(first_fault==MA_STALE);timer.BDTR=0;ma_native_service();assert(ma_native_prepare());
 assert(first_fault==MA_STALE&&run_fault==0); // retain first failure across reset of controller state
 motor_state=1;assert(!ma_native_prepare());motor_state=IDLE;
 ma_native_diag(p,2026102922U);assert(xp_receive(&rx,p,2026102922U,true,50));
 assert(rx.profile_crc==uv3_crc32c((uint8_t*)&m,sizeof(m)));
}
