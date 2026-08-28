#pragma once

#define MIC_PROTOCOL_VERSION 0x02U
#define UART_BAUD 115200U
#define UART_RX_BUF_SIZE 512U
#define UART_TX_TIMEOUT_MS 5U
#define LINK_TIMEOUT_MS 300U
#define BOOT_PING_INTERVAL_MS 250U

// Production bridge: direct USART1 PB6/PB7 link to UNO Q with common HOT_GND.
// This interface is not galvanically isolated and must remain inside the enclosure.
// Dedicated _vcp build profiles select PC4/PC5 for the on-board ST-LINK VCP.
#ifndef NUCLEO_UART_USE_STLINK_VCP
#define NUCLEO_UART_USE_STLINK_VCP 0
#endif

#ifndef MIC_MOTOR_BACKEND_STUB
#define MIC_MOTOR_BACKEND_STUB 0
#endif

#ifndef MIC_MOTOR_BACKEND_PWM_BENCH
#define MIC_MOTOR_BACKEND_PWM_BENCH 0
#endif

#if MIC_MOTOR_BACKEND_STUB && MIC_MOTOR_BACKEND_PWM_BENCH
#error "Select only one motor backend"
#endif

#ifndef NUCLEO_MOTOR_CLOCK_170MHZ
#define NUCLEO_MOTOR_CLOCK_170MHZ 0
#endif

// Provisional low-voltage bench values. The final values must come from the
// MCSDK ACIM board/motor profile, not from this diagnostic firmware.
#define MOTOR_BENCH_PWM_FREQ_HZ 10000U
#define MOTOR_BENCH_DEADTIME_NS 2000U
#define MOTOR_BENCH_DUTY_Q15 16384U
#define MOTOR_BENCH_ADC_SAMPLE_MS 20U

// The benchmark executes at both update points of the center-aligned timer.
// Its result is never connected to CCR registers: physical PWM remains the
// fixed diagnostic pattern while Saleae measures ISR duration and jitter.
#define MOTOR_BENCH_CONTROL_HZ (2U * MOTOR_BENCH_PWM_FREQ_HZ)
#define MOTOR_BENCH_CONTROL_BUDGET_PERCENT 50U
#define MOTOR_BENCH_MARKER_PORT GPIOC
#define MOTOR_BENCH_MARKER_PIN GPIO_PIN_6
#define MOTOR_BENCH_MARKER_ACTIVE_STATE GPIO_PIN_RESET
#if MOTOR_BENCH_CONTROL_BUDGET_PERCENT < 10U || MOTOR_BENCH_CONTROL_BUDGET_PERCENT > 80U
#error "MOTOR_BENCH_CONTROL_BUDGET_PERCENT must be between 10 and 80"
#endif

// X-NUCLEO-IHM09M2 routing for NUCLEO-G431RB.
#define MOTOR_PWM_UH_PORT GPIOA
#define MOTOR_PWM_UH_PIN GPIO_PIN_8
#define MOTOR_PWM_UL_PORT GPIOA
#define MOTOR_PWM_UL_PIN GPIO_PIN_7
#define MOTOR_PWM_VH_PORT GPIOA
#define MOTOR_PWM_VH_PIN GPIO_PIN_9
#define MOTOR_PWM_VL_PORT GPIOB
#define MOTOR_PWM_VL_PIN GPIO_PIN_0
#define MOTOR_PWM_WH_PORT GPIOA
#define MOTOR_PWM_WH_PIN GPIO_PIN_10
#define MOTOR_PWM_WL_PORT GPIOB
#define MOTOR_PWM_WL_PIN GPIO_PIN_1

// STEVAL-IPM15B J2-1 is an active-low EM_STOP input. The diagnostic backend
// deliberately keeps it asserted; only the future MCSDK backend may release it.
#define MOTOR_EM_STOP_PORT GPIOA
#define MOTOR_EM_STOP_PIN GPIO_PIN_6
#define MOTOR_EM_STOP_SAFE_STATE GPIO_PIN_RESET

// This LED is only used by the bridge-only bench firmware. The generated
// MCSDK project owns all motor-control pin assignments.
#ifndef NUCLEO_BRIDGE_STATUS_LED
#define NUCLEO_BRIDGE_STATUS_LED 0
#endif

#define STATUS_LED_PORT GPIOA
#define STATUS_LED_PIN GPIO_PIN_5
