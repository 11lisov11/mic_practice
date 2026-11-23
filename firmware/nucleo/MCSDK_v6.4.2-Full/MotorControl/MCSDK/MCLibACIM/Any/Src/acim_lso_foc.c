/**
  ******************************************************************************
  * @file    acim_lso_foc.c
  * @author  STMicroelectronics - System Lab - MC Team
  * @brief   This file provides firmware functions that implement the  features
  *          of the Rotor Flux Position Feedback component of the Motor Control SDK.
  *           - estimates the rotor flux electrical angle and mechanical rotor speed 
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
#include "acim_lso_foc.h"
#include "math.h"


/* Variables ---------------------------------------------------------*/


/* Function prototypes -----------------------------------------------*/
bool ACIM_LSO_IsNotValidNumber(float fVar);





/*
* @brief  It initializes the handle
* @param  pHandle: handler of the 
* @param  
* @retval none.
*/
void ACIM_LSO_Init(ACIM_LSO_Handle_t *pHandle, BusVoltageSensor_Handle_t *pBVS)
{
  pHandle->pBVS = pBVS;
  PI_Float_HandleInit(pHandle->fPI);
  const ACIM_MotorParams_Handle_t *motor = pHandle->pACIM_MotorParams;
  const float sigma = motor->fsigma;
  const float k = pHandle->k;
  const float inv_tr = 1.0f / motor->ftaur;
  const float inv_ts = 1.0f / motor->ftaus;
  const float sigma_rest = 1.0f - sigma;
  pHandle->invRotorTime = inv_tr;
  pHandle->observerK1 = -((k - 1.0f) / sigma) * (inv_tr + inv_ts);
  pHandle->observerK3 = ((k - 1.0f) / sigma_rest) * (inv_tr - k * inv_ts);
  pHandle->observerK4Scale = ((k - 1.0f) * sigma) / sigma_rest;
  pHandle->currentDecay = -(1.0f / sigma) * (inv_ts + sigma_rest * inv_tr);
  pHandle->speedFluxCoupling = sigma_rest * (1.0f / sigma);
  pHandle->directFluxCoupling = sigma_rest / (sigma * motor->ftaur);
  pHandle->voltageGain = 1.0f / (sigma * motor->fLs);
  pHandle->speedUnitDenominator = 2.0f * (float)PI * motor->bPP;
  
}

static inline float ACIM_LSO_WrapAngle(float angle)
{
  const float turn = 2.0f * (float)PI;
  // The running angle usually stays within one turn or crosses by a single turn.
  if (angle > -turn && angle < turn) { return angle; }
  if (angle >= turn && angle < 2.0f * turn) { return angle - turn; }
  if (angle < -turn && angle > -2.0f * turn) { return angle + turn; }
  if (angle == -turn) { return -0.0f; }
  return fmodf(angle, turn);
}


#if (defined (CCMRAM) || defined(CCMRAM_ENABLED))
#if defined (__ICCARM__)
#pragma location = ".ccmram"
#elif defined (__CC_ARM)
__attribute__((section ("ccmram")))
#elif defined (__GNUC__)
__attribute__((section ("ccmram")))
#endif
#endif

/**
  * @brief   
  *         
  * @param  
  * @param  
  *         
  * @retval 
  */
