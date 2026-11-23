/**
  ******************************************************************************
  * @file    mc_tasks.c
  * @author  Motor Control SDK Team, ST Microelectronics
  * @brief   This file implements tasks definition
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
#include "main.h"
#include "mc_type.h"
#include "mc_math.h"
#include "motorcontrol.h"
#include "regular_conversion_manager.h"
#include "mc_interface.h"
#include "digital_output.h"
#include "pwm_common.h"
#include "mc_tasks.h"
#include "air56_st_lso_limits.h"
#include "air56_lso_capture.h"
#include "air56_lso_start_record.h"
#include "unit_conversions.h"
#include <string.h>
#include "parameters_conversion.h"
#include "air56_lso_field_guard.h"
#include "mcp_config.h"

/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* USER CODE BEGIN Private define */
/* Private define ------------------------------------------------------------*/
#define M1_CHARGE_BOOT_CAP_MS  10
#define M2_CHARGE_BOOT_CAP_MS  10
#define STOPPERMANENCY_MS      400
#define STOPPERMANENCY_MS2     400
#define CHARGE_BOOT_CAP_TICKS  (uint16_t)((SYS_TICK_FREQUENCY * M1_CHARGE_BOOT_CAP_MS)/ 1000)
#define CHARGE_BOOT_CAP_TICKS2 (uint16_t)((SYS_TICK_FREQUENCY * M2_CHARGE_BOOT_CAP_MS)/ 1000)
#define STOPPERMANENCY_TICKS   (uint16_t)((SYS_TICK_FREQUENCY * STOPPERMANENCY_MS)/ 1000)
#define STOPPERMANENCY_TICKS2  (uint16_t)((SYS_TICK_FREQUENCY * STOPPERMANENCY_MS2)/ 1000)

/* Un-Comment this macro define in order to activate the smooth
   braking action on over voltage */
/* #define  MC.SMOOTH_BRAKING_ACTION_ON_OVERVOLTAGE */
#define M1_CHARGE_BOOT_CAP_DUTY_CYCLES (uint32_t)(0.000*(PWM_PERIOD_CYCLES/2))
#define M2_CHARGE_BOOT_CAP_DUTY_CYCLES (uint32_t)(0*(PWM_PERIOD_CYCLES2/2))
/* USER CODE END Private define */

#define VBUS_TEMP_ERR_MASK (MC_OVER_VOLT| MC_UNDER_VOLT| MC_OVER_TEMP)

/* Private variables----------------------------------------------------------*/
FOCVars_t FOCVars[NBR_OF_MOTORS];
PWMC_Handle_t * pwmcHandle[NBR_OF_MOTORS];
DOUT_handle_t *pR_Brake[NBR_OF_MOTORS];
DOUT_handle_t *pOCPDisabling[NBR_OF_MOTORS];
CircleLimitation_Handle_t *pCLM[NBR_OF_MOTORS];
ACIM_LSO_Handle_t *pACIM_LSO[NBR_OF_MOTORS];
static volatile uint32_t air56_adc_stamp;
static uint32_t air56_last_packet_ms;
static uint32_t air56_start_ms;
static bool air56_run_started;
volatile air56_trace air56_lso_trace;
static air56_lso_start_record air56_start_record __attribute__((section(".ccmram.air56_start_record")));
volatile uint32_t air56_trip_raw_pair;
volatile uint32_t air56_trip_adc_timer;
static volatile uint32_t air56_trip_record[16];
static volatile bool air56_trip_saved;

/* Published only after PWM is disabled; CLEAR leaves this record intact. */
static void air56_save_overcurrent(const ab_t *measured)
{
  if (!air56_lso_trace.active || air56_trip_saved) { return; }
  const PWMC_R3_2_Handle_t *pwm = (const PWMC_R3_2_Handle_t *)pwmcHandle[M1];
  air56_trip_record[0] = 0x3150434CU; /* LCP1 */
  air56_trip_record[1] = air56_lso_trace.start_ms;
  air56_trip_record[2] = HAL_GetTick();
  air56_trip_record[3] = DWT->CYCCNT - air56_lso_trace.start_cycles;
  air56_trip_record[4] = air56_lso_trace.injected_samples;
  air56_trip_record[5] = air56_trip_raw_pair;
  air56_trip_record[6] = pwm->PhaseAOffset;
  air56_trip_record[7] = pwm->PhaseBOffset;
  air56_trip_record[8] = pwm->PhaseCOffset;
  air56_trip_record[9] = (uint16_t)measured->a | ((uint32_t)(uint16_t)measured->b << 16);
  air56_trip_record[10] = pwm->_Super.Sector;
  const uint32_t adc_timer = air56_trip_adc_timer;
  air56_trip_record[11] = (adc_timer & 0xFFFFU) | (TIM1->ARR << 16);
  air56_trip_record[12] = (adc_timer >> 16) | (TIM1->SR << 16);
  air56_trip_record[13] = (TIM1->CCR1 & 0xFFFFU) | (TIM1->CCR2 << 16);
  air56_trip_record[14] = (TIM1->CCR3 & 0xFFFFU) | (TIM1->CCR4 << 16);
  air56_trip_record[15] = (ADC1->ISR & 0xFFFFU) | (ADC2->ISR << 16);
  __DMB();
  air56_trip_saved = true;
}
static void AIR56_UnoService(void);

static void air56_capture_begin(uint32_t now)
{
  air56_lso_trace.rows = air56_lso_trace.count = air56_lso_trace.injected_samples = 0;
  air56_lso_trace.first_fault = air56_lso_trace.fast_max = 0;
  air56_lso_trace.peak_a = air56_lso_trace.peak_b = air56_lso_trace.peak_c = 0;
  air56_lso_trace.window_max = 0;
  air56_start_record = (air56_lso_start_record){
    .magic = AIR56_START_RECORD_MAGIC, .start_ms = now, .id_min = INT16_MAX, .id_max = INT16_MIN,
    .speed_target = Mci[M1].hFinalSpeed, .ramp_command_state = (uint8_t)Mci[M1].CommandState
  };
  air56_lso_trace.start_ms = now;
  air56_lso_trace.start_cycles = DWT->CYCCNT;
  air56_lso_trace.magic = AIR56_TRACE_MAGIC;
  __DMB();
  air56_lso_trace.active = 1;
}

static void air56_capture_finish(uint32_t reason, uint32_t now)
{
  air56_lso_trace.active = 0;
  air56_trace_window(&air56_lso_trace, DWT->CYCCNT);
  air56_lso_trace.end_ms = now;
  air56_start_record.end_ms = now;
  air56_start_record.terminal_state = (uint8_t)Mci[M1].State;
  air56_start_record.terminal_faults = MCI_GetCurrentFaults(&Mci[M1]) | MCI_GetOccurredFaults(&Mci[M1]);
  air56_start_record.stop_reason = (uint16_t)reason;
  air56_lso_trace.reason = reason;
}

/* Called by the timer independently of ADC completion. An absent ADC
 * interrupt cannot hold the last duty cycle indefinitely. */
void AIR56_LsoWatchAdc(void)
{
  const MCI_State_t state = Mci[M1].State;
  if ((state == START || state == RUN) && LL_TIM_IsEnabledAllOutputs(TIM1) &&
      air56_lso_stale(DWT->CYCCNT, air56_adc_stamp, AIR56_LSO_ADC_AGE_CYCLES))
  {
    LL_TIM_DisableAllOutputs(TIM1);
    MCI_FaultProcessing(&Mci[M1], MC_DURATION, 0);
  }
}


static volatile uint16_t hMFTaskCounterM1 = 0; //cstat !MISRAC2012-Rule-8.9_a
static volatile uint16_t hBootCapDelayCounterM1 = 0;
static volatile uint16_t hStopPermanencyCounterM1 = 0;

uint8_t bMCBootCompleted = 0;

/* USER CODE BEGIN Private Variables */

/* USER CODE END Private Variables */

static volatile uint8_t bACIM_MagnValidCount = 0;

/* Private functions ---------------------------------------------------------*/
void TSK_MediumFrequencyTaskM1(void);
void FOC_Clear(uint8_t bMotor);
void FOC_InitAdditionalMethods(uint8_t bMotor);
void FOC_CalcCurrRef(uint8_t bMotor);
static uint16_t FOC_CurrControllerM1(void);
static float air56_start_flux_A;
static uint16_t air56_magnetization_steps;
static volatile int16_t air56_magnetization_id;
static uint16_t air56_flux_checks, air56_flux_saturated;
static int32_t air56_flux_id_sum, air56_flux_iq_sum;
static uint8_t air56_flux_step;
static float air56_observer_loss_counts;
static float air56_flux_residual_sum, air56_flux_window_id, air56_flux_window_flux;

