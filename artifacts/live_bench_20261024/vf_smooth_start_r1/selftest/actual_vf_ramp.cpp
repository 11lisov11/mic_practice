
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <algorithm>
#include <cstring>
#include <cstdlib>
using std::isfinite;
#define SPEED_UNIT 10
typedef struct
{
  uint32_t FrequencyHz;             /*!< Execution frequency expressed in Hz */
  int32_t  TargetFinal;             /*!< Backup of hTargetFinal to be applied in the last step. */
  int32_t  Ext;                     /*!< Current state variable multiplied by 32768. */
  uint32_t RampRemainingStep;       /*!< Number of steps remaining to complete the ramp. */
  int32_t  IncDecAmount;            /*!< Increment/decrement amount to be applied to the reference value at each
                                         CalcTorqueReference. */
  uint32_t ScalingFactor;           /*!< Scaling factor between output value and its internal representation. */
} RampExtMngr_Handle_t;

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
enum {VF_OL,VF_CL};struct Motor{uint8_t bPP;};struct Speed{int16_t hAvrMecSpeedUnit;};
struct ACIM_VF_Handle_t {PWM_Handle_t*pPWM;RampExtMngr_Handle_t*pRMNGR=nullptr;Motor*pACIM_MotorParams=nullptr;Speed*SPD_real=nullptr;void*fPI=nullptr;
 int bVF_Mode=VF_OL;int16_t hElAngle=0;float fFlux_Freq_rads=0,fCalcAngleExecTime_s=0,
 fRotorFreqRef_rads=0,fRotorFreqRef_RPM=0,fSlipFrequency_rads=0;
 float fFlux_Freq_Hz=5,fFlux_Angle_rad=0,
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

void MCI_FaultProcessing(MCI_Mock *p,unsigned fault,unsigned){p->fault=fault;}
void MCPA_dataLog(void *){}

float PI_Float_Calc(void*,float){return 0;}
/**
  ******************************************************************************
  * @file    ramp_ext_mngr.c
  * @author  Motor Control SDK Team, ST Microelectronics
  * @brief   This file provides firmware functions that implement the features
  *          of the Ramp Extended Manager component of the Motor Control SDK:
  *
  ******************************************************************************
  * @attention
  *
  * <h2><center>&copy; Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.</center></h2>
  *
  * This software component is licensed by ST under Ultimate Liberty license
  * SLA0044, the "License"; You may not use this file except in compliance with
  * the License. You may obtain a copy of the License at:
  *                             www.st.com/SLA0044
  *
  ******************************************************************************
  */

/* Includes ------------------------------------------------------------------*/


/** @addtogroup MCSDK
  * @{
  */

/** @addtogroup ConvFOC
  * @{
  */

/** @addtogroup MCLLAPI
  * @{
  */
  
/** @defgroup RampExtMngr Ramp Manager
  * @brief Ramp Extended Manager component of the Motor Control SDK
  *
  * @todo Document the Ramp Extended Manager "module".
  *
  * @{
  */
/* Private function prototypes -----------------------------------------------*/
uint32_t getScalingFactor(int32_t Target);

/**
  * @brief  It reset the state variable to zero.
  * @param  pHandle related Handle of struct RampMngr_Handle_t
  * @retval none.
  */
void REMNG_Init(RampExtMngr_Handle_t *pHandle)
{
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  if (MC_NULL == pHandle)
  {
    /* Nothing to do */
  }
  else
  {
#endif
    pHandle->Ext = 0;
    pHandle->TargetFinal = 0;
    pHandle->RampRemainingStep = 0U;
    pHandle->IncDecAmount = 0;
    pHandle->ScalingFactor = 1U;
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  }
#endif
}

#if defined (CCMRAM)
#if defined (__ICCARM__)
#pragma location = ".ccmram"
#elif defined (__CC_ARM) || defined(__GNUC__)
__attribute__((section(".ccmram")))
#endif
#endif
/**
  * @brief  Exec the ramp calculations and returns the current value of the
            state variable.
            It must be called at fixed interval defined in the hExecFreq.
  * @param  pHandle related Handle of struct RampMngr_Handle_t
  * @retval int32_t value of the state variable
  */
__weak int32_t REMNG_Calc(RampExtMngr_Handle_t *pHandle)
{
  int32_t ret_val;
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  if (MC_NULL == pHandle)
  {
    ret_val = 0;
  }
  else
  {
#endif
    int32_t current_ref;

    current_ref = pHandle->Ext;

    /* Update the variable and terminates the ramp if needed */
    if (pHandle->RampRemainingStep > 1U)
    {
      /* Increment/decrement the reference value */
      current_ref += pHandle->IncDecAmount;

      /* Decrement the number of remaining steps */
      pHandle->RampRemainingStep --;
    }
    else if (1U == pHandle->RampRemainingStep)
    {
      /* Set the backup value of TargetFinal */
      current_ref = pHandle->TargetFinal * ((int32_t)pHandle->ScalingFactor);
      pHandle->RampRemainingStep = 0U;
    }
    else
    {
      /* Do nothing */
    }

    pHandle->Ext = current_ref;
    ret_val = pHandle->Ext / ((int32_t)pHandle->ScalingFactor);
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  }
#endif
  return (ret_val);
}

/**
  * @brief  Setup the ramp to be executed
  * @param  pHandle related Handle of struct RampMngr_Handle_t
  * @param  hTargetFinal (signed 32bit) final value of state variable at the end
  *         of the ramp.
  * @param  hDurationms (unsigned 32bit) the duration of the ramp expressed in
  *         milliseconds. It is possible to set 0 to perform an instantaneous
  *         change in the value.
  * @retval bool It returns true is command is valid, false otherwise
  */
__weak bool REMNG_ExecRamp(RampExtMngr_Handle_t *pHandle, int32_t TargetFinal, uint32_t Durationms)
{
  bool retVal = true;
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  if (MC_NULL == pHandle)
  {
    retVal = false;
  }
  else
  {
#endif
    uint32_t aux;
    int32_t aux1;
    int32_t current_ref;


    /* Get current state */
    current_ref = pHandle->Ext / ((int32_t)pHandle->ScalingFactor);

    if (0U == Durationms)
    {
      pHandle->ScalingFactor = getScalingFactor(TargetFinal);
      pHandle->Ext = TargetFinal * ((int32_t)pHandle->ScalingFactor);
      pHandle->RampRemainingStep = 0U;
      pHandle->IncDecAmount = 0;
    }
    else
    {
      uint32_t wScalingFactor = getScalingFactor(TargetFinal - current_ref);
      uint32_t wScalingFactor2 = getScalingFactor(current_ref);
      uint32_t wScalingFactor3 = getScalingFactor(TargetFinal);
      uint32_t wScalingFactorMin;

      if (wScalingFactor <  wScalingFactor2)
      {
        if (wScalingFactor < wScalingFactor3)
        {
          wScalingFactorMin = wScalingFactor;
        }
        else
        {
          wScalingFactorMin = wScalingFactor3;
        }
      }
      else
      {
        if (wScalingFactor2 < wScalingFactor3)
        {
          wScalingFactorMin = wScalingFactor2;
        }
        else
        {
          wScalingFactorMin = wScalingFactor3;
        }
      }

      pHandle->ScalingFactor = wScalingFactorMin;
      pHandle->Ext = current_ref * ((int32_t)pHandle->ScalingFactor);

      /* Store the TargetFinal to be applied in the last step */
      pHandle->TargetFinal = TargetFinal;

      /* Compute the (wRampRemainingStep) number of steps remaining to complete the ramp */
      aux = Durationms * ((uint32_t)pHandle->FrequencyHz); /* Check for overflow and use prescaler */
      aux /= 1000U;
      pHandle->RampRemainingStep = aux;
      pHandle->RampRemainingStep++;

      /* Compute the increment/decrement amount (wIncDecAmount) to be applied to
      the reference value at each CalcTorqueReference */
      aux1 = (TargetFinal - current_ref) * ((int32_t)pHandle->ScalingFactor);
      aux1 /= ((int32_t)pHandle->RampRemainingStep);
      pHandle->IncDecAmount = aux1;
    }
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  }
#endif
  return (retVal);
}

/**
  * @brief  Returns the current value of the state variable.
  * @param  pHandle related Handle of struct RampMngr_Handle_t
  * @retval int32_t value of the state variable
  */
__weak int32_t REMNG_GetValue(const RampExtMngr_Handle_t *pHandle)
{
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  return ((MC_NULL == pHandle) ? 0 : (pHandle->Ext / ((int32_t)pHandle->ScalingFactor)));
#else
  return (pHandle->Ext / ((int32_t)pHandle->ScalingFactor));
#endif
}

#if defined (CCMRAM)
#if defined (__ICCARM__)
#pragma location = ".ccmram"
#elif defined (__CC_ARM) || defined(__GNUC__)
__attribute__((section(".ccmram")))
#endif
#endif
/**
  * @brief  Check if the settled ramp has been completed.
  * @param  pHandle related Handle of struct RampMngr_Handle_t.
  * @retval bool It returns true if the ramp is completed, false otherwise.
  */
__weak bool REMNG_RampCompleted(const RampExtMngr_Handle_t *pHandle)
{
  bool retVal = false;
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  if (MC_NULL == pHandle)
  {
    /* Nothing to do */
  }
  else
  {
#endif
    if (0U == pHandle->RampRemainingStep)
    {
      retVal = true;
    }
    else
    {
      /* nothing to do */
    }
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  }
#endif
  return (retVal);

}

/**
  * @brief  Stop the execution of the ramp keeping the last reached value.
  * @param  pHandle related Handle of struct RampMngr_Handle_t.
  * @retval none
  */
__weak void REMNG_StopRamp(RampExtMngr_Handle_t *pHandle)
{
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  if (MC_NULL == pHandle)
  {
    /* Nothing to do */
  }
  else
  {
#endif
    pHandle->RampRemainingStep = 0U;
    pHandle->IncDecAmount = 0;
#ifdef NULL_PTR_CHECK_RMP_EXT_MNG
  }
#endif
}

/**
  * @brief  Calculating the scaling factor to maximixe the resolution. It
  *         perform the 2^int(31-log2(Target)) with an iterative approach.
  *         It allows to keep Target * Scaling factor inside int32_t type.
  * @param  Target Input data.
  * @retval uint32_t It returns the optimized scaling factor.
  */
__weak uint32_t getScalingFactor(int32_t Target)
{
  uint32_t TargetAbs;
  int32_t aux;
  uint8_t i;

  if (Target < 0)
  {
    aux = -Target;
    TargetAbs = (uint32_t)aux;
  }
  else
  {
    TargetAbs = (uint32_t)Target;
  }
  for (i = 1U; i < 32U; i++)
  {
    uint32_t limit = (((uint32_t)1) << (31U - i));
    if (TargetAbs >= limit)
    {
      break;
    }
    else
    {
      /* Nothing to do */
    }
  }
  return (((uint32_t)1) << (i - 1U));
}

/**
  * @}
  */

/**
  * @}
  */

/************************ (C) COPYRIGHT 2026 STMicroelectronics *****END OF FILE****/

int16_t Convert_Rad_to16bit(float fAngle_rad)
{
  int16_t hElAngle;
       
  hElAngle =  (int16_t) ((fAngle_rad*32767.0f)/(float)PI);
  
  return (hElAngle);
}
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
bool ACIM_VF_ExecRamp(ACIM_VF_Handle_t *pHandle, int16_t hTargetFinal, uint32_t Durationms)
{
  return REMNG_ExecRamp(pHandle->pRMNGR, (hTargetFinal)*pHandle->pACIM_MotorParams->bPP,Durationms); 
}
bool ACIM_VF_RampCompleted( ACIM_VF_Handle_t *pHandle )
{
  return REMNG_RampCompleted(pHandle->pRMNGR);
}
float ACIM_VF_FluxFreqCalc(ACIM_VF_Handle_t *pHandle)
{
  if(pHandle->bVF_Mode == VF_OL)
  {  
    pHandle->fFlux_Freq_Hz = (float)REMNG_Calc(pHandle->pRMNGR)/SPEED_UNIT;
    pHandle->fFlux_Freq_rads = pHandle->fFlux_Freq_Hz*2.0f*(float)PI;
  }
  else // It's is CL
  {
    float fSpeedError_rads = 0.0;
    float fMeasSpeed_rads = (2.0f*(float)PI*(float)pHandle->SPD_real->hAvrMecSpeedUnit)/SPEED_UNIT;
    
    pHandle->fRotorFreqRef_rads = (2.0f*(float)PI*(float)REMNG_Calc(pHandle->pRMNGR))/SPEED_UNIT;
    
  pHandle->fRotorFreqRef_RPM =  (pHandle->fRotorFreqRef_rads*60.0f)/(2.0f*PI);
  
    fSpeedError_rads = pHandle->fRotorFreqRef_rads - fMeasSpeed_rads;
   
    pHandle->fSlipFrequency_rads = PI_Float_Calc(pHandle->fPI, fSpeedError_rads);
    
    pHandle->fFlux_Freq_rads = pHandle->fSlipFrequency_rads + fMeasSpeed_rads;
    pHandle->fFlux_Freq_Hz = pHandle->fFlux_Freq_rads/(2.0f*(float)PI);
  }  
    
  return pHandle->fFlux_Freq_rads;
}
void ACIM_VF_CalcAngle(ACIM_VF_Handle_t *pHandle)
{
  
  pHandle->fFlux_Angle_rad += (pHandle->fFlux_Freq_rads*pHandle->fCalcAngleExecTime_s);
  
  pHandle->fFlux_Angle_rad = (float) fmod((double)pHandle->fFlux_Angle_rad , (double) (2.0f*(float)PI));
  
  pHandle->hElAngle = Convert_Rad_to16bit(pHandle->fFlux_Angle_rad);
  
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
uint16_t old_ACIM_VF_Controller(ACIM_VF_Handle_t *pHandle)
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

static unsigned checks;
static void check(bool ok,const char*why){++checks;if(!ok){fprintf(stderr,"FAIL %s\n",why);exit(1);}}
static float voltage(ACIM_VF_Handle_t &h,float f){h.fFlux_Freq_Hz=f;check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"voltage calculation");return h.VoltageAmpl;}
int main(){
 TIM_TypeDef timer;PWM_Handle_t pwm{&timer};ACIM_VF_Handle_t h{&pwm};
 h.fFlux_Angle_rad=.7f;h.fVoutMax_PWM_Mod_V=200;
 h.fFlux_Freq_Hz=9.999f;old_ACIM_VF_Controller(&h);float oldlow=h.VoltageAmpl;
 h.fFlux_Freq_Hz=10;old_ACIM_VF_Controller(&h);float oldhigh=h.VoltageAmpl;
 check(oldhigh-oldlow>15.9f,"old15.9V discontinuity reproduced");
 check(voltage(h,0)==0,"zero frequency means zero voltage reference");
 check(fabs(voltage(h,5)-20)<.00003f,"original5Hz20V peak anchor preserved");
 float left=voltage(h,9.999f),join=voltage(h,10),right=voltage(h,10.001f);
 check(join-left<.004f && right-join<.004f,"10Hz has no amplitude jump");
 float ls=(join-left)/.001f,rs=(right-join)/.001f;
 check(fabs(ls-rs)<.03f && ls>3.5f && ls<3.7f,"voltage slope joins linear branch continuously");
 float previous=0,max_step=0;
 for(unsigned i=0;i<=50000;++i){
  float value=voltage(h,i*.001f);
  check(value+.00003f>=previous,"dense0..50Hz voltage profile monotonic");
  max_step=std::max(max_step,value-previous);previous=value;
 }
 check(max_step<.0054f,"no hidden voltage discontinuity in dense sweep");
 unsigned controller_calls=0;float max_linear_ccr_difference=0;
 for(float bus:{250.f,325.f,380.f}){
  h.fVoutMax_PWM_Mod_V=bus/2;
  for(unsigned fi=0;fi<=500;++fi)for(unsigned angle=0;angle<360;++angle){
   h.fFlux_Freq_Hz=fi*.1f;h.fFlux_Angle_rad=angle*(2*PI/360);writes=0;
   check(ACIM_VF_Controller(&h)==MC_NO_ERROR && writes==3,"all frequency/angle combinations publish valid PWM");
   for(float d:{pwm.fDuty1,pwm.fDuty2,pwm.fDuty3})check(mic_float_isfinite(d) && d>=0 && d<=1,"duty finite and bounded");
   check(timer.CCR1<timer.ARR && timer.CCR2<timer.ARR && timer.CCR3<timer.ARR,"compare below timer period");
   if(fi>=100){
    float newvoltage=h.VoltageAmpl;uint32_t a=timer.CCR1,b=timer.CCR2,c=timer.CCR3;
    check(old_ACIM_VF_Controller(&h)==MC_NO_ERROR,"old linear branch valid");
    check(fabs(h.VoltageAmpl-newvoltage)<.00005f,"linear amplitude above10Hz unchanged");
    float delta=std::max({fabs(float(a)-timer.CCR1),fabs(float(b)-timer.CCR2),fabs(float(c)-timer.CCR3)});
    max_linear_ccr_difference=std::max(max_linear_ccr_difference,delta);check(delta<=1,"linear duty rounding within one timer count");
   }
   ++controller_calls;
  }
 }
 // Exact MCSDK ramp runs at500Hz; phase/PWM run at16kHz as in this project.
 FILE*trace=fopen("ramp0_to50.csv","w");check(trace,"open ramp trace");
 fprintf(trace,"time_ms,field_hz,phase_peak_v,phase_angle_rad,duty_u,duty_v,duty_w\n");
 float max_freq_step=0,max_ramp_voltage_step=0;unsigned ramp_cases=0;
 for(unsigned rate:{1U,5U,10U}){
  RampExtMngr_Handle_t ramp{};ramp.FrequencyHz=500;REMNG_Init(&ramp);
  Motor motor{1};Speed speed{};h=ACIM_VF_Handle_t{&pwm};h.pRMNGR=&ramp;h.pACIM_MotorParams=&motor;h.SPD_real=&speed;h.bVF_Mode=VF_OL;
  h.fCalcAngleExecTime_s=1.f/16000;h.fVoutMax_PWM_Mod_V=162.5f;
  unsigned duration=50000/rate;check(ACIM_VF_ExecRamp(&h,500,duration),"SDK accepts0..50Hz ramp");
  float last_hz=0,last_v=0;
  for(unsigned ms=0;ms<=duration+4;ms+=2){
   ACIM_VF_FluxFreqCalc(&h);float hz=h.fFlux_Freq_Hz;
   check(hz>=last_hz-.00001f && hz<=50 && hz-last_hz<.1001f,"actual ramp frequency is monotonic and bounded to0.1Hz steps");
   max_freq_step=std::max(max_freq_step,hz-last_hz);
   for(unsigned tick=0;tick<32;++tick){
    float old_angle=h.fFlux_Angle_rad;ACIM_VF_CalcAngle(&h);
    float advance=h.fFlux_Angle_rad-old_angle;if(advance<0)advance+=2*PI;
    check(advance>=0 && advance<.0197f,"actual integrated phase has no reset/jump");
    check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"actual ramp and angle drive exact PWM calculation");
   }
   float delta=h.VoltageAmpl-last_v;
   check(delta>=-.00005f && delta<.53f,"ramp voltage has no former15.9V step");
   max_ramp_voltage_step=std::max(max_ramp_voltage_step,delta);
   if(rate==5 && (ms%20==0 || ms==duration+4))fprintf(trace,"%u,%.6f,%.6f,%.6f,%.7f,%.7f,%.7f\n",ms,hz,h.VoltageAmpl,h.fFlux_Angle_rad,pwm.fDuty1,pwm.fDuty2,pwm.fDuty3);
   last_hz=hz;last_v=h.VoltageAmpl;
  }
  check(ACIM_VF_RampCompleted(&h) && h.fFlux_Freq_Hz==50,"SDK reaches50Hz and completes");++ramp_cases;
  float old_ref=h.fFlux_Freq_Hz;check(ACIM_VF_ExecRamp(&h,250,5000),"retarget ramp accepted");
  ACIM_VF_FluxFreqCalc(&h);check(old_ref-h.fFlux_Freq_Hz<.1001f,"retarget does not jump to new target");
 }
 fclose(trace);
 // Invalid values and profiles still fail before publishing compare registers.
 for(float bad:{0.f,-1.f,NAN,INFINITY}){h=ACIM_VF_Handle_t{&pwm};h.fVoutMax_PWM_Mod_V=bad;writes=0;
  check(ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0,"invalid normalizer fails closed");}
 h=ACIM_VF_Handle_t{&pwm};h.fVoltage_Offset=100;writes=0;
 check(ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0,"nonmonotonic low-speed boost configuration rejected");
 h=ACIM_VF_Handle_t{&pwm};h.fMinFreq_TH_Hz=0;check(voltage(h,0)==0,"zero join threshold never divides by zero");
 h=ACIM_VF_Handle_t{&pwm};h.fVoutMax_PWM_Mod_V=200;
 check(fabs(voltage(h,-5)-20)<.00003f,"negative-frequency amplitude remains symmetric");
 printf("{\"passed\":true,\"checks\":%u,\"controller_sweep_calls\":%u,\"ramp_cases\":%u,\"old_voltage_jump_v\":%.6f,\"new_join_left_v\":%.6f,\"new_join_v\":%.6f,\"new_join_right_v\":%.6f,\"left_slope_v_per_hz\":%.6f,\"right_slope_v_per_hz\":%.6f,\"maximum_0_001hz_voltage_step_v\":%.6f,\"maximum_actual_ramp_frequency_step_hz\":%.6f,\"maximum_actual_ramp_voltage_step_v\":%.6f,\"max_above10hz_ccr_difference\":%.1f,\"hardware_commands\":0}\n",
 checks,controller_calls,ramp_cases,oldhigh-oldlow,left,join,right,ls,rs,max_step,max_freq_step,max_ramp_voltage_step,max_linear_ccr_difference);
}
