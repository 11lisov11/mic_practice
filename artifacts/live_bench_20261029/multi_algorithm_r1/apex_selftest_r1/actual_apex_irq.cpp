#include "multi_native.h"
static void __DMB(){}

#include <cstdint>
#include <cstdio>
#include <cstdlib>
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths);
#define CM_ZERO_REPORT(s,mean,var,paths) mic_zero_record((s)->zero_attempts,(s)->zero_stable,(s)->zero_last_bad,mean,(s)->zero_low,(s)->zero_high,var,paths)
#include "current_core.h"
#include "current_adc_window_plan.h"
#include "current_adc_deadline.h"
struct Timer {uint32_t CCR1,CCR2,CCR3,CCR4,CNT,CR1,ARR,BDTR;};
struct Adc {uint32_t JSQR,JDR1,ISR;};
static Timer timer;static Adc adc1,adc2;
#define TIM1 (&timer)
#define ADC1 (&adc1)
#define ADC2 (&adc2)
#define TIM_CR1_DIR 16U
#define ADC_JSQR_JSQ1_Pos 8
#define LL_ADC_INJ_TRIG_EXT_TIM1_TRGO 4U
#define LL_ADC_INJ_TRIG_EXT_RISING 1U
enum {CM_SETTLE_TICKS=771,CM_BEFORE_TOP=128,CM_IDLE_BEFORE_TOP=384,CM_ACQUIRE_TICKS=112};
static uint32_t tick;
static uint16_t bus;
static struct {int _Super;} BusVoltageSensor_M1;
static uint32_t HAL_GetTick(){return tick;}
static void(*bus_hook)();
static uint16_t VBS_GetAvBusVoltage_V(int*){if(bus_hook)bus_hook();return bus;}
static uint32_t LL_TIM_IsEnabledAllOutputs(Timer *t){return t->BDTR&32768;}
static unsigned LL_ADC_IsActiveFlag_JEOS(Adc *a){return a->ISR&1;}
static void LL_ADC_ClearFlag_JEOS(Adc *a){a->ISR&=~1U;}
static unsigned checks;
static void check_at(bool okay,unsigned line){++checks;if(!okay){fprintf(stderr,"IRQ check %u failed at line%u\n",checks,line);exit(1);}}

#define check(value) check_at((value),__LINE__)

static void(*ch4_hook)();static void LL_TIM_OC_SetCompareCH4(Timer*t,uint32_t v){t->CCR4=v;if(ch4_hook)ch4_hook();}
#include <cassert>
#include <cmath>
#include <cstring>
#include <algorithm>
#include <initializer_list>

#include "peak_core.h"
#include "peak_wire.h"
struct Dwt {uint32_t CYCCNT;};static Dwt dwt;
#define DWT (&dwt)
#define ADC_ISR_JQOVF 1024U
static struct Vf {float fFlux_Freq_Hz=40;} vf;
static Vf *pACIM_VF_Component_M1=&vf;
static cm_core state;
typedef struct { uint8_t bytes[15]; } zh_block;
typedef char zh_block_must_be_15[(sizeof(zh_block)==15)?1:-1];
static zh_block zero_history[8];
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths) {
 if(attempt<1 || attempt>8)return;
 uint8_t *b=zero_history[attempt-1U].bytes;
 for(unsigned i=0;i<4;++i){
   b[2*i]=(uint8_t)mean[i];b[2*i+1]=(uint8_t)(mean[i]>>8);
   unsigned span=high[i]-low[i];b[8+i]=(uint8_t)(span>255U?255U:span);
   if(span>255U)paths|=16U<<i;
 }
 b[12]=(uint8_t)((stable&3U)|(rejected<<2));b[13]=(uint8_t)variance_q7;b[14]=(uint8_t)paths;
}
/* Pack only private ISR flags to make room for a full32-bit context epoch.
 * The public cm_core layout and trace wire remain byte-for-byte unchanged. */
static struct {
  uint8_t pair:2,valid:1,active:1,init:1,lost:1;
} adc_flags;
typedef char adc_flags_must_be_one_byte[(sizeof(adc_flags)==1)?1:-1];
#define pending_pair adc_flags.pair
#define pending_valid adc_flags.valid
#define pending_active adc_flags.active
#define initialized adc_flags.init
#define lost_sync adc_flags.lost
static uint32_t pending_epoch;
static uint32_t packets;

static pc_capture peak;
static volatile uint32_t peak_epoch;
static volatile uint16_t peak_active_ccr[4],peak_update_cnt,peak_update_cr1;
static uint8_t peak_sealed;

static volatile ma_current_sample ma_fast_sample;
int mic_current_fast(ma_current_sample*out){
 uint32_t seq=ma_fast_sample.sequence;__DMB();
 out->sequence=seq;out->cycles=ma_fast_sample.cycles;out->epoch=ma_fast_sample.epoch;
 out->valid=ma_fast_sample.valid;out->zero=ma_fast_sample.zero;
 for(unsigned i=0;i<3;i++)out->counts[i]=ma_fast_sample.counts[i];
 __DMB();
 return !(seq&1)&&seq==ma_fast_sample.sequence;
}
static void ma_publish_current(uint32_t cycles,uint32_t epoch,uint8_t eligible,uint16_t a,uint16_t b){
 ++ma_fast_sample.sequence;__DMB();ma_fast_sample.cycles=cycles;ma_fast_sample.epoch=epoch;
 ma_fast_sample.valid=(uint8_t)(eligible&&state.zero_ready&&a>=16&&b>=16&&a<=4079&&b<=4079);
 ma_fast_sample.zero=state.zero_ready;
 for(unsigned i=0;i<3;i++)ma_fast_sample.counts[i]=state.window.last[i];
 __DMB();++ma_fast_sample.sequence;
}

void mic_current_update_epoch(void) {
  peak_active_ccr[0]=(uint16_t)TIM1->CCR1;
  peak_active_ccr[1]=(uint16_t)TIM1->CCR2;
  peak_active_ccr[2]=(uint16_t)TIM1->CCR3;
  peak_active_ccr[3]=(uint16_t)TIM1->CCR4;
  peak_update_cnt=(uint16_t)TIM1->CNT;peak_update_cr1=(uint16_t)TIM1->CR1;
  ++peak_epoch;
}


static void queue_pair(uint8_t pair) {
  const uint32_t trigger=LL_ADC_INJ_TRIG_EXT_TIM1_TRGO|LL_ADC_INJ_TRIG_EXT_RISING;
  ADC1->JSQR=trigger|((uint32_t)(pair==2?7U:1U)<<ADC_JSQR_JSQ1_Pos);
  ADC2->JSQR=trigger|((uint32_t)(pair==0?7U:6U)<<ADC_JSQR_JSQ1_Pos);
  pending_pair=pair;
}