enum {
  AIR56_FLUX_VOLTAGE_INITIAL = 14,
  AIR56_FLUX_VOLTAGE_STEP = 2,
  AIR56_FLUX_VOLTAGE_STEPS = 5,
  AIR56_FLUX_SATURATION_STEPS = MEDIUM_FREQUENCY_TASK_RATE / 50, /* 20 ms */
  AIR56_FLUX_TIMEOUT_STEPS = MEDIUM_FREQUENCY_TASK_RATE * 2 / 5, /* 400 ms */
  AIR56_FLUX_IQ_FOR_STEP = CURRENT_CONV_FACTOR / 4 /* 0.25 A, qualification unchanged */
};

#define AIR56_FLUX_VOLTAGE_COUNTS(v) ((int16_t)((v) * 1.7320508076f * 32767.0f / 350.0f))

typedef struct {
  uint32_t magic, start_ms;
  int16_t id_mean[AIR56_FLUX_VOLTAGE_STEPS], iq_mean[AIR56_FLUX_VOLTAGE_STEPS];
  uint8_t steps, result; /* 1: qualified, 2: stationary time limit */
  uint16_t observer_loss_mV;
} air56_flux_voltage_record;
#define AIR56_FLUX_VOLTAGE_MAGIC 0x3156464cU /* LFV1 */
_Static_assert(sizeof(air56_flux_voltage_record) == 32, "Flux voltage record must fit one page");
static air56_flux_voltage_record air56_flux_record __attribute__((section(".ccmram.air56_start_record")));

enum { AIR56_MAGNETIZATION_STEPS = 30 }; /* 60 ms at the 500 Hz medium task rate. */

static void AIR56_CurrentPILimits(PID_Handle_t *pid, int16_t limit, uint16_t divisor)
{
  PID_SetUpperOutputLimit(pid, limit);
  PID_SetLowerOutputLimit(pid, -limit);
  PID_SetUpperIntegralTermLimit(pid, (int32_t)limit * divisor);
  PID_SetLowerIntegralTermLimit(pid, -(int32_t)limit * divisor);
}

typedef struct {
  qd_t current, voltage;
  uint32_t adc_pair;
  uint16_t sector;
} air56_start_sample;

typedef struct {
  uint32_t magic, start_ms, peak_ms, adc_pair;
  uint16_t q_blocks, iq_limit, sector, samples;
  int16_t iq_peak, id_at_peak, vq_at_peak, vd_at_peak;
} air56_start_q_record;

#define AIR56_START_Q_MAGIC 0x3151534cU /* LSQ1 */
_Static_assert(sizeof(air56_start_q_record) == 32, "START current diagnostic must fit one page");
static air56_start_sample air56_start_latest __attribute__((section(".ccmram.air56_start_record")));
static air56_start_q_record air56_start_q __attribute__((section(".ccmram.air56_start_record")));
static air56_field_guard air56_run_field __attribute__((section(".ccmram.air56_start_record")));
static air56_field_fault air56_first_field_fault __attribute__((section(".ccmram.air56_start_record")));

static bool AIR56_FieldReady(void)
{
  if (Mci[M1].State != RUN)
  {
    air56_run_field.initialized = false;
    return true;
  }
  if (!air56_run_field.initialized)
  {
    const float scale = 65536.0f * RSHUNT * AMPLIFICATION_GAIN / ADC_REFERENCE_VOLTAGE;
    air56_run_field = (air56_field_guard){ .flux_counts = air56_start_flux_A * scale, .initialized = true };
  }
  const ACIM_LSO_Handle_t *lso = pACIM_LSO[M1];
  const float reference = STC_GetMecSpeedRefUnit(pSTC[M1]) * ((float)POLE_PAIR_NUM / SPEED_UNIT);
  air56_field_fault fault;
  if (air56_field_check(&air56_run_field, FOCVars[M1].Iqd, FOCVars[M1].Iqdref.q,
                        reference, lso->fRotorFluxFreq_rads, lso->fRotorElSpeed_obs_rads, &fault) == 0)
  {
    return true;
  }
  LL_TIM_DisableAllOutputs(TIM1);
  if (air56_lso_trace.active && !air56_first_field_fault.magic)
  {
    fault.start_ms = air56_lso_trace.start_ms;
    fault.magic = AIR56_FIELD_MAGIC;
    air56_first_field_fault = fault;
  }
  return false;
}

void TSK_SetChargeBootCapDelayM1(uint16_t hTickCount);
bool TSK_ChargeBootCapDelayHasElapsedM1(void);
void TSK_SetStopPermanencyTimeM1(uint16_t hTickCount);
bool TSK_StopPermanencyTimeHasElapsedM1(void);
void TSK_SafetyTask_PWMOFF(uint8_t motor);

/* USER CODE BEGIN Private Functions */

/* USER CODE END Private Functions */

static bool ACIM_IsMagnetized(const air56_start_sample *sample);

/**
  * @brief  It initializes the whole MC core according to user defined
  *         parameters.
  * @param  pMCIList pointer to the vector of MCInterface objects that will be
  *         created and initialized. The vector must have length equal to the
  *         number of motor drives.
  */
__weak void MCboot( MCI_Handle_t* pMCIList[NBR_OF_MOTORS] )
{
  /* USER CODE BEGIN MCboot 0 */

  /* USER CODE END MCboot 0 */

  bMCBootCompleted = 0;
  pCLM[M1] = &CircleLimitationM1;
  /**********************************************************/
  /*    PWM and current sensing component initialization    */
  /**********************************************************/

  /* If the V/f is used the pwmcHandle is used to perform the
   * regular conversions (Temp, Bus Voltage, and user conversions)
   * Better name for this component should be something like
   * PWM and Analog Conversions (PWMAC)
   * In this case the PWMC child component is is used only for Analog Conversions
   *
   */

  pwmcHandle[M1] = &PWM_Handle_M1._Super;
  R3_2_Init(&PWM_Handle_M1);
  ASPEP_start (&aspepOverUartA);

  /* USER CODE BEGIN MCboot 1 */

  /* USER CODE END MCboot 1 */

  /**************************************/
  /*    Start timers synchronously      */
  /**************************************/
  startTimers();

  /******************************************************/
  /*   PID component initialization: speed regulation   */
  /******************************************************/
  PID_HandleInit(&PIDSpeedHandle_M1);

  /******************************************************/
  /*   Speed & torque component initialization          */
  /******************************************************/
  STC_Init(pSTC[M1], &PIDSpeedHandle_M1, &ACIM_LSO_Component_M1._SpeedEstimator);

  /********************************************************/
  /*   PID component initialization: current regulation   */
  /********************************************************/
  PID_HandleInit(&PIDIqHandle_M1);
  PID_HandleInit(&PIDIdHandle_M1);

  /********************************************************/
  /*   Bus voltage sensor component initialization        */
  /********************************************************/
  (void)RCM_RegisterRegConv(&VbusRegConv_M1);
  RVBS_Init(&BusVoltageSensor_M1);

  /*************************************************/
  /*   Power measurement component initialization  */
  /*************************************************/
  pMPM[M1]->pVBS = &(BusVoltageSensor_M1._Super);
  pMPM[M1]->pFOCVars = &FOCVars[M1];

  /*******************************************************/
  /*   Temperature measurement component initialization  */
  /*******************************************************/
  (void)RCM_RegisterRegConv(&TempRegConv_M1);
  NTC_Init(&TempSensor_M1);
  FOC_Clear(M1);
  FOCVars[M1].bDriveInput = EXTERNAL;
  FOCVars[M1].Iqdref = STC_GetDefaultIqdref(pSTC[M1]);
  FOCVars[M1].UserIdref = STC_GetDefaultIqdref(pSTC[M1]).d;

  MCI_Init(&Mci[M1], pSTC[M1], &FOCVars[M1],pwmcHandle[M1] );
  MCI_ExecSpeedRamp(&Mci[M1],
  STC_GetMecSpeedRefUnitDefault(pSTC[M1]),0); /*First command to STC*/
  pMCIList[M1] = &Mci[M1];
  Mci[M1].pScale = &scaleParams_M1;

  /********************************************************/
  /*   ACIM LSO-foc component initialization              */
  /********************************************************/
  pACIM_LSO[M1] = pACIM_LSO_Component_M1;
  pACIM_LSO[M1]->pFOCVars = &FOCVars[M1];
  ACIM_LSO_Init(pACIM_LSO[M1], &(BusVoltageSensor_M1._Super));

  /* USER CODE BEGIN MCboot 2 */

  /* USER CODE END MCboot 2 */

  bMCBootCompleted = 1;
}

/**
 * @brief Runs all the Tasks of the Motor Control cockpit
 *
 * This function is to be called periodically at least at the Medium Frequency task
 * rate (It is typically called on the Systick interrupt). Exact invokation rate is
 * the Speed regulator execution rate set in the Motor Contorl Workbench.
 *
 * The following tasks are executed in this order:
 *
 * - Medium Frequency Tasks of each motors
 * - Safety Task
 * - Power Factor Correction Task (if enabled)
 * - User Interface task.
 */
