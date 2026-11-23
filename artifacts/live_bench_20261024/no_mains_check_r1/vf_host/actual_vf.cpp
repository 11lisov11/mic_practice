
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <algorithm>
#include <cstring>
#include <cstdlib>
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
  
  if(fFreqHzAbs >= pHandle->fMinFreq_TH_Hz)
  {
    pHandle->VoltageAmpl = 2.0f*PI*fFreqHzAbs * pHandle->fFlux_K;
  }
  else
  {
   pHandle->VoltageAmpl = pHandle->fVoltage_Offset;
  }
  
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

static unsigned checks=0;
static void check(bool v,const char*why){++checks;if(!v){fprintf(stderr,"FAIL %s\n",why);exit(1);}}
int main(){
 TIM_TypeDef t;PWM_Handle_t p{&t};ACIM_VF_Handle_t h{&p};
 unsigned calls=0;float minimum=1,maximum=0;unsigned clipped50=0;
 for(float bus:{250.f,325.f,380.f}){
  h.fVoutMax_PWM_Mod_V=bus/2;
  for(unsigned fi=0;fi<=500;++fi){
   h.fFlux_Freq_Hz=fi*.1f;
   for(unsigned angle=0;angle<720;++angle){
    h.fFlux_Angle_rad=angle*(2*PI/720);writes=0;
    check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"exact controller returns success in0..50Hz sweep");
    check(writes==3,"exact PWM converter publishes exactly three compares");
    for(float d:{p.fDuty1,p.fDuty2,p.fDuty3}){
     check(mic_float_isfinite(d) && d>=0 && d<=1,"all three calculated duties finite and bounded");
     minimum=std::min(minimum,d);maximum=std::max(maximum,d);
    }
    check(t.CCR1<t.ARR && t.CCR2<t.ARR && t.CCR3<t.ARR,"timer compares remain below period");
    ++calls;
   }
  }
  if(h.VoltageAmpl==h.fVoutMax_PWM_Mod_V)++clipped50;
 }
 h=ACIM_VF_Handle_t{&p};h.fFlux_Angle_rad=.7f;
 float before=0,after=0;
 for(float hz:{9.99f,10.f}){
  h.fFlux_Freq_Hz=hz;check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"threshold sample valid");
  if(hz<10)before=h.VoltageAmpl;else after=h.VoltageAmpl;
 }
 check(before==20 && after>35.9f && after<36,"actual installed code reproduces10Hz voltage discontinuity");
 FILE*table=fopen("vf_points.csv","w");check(table,"open output table");
 fprintf(table,"field_hz,phase_peak_v,line_line_rms_equivalent_v,bus_normalizer_v\n");
 for(float hz:{0.f,5.f,9.99f,10.f,15.f,20.f,23.f,25.f,30.f,40.f,50.f}){
  h.fFlux_Freq_Hz=hz;h.fVoutMax_PWM_Mod_V=162.5f;
  check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"table calculation valid");
  fprintf(table,"%.3f,%.6f,%.6f,%.3f\n",hz,h.VoltageAmpl,h.VoltageAmpl*sqrt(1.5),h.fVoutMax_PWM_Mod_V);
 }
 fclose(table);
 for(float bad:{0.f,-1.f,NAN,INFINITY}){
  h=ACIM_VF_Handle_t{&p};h.fVoutMax_PWM_Mod_V=bad;writes=0;
  check(ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0,"invalid bus normalizer cannot publish PWM compares");
 }
 for(float bad:{-.1f,1.1f,NAN,INFINITY}){
  writes=0;check(PWM_SetPhasePWMOutputs(&p,bad,.5f,.5f)==MC_SW_ERROR && writes==0,"invalid duty cannot publish compares");
 }
 printf("{\"passed\":true,\"controller_calls_in_sweep\":%u,\"assertions\":%u,\"minimum_calculated_duty\":%.8f,\"maximum_calculated_duty\":%.8f,\"voltage_peak_below10hz_v\":%.6f,\"voltage_peak_at10hz_v\":%.6f,\"bus_cases_voltage_limited_at50hz\":%u,\"hardware_commands\":0}\n",
        calls,checks,minimum,maximum,before,after,clipped50);
}
