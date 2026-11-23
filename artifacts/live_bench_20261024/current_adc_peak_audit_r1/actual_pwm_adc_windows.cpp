
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <algorithm>
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

#include "current_core.h"
static bool outside_all_edges(unsigned u,unsigned v,unsigned w,unsigned trigger,
                              unsigned before,unsigned after) {
 for(unsigned c:{u,v,w})if(c+before>=trigger && c<=trigger+after)return false;
 return true;
}
int main() {
 TIM_TypeDef timer; PWM_Handle_t pwm{&timer}; ACIM_VF_Handle_t vf{&pwm};
 const unsigned trigger=5312-384,settle=771,aperture=112;
 FILE *csv=fopen("window_sweep.csv","w");if(!csv)return 2;
 fprintf(csv,"bus_v,field_hz,angles,accepted_pair_windows,unmeasured_compare_in_acquisition,all_edge_guard_rejects,max_ccr\n");
 unsigned total_hazards=0;float first[3]={0,0,0};unsigned example[7]={0};
 unsigned index=0;
 for(float bus:{318.f,320.f,323.f}) {
  vf.fVoutMax_PWM_Mod_V=bus/2;
  for(unsigned fi=0;fi<=500;++fi) {
   vf.fFlux_Freq_Hz=fi*.1f;
   unsigned accepted=0,hazards=0,rejected=0,maximum=0;
   for(unsigned angle=0;angle<3600;++angle) {
    vf.fFlux_Angle_rad=angle*(2*PI/3600);
    if(ACIM_VF_Controller(&vf)!=MC_NO_ERROR)return 3;
    unsigned u=timer.CCR1,v=timer.CCR2,w=timer.CCR3;
    maximum=std::max(maximum,std::max(u,std::max(v,w)));
    unsigned pair=cm_choose_pair(u,v,w);
    bool okay=cm_pair_window(pair,u,v,w,trigger,settle);
    if(!okay)continue;
    ++accepted;
    unsigned excluded=pair==2?u:pair==1?v:w;
    if(excluded>=trigger && excluded<=trigger+aperture) {
     ++hazards;
     if(!example[0]) {
      example[0]=fi;example[1]=angle;example[2]=u;example[3]=v;
      example[4]=w;example[5]=pair;example[6]=(unsigned)bus;
     }
    }
    if(!outside_all_edges(u,v,w,trigger,settle,aperture))++rejected;
   }
   if(hazards && first[index]==0)first[index]=fi*.1f;
   total_hazards+=hazards;
   fprintf(csv,"%.0f,%.1f,3600,%u,%u,%u,%u\n",bus,fi*.1f,accepted,hazards,rejected,maximum);
  }
  ++index;
 }
 fclose(csv);
 if(!total_hazards)return 4;
 // Demonstrate an accepted measurement artifact, not a real motor model.
 // Inject 6 non-clipped raw-ADC outliers into 3200 constant-current samples.
 cm_core state;cm_init(&state);state.zero_ready=1;
 for(unsigned p=0;p<4;++p)state.offset[p]=2068;
 for(unsigned n=0;n<=3200;++n) {
  bool outlier=n>0 && n<=6;
  unsigned a=2068-(outlier?1162:78),b=2068+(outlier?581:39);
  cm_sample(&state,n/16,1,0,a,b,1,0);
 }
 const auto &win=state.published;
 const double scale=3.3/(4095*.04*2.1);
 if(!cm_window_valid(&win) || win.bad || win.flags&CM_CLIP)return 5;
 printf("{\"host_reproduction_passed\":true,\"hardware_commands\":0,"
        "\"first_aperture_collision_hz_at_bus318_320_323\":[%.1f,%.1f,%.1f],"
        "\"example\":{\"field_hz\":%.1f,\"angle_deg\":%.1f,\"ccr\":[%u,%u,%u],\"pair\":%u,\"bus_v\":%u},"
        "\"synthetic_outlier_demo\":{\"assumed_true_u_a\":%.6f,\"published_rms_u_a\":%.6f,"
        "\"published_peak_u_a\":%.6f,\"valid\":true,\"bad\":%u,\"samples\":%u},"
        "\"physical_cause_proven\":false}",
        first[0],first[1],first[2],example[0]*.1,example[1]*.1,
        example[2],example[3],example[4],example[5],example[6],
        78*scale,sqrt((double)win.square[0]/win.n)*scale,win.peak[0]*scale,win.bad,win.n);
}