__weak void MC_RunMotorControlTasks(void)
{
  if ( bMCBootCompleted ) {
    /* ** Medium Frequency Tasks ** */
    MC_Scheduler();

    /* Safety task is run after Medium Frequency task so that
     * it can overcome actions they initiated if needed. */
    TSK_SafetyTask();
  }
  else
  {
    /* Nothing to do */
  }
}

/**
 * @brief Performs stop process and update the state machine.This function
 *        shall be called only during medium frequency task
 */
void TSK_MF_StopProcessing( uint8_t motor)
{
  R3_2_SwitchOffPWM(pwmcHandle[motor]);
  FOC_Clear(motor);
  PQD_Clear(pMPM[motor]);
  TSK_SetStopPermanencyTimeM1(STOPPERMANENCY_TICKS);
  Mci[motor].State = STOP;
}

/**
 * @brief  Executes the Medium Frequency Task functions for each drive instance.
 *
 * It is to be clocked at the Systick frequency.
 */
__weak void MC_Scheduler(void)
{
/* USER CODE BEGIN MC_Scheduler 0 */
  extern void UASPEP_Poll(ASPEP_Handle_t *protocol);

/* USER CODE END MC_Scheduler 0 */

  if (((uint8_t)1) == bMCBootCompleted)
  {
    AIR56_UnoService();
    UASPEP_Poll(&aspepOverUartA);
    if(hMFTaskCounterM1 > 0u)
    {
      hMFTaskCounterM1--;
    }
    else
    {
      TSK_MediumFrequencyTaskM1();

      MCP_Over_UartA.rxBuffer = MCP_Over_UartA.pTransportLayer->fRXPacketProcess(MCP_Over_UartA.pTransportLayer,
                                                                                &MCP_Over_UartA.rxLength);
      if ( 0U == MCP_Over_UartA.rxBuffer)
      {
        /* Nothing to do */
      }
      else
      {
        /* Synchronous answer */
        if (0U == MCP_Over_UartA.pTransportLayer->fGetBuffer(MCP_Over_UartA.pTransportLayer,
                                                     (void **) &MCP_Over_UartA.txBuffer, //cstat !MISRAC2012-Rule-11.3
                                                     MCTL_SYNC))
        {
          /* no buffer available to build the answer ... should not occur */
        }
        else
        {
          MCP_ReceivedPacket(&MCP_Over_UartA);
          MCP_Over_UartA.pTransportLayer->fSendPacket(MCP_Over_UartA.pTransportLayer, MCP_Over_UartA.txBuffer,
                                                      MCP_Over_UartA.txLength, MCTL_SYNC);
          /* no buffer available to build the answer ... should not occur */
        }
      }

      /* USER CODE BEGIN MC_Scheduler 1 */

      /* USER CODE END MC_Scheduler 1 */
      hMFTaskCounterM1 = (uint16_t)MF_TASK_OCCURENCE_TICKS;
    }
    if(hBootCapDelayCounterM1 > 0U)
    {
      hBootCapDelayCounterM1--;
    }
    if(hStopPermanencyCounterM1 > 0U)
    {
      hStopPermanencyCounterM1--;
    }
    else
    {
      /* Nothing to do */
    }
  }
  else
  {
    /* Nothing to do */
  }
  /* USER CODE BEGIN MC_Scheduler 2 */

  /* USER CODE END MC_Scheduler 2 */
}

/**
  * @brief Executes medium frequency periodic Motor Control tasks
  *
  * This function performs some of the control duties on Motor 1 according to the
  * present state of its state machine. In particular, duties requiring a periodic
  * execution at a medium frequency rate (such as the speed controller for instance)
  * are executed here.
  */