void ACIM_LSO_CalcAngleVoltage(ACIM_LSO_Handle_t *pHandle, qd_t applied)
{
  
  float fSlipFreq_rads = 0.0f;
  float fRotorFluxFreq_rads = 0.0f;
  float fRotorElSpeed_obs_rads = 0.0f;
  Signal_Components fIqds_obs_A;
  Signal_Components fFlux_qdr_obs;
  
  
  Signal_Components fVqds_meas_V;
  
  float fSpeedEstError = 0.0f;
    
  const ACIM_MotorParams_Handle_t *motor = pHandle->pACIM_MotorParams;
  const float k1 = pHandle->observerK1;
  const float k3 = pHandle->observerK3;
  const float divftaur = pHandle->invRotorTime;

  /* Previous values for estimated quantities */
  fRotorFluxFreq_rads    = pHandle->fRotorFluxFreq_rads;
  fRotorElSpeed_obs_rads = pHandle->fRotorElSpeed_obs_rads;
  fIqds_obs_A            = pHandle->fIqds_obs_A;
  fFlux_qdr_obs          = pHandle->fFlux_qdr_obs;
    
  fVqds_meas_V = Convert_s16_to_V(pHandle->pBVS, applied);
  
  Signal_Components Iqdmeas_A = Convert_s16_to_A(pHandle->pFOCVars[M1].Iqd);
  
  float ids_obs_A = fIqds_obs_A.fS_Component2;
  
  
  const float k2 = (pHandle->k - 1.0f) * fRotorElSpeed_obs_rads;
  const float k4 = pHandle->observerK4Scale * fRotorElSpeed_obs_rads;

  /* STEP 1 - Computing of prediction errors --------------------------------------------------------- */
  /* Iq error(k) */
  pHandle->fIqds_error_A.fS_Component1 = Iqdmeas_A.fS_Component1 - fIqds_obs_A.fS_Component1;
  /* Id error(k) */
  pHandle->fIqds_error_A.fS_Component2 = Iqdmeas_A.fS_Component2 - fIqds_obs_A.fS_Component2;
  
  /* STEP  2 - Computing of mech. rotor speed estimation --------------------------------------------- */
  /*  SpeedEstError = -(Iq_error * Flux_dr) */
  fSpeedEstError = -(pHandle->fIqds_error_A.fS_Component1 * pHandle->fFlux_qdr_obs.fS_Component2);
  
  pHandle->fRotorElSpeed_obs_rads = PI_Float_Calc(pHandle->fPI, fSpeedEstError);
 
  
  pHandle->_SpeedEstimator.hAvrMecSpeedUnit =    (int16_t)((pHandle->fRotorElSpeed_obs_rads*10.0f)/pHandle->speedUnitDenominator);
  pHandle->fRotorSpeed_RPM = (float)pHandle->_SpeedEstimator.hAvrMecSpeedUnit*6.0f;
  
  
  /* STEP  3 - Computing of rotor frequency */
  
  float fFlux_dr_tmp = pHandle->fFlux_qdr_obs.fS_Component2;

  if(fFlux_dr_tmp==0.0f)
  {
   fFlux_dr_tmp = pHandle->pACIM_MotorParams->fImagn_A;
  }
  
  if(ids_obs_A==0.0f)
  {
    ids_obs_A = pHandle->pACIM_MotorParams->fImagn_A;
  }
  
  /* Slip frequency estimation */
  fSlipFreq_rads = fIqds_obs_A.fS_Component1/(fFlux_dr_tmp * motor->ftaur);
   
  /* Rotor Flux frequency computation */
  fRotorFluxFreq_rads = fSlipFreq_rads + pHandle->fRotorElSpeed_obs_rads;
  pHandle->fRotorFluxFreq_rads = fRotorFluxFreq_rads;
  /* STEP  4 - Computing and output of field angle */
  pHandle->fRotorFlux_Angle_rad +=  fRotorFluxFreq_rads*pHandle->fCalcAngleExecTime_s;
    
  /* Observed Rotor Flux angle between 0 and 2pi */
  pHandle->fRotorFlux_Angle_rad = ACIM_LSO_WrapAngle(pHandle->fRotorFlux_Angle_rad);
   
  /* STEP 5 and 6 - Prediction of currents and flux */
 
  fIqds_obs_A.fS_Component1 +=  ((-fRotorFluxFreq_rads* pHandle->fIqds_obs_A.fS_Component2) + (pHandle->currentDecay*pHandle->fIqds_obs_A.fS_Component1)
                                -(pHandle->speedFluxCoupling*fRotorElSpeed_obs_rads)*pHandle->fFlux_qdr_obs.fS_Component2 
                                +fVqds_meas_V.fS_Component1*pHandle->voltageGain
                                +k2*((pHandle->fIqds_error_A.fS_Component2)) + k1*((pHandle->fIqds_error_A.fS_Component1)))*pHandle->fCalcAngleExecTime_s;
    
  fIqds_obs_A.fS_Component2 += ((pHandle->currentDecay*pHandle->fIqds_obs_A.fS_Component2)+ fRotorFluxFreq_rads*pHandle->fIqds_obs_A.fS_Component1                                     
                                +pHandle->directFluxCoupling*(pHandle->fFlux_qdr_obs.fS_Component2)
                                +fVqds_meas_V.fS_Component2*pHandle->voltageGain 
                                +k1*(pHandle->fIqds_error_A.fS_Component2) - k2*(pHandle->fIqds_error_A.fS_Component1))*pHandle->fCalcAngleExecTime_s;

  fFlux_qdr_obs.fS_Component2 += ((ids_obs_A*divftaur)
                                  -(pHandle->fFlux_qdr_obs.fS_Component2*divftaur)
                                  +k3*pHandle->fIqds_error_A.fS_Component2 - k4*pHandle->fIqds_error_A.fS_Component1)*pHandle->fCalcAngleExecTime_s;
  

  pHandle->fIqds_obs_A = fIqds_obs_A;
  pHandle->fFlux_qdr_obs.fS_Component2 = fFlux_qdr_obs.fS_Component2;

  
  pHandle->hElAngle = Convert_Rad_to16bit(pHandle->fRotorFlux_Angle_rad);
}

