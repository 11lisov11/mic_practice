#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <initializer_list>
#define __weak
#define SPEED_UNIT 10
#define PI 3.14159265358979323846f
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

enum {VF_OL,VF_CL};
struct Motor {uint8_t bPP;};struct Speed {int16_t hAvrMecSpeedUnit;};
struct ACIM_VF_Handle_t {
 RampExtMngr_Handle_t*pRMNGR;Motor*pACIM_MotorParams;Speed*SPD_real;void*fPI;
 int bVF_Mode;float fFlux_Freq_Hz,fFlux_Freq_rads,fRotorFreqRef_rads,fRotorFreqRef_RPM,fSlipFrequency_rads;
};
float PI_Float_Calc(void*,float){return 0;}
struct MCI_Handle_t {ACIM_VF_Handle_t*pACIM_VF;};
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
__weak int16_t ACIM_VF_GetMecSpeedRefUnit( ACIM_VF_Handle_t * pHandle ) {
  return (REMNG_GetValue(pHandle->pRMNGR) / pHandle->pACIM_MotorParams->bPP);
}
bool ACIM_VF_ExecRamp(ACIM_VF_Handle_t *pHandle, int16_t hTargetFinal, uint32_t Durationms)
{
  return REMNG_ExecRamp(pHandle->pRMNGR, (hTargetFinal)*pHandle->pACIM_MotorParams->bPP,Durationms); 
}
bool ACIM_VF_RampCompleted( ACIM_VF_Handle_t *pHandle )
{
  return REMNG_RampCompleted(pHandle->pRMNGR);
}
__weak int16_t MCI_GetMecSpeedRefUnit(MCI_Handle_t *pHandle)
{
  /* VF_OL updates the ramp manager and flux frequency. fRotorFreqRef_RPM is
     updated only by VF_CL and stays zero in open loop. This is a field
     reference, never a measured rotor speed. */
  return ACIM_VF_GetMecSpeedRefUnit(pHandle->pACIM_VF);
}
__weak int16_t old_MCI_GetMecSpeedRefUnit(MCI_Handle_t *pHandle)
{
  int16_t hRefSpeed = 0;
  hRefSpeed = (int16_t)(pHandle->pACIM_VF->fRotorFreqRef_RPM * SPEED_UNIT / 60.0f);
  return hRefSpeed;
}
constexpr int RUN=6,M1=0;
MCI_Handle_t *pMCI[1];
int MCI_GetSTMState(MCI_Handle_t*){return RUN;}
__weak bool MCI_RampCompleted(MCI_Handle_t *pHandle)
{
  bool retVal = false;

    if (RUN == MCI_GetSTMState(pHandle))
  {
    retVal = ACIM_VF_RampCompleted(pHandle->pACIM_VF);
  }

  return retVal;
}
__weak bool MC_HasRampCompletedMotor1(void)
{
  return (MCI_RampCompleted(pMCI[M1]));
}
unsigned checks=0;
void check(bool ok,const char*why){++checks;if(!ok){fprintf(stderr,"FAIL %s\n",why);exit(1);}}
int main(){
 for(unsigned pp : {1U,2U}) {
  RampExtMngr_Handle_t ramp{};ramp.FrequencyHz=1000;REMNG_Init(&ramp);
  Motor motor{(uint8_t)pp};Speed speed{};ACIM_VF_Handle_t vf{};
  vf.pRMNGR=&ramp;vf.pACIM_MotorParams=&motor;vf.SPD_real=&speed;vf.bVF_Mode=VF_OL;
  MCI_Handle_t mci{&vf};pMCI[0]=&mci;
  if(pp==1) {
   ACIM_VF_ExecRamp(&vf,100,0);ACIM_VF_FluxFreqCalc(&vf);
   ACIM_VF_ExecRamp(&vf,99,200);
   for(unsigned i=0;i<50;++i) ACIM_VF_FluxFreqCalc(&vf);
   struct {int16_t ramp_target_speed_unit;} uno_link{99};int16_t target_speed_unit=50;
   check(MCI_GetMecSpeedRefUnit(&mci)==99,"negative control: integer reference reaches rounded segment target early");
   check(!(uno_link.ramp_target_speed_unit!=target_speed_unit && MC_HasRampCompletedMotor1()),"actual Nucleo continuation waits for SDK completion despite rounded reference equality");
   for(unsigned i=0;i<152;++i) ACIM_VF_FluxFreqCalc(&vf);
   check((uno_link.ramp_target_speed_unit!=target_speed_unit && MC_HasRampCompletedMotor1()),"actual Nucleo continuation advances when SDK ramp completes");
   REMNG_Init(&ramp);
  }
  for(auto target : {5,10,50,20,5}) {
   const unsigned duration=target==20?60000:2500;
   check(ACIM_VF_ExecRamp(&vf,target*SPEED_UNIT/(int)pp,duration),"actual SDK ramp accepts target");
   for(unsigned i=0;i<duration+3;++i) {
    ACIM_VF_FluxFreqCalc(&vf);
    check(std::abs(MCI_GetMecSpeedRefUnit(&mci)*pp/(float)SPEED_UNIT-vf.fFlux_Freq_Hz)<.201f,"public API follows actual VF_OL field used by modulation");
   }
   check(std::abs(vf.fFlux_Freq_Hz-target)<.001f,"actual SDK flux field settles at target");
   check(vf.fRotorFreqRef_RPM==0,"VF_OL leaves CL-only rotor reference unchanged");
   check(old_MCI_GetMecSpeedRefUnit(&mci)==0,"negative control reproduces installed zero-reference bug");
  }
 }
 printf("{\"pass\":true,\"assertions\":%u,\"negative_control_reproduced\":true}\n",checks);
}