__weak void TSK_MediumFrequencyTaskM1(void)
{
  /* USER CODE BEGIN MediumFrequencyTask M1 0 */

  /* USER CODE END MediumFrequencyTask M1 0 */

  PQD_CalcElMotorPower(pMPM[M1]);

  if (MCI_GetCurrentFaults(&Mci[M1]) == MC_NO_FAULTS)
  {
    if (MCI_GetOccurredFaults(&Mci[M1]) == MC_NO_FAULTS)
    {
      const MCI_State_t bench_state = Mci[M1].State;
      if (bench_state == IDLE && Mci[M1].DirectCommand == MCI_START)
      {
        air56_start_ms = HAL_GetTick();
        air56_run_started = true;
      }
      if (air56_run_started &&
          air56_lso_stale(HAL_GetTick(), air56_start_ms, AIR56_LSO_RUN_MS))
      {
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        TSK_MF_StopProcessing(M1);
        air56_capture_finish(AIR56_END_TIMER, HAL_GetTick());
        air56_run_started = false;
        return;
      }
      if (air56_run_started && (bench_state == STOP || bench_state == IDLE) &&
          Mci[M1].DirectCommand != MCI_START)
      {
        air56_run_started = false;
      }
      if (air56_run_started &&
          air56_lso_stale(HAL_GetTick(), air56_last_packet_ms, AIR56_LSO_LINK_MS))
      {
        LL_TIM_DisableAllOutputs(TIM1);
        air56_run_started = false;
        air56_capture_finish(AIR56_END_LINK, HAL_GetTick());
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        MCI_FaultProcessing(&Mci[M1], MC_SW_ERROR, 0);
        return;
      }
      switch (Mci[M1].State)
      {
        case IDLE:
        {
          if ((MCI_START == Mci[M1].DirectCommand) || (MCI_MEASURE_OFFSETS == Mci[M1].DirectCommand))
          {
            if (pwmcHandle[M1]->offsetCalibStatus == false)
            {
              PWMC_CurrentReadingCalibr(pwmcHandle[M1], CRC_START);
              Mci[M1].State = OFFSET_CALIB;
            }
            else
            {
              /* calibration already done. Enables only TIM channels */
              pwmcHandle[M1]->OffCalibrWaitTimeCounter = 1u;
              PWMC_CurrentReadingCalibr(pwmcHandle[M1], CRC_EXEC);
              R3_2_TurnOnLowSides(pwmcHandle[M1],M1_CHARGE_BOOT_CAP_DUTY_CYCLES);
              TSK_SetChargeBootCapDelayM1(CHARGE_BOOT_CAP_TICKS);
              Mci[M1].State = CHARGE_BOOT_CAP;
            }
          }
          else
          {
            /* nothing to be done, FW stays in IDLE state */
          }
          break;
        }

        case OFFSET_CALIB:
        {
          if (MCI_STOP == Mci[M1].DirectCommand)
          {
            TSK_MF_StopProcessing(M1);
          }
          else
          {
            if (PWMC_CurrentReadingCalibr(pwmcHandle[M1], CRC_EXEC))
            {
              if (MCI_MEASURE_OFFSETS == Mci[M1].DirectCommand)
              {
                FOC_Clear(M1);
                PQD_Clear(pMPM[M1]);
                Mci[M1].DirectCommand = MCI_NO_COMMAND;
                Mci[M1].State = IDLE;
              }
              else
              {
                R3_2_TurnOnLowSides(pwmcHandle[M1],M1_CHARGE_BOOT_CAP_DUTY_CYCLES);
                TSK_SetChargeBootCapDelayM1(CHARGE_BOOT_CAP_TICKS);
                Mci[M1].State = CHARGE_BOOT_CAP;
              }
            }
            else
            {
              /* nothing to be done, FW waits for offset calibration to finish */
            }
          }
          break;
        }

        case CHARGE_BOOT_CAP:
        {
          if (MCI_STOP == Mci[M1].DirectCommand)
          {
            TSK_MF_StopProcessing(M1);
          }
          else
          {
            if (TSK_ChargeBootCapDelayHasElapsedM1())
            {
              R3_2_SwitchOffPWM(pwmcHandle[M1]);
              FOC_Clear( M1 );
              bACIM_MagnValidCount = 0;
              air56_start_flux_A = 0.0f;
              air56_magnetization_steps = 0;
              air56_magnetization_id = 0;
              air56_flux_checks = 0;
              air56_flux_saturated = 0;
              air56_flux_step = 0;
              air56_observer_loss_counts = 0.0f;
              air56_flux_record = (air56_flux_voltage_record){ .magic = AIR56_FLUX_VOLTAGE_MAGIC,
                  .start_ms = air56_lso_trace.start_ms };
              const int16_t voltage_limit = AIR56_FLUX_VOLTAGE_COUNTS(AIR56_FLUX_VOLTAGE_INITIAL);
              AIR56_CurrentPILimits(pPIDIq[M1], voltage_limit, T_KIDIV);
              AIR56_CurrentPILimits(pPIDId[M1], voltage_limit, F_KIDIV);
              air56_start_latest = (air56_start_sample){0};
              air56_start_q = (air56_start_q_record){ .magic = AIR56_START_Q_MAGIC,
                                                      .start_ms = air56_lso_trace.start_ms };
              ACIM_LSO_Clear(pACIM_LSO[M1]);
              air56_adc_stamp = DWT->CYCCNT;
              Mci[M1].State = START;
              R3_2_SwitchOnPWM(pwmcHandle[M1]);
            }
            else
            {
              /* nothing to be done, FW waits for bootstrap capacitor to charge */
            }
          }
          break;
        }

        case START:
        {
          if (MCI_STOP == Mci[M1].DirectCommand)
          {
            TSK_MF_StopProcessing(M1);
          }
          else
          {
#if (defined(DEBUG_LSO))
            Mci[M1].State = RUN;
#else /* If it is LSO-FOC without debug */
            /*ACIM_Magnetization stage in order to start the
            *speed control once the IM is magnetized.... */
            const uint32_t mask = __get_PRIMASK();
            __disable_irq();
            const air56_start_sample sample = air56_start_latest;
            __set_PRIMASK(mask);
            if (ACIM_IsMagnetized(&sample))
            {
              air56_flux_record.result = 1U;
              /* Use exactly the sample qualified above while the fast loop holds angle zero. */
              pACIM_LSO[M1]->fIqds_obs_A = Convert_s16_to_A(sample.current);
              pACIM_LSO[M1]->fFlux_qdr_obs.fS_Component2 = air56_start_flux_A;
              FOC_InitAdditionalMethods(M1);
              FOC_CalcCurrRef(M1);
              STC_ForceSpeedReferenceToCurrentSpeed(pSTC[M1]); /* Init the reference speed to current speed */
              MCI_ExecBufferedCommands(&Mci[M1]); /* Exec the speed ramp after changing of the speed sensor */
              const uint32_t handoff_mask = __get_PRIMASK();
              __disable_irq();
              AIR56_CurrentPILimits(pPIDIq[M1], INT16_MAX, T_KIDIV);
              AIR56_CurrentPILimits(pPIDId[M1], INT16_MAX, F_KIDIV);
              Mci[M1].State = RUN;
              __set_PRIMASK(handoff_mask);
              if (air56_lso_trace.active)
              {
                air56_start_record.stages |= AIR56_START_RUN_ENTERED;
                air56_start_record.run_enter_ms = HAL_GetTick();
                air56_start_record.ramp_command_state = (uint8_t)Mci[M1].CommandState;
                air56_start_record.speed_target = Mci[M1].hFinalSpeed;
              }
            }
            else if (air56_flux_checks >= AIR56_FLUX_TIMEOUT_STEPS)
            {
              air56_flux_record.result = 2U;
              LL_TIM_DisableAllOutputs(TIM1);
              MCI_FaultProcessing(&Mci[M1], MC_START_UP, 0U);
              air56_run_started = false;
              if (air56_lso_trace.active)
              {
                air56_lso_trace.first_fault = MC_START_UP;
                air56_capture_finish(AIR56_END_FAULT, HAL_GetTick());
              }
            }
#endif
          }
          break;
        }

        /* Nothing to do for ACIM No REVUP*/
        case SWITCH_OVER:
        {
          if (MCI_STOP == Mci[M1].DirectCommand)
          {
            TSK_MF_StopProcessing(M1);
          }
          else
          {
              /* USER CODE BEGIN MediumFrequencyTask M1 1 */

              /* USER CODE END MediumFrequencyTask M1 1 */
              Mci[M1].State = RUN;
          }
          break;
        }

        case RUN:
        {
          if (MCI_STOP == Mci[M1].DirectCommand)
          {
            TSK_MF_StopProcessing(M1);
          }
          else
          {
            /* USER CODE BEGIN MediumFrequencyTask M1 2 */

            /* USER CODE END MediumFrequencyTask M1 2 */
            MCI_ExecBufferedCommands(&Mci[M1]);
            #if (!defined(DEBUG_LSO))
            if(!ACIM_LSO_CheckIntegrity(pACIM_LSO[M1]))
            {
              MCI_FaultProcessing(&Mci[M1], MC_SPEED_FDBK, 0);
            }
            #endif
            FOC_CalcCurrRef(M1);
            if (air56_lso_trace.active)
            {
              const int16_t speed_ref = STC_GetMecSpeedRefUnit(pSTC[M1]);
              const int16_t iq_ref = FOCVars[M1].Iqdref.q;
              ++air56_start_record.run_checks;
              air56_start_record.speed_ref = speed_ref;
              if (speed_ref > air56_start_record.max_speed_ref) { air56_start_record.max_speed_ref = speed_ref; }
              if (iq_ref > air56_start_record.iq_ref_max) { air56_start_record.iq_ref_max = iq_ref; }
              air56_start_record.last_run_id = FOCVars[M1].Iqd.d;
              air56_start_record.last_run_iq = FOCVars[M1].Iqd.q;
            }

            /* USER CODE BEGIN MediumFrequencyTask M1 3 */

            /* USER CODE END MediumFrequencyTask M1 3 */
          }
          break;
        }

        case STOP:
        {

          R3_2_SwitchOffPWM(pwmcHandle[M1]);
          FOC_Clear(M1);
          ACIM_LSO_Clear(pACIM_LSO[M1]);

          /* USER CODE BEGIN MediumFrequencyTask M1 4 */

          /* USER CODE END MediumFrequencyTask M1 4 */

          if(TSK_StopPermanencyTimeHasElapsedM1())
          {
            Mci[M1].State = IDLE;
          }
          else
          {
            /* Nothing to do */
          }
          break;
        }

        case FAULT_OVER:
        {
          if (MCI_ACK_FAULTS == Mci[M1].DirectCommand)
          {
            Mci[M1].DirectCommand = MCI_NO_COMMAND;
            Mci[M1].State = IDLE;
          }
          else
          {
            /* nothing to do, FW stays in FAULT_OVER state until acknowledgement */
          }
          break;
        }

        case FAULT_NOW:
        {
          Mci[M1].State = FAULT_OVER;
          break;
        }

        default:
          break;
      }
    }
    else
    {
      Mci[M1].State = FAULT_OVER;
    }
  }
  else
  {
    Mci[M1].State = FAULT_NOW;
  }

  /* USER CODE BEGIN MediumFrequencyTask M1 6 */

  /* USER CODE END MediumFrequencyTask M1 6 */
}
/**
  * @brief  It re-initializes the current and voltage variables. Moreover
  *         it clears qd currents PI controllers, voltage sensor and SpeednTorque
  *         controller. It must be called before each motor restart.
  *         It does not clear speed sensor.
  * @param  bMotor related motor it can be M1 or M2
  */
__weak void FOC_Clear(uint8_t bMotor)
{
  /* USER CODE BEGIN FOC_Clear 0 */

  /* USER CODE END FOC_Clear 0 */

  ab_t        NULL_ab        = {(int16_t)0, (int16_t)0};
  qd_t        NULL_qd        = {(int16_t)0, (int16_t)0};
  alphabeta_t NULL_alphabeta = {(int16_t)0, (int16_t)0};

  FOCVars[bMotor].Iab = NULL_ab;
  FOCVars[bMotor].Ialphabeta = NULL_alphabeta;
  FOCVars[bMotor].Iqd = NULL_qd;
  FOCVars[bMotor].Iqdref = NULL_qd;
  FOCVars[bMotor].hTeref = (int16_t)0;
  FOCVars[bMotor].Vqd = NULL_qd;
  FOCVars[bMotor].Valphabeta = NULL_alphabeta;
  FOCVars[bMotor].hElAngle = (int16_t)0;

  PID_SetIntegralTerm(pPIDIq[bMotor], (int32_t)0);
  PID_SetIntegralTerm(pPIDId[bMotor], (int32_t)0);

  STC_Clear(pSTC[bMotor]);

  PWMC_SwitchOffPWM(pwmcHandle[bMotor]);

  /* USER CODE BEGIN FOC_Clear 1 */

  /* USER CODE END FOC_Clear 1 */
}

/**
  * @brief  Use this method to initialize additional methods (if any) in
  *         START_TO_RUN state
  * @param  bMotor related motor it can be M1 or M2
  */
__weak void FOC_InitAdditionalMethods(uint8_t bMotor)
{
  /* USER CODE BEGIN FOC_InitAdditionalMethods 0 */
    if (M_NONE == bMotor)
    {
      /* Nothing to do */
    }
  /* USER CODE END FOC_InitAdditionalMethods 0 */
}

/**
  * @brief  It computes the new values of Iqdref (current references on qd
  *         reference frame) based on the required electrical torque information
  *         provided by oTSC object (internally clocked).
  *         If implemented in the derived class it executes flux weakening and/or
  *         MTPA algorithm(s). It must be called with the periodicity specified
  *         in oTSC parameters
  * @param  bMotor related motor it can be M1 or M2
  */
__weak void FOC_CalcCurrRef(uint8_t bMotor)
{

  /* USER CODE BEGIN FOC_CalcCurrRef 0 */

  /* USER CODE END FOC_CalcCurrRef 0 */

  if(FOCVars[bMotor].bDriveInput == INTERNAL)
  {
    FOCVars[bMotor].hTeref = STC_CalcTorqueReference(pSTC[bMotor]);
    FOCVars[bMotor].Iqdref.q = FOCVars[bMotor].hTeref;
  }
  else
  {
    /* Nothing to do */
  }

  /* USER CODE BEGIN FOC_CalcCurrRef 1 */

  /* USER CODE END FOC_CalcCurrRef 1 */
}