void mic_current_adc_irq(void) {
  if(!initialized || !LL_ADC_IsActiveFlag_JEOS(ADC1))return;
  /* Bind the completed sample to one update epoch BEFORE changing shadows.
   * UPDATE latches all CCRs, then the VF task writes the following cycle.
   * OC4 preload is mandatory: changing a shadow must not create a trigger now. */
  uint32_t epoch0=peak_epoch,cycles0=DWT->CYCCNT;
  uint16_t current_ccr[4];
  for(unsigned i=0;i<4;++i)current_ccr[i]=peak_active_ccr[i];
  uint16_t current_update_cnt=peak_update_cnt,current_update_cr1=peak_update_cr1;
  uint32_t epoch1=peak_epoch;
  uint32_t u=TIM1->CCR1,v=TIM1->CCR2,w=TIM1->CCR3,old_trigger=TIM1->CCR4;
  uint32_t count=TIM1->CNT,direction=TIM1->CR1&TIM_CR1_DIR;
  /* The apex is NOT the update deadline. Check time until bottom UEV. */
  uint8_t early=(uint8_t)mic_adc_publish_in_time(TIM1->ARR,count,direction,old_trigger);
  uint32_t isr1=ADC1->ISR,isr2=ADC2->ISR,jsqr1=0,jsqr2=0;
  /* JQM=1 must be EMPTY after this single injected sequence. */
  jsqr1=ADC1->JSQR;jsqr2=ADC2->JSQR;
  uint8_t both=(uint8_t)LL_ADC_IsActiveFlag_JEOS(ADC2);
  if(!both || ((isr1|isr2)&ADC_ISR_JQOVF) || jsqr1 || jsqr2)lost_sync=1;
  uint16_t a=(uint16_t)(ADC1->JDR1>>4),b=(uint16_t)(ADC2->JDR1>>4);
  LL_ADC_ClearFlag_JEOS(ADC1);LL_ADC_ClearFlag_JEOS(ADC2);
  uint8_t active=(uint8_t)(LL_TIM_IsEnabledAllOutputs(TIM1)!=0);
  uint16_t bus=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  uint8_t captured_pair=pending_pair,valid0=pending_valid,active0=pending_active;
  uint8_t stamp_ok=(uint8_t)(pending_epoch==epoch0);
  uint8_t bottom_ok=(uint8_t)mic_adc_bottom_update(TIM1->ARR,current_update_cnt,current_update_cr1&TIM_CR1_DIR);
  uint8_t context_ok=(uint8_t)(epoch0==epoch1 && epoch1==peak_epoch &&
      current_ccr[3]==old_trigger && stamp_ok && bottom_ok);
  uint8_t geometry_ok=(uint8_t)mic_current_window_safe(captured_pair,
      current_ccr[0],current_ccr[1],current_ccr[2],current_ccr[3],
      CM_SETTLE_TICKS,CM_ACQUIRE_TICKS);
  /* Raw trigger eligibility is deliberately independent of geometry: retain
   * an invalid-window spike as evidence, but NEVER include it in RMS/peak. */
  uint8_t raw_eligible=(uint8_t)(both && !lost_sync && context_ok &&
      active0 && active && state.zero_ready);
  uint8_t eligible=(uint8_t)(raw_eligible && valid0 && geometry_ok);
  uint8_t pair=active?cm_choose_pair(u,v,w):(pending_pair==0?2:0);
  mic_current_window_plan plan=mic_plan_current_window(u,v,w,
      TIM1->ARR-CM_BEFORE_TOP,CM_SETTLE_TICKS,CM_ACQUIRE_TICKS);
  if(!active){plan.trigger=TIM1->ARR-CM_IDLE_BEFORE_TOP;plan.valid=1;}
  else pair=plan.pair;
  /* Even if no safe interval exists, keep ADC heartbeat at the bounded latest
   * point and explicitly invalidate the following measurement. */
  if(!plan.valid)plan.trigger=TIM1->ARR-CM_BEFORE_TOP;
  LL_TIM_OC_SetCompareCH4(TIM1,plan.trigger);
  pending_valid=(uint8_t)(early && plan.valid && bottom_ok && epoch0==peak_epoch);
  pending_active=active;
  pending_epoch=epoch0+1U;
  queue_pair(pair);
  uint16_t queue_cnt=(uint16_t)TIM1->CNT,queue_dir=(uint16_t)(TIM1->CR1&TIM_CR1_DIR);
  uint32_t queue_cycles=DWT->CYCCNT-cycles0;
  if(epoch0!=peak_epoch)pending_valid=0;
  /* Publish next context before zero statistics and diagnostic work. */
  cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,
            bus<=20U && both && !lost_sync && early && !active);
  ma_publish_current(cycles0,epoch0,eligible,a,b);
  /* With MOE off MCSDK may mask UPDATE IRQ. Autonull needs the freshly
   * completed single mux context (JQM empty), not an unserviced UEV stamp.
   * Its500ms settling and unchanged three-block/statistical gates stay in core. */
  if(!peak.frozen && (active || peak.running)) {
    if(queue_cycles>peak.blob.header.reserved)peak.blob.header.reserved=queue_cycles;
    pc_sample sample={0};
    sample.cycles=cycles0;sample.epoch_before=epoch0;sample.epoch_after=epoch1;
    sample.isr1=isr1;sample.isr2=isr2;sample.jsqr1=jsqr1;sample.jsqr2=jsqr2;
    for(unsigned i=0;i<4;++i){sample.active_ccr[i]=current_ccr[i];sample.offset[i]=state.offset[i];}
    sample.update_cnt=current_update_cnt;sample.update_cr1=current_update_cr1;
    sample.preload_ccr[0]=(uint16_t)u;sample.preload_ccr[1]=(uint16_t)v;
    sample.preload_ccr[2]=(uint16_t)w;sample.preload_ccr[3]=(uint16_t)plan.trigger;
    sample.cnt=(uint16_t)count;sample.arr=(uint16_t)TIM1->ARR;sample.cr1=(uint16_t)direction;
    sample.raw[0]=a;sample.raw[1]=b;sample.pair=captured_pair;sample.next_pair=pair;
    sample.cnt_exit=queue_cnt;sample.bus_v=bus;
    sample.reference_deci_hz=(uint16_t)(pACIM_VF_Component_M1->fFlux_Freq_Hz*10.0f);
    uint8_t accepted=(uint8_t)(eligible && a>=16 && b>=16 && a<=4079 && b<=4079);
    sample.flags=(uint16_t)((active?1:0)|(valid0?2:0)|(active0?4:0)|(both?8:0)|
        (lost_sync?16:0)|(early?32:0)|(accepted?64:0)|(!context_ok?128:0)|
        (((isr1|isr2)&ADC_ISR_JQOVF)?256:0)|(queue_dir?512:0)|
        (!geometry_ok?1024:0)|(!early?2048:0)|(!stamp_ok?4096:0)|((jsqr1||jsqr2)?8192:0));
    int32_t ia=(int32_t)state.offset[cm_path1(captured_pair)]-a;
    int32_t ib=(int32_t)state.offset[cm_path2(captured_pair)]-b,ic=-ia-ib;
    uint32_t mag=(uint32_t)(ia<0?-ia:ia),m=(uint32_t)(ib<0?-ib:ib);
    if(m>mag)mag=m;
    m=(uint32_t)(ic<0?-ic:ic);
    if(m>mag)mag=m;
    pc_push(&peak,&sample,HAL_GetTick(),active,raw_eligible,mag);
  }
}


