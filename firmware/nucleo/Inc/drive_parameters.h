
/**
  ******************************************************************************
  * @file    drive_parameters.h
  * @author  Motor Control SDK Team, ST Microelectronics
  * @brief   This file contains the parameters needed for the Motor Control SDK
  *          in order to configure a motor drive.
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

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef DRIVE_PARAMETERS_H
#define DRIVE_PARAMETERS_H

/* ACIM mode: define here the control mode as one of the following selection (MAIN_IFOC, MAIN_LSO_FOC, MAIN_VF_OL, MAIN_VF_CL) */
#define MAIN_LSO_FOC

/* PWM frequency */
#define PWM_FREQUENCY                     16000
#define REGULATION_EXECUTION_RATE         1 /*!< FOC execution rate in number of PWM cycles */

/*** Speed measurement settings ***/
#define MAX_APPLICATION_SPEED_RPM         300 /*!< rpm, mechanical */

/* Currents regulators bandwidth */
#define CURRENT_CTRL_BANDWIDTH            400.0 /* Expressed in rad/s */

/* Gains values for torque and flux control loops */
#define PID_TORQUE_KP_DEFAULT             22328
#define PID_TORQUE_KI_DEFAULT             1048

#define PID_FLUX_KP_DEFAULT               22328
#define PID_FLUX_KI_DEFAULT               1992

/* Torque/Flux control loop gains dividers*/
#define T_KPDIV                           8192
#define T_KIDIV                           32768

#define T_KPDIV_LOG                       LOG2(T_KPDIV)
#define T_KIDIV_LOG                       LOG2(T_KIDIV)

#define F_KPDIV                           8192
#define F_KIDIV                           32768

#define F_KPDIV_LOG                       LOG2(F_KPDIV)
#define F_KIDIV_LOG                       LOG2(F_KIDIV)

/* Number of consecutive Speed Loop task ticks when the measured Id current is into the [Low BW limit, UP BW limit]
   bandwidth. It is used at any startup to magnetize the motor. */
#define MAGN_VALIDATION_TICKS             10
#define LOWER_BW_LIMIT_PERC               ((float)(0.7))
#define UPPER_BW_LIMIT_PERC               ((float)(1.3))

#define SPEED_LOOP_FREQUENCY_HZ           500 /* Execution rate of speed regulation loop (Hz) */

/* Speed control loop */
#define SPEED_CTRL_BANDWIDTH              12.0 /* Expressed in rad/s */
#define PID_SPEED_KP_DEFAULT              29344
#define PID_SPEED_KI_DEFAULT              346

/* Speed PID parameter dividers */
#define SP_KPDIV                          4096
#define SP_KIDIV                          32768
#define SP_KPDIV_LOG                      LOG2(4096)
#define SP_KIDIV_LOG                      LOG2(32768)

/* Max Output of PI speed regulator*/
#define IQMAX                             1033
#define DEFAULT_FLUX_COMPONENT_A           843

#define DEFAULT_TARGET_SPEED_RPM          0

/************************
 *** Motor Parameters ***
 ************************/

/******** MAIN AND AUXILIARY SPEED/POSITION SENSOR(S) SETTINGS SECTION ********/

/*** Speed measurement settings ***/
#define MIN_APPLICATION_SPEED_RPM         0 /*!< rpm, mechanical,
                                                           absolute value */
#define M1_SS_MEAS_ERRORS_BEFORE_FAULTS         3 /*!< Number of speed
                                                             measurement errors before
                                                             main sensor goes in fault */

/* USER CODE BEGIN angle reconstruction M1 */
#define REV_PARK_ANGLE_COMPENSATION_FACTOR 0
/* USER CODE END angle reconstruction M1 */