/**
  * @brief  It set a counter intended to be used for counting the delay required
  *         for drivers boot capacitors charging of motor 1
  * @param  hTickCount number of ticks to be counted
  * @retval void
  */
__weak void TSK_SetChargeBootCapDelayM1(uint16_t hTickCount)
{
   hBootCapDelayCounterM1 = hTickCount;
}

/**
  * @brief  Use this function to know whether the time required to charge boot
  *         capacitors of motor 1 has elapsed
  * @param  none
  * @retval bool true if time has elapsed, false otherwise
  */
__weak bool TSK_ChargeBootCapDelayHasElapsedM1(void)
{
  bool retVal = false;

  if (hBootCapDelayCounterM1 == 0)
  {
    retVal = true;
  }
  else
  {
    /* Nothing to do */
  }

  return (retVal);
}

/**
  * @brief  It set a counter intended to be used for counting the permanency
  *         time in STOP state of motor 1
  * @param  hTickCount number of ticks to be counted
  * @retval void
  */
__weak void TSK_SetStopPermanencyTimeM1(uint16_t hTickCount)
{
  hStopPermanencyCounterM1 = hTickCount;
}

/**
  * @brief  Use this function to know whether the permanency time in STOP state
  *         of motor 1 has elapsed
  * @param  none
  * @retval bool true if time is elapsed, false otherwise
  */