uint8_t mic_current_peak_packet(uint8_t *packet,uint8_t page,uint32_t build) {
  if(!peak.frozen || LL_TIM_IsEnabledAllOutputs(TIM1) || page>=35)return 0;
  if(!peak_sealed) {
    peak.blob.header.firmware=build;
    peak.blob.header.crc=pc_crc((const uint8_t *)&peak.blob);
    peak_sealed=1;
  }
  memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=0xd8;
  packet[3]=1;packet[4]=1;packet[5]=page;packet[6]=35;
  uint8_t size=page==34?4:30;packet[7]=size;
  memcpy(packet+8,((const uint8_t *)&peak.blob)+page*30U,size);
  packet[38]=1;uv3_seal(packet);return 1;
}namespace production {






using std::isfinite;
#define __weak
#define PI 3.14159265358979323846
#define MC_NO_ERROR 0U
#define MC_NO_FAULTS 0U
#define MC_DURATION 1U
#define MC_OVER_VOLT 2U
#define MC_UNDER_VOLT 4U
#define MC_SW_ERROR 128U
struct TIM_TypeDef {uint32_t ARR=5312,CCR1=0,CCR2=0,CCR3=0,BDTR=32768; bool update=false,update_irq=true;};
struct PWM_Handle_t {TIM_TypeDef *TIMx; float fDuty1=0,fDuty2=0,fDuty3=0; uint16_t hCCR1=0,hCCR2=0,hCCR3=0;};
struct ACIM_VF_Handle_t {PWM_Handle_t *pPWM; float fFlux_Freq_Hz=5,fFlux_Angle_rad=0,
    fMinFreq_TH_Hz=10,fFlux_K=.5717009f,fVoltage_Offset=20,
    fNominalPhaseVoltagePeak_V=127*1.4142f,fVoutMax_PWM_Mod_V=162.5f,VoltageAmpl=0;};
struct BusVoltageSensor_Handle_t {uint16_t ConversionFactor=416,LatestConv=0,AvBusVoltage_d=0,FaultState=0;};
struct RDivider_Handle_t {BusVoltageSensor_Handle_t _Super; uint16_t OverVoltageThreshold=65000,
    OverVoltageThresholdLow=65000; bool OverVoltageHysteresisUpDir=false; uint16_t UnderVoltageThreshold=0;
    int32_t FilterRemainder=0;};
struct fTrig_Components {float fSin,fCos;};
unsigned writes=0;
void LL_TIM_OC_SetCompareCH1(TIM_TypeDef *p,uint16_t v){p->CCR1=v;++writes;}
void LL_TIM_OC_SetCompareCH2(TIM_TypeDef *p,uint16_t v){p->CCR2=v;++writes;}
void LL_TIM_OC_SetCompareCH3(TIM_TypeDef *p,uint16_t v){p->CCR3=v;++writes;}
bool LL_TIM_IsActiveFlag_UPDATE(TIM_TypeDef *p){return p->update;}
#define LL_TIM_OSSI_ENABLE 1024U
#define M1 0
void LL_TIM_DisableAllOutputs(TIM_TypeDef *p){p->BDTR&=~32768U;}
void LL_TIM_DisableIT_UPDATE(TIM_TypeDef *p){p->update_irq=false;}
ACIM_VF_Handle_t *pACIM_VF[1];
PWM_Handle_t *pwmHandle[1];
struct MCI_Mock {unsigned fault=0;}; MCI_Mock Mci[1];
struct {unsigned Mark=0;} MCPA_UART_A;
unsigned GLOBAL_TIMESTAMP=0;
// Model only dispatch here; physical IRQ execution/angle integration are out of scope.
void ACIM_VF_CalcAngle(ACIM_VF_Handle_t *){}
void MCI_FaultProcessing(MCI_Mock *p,unsigned fault,unsigned){p->fault=fault;}
void MCPA_dataLog(void *){}
static bool mic_float_isfinite(float value)
{
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return (bits & 0x7f800000U) != 0x7f800000U;
}
#define SIN_FLOAT_0_90_TABLE {\
0.000000,0.006133,0.012265,0.018397,0.024529,0.030659,0.036789,0.042917,\
0.049043,0.055167,0.061290,0.067410,0.073527,0.079642,0.085754,0.091862,\
0.097968,0.104069,0.110167,0.116260,0.122349,0.128433,0.134513,0.140587,\
0.146657,0.152720,0.158778,0.164830,0.170876,0.176915,0.182948,0.188974,\
0.194993,0.201004,0.207008,0.213004,0.218992,0.224972,0.230943,0.236906,\
0.242859,0.248804,0.254739,0.260665,0.266581,0.272487,0.278382,0.284267,\
0.290142,0.296005,0.301858,0.307699,0.313528,0.319346,0.325151,0.330945,\
0.336726,0.342494,0.34825,0.353992,0.3597210,0.365436,0.371138,0.376826,\
0.382499,0.388159,0.393803,0.399433,0.405048,0.410647,0.416232,0.421800,\
0.427353,0.432889,0.438409,0.443913,0.449400,0.454870,0.460323,0.465759,\
0.471177,0.476578,0.481960,0.487325,0.492671,0.497998,0.503307,0.508597,\
0.513868,0.519119,0.524351,0.529564,0.534756,0.539928,0.545080,0.550211,\
0.555322,0.560412,0.565480,0.570528,0.575554,0.580558,0.585541,0.590501,\
0.595439,0.600355,0.605249,0.610119,0.614967,0.619791,0.624592,0.629370,\
0.634124,0.638854,0.643560,0.648242,0.652900,0.657533,0.662141,0.666724,\
0.671282,0.675815,0.680323,0.684805,0.689261,0.693691,0.698096,0.702474,\
0.706825,0.711150,0.715448,0.719720,0.723964,0.728181,0.732371,0.736533,\
0.740667,0.744773,0.748852,0.752902,0.756924,0.760918,0.764883,0.768819,\
0.772726,0.776604,0.780453,0.784273,0.788063,0.791824,0.795554,0.799255,\
0.802926,0.806566,0.810176,0.813756,0.817305,0.820824,0.824311,0.827768,\
0.831193,0.834587,0.837950,0.841281,0.844581,0.847848,0.851084,0.854288,\
0.857460,0.860599,0.863706,0.866781,0.869823,0.872832,0.875809,0.878753,\
0.881663,0.884540,0.887384,0.890195,0.892972,0.895716,0.898426,0.901102,\
0.903744,0.906353,0.908927,0.911467,0.913973,0.916444,0.918881,0.921283,\
0.923651,0.925984,0.928282,0.930545,0.932773,0.934966,0.937124,0.939247,\
0.941334,0.943386,0.945403,0.947384,0.949329,0.951239,0.953112,0.954950,\
0.956752,0.958518,0.960248,0.961942,0.963600,0.965221,0.966807,0.968355,\
0.969868,0.971344,0.972783,0.974186,0.975552,0.976881,0.978174,0.979430,\
0.980649,0.981831,0.982977,0.984085,0.985156,0.986190,0.987188,0.988148,\
0.989070,0.989956,0.990804,0.991616,0.992389,0.993126,0.993825,0.994487,\
0.995111,0.995698,0.996248,0.996760,0.997234,0.997671,0.998071,0.998433,\
0.998757,0.999044,0.999293,0.999505,0.999679,0.999816,0.999915,0.999976}
const float fSin_Table[256]=SIN_FLOAT_0_90_TABLE;
fTrig_Components MCM_floatTrig_Functions(float fAngleDeg)
{
  fTrig_Components fSinCos;
  volatile uint32_t SinIndex,CosIndex;
  float fAngleTmp;
  uint8_t bSector=0;

  /* Correction for erroneous angle convention */
  if(fAngleDeg>=360.0f)
  {
   fAngleDeg -= 360.0f;
  }
  else if(fAngleDeg<=0.0f)
  {
    fAngleDeg +=360.0f;
  }

  fAngleTmp =  fAngleDeg;

  if((fAngleTmp>= 0.0f) && (fAngleTmp<=(90.0f)))
  { /* Between 0-90 degrees */
    bSector = 1;
  }
  else if((fAngleTmp> (90.0f)) && (fAngleTmp<=180.0f))
  {/* Between 90-180 degrees */
    bSector = 2;
  }
  else if((fAngleTmp> 180.0f) && (fAngleTmp<=(270.0f)))
  {/* Between 180-270 degrees */
    bSector = 3;
  }
    else if((fAngleTmp> (270.0f)) && (fAngleTmp<=(360.0f)))
  {/* Between 270-360 degrees */
    bSector = 4;
  }

  /*NOTE.
      Sin(Theta) = Cos (90�-Theta)
      Cos(Theta) = Sin (90�-Theta)
  */

  /* Index computation */
  switch(bSector)
  {
  case 1:
    {
      SinIndex =  (uint32_t)((fAngleTmp*1024.0f)/360.0f);
      if(SinIndex>255)
      {
       SinIndex = 255;
      }
      fSinCos.fSin = fSin_Table[(uint8_t)SinIndex];

      CosIndex =  (uint32_t)(((90.0f-fAngleTmp)*1024.0f)/360.0f);

      if(CosIndex>255)
      {
        CosIndex = 255;
      }
      fSinCos.fCos = +fSin_Table[(uint8_t)CosIndex];

    }
    break;
  case 2:
    {
      SinIndex =  (uint32_t)(((180.0f - fAngleTmp)*1024.0f)/360.0f);
      if(SinIndex>255)
      {
        SinIndex = 255;
      }
      fSinCos.fSin = fSin_Table[(uint8_t)SinIndex];

      CosIndex =  (uint32_t)(((90.0f- (180.0f - fAngleTmp))*1024.0f)/360.0f);

      if(CosIndex>255)
      {
        CosIndex = 255;
      }
      fSinCos.fCos = -fSin_Table[(uint8_t)CosIndex];

    }
    break;
  case 3:
    {
      SinIndex =  (uint32_t)(((fAngleTmp-180.0f)*1024.0f)/360.0f);
      if(SinIndex>255)
      {
       SinIndex = 255;
      }
      fSinCos.fSin = -fSin_Table[(uint8_t)SinIndex];

      CosIndex =  (uint32_t)(((90.0f -(fAngleTmp-180.0f))*1024.0f)/360.0f);

      if(CosIndex>255)
      {
        CosIndex = 255;
      }
      fSinCos.fCos = -fSin_Table[(uint8_t)CosIndex];

    }
    break;
  case 4:
    {
      SinIndex =  (uint32_t)(((360.0f - fAngleTmp)*1024.0f)/360.0f);
      if(SinIndex>255)
      {
       SinIndex = 255;
      }
      fSinCos.fSin = -fSin_Table[(uint8_t)SinIndex];

      CosIndex =  (uint32_t)(((90.0f -(360.0f - fAngleTmp))*1024.0f)/360.0f);

      if(CosIndex>255)
      {
        CosIndex = 255;
      }
      fSinCos.fCos = +fSin_Table[(uint8_t)CosIndex];
    }
    break;
  }
  return (fSinCos);
}
uint16_t PWM_SetPhasePWMOutputs(PWM_Handle_t *pHandle, float fDuty1, float fDuty2, float fDuty3)
{
  /* Reject the whole update before conversion or any CCR publication. */
  if (!mic_float_isfinite(fDuty1) || !mic_float_isfinite(fDuty2) || !mic_float_isfinite(fDuty3) ||
      fDuty1 < 0.0f || fDuty1 > 1.0f || fDuty2 < 0.0f || fDuty2 > 1.0f ||
      fDuty3 < 0.0f || fDuty3 > 1.0f || pHandle->TIMx->ARR < 2U ||
      pHandle->TIMx->ARR > 65535U)
  {
    return MC_SW_ERROR;
  }


  uint16_t hAux;
  
  
  uint16_t hCCR1, hCCR2, hCCR3;
  
  /* Timer capture compare register values computation */
  hCCR1 = (uint16_t)(fDuty1*(float)(pHandle->TIMx->ARR-1));
  hCCR2 = (uint16_t)(fDuty2*(float)(pHandle->TIMx->ARR-1));
  hCCR3 = (uint16_t)(fDuty3*(float)(pHandle->TIMx->ARR-1));
  
  
  /* Store */
  pHandle->fDuty1 = fDuty1;
  pHandle->fDuty2 = fDuty2;
  pHandle->fDuty3 = fDuty3;
  
  pHandle->hCCR1 = hCCR1;
  pHandle->hCCR2 = hCCR2;
  pHandle->hCCR3 = hCCR3;
  
  
  LL_TIM_OC_SetCompareCH1 (pHandle->TIMx,hCCR1);
  LL_TIM_OC_SetCompareCH2 (pHandle->TIMx,hCCR2);
  LL_TIM_OC_SetCompareCH3 (pHandle->TIMx,hCCR3);
 

  if (LL_TIM_IsActiveFlag_UPDATE(pHandle->TIMx))
  {
    hAux = MC_DURATION;
  }
  else
  {
    hAux = MC_NO_ERROR;
  }
  
  return hAux;
}
uint16_t ACIM_VF_Controller(ACIM_VF_Handle_t *pHandle)
{
  /* A zero/invalid normalizer must never reach duty conversion. */
  if (!mic_float_isfinite(pHandle->fVoutMax_PWM_Mod_V) || !(pHandle->fVoutMax_PWM_Mod_V > 0.0f) ||
      !mic_float_isfinite(pHandle->fFlux_Freq_Hz) || !mic_float_isfinite(pHandle->fFlux_Angle_rad) ||
      !mic_float_isfinite(pHandle->fFlux_K) || pHandle->fFlux_K < 0.0f ||
      !mic_float_isfinite(pHandle->fMinFreq_TH_Hz) || pHandle->fMinFreq_TH_Hz < 0.0f ||
      !mic_float_isfinite(pHandle->fVoltage_Offset) || pHandle->fVoltage_Offset < 0.0f ||
      !mic_float_isfinite(pHandle->fNominalPhaseVoltagePeak_V) || !(pHandle->fNominalPhaseVoltagePeak_V > 0.0f))
  {
    return MC_SW_ERROR;
  }

  float vas, vbs, vcs;
  float fdutyA, fdutyB, fdutyC;
  
   uint16_t hCodeError;  
  float fFreqHzAbs = pHandle->fFlux_Freq_Hz;
  
  if(fFreqHzAbs<0.0f)
  {
   fFreqHzAbs = -fFreqHzAbs;
  }
  
  /* C1 low-speed envelope: V(0)=0, V(F/2)=configured low-speed
     anchor, V(F)=k*F and dV/df(F)=k. Above F the original linear
     characteristic is unchanged. No DC boost is applied at zero Hz.
     For this drive: F=10 Hz, V(5 Hz)=20 V phase peak. */
  const float slope=2.0f*(float)PI*pHandle->fFlux_K;
  pHandle->VoltageAmpl=2.0f*PI*fFreqHzAbs*pHandle->fFlux_K;
  if(pHandle->fMinFreq_TH_Hz>0.0f && fFreqHzAbs<pHandle->fMinFreq_TH_Hz)
  {
    const float linear_at_join=slope*pHandle->fMinFreq_TH_Hz;
    const float boost=pHandle->fVoltage_Offset-0.5f*linear_at_join;
    if(boost>0.0f)
    {
      /* d[x(1-x)^2]/dx >= -1/3. Reject a profile that could make
         voltage decrease with increasing frequency, before writing CCR. */
      if(!mic_float_isfinite(linear_at_join) || boost>0.375f*linear_at_join)
        return MC_SW_ERROR;
      const float x=fFreqHzAbs/pHandle->fMinFreq_TH_Hz;
      const float tail=1.0f-x;
      pHandle->VoltageAmpl+=8.0f*boost*x*tail*tail;
    }
  }
  if(!mic_float_isfinite(pHandle->VoltageAmpl) || pHandle->VoltageAmpl<0.0f)
    return MC_SW_ERROR;
  
  float fDeg = ((pHandle->fFlux_Angle_rad)*180.0f)/PI;
  
  if(pHandle->VoltageAmpl>pHandle->fNominalPhaseVoltagePeak_V)
  {
   pHandle->VoltageAmpl = pHandle->fNominalPhaseVoltagePeak_V;
  }
  
 
  if(pHandle->VoltageAmpl > pHandle->fVoutMax_PWM_Mod_V)
  {
   pHandle->VoltageAmpl = pHandle->fVoutMax_PWM_Mod_V;
  }
  
  /* Voltage reference generator */ 
  vas = pHandle->VoltageAmpl * MCM_floatTrig_Functions(fDeg).fSin;  
  vbs = pHandle->VoltageAmpl * MCM_floatTrig_Functions(fDeg+240.0f).fSin;
  vcs = pHandle->VoltageAmpl * MCM_floatTrig_Functions(fDeg+120.0f).fSin;
   
  
  /* Normalization between 0 and 1 considering the maximum voltage available
     at the output of inverter using the sin-tri PWM modulation */
  
  fdutyA = ((vas/pHandle->fVoutMax_PWM_Mod_V)+1.0f)/2.0f;
  fdutyB = ((vbs/pHandle->fVoutMax_PWM_Mod_V)+1.0f)/2.0f;
  fdutyC = ((vcs/pHandle->fVoutMax_PWM_Mod_V)+1.0f)/2.0f;
  
  
  float fMax = 1.0f;
  
  if(fdutyA > fMax)
  {
    fdutyA = fMax;
  }
  if(fdutyB > fMax)
  {
    fdutyB = fMax;
  }
  
  if(fdutyC > fMax)
  {
    fdutyC = fMax;
  }
  
  hCodeError = PWM_SetPhasePWMOutputs(pHandle->pPWM,fdutyA,fdutyB,fdutyC);
  
  return(hCodeError);
    
}
}

