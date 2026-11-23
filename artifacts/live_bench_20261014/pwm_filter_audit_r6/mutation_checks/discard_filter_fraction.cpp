
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
uint16_t baseline_PWM_SetPhasePWMOutputs(PWM_Handle_t *pHandle, float fDuty1, float fDuty2, float fDuty3)
{

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
uint16_t baseline_ACIM_VF_Controller(ACIM_VF_Handle_t *pHandle)
{
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
  
  hCodeError = baseline_PWM_SetPhasePWMOutputs(pHandle->pPWM,fdutyA,fdutyB,fdutyC);
  
  return(hCodeError);
    
}
void baseline_PWM_SwitchOffPWM(PWM_Handle_t *pHandle)
{
  /* Main PWM Output Disable */
  pHandle->TIMx->BDTR &= ~((uint32_t)(LL_TIM_OSSI_ENABLE));
  LL_TIM_DisableAllOutputs(pHandle->TIMx);
  
  /* Disable the TIMx Update - it is used as HFT time base to perform the V/F conntrol */ 
  LL_TIM_DisableIT_UPDATE(pHandle->TIMx);
}
__weak uint8_t baseline_TSK_HighFrequencyTask(void)
{
  /* USER CODE BEGIN HighFrequencyTask 0 */

  /* USER CODE END HighFrequencyTask 0 */
  uint16_t returnValue;
  uint8_t bMotorNbr = 0;

  ACIM_VF_CalcAngle(pACIM_VF[M1]);

  /* USER CODE BEGIN HighFrequencyTask SINGLEDRIVE_1 */

  /* USER CODE END HighFrequencyTask SINGLEDRIVE_1 */

  returnValue = baseline_ACIM_VF_Controller(pACIM_VF[M1]);

  if(returnValue == MC_DURATION)
  {
    // Induction motor  V/F
    baseline_PWM_SwitchOffPWM(pwmHandle[M1]);
    MCI_FaultProcessing(&Mci[M1], MC_DURATION, 0);
  }

  /* USER CODE BEGIN HighFrequencyTask SINGLEDRIVE_2 */

  /* USER CODE END HighFrequencyTask SINGLEDRIVE_2 */

  /* USER CODE BEGIN HighFrequencyTask 1 */

  /* USER CODE END HighFrequencyTask 1 */

  GLOBAL_TIMESTAMP++;
  if (0U == MCPA_UART_A.Mark)
  {
    /* Nothing to do */
  }
  else
  {
    MCPA_dataLog (&MCPA_UART_A);
  }

  return (bMotorNbr);
}
uint16_t baseline_RVBS_CheckFaultState(RDivider_Handle_t *pHandle)
{
  uint16_t fault;
  /* If both thresholds are equal, single threshold feature is used */
  if (pHandle->OverVoltageThreshold == pHandle->OverVoltageThresholdLow)
  {
    if (pHandle->_Super.AvBusVoltage_d > pHandle->OverVoltageThreshold)
    {
      fault = MC_OVER_VOLT;
    }
    else if (pHandle->_Super.AvBusVoltage_d < pHandle->UnderVoltageThreshold)
    {
      fault = MC_UNDER_VOLT;
    }
    else
    {
      fault = MC_NO_ERROR;
    }
  }
  else
  {
    /* If both thresholds are different, hysteresis feature is used (Brake mode) */
    if (pHandle->_Super.AvBusVoltage_d < pHandle->UnderVoltageThreshold)
    {
      fault = MC_UNDER_VOLT;
    }
    else if ( false == pHandle->OverVoltageHysteresisUpDir )
    {
      if (pHandle->_Super.AvBusVoltage_d < pHandle->OverVoltageThresholdLow)
      {
        pHandle->OverVoltageHysteresisUpDir = true;
        fault = MC_NO_ERROR;
      }
      else{
        fault = MC_OVER_VOLT;
      }
    }
    else
    {
      if (pHandle->_Super.AvBusVoltage_d > pHandle->OverVoltageThreshold)
      {
        pHandle->OverVoltageHysteresisUpDir = false;
        fault = MC_OVER_VOLT;
      }
      else{
        fault = MC_NO_ERROR;
      }
    }
  }
  return (fault);
}
__weak uint16_t baseline_RVBS_CalcAvVbus(RDivider_Handle_t *pHandle, uint16_t rawValue)
{
  uint16_t tempValue = 0U;
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  if (MC_NULL == pHandle)
  {
    /* Nothing to do. */
  }
  else
  {
#endif
    uint16_t hAux = rawValue;

    if (0xFFFFU == hAux)
    {
      /* Nothing to do */
    }
    else
    {
      pHandle->_Super.AvBusVoltage_d += (hAux - pHandle->_Super.AvBusVoltage_d) >> 8U;
      pHandle->_Super.FaultState = baseline_RVBS_CheckFaultState(pHandle);
      tempValue = pHandle->_Super.FaultState;
    }
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  }
#endif
  return (tempValue);
}
__weak void baseline_RVBS_Init(RDivider_Handle_t *pHandle)
{
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  if (MC_NULL == pHandle)
  {
    /* Nothing to do */
  }
  else
  {
#endif
    pHandle->_Super.AvBusVoltage_d = (pHandle->OverVoltageThreshold + pHandle->UnderVoltageThreshold) / 2U;
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  }
#endif
}
uint16_t candidate_PWM_SetPhasePWMOutputs(PWM_Handle_t *pHandle, float fDuty1, float fDuty2, float fDuty3)
{
  /* Reject the whole update before conversion or any CCR publication. */
  if (!isfinite(fDuty1) || !isfinite(fDuty2) || !isfinite(fDuty3) ||
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
uint16_t candidate_ACIM_VF_Controller(ACIM_VF_Handle_t *pHandle)
{
  /* A zero/invalid normalizer must never reach duty conversion. */
  if (!isfinite(pHandle->fVoutMax_PWM_Mod_V) || !(pHandle->fVoutMax_PWM_Mod_V > 0.0f) ||
      !isfinite(pHandle->fFlux_Freq_Hz) || !isfinite(pHandle->fFlux_Angle_rad) ||
      !isfinite(pHandle->fFlux_K) || pHandle->fFlux_K < 0.0f ||
      !isfinite(pHandle->fMinFreq_TH_Hz) || pHandle->fMinFreq_TH_Hz < 0.0f ||
      !isfinite(pHandle->fVoltage_Offset) || pHandle->fVoltage_Offset < 0.0f ||
      !isfinite(pHandle->fNominalPhaseVoltagePeak_V) || !(pHandle->fNominalPhaseVoltagePeak_V > 0.0f))
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
  
  hCodeError = candidate_PWM_SetPhasePWMOutputs(pHandle->pPWM,fdutyA,fdutyB,fdutyC);
  
  return(hCodeError);
    
}
void candidate_PWM_SwitchOffPWM(PWM_Handle_t *pHandle)
{
  /* Main PWM Output Disable */
  pHandle->TIMx->BDTR &= ~((uint32_t)(LL_TIM_OSSI_ENABLE));
  LL_TIM_DisableAllOutputs(pHandle->TIMx);
  
  /* Disable the TIMx Update - it is used as HFT time base to perform the V/F conntrol */ 
  LL_TIM_DisableIT_UPDATE(pHandle->TIMx);
}
__weak uint8_t candidate_TSK_HighFrequencyTask(void)
{
  /* USER CODE BEGIN HighFrequencyTask 0 */

  /* USER CODE END HighFrequencyTask 0 */
  uint16_t returnValue;
  uint8_t bMotorNbr = 0;

  ACIM_VF_CalcAngle(pACIM_VF[M1]);

  /* USER CODE BEGIN HighFrequencyTask SINGLEDRIVE_1 */

  /* USER CODE END HighFrequencyTask SINGLEDRIVE_1 */

  returnValue = candidate_ACIM_VF_Controller(pACIM_VF[M1]);

  if(returnValue != MC_NO_ERROR)
  {
    // Induction motor  V/F
    candidate_PWM_SwitchOffPWM(pwmHandle[M1]);
    MCI_FaultProcessing(&Mci[M1], returnValue, 0);
  }

  /* USER CODE BEGIN HighFrequencyTask SINGLEDRIVE_2 */

  /* USER CODE END HighFrequencyTask SINGLEDRIVE_2 */

  /* USER CODE BEGIN HighFrequencyTask 1 */

  /* USER CODE END HighFrequencyTask 1 */

  GLOBAL_TIMESTAMP++;
  if (0U == MCPA_UART_A.Mark)
  {
    /* Nothing to do */
  }
  else
  {
    MCPA_dataLog (&MCPA_UART_A);
  }

  return (bMotorNbr);
}
uint16_t candidate_RVBS_CheckFaultState(RDivider_Handle_t *pHandle)
{
  uint16_t fault;
  /* If both thresholds are equal, single threshold feature is used */
  if (pHandle->OverVoltageThreshold == pHandle->OverVoltageThresholdLow)
  {
    if (pHandle->_Super.AvBusVoltage_d > pHandle->OverVoltageThreshold)
    {
      fault = MC_OVER_VOLT;
    }
    else if (pHandle->_Super.AvBusVoltage_d < pHandle->UnderVoltageThreshold)
    {
      fault = MC_UNDER_VOLT;
    }
    else
    {
      fault = MC_NO_ERROR;
    }
  }
  else
  {
    /* If both thresholds are different, hysteresis feature is used (Brake mode) */
    if (pHandle->_Super.AvBusVoltage_d < pHandle->UnderVoltageThreshold)
    {
      fault = MC_UNDER_VOLT;
    }
    else if ( false == pHandle->OverVoltageHysteresisUpDir )
    {
      if (pHandle->_Super.AvBusVoltage_d < pHandle->OverVoltageThresholdLow)
      {
        pHandle->OverVoltageHysteresisUpDir = true;
        fault = MC_NO_ERROR;
      }
      else{
        fault = MC_OVER_VOLT;
      }
    }
    else
    {
      if (pHandle->_Super.AvBusVoltage_d > pHandle->OverVoltageThreshold)
      {
        pHandle->OverVoltageHysteresisUpDir = false;
        fault = MC_OVER_VOLT;
      }
      else{
        fault = MC_NO_ERROR;
      }
    }
  }
  return (fault);
}
__weak uint16_t candidate_RVBS_CalcAvVbus(RDivider_Handle_t *pHandle, uint16_t rawValue)
{
  uint16_t tempValue = 0U;
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  if (MC_NULL == pHandle)
  {
    /* Nothing to do. */
  }
  else
  {
#endif
    uint16_t hAux = rawValue;

    if (0xFFFFU == hAux)
    {
      /* No new ADC result: do not erase a previously measured voltage fault. */
      tempValue = pHandle->_Super.FaultState;
    }
    else
    {
      pHandle->_Super.AvBusVoltage_d += (hAux - pHandle->_Super.AvBusVoltage_d) >> 8U;
      pHandle->_Super.FaultState = candidate_RVBS_CheckFaultState(pHandle);
      tempValue = pHandle->_Super.FaultState;
    }
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  }
#endif
  return (tempValue);
}
__weak void candidate_RVBS_Init(RDivider_Handle_t *pHandle)
{
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  if (MC_NULL == pHandle)
  {
    /* Nothing to do */
  }
  else
  {
#endif
    pHandle->_Super.AvBusVoltage_d = (pHandle->OverVoltageThreshold + pHandle->UnderVoltageThreshold) / 2U;
    pHandle->FilterRemainder = 0;
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  }
#endif
}

int main(){
 TIM_TypeDef t; PWM_Handle_t p{&t}; ACIM_VF_Handle_t h{&p};
 unsigned comparisons=0,invalid_cases=0;
 // Use the production lookup table and controller, including reverse rotation.
 for(float bus:{125.f,250.f,325.f,360.f,385.f})
  for(float hz:{-60.f,-10.f,-5.f,0.f,5.f,9.99f,10.f,50.f,60.f})
   for(unsigned k=0;k<2048;++k){
    h.fVoutMax_PWM_Mod_V=bus/2;h.fFlux_Freq_Hz=hz;
    h.fFlux_Angle_rad=float((hz<0?-1.0:1.0)*double(k)*(2*PI/2048));
    writes=0; auto a=baseline_ACIM_VF_Controller(&h);
    uint32_t c1=t.CCR1,c2=t.CCR2,c3=t.CCR3;
    float d1=p.fDuty1,d2=p.fDuty2,d3=p.fDuty3;
    auto b=candidate_ACIM_VF_Controller(&h);
    if(!(a==b && c1==t.CCR1 && c2==t.CCR2 && c3==t.CCR3)) {
      std::fprintf(stderr,"valid comparison bus=%g hz=%g k=%u angle=%g results=%u/%u duties=%g,%g,%g CCR=%u,%u,%u -> %u,%u,%u\n",
        bus,hz,k,h.fFlux_Angle_rad,a,b,d1,d2,d3,c1,c2,c3,t.CCR1,t.CCR2,t.CCR3);
      return 2;
    }
    assert(d1==p.fDuty1 && d2==p.fDuty2 && d3==p.fDuty3 && writes==6);
    assert(t.CCR1<t.ARR && t.CCR2<t.ARR && t.CCR3<t.ARR);++comparisons;
   }
 // Witness: original accepts a zero normalizer and stores nonfinite duties.
 h=ACIM_VF_Handle_t{&p};h.fVoutMax_PWM_Mod_V=0; writes=0;
 auto zero_result=baseline_ACIM_VF_Controller(&h);
 bool zero_bad=!std::isfinite(p.fDuty1)||!std::isfinite(p.fDuty2)||!std::isfinite(p.fDuty3);
 unsigned zero_writes=writes;
 assert(zero_result==MC_NO_ERROR && zero_bad && zero_writes==3);
 writes=0;assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;
 h=ACIM_VF_Handle_t{&p};
 for(float bad:{-.1f,1.1f,NAN,INFINITY,-INFINITY})for(unsigned phase=0;phase<3;++phase){
  float duty[3]={.5f,.5f,.5f};duty[phase]=bad;writes=0;
  uint32_t a=t.CCR1,b=t.CCR2,c=t.CCR3;
  assert(candidate_PWM_SetPhasePWMOutputs(&p,duty[0],duty[1],duty[2])==MC_SW_ERROR);
  assert(writes==0 && a==t.CCR1 && b==t.CCR2 && c==t.CCR3);++invalid_cases;
 }
 for(uint32_t arr:{0U,1U,65536U}){t.ARR=arr;writes=0;
  assert(candidate_PWM_SetPhasePWMOutputs(&p,.5f,.5f,.5f)==MC_SW_ERROR && writes==0);++invalid_cases;}
 t.ARR=5312;
 for(float norm:{-1.f,NAN,INFINITY}){h=ACIM_VF_Handle_t{&p};h.fVoutMax_PWM_Mod_V=norm;writes=0;
  assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;}
 h=ACIM_VF_Handle_t{&p};h.fFlux_Freq_Hz=NAN;writes=0;
 assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;
 h=ACIM_VF_Handle_t{&p};h.fFlux_Angle_rad=NAN;writes=0;
 assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;
 for(unsigned field=0;field<4;++field)for(float bad:{-1.f,NAN,INFINITY}){
  h=ACIM_VF_Handle_t{&p};
  float *fields[]={&h.fFlux_K,&h.fMinFreq_TH_Hz,&h.fVoltage_Offset,&h.fNominalPhaseVoltagePeak_V};
  *fields[field]=bad;writes=0;
  assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;
 }
 t.update=true;h=ACIM_VF_Handle_t{&p};
 assert(candidate_ACIM_VF_Controller(&h)==MC_DURATION);t.update=false;++invalid_cases;
 pACIM_VF[0]=&h;pwmHandle[0]=&p;
 h=ACIM_VF_Handle_t{&p};h.fVoutMax_PWM_Mod_V=0; t.BDTR=32768;t.update_irq=true;Mci[0].fault=0;writes=0;
 baseline_TSK_HighFrequencyTask();
 assert(t.BDTR==32768 && Mci[0].fault==0 && writes==3);
 t.BDTR=32768;t.update_irq=true;Mci[0].fault=0;writes=0;
 candidate_TSK_HighFrequencyTask();
 assert(!(t.BDTR&32768) && !t.update_irq && Mci[0].fault==MC_SW_ERROR && writes==0);++invalid_cases;
 h=ACIM_VF_Handle_t{&p};t.BDTR=32768;t.update_irq=true;t.update=true;Mci[0].fault=0;
 candidate_TSK_HighFrequencyTask();
 assert(!(t.BDTR&32768) && !t.update_irq && Mci[0].fault==MC_DURATION);t.update=false;++invalid_cases;
 unsigned max_old_lag=0,max_new_lag=0,filter_cases=0;
 for(unsigned code=0;code<4096;++code)for(unsigned init:{0U,65535U}){
  uint16_t raw=uint16_t(code<<4);RDivider_Handle_t a,b;
  a._Super.AvBusVoltage_d=b._Super.AvBusVoltage_d=uint16_t(init);
  for(unsigned n=0;n<4096;++n){
   baseline_RVBS_CalcAvVbus(&a,raw);candidate_RVBS_CalcAvVbus(&b,raw);
   assert(b._Super.AvBusVoltage_d>=std::min(unsigned(raw),init));
   assert(b._Super.AvBusVoltage_d<=std::max(unsigned(raw),init));
   assert(std::abs(b.FilterRemainder)<256);
  }
  unsigned old=std::abs(int(raw)-int(a._Super.AvBusVoltage_d));
  unsigned fixed=std::abs(int(raw)-int(b._Super.AvBusVoltage_d));
  max_old_lag=std::max(max_old_lag,old);max_new_lag=std::max(max_new_lag,fixed);
  assert(fixed==0);
  auto state=b;candidate_RVBS_CalcAvVbus(&b,0xffff);
  assert(b._Super.AvBusVoltage_d==state._Super.AvBusVoltage_d && b.FilterRemainder==state.FilterRemainder);
  ++filter_cases;
 }
 RDivider_Handle_t up,down;unsigned up95=0,down95=0;
 down._Super.AvBusVoltage_d=50000;
 for(unsigned n=1;n<4096;++n){candidate_RVBS_CalcAvVbus(&up,50000);candidate_RVBS_CalcAvVbus(&down,0);
  if(!up95 && up._Super.AvBusVoltage_d>=47500)up95=n;
  if(!down95 && down._Super.AvBusVoltage_d<=2500)down95=n;}
 assert(up95==down95 && up95>=760 && up95<=770);
 unsigned unavailable_fault_cases=0;
 for(uint16_t fault:{uint16_t(0),uint16_t(2),uint16_t(4)}){
  RDivider_Handle_t h;h._Super.FaultState=fault;
  assert(baseline_RVBS_CalcAvVbus(&h,0xffff)==MC_NO_ERROR);
  assert(candidate_RVBS_CalcAvVbus(&h,0xffff)==fault);++unavailable_fault_cases;
 }
 RDivider_Handle_t init;init.FilterRemainder=250;candidate_RVBS_Init(&init);assert(init.FilterRemainder==0);
 // Actual unchanged fault predicate still handles threshold/hysteresis correctly.
 for(unsigned value:{0U,9999U,10000U,30000U,50000U,50001U,65535U}){
  RDivider_Handle_t a,b;a.UnderVoltageThreshold=b.UnderVoltageThreshold=10000;
  a.OverVoltageThreshold=b.OverVoltageThreshold=50000;
  a.OverVoltageThresholdLow=b.OverVoltageThresholdLow=40000;
  a._Super.AvBusVoltage_d=b._Super.AvBusVoltage_d=uint16_t(value);
  assert(baseline_RVBS_CheckFaultState(&a)==candidate_RVBS_CheckFaultState(&b));
  assert(a.OverVoltageHysteresisUpDir==b.OverVoltageHysteresisUpDir);
 }
 std::printf("{\"pass\":true,\"valid_pwm_comparisons\":%u,\"invalid_input_cases\":%u,"
  "\"baseline_zero_normalizer_result\":%u,\"baseline_zero_normalizer_nonfinite_duty\":true,"
  "\"baseline_zero_normalizer_ccr_writes\":%u,\"filter_constant_input_cases\":%u,"
  "\"baseline_max_filter_lag_u16\":%u,\"candidate_max_filter_lag_u16\":%u,"
  "\"candidate_rise_95_samples\":%u,\"candidate_fall_95_samples\":%u,"
  "\"unavailable_adc_fault_preservation_cases\":%u}\n",
  comparisons,invalid_cases,zero_result,zero_writes,filter_cases,max_old_lag,max_new_lag,up95,down95,unavailable_fault_cases);
}