__weak bool TSK_StopPermanencyTimeHasElapsedM1(void)
{
  bool retVal = false;
  if (hStopPermanencyCounterM1 == 0)
  {
    retVal = true;
  }
  else
  {
    /* Nothing to do */
  }
  return (retVal);
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
  * @brief  Executes the Motor Control duties that require a high frequency rate and a precise timing
  *
  *  This is mainly the FOC current control loop. It is executed depending on the state of the Motor Control
  * subsystem (see the state machine(s)).
  *
  * @retval Number of the  motor instance which FOC loop was executed.
  */
__attribute__((noinline)) static void AIR56_ObserverStep(ACIM_LSO_Handle_t *lso, float loss)
{
  enum { SIGN_RAMP = (int)(CURRENT_CONV_FACTOR * 0.035f) };
  const FOCVars_t *foc = lso->pFOCVars;
  const int32_t a = foc->Iab.a, b = foc->Iab.b, c = -a - b;
  const int32_t sa = a < -SIGN_RAMP ? -SIGN_RAMP : (a > SIGN_RAMP ? SIGN_RAMP : a);
  const int32_t sb = b < -SIGN_RAMP ? -SIGN_RAMP : (b > SIGN_RAMP ? SIGN_RAMP : b);
  const int32_t sc = c < -SIGN_RAMP ? -SIGN_RAMP : (c > SIGN_RAMP ? SIGN_RAMP : c);
  const Vector_s16_Components ab_loss = {
    (int16_t)(loss * ((float)(2 * sa - sb - sc) / (3.0f * SIGN_RAMP))),
    (int16_t)(loss * ((float)(sc - sb) * (RAD3DIV3 / SIGN_RAMP)))
  };
  const Vector_s16_Components dq_loss = MCM_Park_Generic(ab_loss, foc->hElAngle);
  qd_t correction;
  memcpy(&correction, &dq_loss, sizeof(correction));
  const int32_t q = (int32_t)foc->Vqd.q - correction.q, d = (int32_t)foc->Vqd.d - correction.d;
  ACIM_LSO_CalcAngleVoltage(lso, (qd_t){
    .q = q < -INT16_MAX ? -INT16_MAX : (q > INT16_MAX ? INT16_MAX : q),
    .d = d < -INT16_MAX ? -INT16_MAX : (d > INT16_MAX ? INT16_MAX : d)
  });
}

#if defined(CCMRAM) || defined(CCMRAM_ENABLED)
#if defined(__GNUC__)
__attribute__((section("ccmram")))
#endif
#endif
__weak uint8_t TSK_HighFrequencyTask(void)
{
  /* USER CODE BEGIN HighFrequencyTask 0 */

  /* USER CODE END HighFrequencyTask 0 */
  uint16_t returnValue;
  uint8_t bMotorNbr = 0;

  const uint32_t air56_begin = DWT->CYCCNT;
  if (Mci[M1].State == RUN)
  {
    AIR56_ObserverStep(pACIM_LSO[M1], air56_observer_loss_counts);
  }
  else if (Mci[M1].State != START)
  {
    ACIM_LSO_CalcAngle(pACIM_LSO[M1]);
  }
#if defined(DEBUG_LSO)
  float fFreqHz = (float) MCI_GetMecSpeedRef01Hz(oMCInterface[M1])/10.0f;
  ACIM_DBG_LSO_CalcAngle(pACIM_LSO[M1],fFreqHz);
#endif

  /* USER CODE BEGIN HighFrequencyTask SINGLEDRIVE_1 */

  /* USER CODE END HighFrequencyTask SINGLEDRIVE_1 */

  returnValue = AIR56_FieldReady() ? FOC_CurrControllerM1() : MC_SPEED_FDBK;

  /* USER CODE BEGIN HighFrequencyTask SINGLEDRIVE_2 */

  /* USER CODE END HighFrequencyTask SINGLEDRIVE_2 */
  if (Mci[M1].State == START || Mci[M1].State == RUN)
  {
    if (air56_lso_trace.active)
    {
      const unsigned row = air56_lso_trace.rows;
      const uint32_t before_log = DWT->CYCCNT;
      air56_trace_cycles(&air56_lso_trace, before_log, before_log - air56_begin, returnValue);
      air56_trace_total(&air56_lso_trace, row, DWT->CYCCNT - air56_begin);
    }
    if (DWT->CYCCNT - air56_begin > AIR56_LSO_FAST_CYCLES)
    {
      returnValue |= MC_DURATION;
      if (air56_lso_trace.active && !air56_lso_trace.first_fault)
      {
        air56_lso_trace.first_fault = returnValue;
      }
    }
  }
  if (returnValue != MC_NO_FAULTS)
  {
    LL_TIM_DisableAllOutputs(TIM1);
    MCI_FaultProcessing(&Mci[M1], returnValue, 0);
  }
  else
  {
    air56_adc_stamp = air56_begin;
    /* USER CODE BEGIN HighFrequencyTask SINGLEDRIVE_3 */

    /* USER CODE END HighFrequencyTask SINGLEDRIVE_3 */
  }

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
  * @brief It executes the core of FOC drive that is the controllers for Iqd
  *        currents regulation. Reference frame transformations are carried out
  *        accordingly to the active speed sensor. It must be called periodically
  *        when new motor currents have been converted
  * @param this related object of class CFOC.
  * @retval uint16_t It returns MC_NO_FAULTS if the FOC has been ended before
  *         next PWM Update event, MC_DURATION otherwise
  */

static inline alphabeta_t AIR56_CurrentVoltage(ab_t ab, int16_t angle,
    FOCVars_t *foc, PID_Handle_t *pid_q, PID_Handle_t *pid_d, int16_t id_ref)
{
  const alphabeta_t alpha_beta = MCM_Clarke(ab);
  Vector_s16_Components vector;
  memcpy(&vector, &alpha_beta, sizeof(vector));
  vector = MCM_Park_Generic(vector, angle);
  qd_t measured;
  memcpy(&measured, &vector, sizeof(measured));

  int32_t iq = foc->Iqdref.q;
  if (iq < 0) { iq = 0; }
  if (iq > IQMAX) { iq = IQMAX; }
  const qd_t voltage = {
    .q = PI_Controller(pid_q, iq - measured.q),
    .d = PI_Controller(pid_d, (int32_t)id_ref - measured.d)
  };
  const qd_t limited = Circle_Limitation(&CircleLimitationM1, voltage);
  memcpy(&vector, &limited, sizeof(vector));
  vector = MCM_Rev_Park_Generic(vector, angle);
  alphabeta_t command;
  memcpy(&command, &vector, sizeof(command));

  foc->Iab = ab;
  foc->Ialphabeta = alpha_beta;
  foc->Iqd = measured;
  foc->Vqd = limited;
  foc->Valphabeta = command;
  foc->hElAngle = angle;
  return command;
}

inline uint16_t FOC_CurrControllerM1(void)
{
  ab_t measured;
  PWMC_GetPhaseCurrents(pwmcHandle[M1], &measured);
  if (air56_lso_trace.active && (Mci[M1].State == START || Mci[M1].State == RUN))
  {
    air56_trace_current(&air56_lso_trace, measured.a, measured.b);
  }
  if ((Mci[M1].State == START || Mci[M1].State == RUN) &&
      air56_lso_overcurrent(measured.a, measured.b))
  {
    LL_TIM_DisableAllOutputs(TIM1);
    air56_save_overcurrent(&measured);
    return MC_OVER_CURR;
  }
  const bool magnetizing = Mci[M1].State == START;
  const int16_t angle = magnetizing ? 0 : ACIM_LSO_GetElAngle(pACIM_LSO[M1]);
  const int16_t id_ref = magnetizing ? air56_magnetization_id : DEFAULT_FLUX_COMPONENT_A;
  const alphabeta_t applied = AIR56_CurrentVoltage(measured, angle, &FOCVars[M1], pPIDIq[M1], pPIDId[M1], id_ref);
  if (Mci[M1].State == START)
  {
    air56_start_latest = (air56_start_sample){ .current = FOCVars[M1].Iqd, .voltage = FOCVars[M1].Vqd,
                 .adc_pair = air56_trip_raw_pair, .sector = pwmcHandle[M1]->Sector };
  }
  return PWMC_SetPhaseVoltage(pwmcHandle[M1], applied);
}

/* Independent RAM-backed devices. Only register reads use real TIM1/ADC. */
static TIM_TypeDef air56_test_tim;
static ADC_TypeDef air56_test_adc1, air56_test_adc2;
static R3_2_Params_t air56_test_params = {
  .TIMx = &air56_test_tim, .Tafter = TW_AFTER, .Tbefore = TW_BEFORE,
  .ADCDataReg1 = { &air56_test_adc1, &air56_test_adc1, &air56_test_adc1,
                  &air56_test_adc1, &air56_test_adc1, &air56_test_adc1 },
  .ADCDataReg2 = { &air56_test_adc2, &air56_test_adc2, &air56_test_adc2,
                  &air56_test_adc2, &air56_test_adc2, &air56_test_adc2 }
};

enum { AIR56_DWT_CASES = 64, AIR56_DWT_ITERATIONS = 8 };
volatile struct {
  uint32_t format, cases_done, max_cycles, max_lso_cycles, failures;
  uint32_t cycles[AIR56_DWT_CASES], lso_cycles[AIR56_DWT_CASES];
} air56_off_dwt = { .format = 0x414C5331U };

bool AIR56_OffDwtReady(void)
{
  return air56_off_dwt.cases_done == AIR56_DWT_CASES && air56_off_dwt.failures == 0;
}

void AIR56_OffDwtService(void)
{
  static uint32_t last_ms;
  const uint32_t index = air56_off_dwt.cases_done;
  const uint32_t now = HAL_GetTick();
  if (index >= AIR56_DWT_CASES || now == last_ms ||
      (TIM1->BDTR & (TIM_BDTR_MOE | TIM_BDTR_AOE | TIM_BDTR_BKE)) != TIM_BDTR_BKE ||
      VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super) >= 20U)
  {
    return;
  }
  last_ms = now;

  FOCVars_t foc = {0};
  PID_Handle_t id = *pPIDId[M1], iq = *pPIDIq[M1];
  PI_Float_Handle_t speed = *pACIM_LSO[M1]->fPI;
  ACIM_LSO_Handle_t lso = *pACIM_LSO[M1];
  BusVoltageSensor_Handle_t bus = BusVoltageSensor_M1._Super;
  PWMC_R3_2_Handle_t pwm = PWM_Handle_M1;
  pwm.pParams_str = &air56_test_params;
  pwm._Super.pFctGetPhaseCurrents = &R3_2_GetPhaseCurrents;
  pwm._Super.pFctSetADCSampPointSectX = &R3_2_SetADCSampPointSectX;
  pwm.PhaseAOffset = pwm.PhaseBOffset = pwm.PhaseCOffset = 32768U;
  id.wIntegralTerm = iq.wIntegralTerm = 0;
  bus.AvBusVoltage_d = (uint16_t)(((index & 16U ? 350U : 250U) * 65536U) / bus.ConversionFactor);
  lso.pFOCVars = &foc;
  lso.fPI = &speed;
  ACIM_LSO_Init(&lso, &bus);
  ACIM_LSO_Clear(&lso);
  lso.fFlux_qdr_obs.fS_Component2 = (index & 8U) ? 0.50f : 0.05f;
  lso.fRotorFlux_Angle_rad = (float)(index % 16U) * 0.3926990817f;
  if (index & 32U) { lso.fRotorFlux_Angle_rad = 6.282f; }
  lso.fIqds_obs_A.fS_Component1 = 0.12f;
  lso.fIqds_obs_A.fS_Component2 = 0.40f;
  foc.Iqdref.q = (index & 8U) ? IQMAX : 0;
  foc.Iqd.q = 200;
  foc.Iqd.d = DEFAULT_FLUX_COMPONENT_A;
  foc.Vqd.q = (index & 16U) ? 26000 : 900;
  foc.Vqd.d = (index & 16U) ? 15000 : 1400;
  const int32_t a = (int32_t)((index % 8U) * 290U) - 1000;
  const int32_t b = (index & 8U) ? 625 : -525;
  const int32_t c = -a - b;
  uint32_t worst = 0, worst_lso = 0;
  uint16_t code = MC_NO_FAULTS;
  for (uint32_t j = 0; j < AIR56_DWT_ITERATIONS; ++j)
  {
    const uint8_t sector = (uint8_t)((index + j) % 6U);
    pwm._Super.Sector = sector;
    air56_test_adc1.JDR1 = (uint32_t)(32768 - (sector == SECTOR_1 || sector == SECTOR_6 ? b : a));
    air56_test_adc2.JDR1 = (uint32_t)(32768 - (sector == SECTOR_4 || sector == SECTOR_5 ? b : c));
    ab_t measured;
    // Include the row publication path in every OFF qualification case.
    air56_lso_trace.rows = 0;
    air56_lso_trace.count = AIR56_TRACE_WINDOW - 1U;
    air56_lso_trace.peak_a = air56_lso_trace.peak_b = air56_lso_trace.peak_c = 0;
    air56_lso_trace.window_max = 0;
    foc.Iab = (ab_t){ .a = a, .b = b };
    const uint32_t begin = DWT->CYCCNT;
    AIR56_ObserverStep(&lso, AIR56_FLUX_VOLTAGE_COUNTS(14.0f));
    const uint32_t lso_cycles = DWT->CYCCNT - begin;
    /* Exercise window closure and division on every OFF timing case. */
    const float test_field = (index & 2U) ? 13.0f : 20.0f;
    air56_field_guard guard = { .initialized = true, .flux_counts = 843.0f,
      .frames = AIR56_FIELD_WINDOW - 1U, .field_sum = (AIR56_FIELD_WINDOW - 1U) * test_field,
      .rotor_sum = (AIR56_FIELD_WINDOW - 1U) * 7.0f,
      .reference_sum = (AIR56_FIELD_WINDOW - 1U) * 1.2f,
      .iq_sum = (AIR56_FIELD_WINDOW - 1U) * 243, .iq_ref_sum = (AIR56_FIELD_WINDOW - 1U) * 300 };
    air56_field_fault field_fault;
    const unsigned guard_result = air56_field_check(&guard, (qd_t){ .q = 243, .d = 843 },
                                                    300, 1.2f, test_field, 7.0f, &field_fault);
    if (guard_result != ((index & 2U) ? 0U : AIR56_FIELD_SLIP_DISAGREEMENT)) { code |= MC_SW_ERROR; }
    PWMC_GetPhaseCurrents(&pwm._Super, &measured);
    air56_trace_current(&air56_lso_trace, measured.a, measured.b);
    if (air56_lso_overcurrent(measured.a, measured.b)) { code |= MC_OVER_CURR; }
    const alphabeta_t applied = AIR56_CurrentVoltage(measured,
        ACIM_LSO_GetElAngle(&lso), &foc, &iq, &id, DEFAULT_FLUX_COMPONENT_A);
    code |= PWMC_SetPhaseVoltage(&pwm._Super, applied);
    const uint32_t before_log = DWT->CYCCNT;
    air56_trace_cycles(&air56_lso_trace, before_log, before_log - begin, code);
    air56_trace_total(&air56_lso_trace, 0U, DWT->CYCCNT - begin);
    const uint32_t cycles = DWT->CYCCNT - begin;
    if (cycles > worst) { worst = cycles; }
    if (lso_cycles > worst_lso) { worst_lso = lso_cycles; }
  }
  if (!worst || worst > AIR56_LSO_FAST_CYCLES || code != MC_NO_FAULTS)
  {
    ++air56_off_dwt.failures;
  }
  if (worst > air56_off_dwt.max_cycles) { air56_off_dwt.max_cycles = worst; }
  if (worst_lso > air56_off_dwt.max_lso_cycles) { air56_off_dwt.max_lso_cycles = worst_lso; }
  air56_off_dwt.cycles[index] = worst;
  air56_off_dwt.lso_cycles[index] = worst_lso;
  __DMB();
  air56_off_dwt.cases_done = index + 1U;
}


/**
  * @brief  Executes safety checks (e.g. bus voltage and temperature) for all drive instances.
  *
  * Faults flags are updated here.
  */
__weak void TSK_SafetyTask(void)
{
  /* USER CODE BEGIN TSK_SafetyTask 0 */

  /* USER CODE END TSK_SafetyTask 0 */
  if (bMCBootCompleted == 1)
  {
    TSK_SafetyTask_PWMOFF(M1);

  /* USER CODE BEGIN TSK_SafetyTask 1 */

  /* USER CODE END TSK_SafetyTask 1 */
  }
  else
  {
    /* Nothing to do */
  }
}

/**
  * @brief  Safety task implementation if  MC.M1_ON_OVER_VOLTAGE == TURN_OFF_PWM
  * @param  bMotor Motor reference number defined
  *         \link Motors_reference_number here \endlink
  */
__weak void TSK_SafetyTask_PWMOFF(uint8_t bMotor)
{
  /* USER CODE BEGIN TSK_SafetyTask_PWMOFF 0 */

  /* USER CODE END TSK_SafetyTask_PWMOFF 0 */

   uint16_t CodeReturn = MC_NO_ERROR;
   uint8_t lbMotor = M1;
  const uint16_t errMask[NBR_OF_MOTORS] = {VBUS_TEMP_ERR_MASK};
  /* Check for fault if FW protection is activated. It returns MC_OVER_TEMP or MC_NO_ERROR */
  if (M1 == bMotor)
  {
    uint16_t rawValueM1 = RCM_ExecRegularConv(&TempRegConv_M1);
    CodeReturn |= errMask[bMotor] & NTC_CalcAvTemp(&TempSensor_M1, rawValueM1);
  }
  else
  {
    /* Nothing to do */
  }

  /* Due to warning array subscript 1 is above array bounds of PWMC_Handle_t *[1] [-Warray-bounds] */
   CodeReturn |= PWMC_IsFaultOccurred(pwmcHandle[lbMotor]);     /* check for fault. It return MC_OVER_CURR or MC_NO_FAULTS
                                                     (for STM32F30x can return MC_OVER_VOLT in case of HW Overvoltage) */

  if (M1 == bMotor)
  {
    uint16_t rawValueM1 =  RCM_ExecRegularConv(&VbusRegConv_M1);
    CodeReturn |= errMask[bMotor] & RVBS_CalcAvVbus(&BusVoltageSensor_M1, rawValueM1);
  }
  else
  {
    /* Nothing to do */
  }
  MCI_FaultProcessing(&Mci[bMotor], CodeReturn, ~CodeReturn); /* process faults */

  if (MCI_GetFaultState(&Mci[bMotor]) != (uint32_t)MC_NO_FAULTS)
  {
    PWMC_SwitchOffPWM(pwmcHandle[bMotor]);
    FOC_Clear(bMotor);

    if (MCPA_UART_A.Mark != 0)
    {
      MCPA_flushDataLog (&MCPA_UART_A);
    }
    else
    {
      /* Nothing to do */
    }

    PQD_Clear(pMPM[bMotor]); //cstat !MISRAC2012-Rule-11.3

    /* USER CODE BEGIN TSK_SafetyTask_PWMOFF 1 */

    /* USER CODE END TSK_SafetyTask_PWMOFF 1 */
  }
  else
  {
    /* no errors */
  }

  /* USER CODE BEGIN TSK_SafetyTask_PWMOFF 3 */

  /* USER CODE END TSK_SafetyTask_PWMOFF 3 */
}

/**
  * @brief  Safety task implementation if  MC.M1_ON_OVER_VOLTAGE == TURN_ON_R_BRAKE
  * @param  motor Motor reference number defined
  *         \link Motors_reference_number here \endlink
  */
__weak void TSK_SafetyTask_RBRK(uint8_t bMotor)
{
  /* USER CODE BEGIN TSK_SafetyTask_RBRK 0 */

  /* USER CODE END TSK_SafetyTask_RBRK 0 */
  uint16_t CodeReturn = MC_NO_ERROR;
  uint16_t BusVoltageFaultsFlag = MC_OVER_VOLT;
  uint8_t lbMotor = M1;

  uint16_t errMask[NBR_OF_MOTORS] = {VBUS_TEMP_ERR_MASK};
  /* Brake resistor management */
  if (M1 == bMotor)
  {
    uint16_t rawValueM1 =  RCM_ExecRegularConv(&VbusRegConv_M1);
    BusVoltageFaultsFlag =  errMask[bMotor] & RVBS_CalcAvVbus(&BusVoltageSensor_M1, rawValueM1);
  }
  else
  {
    /* Nothing to do */
  }

  if (MC_OVER_VOLT == BusVoltageFaultsFlag)
  {
    DOUT_SetOutputState(pR_Brake[lbMotor], ACTIVE);
  }
  else
  {
    DOUT_SetOutputState(pR_Brake[lbMotor], INACTIVE);
  }
  /* Check for fault if FW protection is activated. It returns MC_OVER_TEMP or MC_NO_ERROR */
  if (M1 == bMotor)
  {
    uint16_t rawValueM1 = RCM_ExecRegularConv(&TempRegConv_M1);
    CodeReturn |= errMask[bMotor] & NTC_CalcAvTemp(&TempSensor_M1, rawValueM1);
  }
  else
  {
    /* Nothing to do */
  }

  CodeReturn |= PWMC_IsFaultOccurred (pwmcHandle[bMotor]);    /* check for fault. It return MC_OVER_CURR or MC_NO_FAULTS
                                                                 (for STM32F30x can return MC_OVER_VOLT in case of HW Overvoltage) */
  CodeReturn |= (BusVoltageFaultsFlag & MC_UNDER_VOLT);       /* MC_UNDER_VOLT generates fault if FW protection is activated,
                                                                 MC_OVER_VOLT doesn't generate fault */
  MCI_FaultProcessing(&Mci[bMotor], CodeReturn, ~CodeReturn); /* Update the STM according error code */

  if (MCI_GetFaultState(&Mci[bMotor]) != (uint32_t)MC_NO_FAULTS)
  {

    PWMC_SwitchOffPWM(pwmcHandle[bMotor]);
    FOC_Clear(bMotor);
    if (MCPA_UART_A.Mark != 0)
    { /* Dual motor not yet supported */
      MCPA_flushDataLog (&MCPA_UART_A);
    }
    else
    {
      /* Nothing to do */
    }

    PQD_Clear(pMPM[bMotor]); //cstat !MISRAC2012-Rule-11.3
    /* USER CODE BEGIN TSK_SafetyTask_RBRK 1 */

    /* USER CODE END TSK_SafetyTask_RBRK 1 */
  }
  /* USER CODE BEGIN TSK_SafetyTask_RBRK 2 */

  /* USER CODE END TSK_SafetyTask_RBRK 2 */
}

/**
  * @brief  This function returns the reference of the MCInterface relative to
  *         the selected drive.
  * @param  bMotor Motor reference number defined
  *         \link Motors_reference_number here \endlink
  * @retval MCI_Handle_t * Reference to MCInterface relative to the selected drive.
  *         Note: it can be MC_NULL if MCInterface of selected drive is not
  *         allocated.
  */
__weak MCI_Handle_t * GetMCI(uint8_t bMotor)
{
  MCI_Handle_t * retVal = MC_NULL;
  if (bMotor < NBR_OF_MOTORS)
  {
    retVal = &Mci[bMotor];
  }
  else
  {
    /* Nothing to do */
  }
  return retVal;
}

/**
  * @brief  Puts the Motor Control subsystem in in safety conditions on a Hard Fault
  *
  *  This function is to be executed when a general hardware failure has been detected
  * by the microcontroller and is used to put the system in safety condition.
  */
__weak void TSK_HardwareFaultTask(void)
{
  /* USER CODE BEGIN TSK_HardwareFaultTask 0 */

  /* USER CODE END TSK_HardwareFaultTask 0 */

  R3_2_SwitchOffPWM(pwmcHandle[M1]);
  MCI_FaultProcessing(&Mci[M1], MC_SW_ERROR, 0);

  /* USER CODE BEGIN TSK_HardwareFaultTask 1 */

  /* USER CODE END TSK_HardwareFaultTask 1 */
}

__weak void UI_HandleStartStopButton_cb (void)
{
/* USER CODE BEGIN START_STOP_BTN */
  /* The local button is STOP only. The Uno link owns trial starts. */
  (void)MCI_StopMotor(&Mci[M1]);
/* USER CODE END START_STOP_BTN */
}

 /**
  * @brief  Locks GPIO pins used for Motor Control to prevent accidental reconfiguration
  */
__weak void mc_lock_pins (void)
{
LL_GPIO_LockPin(M1_CURR_AMPL_U_GPIO_Port, M1_CURR_AMPL_U_Pin);
LL_GPIO_LockPin(M1_CURR_AMPL_V_GPIO_Port, M1_CURR_AMPL_V_Pin);
LL_GPIO_LockPin(M1_CURR_AMPL_W_GPIO_Port, M1_CURR_AMPL_W_Pin);
LL_GPIO_LockPin(M1_PWM_UL_GPIO_Port, M1_PWM_UL_Pin);
LL_GPIO_LockPin(M1_PWM_UH_GPIO_Port, M1_PWM_UH_Pin);
LL_GPIO_LockPin(M1_PWM_VL_GPIO_Port, M1_PWM_VL_Pin);
LL_GPIO_LockPin(M1_PWM_VH_GPIO_Port, M1_PWM_VH_Pin);
LL_GPIO_LockPin(M1_PWM_WL_GPIO_Port, M1_PWM_WL_Pin);
LL_GPIO_LockPin(M1_PWM_WH_GPIO_Port, M1_PWM_WH_Pin);
LL_GPIO_LockPin(M1_OCP_GPIO_Port, M1_OCP_Pin);
LL_GPIO_LockPin(M1_BUS_VOLTAGE_GPIO_Port, M1_BUS_VOLTAGE_Pin);
LL_GPIO_LockPin(M1_TEMPERATURE_GPIO_Port, M1_TEMPERATURE_Pin);
}

/* USER CODE BEGIN mc_task 0 */

/* USER CODE END mc_task 0 */

static bool ACIM_IsMagnetized(const air56_start_sample *sample)
{
  FOCVars[M1].Iqdref = STC_GetDefaultIqdref(pSTC[M1]);
  const qd_t current = sample->current;
  const float id_A = Convert_s16_to_A(current).fS_Component2;
  const float previous_flux = air56_start_flux_A;
  /* In the stationary frame lambda_r / Lm follows Id with the rotor time constant. */
  air56_start_flux_A += (id_A - air56_start_flux_A) / (MEDIUM_FREQUENCY_TASK_RATE * TAU_R);

  const int16_t id_ref = FOCVars[M1].Iqdref.d;
  if (air56_magnetization_steps < AIR56_MAGNETIZATION_STEPS)
  {
    ++air56_magnetization_steps;
    air56_magnetization_id = (int16_t)(DEFAULT_FLUX_COMPONENT_A * air56_magnetization_steps / AIR56_MAGNETIZATION_STEPS);
  }
  const int16_t id = current.d;
  const int16_t id_low = (int16_t)((float)id_ref * LOWER_BW_LIMIT_PERC);
  const int16_t id_high = (int16_t)((float)id_ref * UPPER_BW_LIMIT_PERC);
  const bool in_band = id >= id_low && id <= id_high;
  /* At the minimum qualified flux, the seeded Iq must explain at most the
   * already allowed 0.75 Hz of slip in the first observer step. */
  const int16_t iq_limit = (int16_t)(id_low * TAU_R * AIR56_FIELD_RAD_PER_TURN * AIR56_FIELD_MARGIN_HZ);
  const bool iq_ready = current.q >= -iq_limit && current.q <= iq_limit;
  ++air56_flux_checks;
  /* At 16 kHz an effective 1.35–2 us switching interval can cost 7–11 V per
   * pole at the operating bus. Leave Iq authority unchanged. Release only the
   * positive Id clamp, in 2 V steps, after measured sustained saturation.
   * The 24 V ceiling covers the d-axis switching loss plus Rs * Id.
   */
  const int16_t limit = AIR56_FLUX_VOLTAGE_COUNTS(AIR56_FLUX_VOLTAGE_INITIAL +
      AIR56_FLUX_VOLTAGE_STEP * air56_flux_step);
  if (air56_flux_step < AIR56_FLUX_VOLTAGE_STEPS &&
      air56_magnetization_steps == AIR56_MAGNETIZATION_STEPS && id < id_low &&
      air56_abs_i16(current.q) <= AIR56_FLUX_IQ_FOR_STEP && sample->voltage.d == limit)
  {
    if (air56_flux_saturated == 0U) { air56_flux_id_sum = air56_flux_iq_sum = 0; }
    air56_flux_id_sum += id;
    air56_flux_iq_sum += current.q;
    if (++air56_flux_saturated == AIR56_FLUX_SATURATION_STEPS)
    {
      air56_flux_record.id_mean[air56_flux_step] = air56_flux_id_sum / AIR56_FLUX_SATURATION_STEPS;
      air56_flux_record.iq_mean[air56_flux_step] = air56_flux_iq_sum / AIR56_FLUX_SATURATION_STEPS;
      air56_flux_record.steps = ++air56_flux_step;
      const int16_t updated = AIR56_FLUX_VOLTAGE_COUNTS(AIR56_FLUX_VOLTAGE_INITIAL +
          AIR56_FLUX_VOLTAGE_STEP * air56_flux_step);
      const uint32_t mask = __get_PRIMASK();
      __disable_irq();
      PID_SetUpperIntegralTermLimit(pPIDId[M1], (int32_t)updated * F_KIDIV);
      PID_SetUpperOutputLimit(pPIDId[M1], updated);
      __set_PRIMASK(mask);
      air56_flux_saturated = 0U;
    }
  }
  else
  {
    air56_flux_saturated = 0U;
  }
  if (air56_magnetization_steps == AIR56_MAGNETIZATION_STEPS && in_band && iq_ready)
  {
    if (bACIM_MagnValidCount == 0U)
    {
      air56_flux_window_id = id_A;
      air56_flux_window_flux = previous_flux;
      air56_flux_residual_sum = 0.0f;
    }
    /* Estimate from the most recent complete qualification window.
     * Mean applied d voltage minus Rs*Id and change in stator flux estimates
     * the inverter drop. V and W carry opposite current in this fixed frame.
     */
    const float bus = VBS_GetAvBusVoltage_V(pACIM_LSO[M1]->pBVS);
    const float volts_per_count = bus * (RAD3DIV3 / 32767.0f);
    air56_flux_residual_sum += sample->voltage.d * volts_per_count - (float)RS * id_A;
    if (++bACIM_MagnValidCount == MAGN_VALIDATION_TICKS)
    {
      const float stator_flux_change = SIGMA * LS * (id_A - air56_flux_window_id) +
          (LM * LM / LR) * (air56_start_flux_A - air56_flux_window_flux);
      const float d_loss = (air56_flux_residual_sum - MEDIUM_FREQUENCY_TASK_RATE * stator_flux_change) /
          MAGN_VALIDATION_TICKS;
      const float pole_loss = 0.866025404f * d_loss;
      const float bounded = pole_loss < 0.0f ? 0.0f : (pole_loss > 14.0f ? 14.0f : pole_loss);
      air56_observer_loss_counts = bus > 0.0f ? bounded / volts_per_count : 0.0f;
      air56_flux_record.observer_loss_mV = (uint16_t)(1000.0f * bounded + 0.5f);
    }
  }
  else
  {
    bACIM_MagnValidCount = 0;
  }
  if (air56_lso_trace.active)
  {
    if (!air56_start_record.checks)
    {
      air56_start_record.stages |= AIR56_START_CHECK_SEEN;
      air56_start_record.first_check_ms = HAL_GetTick();
    }
    ++air56_start_record.checks;
    if (in_band) { ++air56_start_record.in_band; }
    air56_start_record.id_ref = id_ref;
    air56_start_record.iq_ref = FOCVars[M1].Iqdref.q;
    air56_start_record.id_low = id_low;
    air56_start_record.id_high = id_high;
    air56_start_record.id_last = id;
    air56_start_record.iq_last = current.q;
    ++air56_start_q.samples;
    air56_start_q.iq_limit = iq_limit;
    if (in_band && !iq_ready) { ++air56_start_q.q_blocks; }
    if (air56_start_q.samples == 1 || air56_abs_i16(current.q) > air56_abs_i16(air56_start_q.iq_peak))
    {
      air56_start_q.peak_ms = HAL_GetTick();
      air56_start_q.adc_pair = sample->adc_pair;
      air56_start_q.sector = sample->sector;
      air56_start_q.iq_peak = current.q;
      air56_start_q.id_at_peak = current.d;
      air56_start_q.vq_at_peak = sample->voltage.q;
      air56_start_q.vd_at_peak = sample->voltage.d;
    }
    air56_start_record.last_streak = bACIM_MagnValidCount;
    if (id < air56_start_record.id_min) { air56_start_record.id_min = id; }
    if (id > air56_start_record.id_max) { air56_start_record.id_max = id; }
    if (bACIM_MagnValidCount > air56_start_record.max_streak)
    {
      air56_start_record.max_streak = bACIM_MagnValidCount;
    }
  }

  if (bACIM_MagnValidCount < MAGN_VALIDATION_TICKS) { return false; }
  if (air56_start_flux_A >= Convert_s16_to_A((qd_t){ .d = id_low }).fS_Component2 &&
      air56_start_flux_A <= Convert_s16_to_A((qd_t){ .d = id_high }).fS_Component2)
  {
    return true;
  }
  bACIM_MagnValidCount = 0;
  return false;
}

/* USER CODE BEGIN mc_task 0 */

/* USER CODE END mc_task 0 */
/******************* (C) COPYRIGHT 2026 STMicroelectronics *****END OF FILE****/

#include "air56_lso_uno.inc"