void ACIM_LSO_CalcAngle(ACIM_LSO_Handle_t *pHandle)
{
  ACIM_LSO_CalcAngleVoltage(pHandle, pHandle->pFOCVars->Vqd);
}

#if (defined (CCMRAM) || defined(CCMRAM_ENABLED))
#if defined (__ICCARM__)
#pragma location = ".ccmram"
#elif defined (__CC_ARM)
__attribute__((section ("ccmram")))
#elif defined (__GNUC__)
__attribute__((section ("ccmram")))
#endif
#endif
int16_t ACIM_LSO_GetElAngle(ACIM_LSO_Handle_t *pHandle)
{
 return pHandle->hElAngle;
}



void ACIM_LSO_Clear(ACIM_LSO_Handle_t *pHandle)
{
  Signal_Components fnull = {0.0f,0.0f};
  
  
  pHandle->fFlux_qdr_obs = fnull;   
  pHandle->fIqds_error_A = fnull;
  pHandle->fIqds_obs_A = fnull;
  
  
   PI_Float_HandleInit(pHandle->fPI);
  
  pHandle->fRotorElSpeed_obs_rads = 0.0f;
  pHandle->fRotorFluxFreq_rads = 0.0f;
  pHandle->fRotorFlux_Angle_rad = 0.0f;
  
  pHandle->hElAngle = 0.0f;
  
  
  pHandle->fRotorSpeed_RPM = 0.0f;
  pHandle->_SpeedEstimator.hAvrMecSpeedUnit = 0;
  
  
  pHandle->fdbg_Vampl = 0.0f;
  pHandle->fdbg_ElAngle_rad = 0.0f;
  pHandle->fdbg_Frequency_rads = 0.0f;
  pHandle->hdbg_ElAngle = 0.0f;

  
  
}
#if (defined (CCMRAM) || defined(CCMRAM_ENABLED))
#if defined (__ICCARM__)
#pragma location = ".ccmram"
#elif defined (__CC_ARM)
__attribute__((section ("ccmram")))
#elif defined (__GNUC__)
__attribute__((section ("ccmram")))
#endif
#endif
/*
   It returns true if LSO variables are valid numerical values 
   It return false as soon as one of the LSO variables becomes Nan or INF
*/