struct Frame{unsigned ccr[4],next[4],raw[2],cnt,cycles;};static Frame replay[]={
{{601,2684,4673,4928},{622,2655,4688,4928},{2168,1969},5230,4080261577U},
{{622,2655,4688,4928},{637,2626,4709,4928},{2147,1951},5229,4080272200U},
{{637,2626,4709,4928},{660,2583,4723,4928},{2112,1924},5226,4080282821U},
{{660,2583,4723,4928},{683,2554,4743,4928},{2161,1971},5230,4080293449U},
{{683,2554,4743,4928},{699,2511,4757,4928},{2419,2209},5229,4080304072U},
{{699,2511,4757,4928},{723,2482,4776,4928},{1719,1665},5226,4080314693U},
{{723,2482,4776,4928},{740,2439,4788,4928},{2153,1965},5229,4080325320U},
{{740,2439,4788,4928},{765,2410,4806,4928},{2242,1982},5231,4080335946U},
{{765,2410,4806,4928},{783,2367,4823,4928},{2155,1959},5226,4080346565U},
{{783,2367,4823,4928},{809,2338,4834,4928},{2165,1963},5228,4080357191U},
{{809,2338,4834,4928},{827,2296,4850,4928},{2158,1954},5229,4080367816U},
{{827,2296,4850,4928},{855,2267,4861,4928},{2166,1962},5233,4080378444U},
};
struct Saved{unsigned ccr[4],next[4],raw[2],offsets[4],cnt,dir,epoch,cycles,update_cnt,update_dir,flags;};static Saved saved[]={
{{3028,190,4727,4207},{3093,172,4697,4224},{2152,2046},{2067,2067,2067,2069},4542U,0U,9433013U,1432067972U,104U,0U,111U},
{{3093,172,4697,4224},{3141,150,4665,4232},{2160,2053},{2067,2067,2067,2069},4555U,0U,9433014U,1432078609U,105U,0U,111U},
{{3141,150,4665,4232},{3189,134,4633,4240},{2152,2064},{2067,2067,2067,2069},4564U,0U,9433015U,1432089242U,107U,0U,111U},
{{3189,134,4633,4240},{3237,119,4589,4242},{2151,2051},{2067,2067,2067,2069},4574U,0U,9433016U,1432099876U,107U,0U,111U},
{{3237,119,4589,4242},{3284,105,4555,4249},{2151,2061},{2067,2067,2067,2069},4578U,0U,9433017U,1432110504U,103U,0U,111U},
{{3284,105,4555,4249},{3347,92,4520,4263},{2143,2057},{2067,2067,2067,2069},4583U,0U,9433018U,1432121133U,104U,0U,111U},
{{3347,92,4520,4263},{3394,76,4485,4269},{2143,2068},{2067,2067,2067,2069},4595U,0U,9433019U,1432131769U,111U,0U,111U},
{{3394,76,4485,4269},{3441,64,4450,4275},{2143,2066},{2067,2067,2067,2069},4603U,0U,9433020U,1432142401U,103U,0U,111U},
{{3441,64,4450,4275},{3488,54,4401,4274},{2141,2075},{2067,2067,2067,2069},4609U,0U,9433021U,1432153031U,106U,0U,111U},
{{3488,54,4401,4274},{3534,45,4364,4928},{2147,2076},{2067,2067,2067,2069},4609U,0U,9433022U,1432163655U,103U,0U,623U},
{{3534,45,4364,4928},{3595,36,4326,4928},{2148,2075},{2067,2067,2067,2069},5259U,0U,9433023U,1432174929U,103U,0U,1581U},
{{3595,36,4326,4928},{3641,26,4288,4928},{2067,2071},{2067,2067,2067,2069},5263U,0U,9433024U,1432185557U,103U,0U,1580U},
};

