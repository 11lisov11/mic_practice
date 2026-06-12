#pragma once

#include <stdint.h>

#define UART_BAUD 460800
#define UART_RX_BUF_SIZE 1024

// Link selection (UNO Q -> Blue Pill)
// 0 = UART (PA2/PA3), 1 = SPI1 slave (PA4/PA5/PA6/PA7)
#define LINK_USE_SPI 0

#define PWM_FREQ_HZ 10000
#define PWM_DEADTIME_NS 800
#define PWM_MIN_PERCENT 5
#define PWM_MAX_PERCENT 95

#define TIMEOUT_MS 300

// STEVAL-IPM15B: EM_STOP on J2-1 is the shutdown line (active-low on the IPM).
// EM_STOP is driven as a GPIO output by default.
#define BRAKE_ACTIVE_STATE 0
#define EM_STOP_GPIO_PORT GPIOB
#define EM_STOP_GPIO_PIN GPIO_PIN_12

// Optional hardware break input (TIM1_BKIN on PB12).
// If enabled, you MUST move EM_STOP to a different GPIO pin.
#define USE_TIM1_BKIN 0
#define BKIN_ACTIVE_LOW 1
#define BKIN_ENABLE_PULLUP 1
// Set to 1 if EM_STOP is currently on PB12 (default wiring).
#define EM_STOP_IS_PB12 1

#if USE_TIM1_BKIN && EM_STOP_IS_PB12
#error "EM_STOP uses PB12 which is TIM1_BKIN. Move EM_STOP to another pin or disable USE_TIM1_BKIN."
#endif

// ADC scaling (per-unit)
#define ADC_CALIB_SAMPLES 256
#define ADC_I_SCALE (1.0f / 2048.0f)
// STEVAL J2-14 HV bus telemetry is sampled on PA5 in UART mode.
// UM2014 bus-voltage output is offset near mid-scale when the DC bus is off.
// Live calibration: bus-off median raw ~=1763; raw=3256 was 315 V on meter.
#define ADC_VBUS_ZERO_RAW 1763U
#define ADC_VBUS_CAL_RAW 3256U
#define ADC_VBUS_CAL_V 315.0f
#define ADC_VBUS_SCALE (ADC_VBUS_CAL_V / ((float)ADC_VBUS_CAL_RAW - (float)ADC_VBUS_ZERO_RAW))

// STEVAL-IPM15B J2-26 "heat sink temperature".
// UM2014 SW3 selects the source:
//   TSO: jumper 1-2, low-side driver temperature sensor output.
//   NTC: jumper 2-3, 85 kOhm IPM thermistor through the board 12 kOhm pull-up.
// The live bench is wired as TSO, so keep firmware in TSO mode unless SW3 is
// physically moved to NTC. PB0/ADC1_IN8 is reserved for this signal, so do not
// wire J2-34 "measure phase C" to PB0 at the same time.
#define USE_HEATSINK_TEMP 1
#define HEATSINK_TEMP_SENSOR_NTC 0
#define HEATSINK_TEMP_SENSOR_TSO 1
#define HEATSINK_TEMP_SENSOR_MODE HEATSINK_TEMP_SENSOR_TSO
#define HEATSINK_TEMP_PORT GPIOB
#define HEATSINK_TEMP_PIN GPIO_PIN_0
#define HEATSINK_TEMP_ADC_CHANNEL ADC_CHANNEL_8
#define HEATSINK_TEMP_SAMPLE_MS 100
#define HEATSINK_TEMP_PROTECTION_ENABLE 1
#define HEATSINK_TEMP_VREF 3.3f
#define HEATSINK_TEMP_PULLUP_OHM 12000.0f
#define HEATSINK_TEMP_NTC_R25_OHM 85000.0f
#define HEATSINK_TEMP_NTC_BETA_K 4092.0f
#define HEATSINK_TEMP_TRIP_C 90.0f
// TSO is roughly linear; VTSO at 25 C is 0.974..1.345 V per STGIB15CH60TS-L.
// Use typ. 1.16 V and an 18 mV/C slope for diagnostics and a conservative
// overtemperature trip. Exact thermal shutdown still remains inside the IPM.
#define HEATSINK_TEMP_TSO_V25 1.16f
#define HEATSINK_TEMP_TSO_MV_PER_C 18.0f
// Treat rail-like ADC values as wiring faults.
#define HEATSINK_TEMP_SHORT_RAW 16U
#define HEATSINK_TEMP_OPEN_RAW 4080U

// IPM15 (UM2014) optional I/O
#if LINK_USE_SPI
// SPI1 uses PA4..PA7 so keep these free.
#define USE_PHASE_MEAS 0
#else
#define USE_PHASE_MEAS 1
#endif
#define PHASE_MEAS_A_PORT GPIOA
#define PHASE_MEAS_A_PIN GPIO_PIN_6   // J2-31 measure phase A (ADC1_IN6)
#define PHASE_MEAS_B_PORT GPIOA
#define PHASE_MEAS_B_PIN GPIO_PIN_7   // J2-33 measure phase B (ADC1_IN7)
#define PHASE_MEAS_C_PORT GPIOB
#define PHASE_MEAS_C_PIN GPIO_PIN_0   // J2-34 measure phase C (disabled while USE_HEATSINK_TEMP uses PB0)
#define PHASE_MEAS_SAMPLE_MS 100
#define PHASE_MEAS_CENTER_RAW 2048
#define PHASE_MEAS_VREF 3.3f

#define NTC_RELAY_PORT GPIOB
#define NTC_RELAY_PIN GPIO_PIN_1      // J2-21 NTC bypass relay
#define NTC_RELAY_ACTIVE_STATE 1

#define PFC_SYNC_PORT GPIOB
#define PFC_SYNC_PIN GPIO_PIN_5       // J2-27 PFC sync
#define PFC_SYNC_ACTIVE_STATE 1

#define PRECHARGE_RELAY_PORT GPIOB
#define PRECHARGE_RELAY_PIN GPIO_PIN_4  // MIC_AI RELAY1 driver input via R2/Q1
#define PRECHARGE_RELAY_ACTIVE_STATE 1

#define USE_BRAKE_PWM 1
#define BRAKE_PWM_PORT GPIOB
#define BRAKE_PWM_PIN GPIO_PIN_9      // J2-23 dissipative brake PWM (TIM4_CH4)
#define BRAKE_PWM_FREQ_HZ 1000

// AS5600 magnetic encoder (I2C)
#define USE_AS5600 1
#define AS5600_I2C_SPEED 100000
#define AS5600_I2C_ADDR 0x36
// Set to your motor pole pairs (electrical = mechanical * pole_pairs).
// Keep this aligned with UNOQ_MOTOR/UNOQ_MOTOR.ino:POLE_PAIRS.
#define AS5600_POLE_PAIRS 2

// FOC controller gains and limits (per-unit)
#define FOC_ID_KP 1.0f
#define FOC_ID_KI 50.0f
#define FOC_IQ_KP 1.0f
#define FOC_IQ_KI 50.0f
#define FOC_V_LIMIT 0.95f

// Hall sensor inputs (120-degree, 3-phase). UM2014 Table 6: J9 H1/H2/H3 -> PB6/PB7/PB8.
#define HALL_GPIO_PORT GPIOB
#define HALL_PIN1 GPIO_PIN_6
#define HALL_PIN2 GPIO_PIN_7
#define HALL_PIN3 GPIO_PIN_8
#define HALL_GPIO_PULL GPIO_PULLUP
#define HALL_TIMEOUT_MS 100
#define FOC_REQUIRE_HALL 1