bool ACIM_LSO_CheckIntegrity(ACIM_LSO_Handle_t *pHandle)
{
  bool bRetVal = true;
  
  if( ACIM_LSO_IsNotValidNumber(pHandle->fFlux_qdr_obs.fS_Component1)||
      ACIM_LSO_IsNotValidNumber(pHandle->fFlux_qdr_obs.fS_Component2)||  
      ACIM_LSO_IsNotValidNumber(pHandle->fIqds_obs_A.fS_Component1)||
      ACIM_LSO_IsNotValidNumber(pHandle->fIqds_obs_A.fS_Component2)||  
      ACIM_LSO_IsNotValidNumber(pHandle->fRotorElSpeed_obs_rads)||
      ACIM_LSO_IsNotValidNumber(pHandle->fRotorFluxFreq_rads)||
      ACIM_LSO_IsNotValidNumber(pHandle->fRotorFlux_Angle_rad)||  
      ACIM_LSO_IsNotValidNumber(pHandle->fRotorSpeed_RPM)||
      (pHandle->fRotorElSpeed_obs_rads >=  pHandle->fMaxObsRotorSpeed_RPM)||
      (pHandle->fRotorElSpeed_obs_rads <= -pHandle->fMaxObsRotorSpeed_RPM)  
   )
  {
    bRetVal = false;
  }
  
  
  return bRetVal;
  
}

bool ACIM_LSO_IsNotValidNumber(float fVar)
{
  bool bRetVar = false;
  
  if(isnan(fVar)||isnan(fVar))
  {
   bRetVar = true;
  }
 
    return bRetVar;
}


#if (defined (CCMRAM) || defined(CCMRAM_ENABLED))
#if defined (__ICCARM__)
#pragma location = ".ccmram"
#elif defined (__CC_ARM)
__attribute__((section ("ccmram")))
#elif defined (__GNUC__)
__attribute__((section ("ccmram")))
#endif
#endif
void ACIM_DBG_LSO_CalcAngle(ACIM_LSO_Handle_t *pHandle, float fFrequency_Hz)
{
    
  
  pHandle->fdbg_Frequency_rads = fFrequency_Hz*2.0f*PI;
  
  /* Discrete Integration */
  pHandle->fdbg_ElAngle_rad += (pHandle->fdbg_Frequency_rads * pHandle->fCalcAngleExecTime_s);

  pHandle->fdbg_ElAngle_rad = (float) fmod((double)pHandle->fdbg_ElAngle_rad , (double) (2.0f*(float)PI));

  pHandle->hdbg_ElAngle = Convert_Rad_to16bit(pHandle->fdbg_ElAngle_rad);
    
}

#if (defined (CCMRAM) || defined(CCMRAM_ENABLED))
#if defined (__ICCARM__)
#pragma location = ".ccmram"
#elif defined (__CC_ARM)
__attribute__((section ("ccmram")))
#elif defined (__GNUC__)
__attribute__((section ("ccmram")))
#endif
#endif
int16_t ACIM_DBG_LSO_GetdbgElAngle(ACIM_LSO_Handle_t *pHandle)
{ 
 return (pHandle->hdbg_ElAngle);
 
}
#if (defined (CCMRAM) || defined(CCMRAM_ENABLED))
#if defined (__ICCARM__)
#pragma location = ".ccmram"
#elif defined (__CC_ARM)
__attribute__((section ("ccmram")))
#elif defined (__GNUC__)
__attribute__((section ("ccmram")))
#endif
#endif
qd_t ACIM_DBG_LSO_CalcVoltage(ACIM_LSO_Handle_t *pHandle)
{
  qd_t Vqd = {0,0};
  float fFreq_rads_abs=0;
  
  fFreq_rads_abs = pHandle->fdbg_Frequency_rads;
  
  if(fFreq_rads_abs <0.0f)
  {
    fFreq_rads_abs = -fFreq_rads_abs;
  }	  

  if(fFreq_rads_abs < pHandle->fdbg_MinFreqTH_rads) 
  {   
    pHandle->fdbg_Vampl = pHandle->fdbg_VoltageOffset_V;
  }
  else
  {
    pHandle->fdbg_Vampl = (fFreq_rads_abs * pHandle->fdbg_Flux_K);
  }
  
  Signal_Components fVqd_V = {pHandle->fdbg_Vampl, 0.0f};
  
  Vqd = Convert_V_to_s16(pHandle->pBVS, fVqd_V);
  
  return Vqd;
}

/************************ (C) COPYRIGHT 2026 STMicroelectronics *****END OF FILE****/