static void reset_test(){
 cm_init(&state);state.zero_ready=1;pc_init(&peak);peak_sealed=0;
 for(unsigned i=0;i<4;++i)state.offset[i]=2067;
 lost_sync=0;pending_pair=0;pending_valid=0;pending_active=0;peak_epoch=0;
 initialized=1;bus=320;timer={2656,2656,2656,4928,0,0,5312,32768};
 bus_hook=nullptr;ch4_hook=nullptr;pending_epoch=0;
}
// CCR fields model readable preload registers. 'active' only changes on UEV.
// Writing CH4 while counting MUST leave the current cycle's active CCR alone.
static uint16_t active_ccr[4];
static void update(unsigned u,unsigned v,unsigned w){
 active_ccr[0]=(uint16_t)timer.CCR1;active_ccr[1]=(uint16_t)timer.CCR2;
 active_ccr[2]=(uint16_t)timer.CCR3;active_ccr[3]=(uint16_t)timer.CCR4;
 timer.CNT=110;timer.CR1=0;mic_current_update_epoch();
 timer.CCR1=u;timer.CCR2=v;timer.CCR3=w;
}
static void conversion(unsigned n,int ia=78,int ib=-39,bool second=true){
 tick=1000+n/16;unsigned phase=active_ccr[3]+302;timer.CNT=phase>=5312?10624-phase:phase;timer.CR1=phase>=5312?16:0;dwt.CYCCNT+=10624;adc1.JSQR=adc2.JSQR=0;
 unsigned x=cm_path1(pending_pair),y=cm_path2(pending_pair);
 adc1.JDR1=(state.offset[x]-ia)<<4;adc2.JDR1=(state.offset[y]-ib)<<4;
 adc1.ISR=1;adc2.ISR=second?1:0;
 unsigned power[3]={timer.CCR1,timer.CCR2,timer.CCR3};
 unsigned old_active=active_ccr[3];
 mic_current_adc_irq();
 check(timer.CCR1==power[0] && timer.CCR2==power[1] && timer.CCR3==power[2]);
 check(active_ccr[3]==old_active); // no immediate CH4/trigger change
 check(timer.CCR4<=5184 && timer.CCR4>0);
 check((adc1.JSQR>>8)==(pending_pair==2?7U:1U));
 check((adc2.JSQR>>8)==(pending_pair==0?7U:6U));
}
static void regression_tests(){
 // Independent brute-force interval oracle on a dense small-integer domain.
 for(unsigned u=0;u<=30;u+=2)for(unsigned v=0;v<=30;v+=2)
 for(unsigned w=0;w<=30;w+=2){
  auto plan=mic_plan_current_window(u,v,w,30,5,2);
  unsigned c[3]={u,v,w};unsigned excluded=u>=v&&u>=w?0:v>=w?1:2;
  bool found=false;
  for(unsigned t=1;t<=30;++t){
   bool okay=t>5;
   for(unsigned j=0;j<3;++j){
    if(j!=excluded && (c[j]+5>=t))okay=false;
    if(c[j]+5>=t && c[j]<=t+2)okay=false;
   }
   found|=okay;
   check(mic_current_window_safe(plan.pair,u,v,w,t,5,2)==okay);
  }
  check(bool(plan.valid)==found);
  if(found)check(mic_current_window_safe(plan.pair,u,v,w,plan.trigger,5,2));
 }
 check(!mic_current_window_safe(3,0,0,0,100,5,2));
 check(!mic_current_window_safe(0,0,0,0,0xffffffffU,5,2));
 check(!mic_plan_current_window(5000,5000,5000,4928,771,112).valid);
 // The physical trigger frame must fail the NEW geometry check, while a
 // counterfactual different trigger is safe. It is not a remeasured ADC value.
 FILE *csv=fopen("window_replay.csv","w");check(csv!=nullptr);
 fprintf(csv,"frame,old_trigger,new_trigger,new_pair,u_compare,v_compare,w_compare,old_safe,new_safe,raw1,raw2\n");
 unsigned ordinal=0;
 for(auto &x:replay){
  check(cm_pair_window(0,x.ccr[0],x.ccr[1],x.ccr[2],x.ccr[3],771));
  check(!mic_current_window_safe(0,x.ccr[0],x.ccr[1],x.ccr[2],x.ccr[3],771,112));
  auto plan=mic_plan_current_window(x.ccr[0],x.ccr[1],x.ccr[2],4928,771,112);
  check(plan.valid && plan.trigger!=4928);
  check(mic_current_window_safe(plan.pair,x.ccr[0],x.ccr[1],x.ccr[2],plan.trigger,771,112));
  fprintf(csv,"%u,%u,%u,%u,%u,%u,%u,0,1,%u,%u\n",ordinal++,x.ccr[3],plan.trigger,plan.pair,x.ccr[0],x.ccr[1],x.ccr[2],x.raw[0],x.raw[1]);
 }
 fclose(csv);
 // Replay the ACTUAL raw pairs/CCRs, not a fabricated shifted waveform.
 reset_test();
 for(unsigned n=0;n<12;++n){auto &x=replay[n];
  for(unsigned j=0;j<4;++j)peak_active_ccr[j]=x.ccr[j];
  peak_epoch=n+1;pending_epoch=peak_epoch;adc1.JSQR=adc2.JSQR=0;pending_pair=0;pending_valid=1;pending_active=1;
  timer.CCR1=x.next[0];timer.CCR2=x.next[1];timer.CCR3=x.next[2];timer.CCR4=x.ccr[3];
  timer.CNT=x.cnt;timer.CR1=0;tick=2000;dwt.CYCCNT=x.cycles;
  adc1.ISR=1;adc2.ISR=1;adc1.JDR1=x.raw[0]<<4;adc2.JDR1=x.raw[1]<<4;
  mic_current_adc_irq();
 }
 check(state.window.n==0 && state.window.bad==12);
 check((state.window.flags&CM_TIMING)!=0);
 check(peak.frozen && peak.blob.header.flags==PC_PEAK && peak.blob.header.count==12);
 auto &trigger=peak.blob.samples[peak.blob.header.trigger_slot];
 check(trigger.raw[0]==1719 && trigger.raw[1]==1665);
 check((trigger.flags&1024)!=0 && (trigger.flags&64)==0);
 uint8_t packet[UV3_FRAME];timer.BDTR=0;
 pc_receiver rx{};
 for(int page=34;page>=0;--page){
  check(mic_current_peak_packet(packet,page,CT_PEER_BUILD));
  check(pc_receive(&rx,packet,CT_PEER_BUILD,true,1));
 }
 check(rx.complete && memcmp(rx.data,&peak.blob,1024)==0);
 FILE *f=fopen("replayed_trace.bin","wb");check(f!=nullptr);
 check(fwrite(&peak.blob,1,1024,f)==1024);fclose(f);
 // Cycle pipeline: current sample uses the previously committed tuple;
 // plan for NEXT shadows is not treated as though already active.
 reset_test();
 for(unsigned n=0;n<8000;++n){
  unsigned w=4600+(n%60)*5;
  update(700,2500,w);conversion(n);
  if(n>2)check(mic_current_window_safe(pending_pair,700,2500,w,timer.CCR4,771,112));
 }
 check(cm_window_valid(&state.published) && state.published.bad==0);
 check(state.window.last[0]==78 && state.window.last[1]==-39 && state.window.last[2]==-39);
 // Rotate all three shadows, including changes of reconstructed phase.
 // Encode known currents through the PREVIOUS queued mux tuple.
 reset_test();
 for(unsigned n=0;n<10000;++n){
  unsigned u=500+n%4000,v=500+(n+1333)%4000,w=500+(n+2666)%4000;
  update(u,v,w);
  unsigned captured=pending_pair,valid=pending_valid,active=pending_active;
  bool expected=valid && active && mic_current_window_safe(captured,
      active_ccr[0],active_ccr[1],active_ccr[2],active_ccr[3],771,112);
  int currents[3]={100,-40,-60};
  conversion(n,currents[captured==2?1:0],currents[captured==0?1:2]);
  auto &sample=peak.blob.samples[(peak.write+11)%12];
  check(sample.pair==captured && bool(sample.flags&64)==expected);
  for(unsigned j=0;j<4;++j)check(sample.active_ccr[j]==active_ccr[j]);
  const auto &latest=state.published.end_ms==tick?state.published:state.window;
  if(expected)for(unsigned j=0;j<3;++j)check(latest.last[j]==currents[j]);
 }
 // Genuine large counts in a safe window are preserved, never amplitude-clipped.
 reset_test();
 for(unsigned n=0;n<20;++n){update(2656,2656,2656);conversion(n);}
 update(2656,2656,2656);conversion(20,1162,-581);
 check(peak.triggered && state.window.peak[1]==1162);
 for(unsigned n=21;n<27;++n){update(2656,2656,2656);conversion(n);}
 check(peak.frozen && peak.blob.header.flags==PC_PEAK);
 // Even frozen diagnostic storage must not stop epoch tracking for monitoring.
 unsigned ep=peak_epoch;update(2656,2656,2656);check(peak_epoch==ep+1);
 unsigned old_n=state.window.n;conversion(27);check(state.window.n==old_n+1);
 // Wrong context, missing ADC2, JQ overflow, and no safe window fail closed.
 reset_test();update(2656,2656,2656);conversion(0);
 update(2656,2656,2656);++peak_active_ccr[3];old_n=state.window.n;conversion(1);
 check(state.window.n==old_n && state.window.bad>0);
 reset_test();update(2656,2656,2656);conversion(0);
 update(2656,2656,2656);conversion(1,78,-39,false);check(lost_sync);
 old_n=state.window.n;update(2656,2656,2656);conversion(2);check(state.window.n==old_n);
 reset_test();update(5000,5000,5000);conversion(0);check(!pending_valid);
 update(5000,5000,5000);old_n=state.window.n;conversion(1);check(state.window.n==old_n);
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 bus_hook=[](){++peak_epoch;};old_n=state.window.n;conversion(1);
 check(!pending_valid && state.window.n==old_n);bus_hook=nullptr;
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 timer.CNT=5230;adc1.ISR=1|ADC_ISR_JQOVF;adc2.ISR=1;mic_current_adc_irq();check(lost_sync);
 // Real OFF IRQ path still alternates four ADC paths and completes the same
 // three-block zero sequence at low bus; no power PWM or trace trigger.
 reset_test();state.zero_ready=0;timer.BDTR=0;bus=10;
 for(unsigned n=0;n<10000;++n){update(2656,2656,2656);conversion(n,0,0);}
 check(state.zero_ready && !state.zero_bad && state.zero_stable==3 && state.zero_attempts==3);
 for(unsigned j=0;j<4;++j)check(state.offset[j]==2067 && state.count[j]==256);
 check(!peak.running && !peak.frozen && peak.count==0);
 check(packets==0);
}