/**************************    DRIVE SETTINGS SECTION   **********************/
/* PWM generation and current reading */
#define PWM_FREQ_SCALING 1
#define LOW_SIDE_SIGNALS_ENABLING         LS_PWM_TIMER
#define SW_DEADTIME_NS                    1350 /*!< Dead-time to be inserted
                                                           by FW, only if low side
                                                           signals are enabled */

/* Torque and flux regulation loops */
/* Gains values for torque and flux control loops */
#define PID_TORQUE_KD_DEFAULT             100
#define PID_FLUX_KD_DEFAULT               100

/* Torque/Flux control loop gains dividers*/
#define TF_KPDIV                          2048
#define TF_KIDIV                          16384
#define TF_KDDIV                          8192
#define TF_KPDIV_LOG                      LOG2(2048)
#define TF_KIDIV_LOG                      LOG2(16384)
#define TF_KDDIV_LOG                      LOG2(8192)
#define TFDIFFERENTIAL_TERM_ENABLING      DISABLE
#define PID_SPEED_KD_DEFAULT              0/(SPEED_UNIT/10) /* Workbench compute the gain for 01Hz unit*/

/* Speed PID parameter dividers */
#define SP_KDDIV                          16
#define SP_KDDIV_LOG                      LOG2(16)

/* USER CODE BEGIN PID_SPEED_INTEGRAL_INIT_DIV */
#define PID_SPEED_INTEGRAL_INIT_DIV       1 /*  */
/* USER CODE END PID_SPEED_INTEGRAL_INIT_DIV */

#define SPD_DIFFERENTIAL_TERM_ENABLING DISABLE

/* Default settings */
#define DEFAULT_CONTROL_MODE              MCM_SPEED_MODE

#define DEFAULT_TARGET_SPEED_UNIT         (DEFAULT_TARGET_SPEED_RPM*SPEED_UNIT/U_RPM)
#define DEFAULT_TORQUE_COMPONENT_A        0

/**************************    FIRMWARE PROTECTIONS SECTION   *****************/
#define OV_VOLTAGE_THRESHOLD_V            350 /*!< Over-voltage threshold */
#define UD_VOLTAGE_THRESHOLD_V            250 /*!< Under-voltage threshold */
#if NOT_IMPLEMENTED
#define ON_OVER_VOLTAGE                   TURN_OFF_PWM /*!< TURN_OFF_PWM, TURN_ON_R_BRAKE or TURN_ON_LOW_SIDES */
#endif /* NOT_IMPLEMENTED */
#define OV_TEMPERATURE_THRESHOLD_C        100 /*!< Celsius degrees */
#define OV_TEMPERATURE_HYSTERESIS_C       10 /*!< Celsius degrees */
#define HW_OV_CURRENT_PROT_BYPASS         DISABLE /*!< In case ON_OVER_VOLTAGE
                                                          is set to TURN_ON_LOW_SIDES
                                                          this feature may be used to
                                                          bypass HW over-current
                                                          protection (if supported by
                                                          power stage) */

/******************************   START-UP PARAMETERS   **********************/

#define TRANSITION_DURATION               25  /* Switch over duration, ms */

/******************************   BUS VOLTAGE Motor 1  **********************/
#define  M1_VBUS_SAMPLING_TIME            LL_ADC_SAMPLING_CYCLE(47)

/******************************   Temperature sensing Motor 1  **********************/
#define  M1_TEMP_SAMPLING_TIME            LL_ADC_SAMPLING_CYCLE(47)

/******************************   Current sensing Motor 1   **********************/
#define ADC_SAMPLING_CYCLES              (6 + SAMPLING_CYCLE_CORRECTION)

/******************************   ADDITIONAL FEATURES   **********************/

/*** On the fly start-up ***/

/**************************
 *** Control Parameters ***
 **************************/

/* ##@@_USER_CODE_START_##@@ */
/* ##@@_USER_CODE_END_##@@ */

#endif /*DRIVE_PARAMETERS_H*/
/******************* (C) COPYRIGHT 2026 STMicroelectronics *****END OF FILE****/