static void apex_tests(){
 // Independent whole-period deadline oracle; the apex is not a UEV here.
 for(unsigned phase=0;phase<10624;++phase){
  unsigned cnt=phase>=5312?10624-phase:phase,down=phase>=5312?16:0;
  bool expected=phase>=5184 && 10624-phase>2048;
  check(bool(mic_adc_publish_in_time(5312,cnt,down,5184))==expected);
 }
 check(mic_adc_publish_in_time(5312,5138,16,5184));
 check(!mic_adc_publish_in_time(5312,2048,16,5184));
 check(!mic_adc_publish_in_time(5312,6000,0,5184));
 check(!mic_adc_publish_in_time(0,0,0,0));
 check(!mic_adc_bottom_update(5312,5200,16));
 // OFF calibration must also work when MCSDK masks UIE, as on STOP/fault.
 // Timer/ADC still run; the ADC queue is freshly consumed, but no epoch IRQ.
 reset_test();state.zero_ready=0;timer.BDTR=0;bus=10;
 for(unsigned k=0;k<10000;++k){
  for(unsigned j=0;j<4;++j)active_ccr[j]=j==3?4928:2656;
  timer.CCR1=timer.CCR2=timer.CCR3=2656;timer.CCR4=4928;
  conversion(k,0,0);
 }
 check(state.zero_ready && state.zero_stable==3 && !state.zero_bad);
 // High bus NEVER becomes a zero reference even though power PWM is off.
 reset_test();state.zero_ready=0;timer.BDTR=0;bus=320;
 for(unsigned k=0;k<10000;++k){update(2656,2656,2656);conversion(k,0,0);}
 check(!state.zero_ready && state.zero_attempts==0);
 // A completed context from a different full32-bit update epoch is rejected.
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 --pending_epoch;unsigned n=state.window.n;conversion(1);
 check(state.window.n==n && !lost_sync);
 check(peak.blob.samples[(peak.write+11)%12].flags&4096);
 // An apex UEV (wrong RCR phasing) is not accepted as a bottom update.
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 peak_update_cnt=5200;peak_update_cr1=16;n=state.window.n;conversion(1);
 check(!pending_valid && state.window.n==n);
 // Epoch wrap is defined unsigned arithmetic, not a loss of synchronization.
 reset_test();peak_epoch=0xfffffffeU;pending_epoch=0xffffffffU;
 update(2656,2656,2656);conversion(0);
 update(2656,2656,2656);check(peak_epoch==0);conversion(1);
 check(!lost_sync && (peak.blob.samples[(peak.write+11)%12].flags&64));
 // JQM=1 must have consumed the previous sequence before another is queued.
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 timer.CNT=5138;timer.CR1=16;adc1.ISR=adc2.ISR=1;adc1.JSQR=0x105;adc2.JSQR=0;
 mic_current_adc_irq();check(lost_sync);
 check(peak.blob.samples[(peak.write+11)%12].flags&8192);
 // A preemption causing UEV between CH4 and JSQR publication invalidates NEXT.
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 ch4_hook=[](){++peak_epoch;};conversion(1);check(!pending_valid);ch4_hook=nullptr;
 // Replay the12 measured2508 samples at their ORIGINAL timestamps/CCRs.
 // Do not relabel old rejected raw values as measurements at a new time.
 reset_test();FILE *csv=fopen("saved_window_plans.csv","w");check(csv!=nullptr);
 fprintf(csv,"frame,old_plan_valid,new_plan_valid,old_recorded_trigger,new_planned_trigger,recorded_raw1,recorded_raw2\n");
 unsigned index=0;
 for(auto &x:saved){
  auto a=mic_plan_current_window(x.ccr[0],x.ccr[1],x.ccr[2],4928,771,112);
  auto b=mic_plan_current_window(x.ccr[0],x.ccr[1],x.ccr[2],5184,771,112);
  check(b.valid && mic_current_window_safe(b.pair,x.ccr[0],x.ccr[1],x.ccr[2],b.trigger,771,112));
  fprintf(csv,"%u,%u,%u,%u,%u,%u,%u\n",index++,a.valid,b.valid,x.ccr[3],b.trigger,x.raw[0],x.raw[1]);
  for(unsigned j=0;j<4;++j){peak_active_ccr[j]=x.ccr[j];state.offset[j]=x.offsets[j];}
  peak_epoch=pending_epoch=x.epoch;pending_pair=0;pending_valid=bool(x.flags&2);pending_active=bool(x.flags&4);
  peak_update_cnt=x.update_cnt;peak_update_cr1=x.update_dir;
  timer.CCR1=x.next[0];timer.CCR2=x.next[1];timer.CCR3=x.next[2];timer.CCR4=x.ccr[3];
  timer.CNT=x.cnt;timer.CR1=x.dir;timer.BDTR=(x.flags&1)?32768:0;
  tick=2000;dwt.CYCCNT=x.cycles;vf.fFlux_Freq_Hz=50;
  adc1.JDR1=x.raw[0]<<4;adc2.JDR1=x.raw[1]<<4;adc1.ISR=adc2.ISR=1;adc1.JSQR=adc2.JSQR=0;
  mic_current_adc_irq();
 }
 fclose(csv);
 check(peak.frozen && peak.blob.header.flags==PC_NO_PEAK && peak.blob.header.count==12);
 unsigned accepted=0;
 for(auto &x:peak.blob.samples)accepted+=bool(x.flags&64);
 check(accepted==10); // the2previously unsafe raw frames are STILL rejected
 uint8_t packet[UV3_FRAME];timer.BDTR=0;check(mic_current_peak_packet(packet,0,CT_PEER_BUILD));
 FILE *f=fopen("saved2508_replayed.bin","wb");check(f!=nullptr);
 check(fwrite(&peak.blob,1,1024,f)==1024);fclose(f);
 // Actual production PWM/Vf functions drive the shadow/update model at the
 // requested high frequencies. ADC currents here are explicitly synthetic.
 FILE *rms=fopen("synthetic_rms.csv","w");check(rms!=nullptr);
 fprintf(rms,"field_hz,valid_windows,accepted_samples,total_samples,rms_u_counts,rms_v_counts,rms_w_counts\n");
 for(float hz:{40.f,45.f,50.f}){
  reset_test();vf.fFlux_Freq_Hz=hz;
  production::TIM_TypeDef next_timer;production::PWM_Handle_t pwm{&next_timer};
  production::ACIM_VF_Handle_t controller{&pwm};controller.fVoutMax_PWM_Mod_V=159;controller.fFlux_Freq_Hz=hz;
  unsigned accepted_samples=0,valid_windows=0,previous_end=0;
  for(unsigned k=0;k<16000;++k){
   controller.fFlux_Angle_rad=float(std::fmod((k+1)*hz*10624.0/170000000*(2*PI),2*PI));
   check(production::ACIM_VF_Controller(&controller)==0);
   update(next_timer.CCR1,next_timer.CCR2,next_timer.CCR3);
   double angle=(k*10624.0+active_ccr[3])*hz/170000000*(2*PI)+.4;
   int i[3]={int(std::lround(120*std::sin(angle))),int(std::lround(120*std::sin(angle-2*PI/3))),0};i[2]=-i[0]-i[1];
   unsigned pair=pending_pair;conversion(k,i[pair==2?1:0],i[pair==0?1:2]);
   auto &sample=peak.blob.samples[(peak.write+11)%12];
   if(k>1 && !(sample.flags&64))fprintf(stderr,"model hz=%g k=%u flags=%u ccr=%u,%u,%u,%u pending_epoch=%u epoch=%u\n",hz,k,sample.flags,active_ccr[0],active_ccr[1],active_ccr[2],active_ccr[3],pending_epoch,peak_epoch);
   if(k>1)check(sample.flags&64);
   accepted_samples+=bool(sample.flags&64);
   check(mic_adc_publish_in_time(5312,timer.CNT,timer.CR1&16,active_ccr[3]));
   if(state.published.end_ms!=previous_end){previous_end=state.published.end_ms;
    check(cm_window_valid(&state.published));++valid_windows;
    for(unsigned j=0;j<3;++j){double value=std::sqrt(double(state.published.square[j])/state.published.n);
     check(std::abs(value-120/std::sqrt(2.0))<1.5);}
   }
  }
  check(valid_windows>=4 && accepted_samples>=15998 && !lost_sync);
  fprintf(rms,"%.0f,%u,%u,16000,%.6f,%.6f,%.6f\n",hz,valid_windows,accepted_samples,
      std::sqrt(double(state.published.square[0])/state.published.n),
      std::sqrt(double(state.published.square[1])/state.published.n),
      std::sqrt(double(state.published.square[2])/state.published.n));
 }
 fclose(rms);
}
int main(){regression_tests();apex_tests();
 printf("{\"passed\":true,\"checks\":%u,\"hardware_commands\":0,\"actual_irq\":true,\"post_apex_jeos\":true,\"full_epoch_and_wrap_checks\":true,\"raw_capture_frames_replayed\":24,\"new_currents_are_synthetic\":true}\n",checks);
}
