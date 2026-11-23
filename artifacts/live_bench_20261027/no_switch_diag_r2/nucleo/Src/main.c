/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

#include "acim_motor_parameters.h"
#include "bus_voltage_sensor.h"
#include "mc_api.h"
#include "mc_config.h"
#include "mc_stm_types.h"
#include "ntc_temperature_sensor.h"
#include "stm32g4xx_ll_tim.h"
#include "bkin_wave_capture.h"
#include "pulse_core.h"
#include "sd_live_status.h"
#include "current_shunt.h"
#include "nucleo_encoder.h"
#include "fault_wire.h"
#include "encoder_health_wire.h"
#include "release_wire.h"
#include "uart_reject_record.h"

#include <string.h>

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
ADC_HandleTypeDef hadc1;
ADC_HandleTypeDef hadc2;

CORDIC_HandleTypeDef hcordic;

TIM_HandleTypeDef htim1;

UART_HandleTypeDef huart2;
DMA_HandleTypeDef hdma_usart2_rx;
DMA_HandleTypeDef hdma_usart2_tx;
static DMA_HandleTypeDef hdma_mic_bkin;
volatile uint16_t mic_bkin_ring[MIC_BKIN_SAMPLE_COUNT];
volatile uint32_t mic_bkin_capture_state;
volatile uint32_t mic_bkin_remaining;
volatile uint32_t mic_bkin_dma_flags;
volatile uint32_t mic_bkin_event_tick_ms;
volatile uint32_t mic_bkin_record_ready;
uint8_t mic_bkin_record[MIC_BKIN_RECORD_BYTES];
uint32_t mic_bkin_record_crc;

/* USER CODE BEGIN PV */

/* Application-owned direct UNO Q link: USART1 PB6/PB7 at 115200 8N1.
 * UNO Q and Nucleo share HOT_GND; this interface is not galvanically isolated. */
UART_HandleTypeDef huart1;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_DMA_Init(void);
static void MX_ADC1_Init(void);
static void MX_ADC2_Init(void);
static void MX_CORDIC_Init(void);
static void MX_TIM1_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_NVIC_Init(void);
/* USER CODE BEGIN PFP */

static void MX_USART1_UART_Init(void);
static void uno_link_init(void);
static void uno_link_poll(void);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

#include "stm32g4xx_ll_exti.h"
#include "local_stop.h"
#include "load_diag.h"

volatile uint32_t mic_local_stop_latched;
extern uint8_t bMCBootCompleted;

static bool mic_local_button_pending(void) {
  /* MB1367 B1 connects B_USER to VDD; R26 pulls the released input LOW. */
  return HAL_GPIO_ReadPin(Start_Stop_GPIO_Port, Start_Stop_Pin) == GPIO_PIN_SET ||
         LL_EXTI_IsActiveFlag_0_31(LL_EXTI_LINE_13);
}

bool mic_local_stop_blocked(void) {
  if (mic_local_button_pending()) mic_local_stop_latched = 1U;
  return mic_local_stop_latched != 0U;
}

/* Strong override of the MCSDK weak callback. No UART or RPC dependency. */
void UI_HandleStartStopButton_cb(void) {
  mic_local_stop_latched = 1U;
  LL_TIM_DisableAllOutputs(TIM1);
  if (bMCBootCompleted != 0U) (void)MC_StopMotor1();
}

void mic_local_stop_enable_outputs(TIM_TypeDef *timer) {
  /* Only the MOE publication is atomic; BKIN remains hardware-active. */
  const uint32_t mask = __get_PRIMASK();
  __disable_irq();
  if (mic_local_stop_blocked()) LL_TIM_DisableAllOutputs(timer);
  else LL_TIM_DisableAllOutputs(timer); /* Diagnostic image: never enable phase outputs. */
  __set_PRIMASK(mask);
}

bool mic_local_stop_clear(void) {
  const uint32_t mask = __get_PRIMASK();
  __disable_irq();
  const bool allowed = !mic_local_button_pending() &&
      !LL_TIM_IsEnabledAllOutputs(TIM1) && MC_GetSTMStateMotor1() == IDLE &&
      MC_GetCurrentFaultsMotor1() == MC_NO_FAULTS &&
      MC_GetOccurredFaultsMotor1() == MC_NO_FAULTS;
  if (allowed) mic_local_stop_latched = 0U;
  __set_PRIMASK(mask);
  return allowed;
}

#include "uart_v3_transport.h"
#include "manual_scalar_control.h"
#include "first_break_snapshot.h"
#include "break_wire.h"
static uint32_t mic_break_diag_tx_errors;
static bool mic_last_control_reply_safe_off;
volatile mic_break_snapshot_t mic_first_break;
volatile mic_break_snapshot_t mic_first_start_break;
volatile uint32_t mic_break_start_window;
volatile uint32_t mic_break_irq_count;
volatile mic_break_context_t mic_break_context[2];
volatile uint32_t mic_break_context_index;
volatile uint32_t mic_break_context_valid;

enum {
  UNO_FRAME_LEN = UV3_FRAME,
  UNO_PROTOCOL_VERSION = UV3_VERSION,
  UNO_CMD_HDR0 = 0xAAU,
  UNO_CMD_HDR1 = 0x55U,
  UNO_RSP_HDR0 = 0x55U,
  UNO_RSP_HDR1 = 0xAAU,
  UNO_FLAG_ENABLE = 0x01U,
  UNO_FLAG_ESTOP = 0x02U,
  UNO_FLAG_CLEAR_FAULT = 0x08U,
  UNO_MODE_OFF = 0U,
  UNO_MODE_SCALAR = 3U,
  UNO_STATUS_LINK_OK = 0x01U,
  UNO_STATUS_ENABLED = 0x02U,
  UNO_STATUS_ESTOP = 0x04U,
  UNO_STATUS_FAULT = 0x08U,
  UNO_STATUS_TIMEOUT = 0x10U,
  UNO_STATUS_PWM_ACTIVE = 0x20U,
  UNO_STATUS_SHUTDOWN_RELEASED = 0x40U,
  UNO_TELEMETRY_FW_BUILD_VALID = 0x10U,
  UNO_TELEMETRY_SOFTSTART_READY = 0x20U,
  UNO_TELEMETRY_VBUS_VALID = 0x40U,
  UNO_TELEMETRY_MCSDK_UNITS = 0x80U,
  UNO_TEMP_VALID = 0x01U,
  UNO_TEMP_FAULT = 0x02U,
  UNO_FAULT_OK = 0U,
  UNO_FAULT_ESTOP = 1U,
  UNO_FAULT_TIMEOUT = 2U,
  UNO_FAULT_BAD_CRC = 3U,
  UNO_FAULT_INTERNAL = 5U,
  UNO_LINK_TIMEOUT_MS = 300U,
  UNO_REPLY_TIMEOUT_MS = 5U,
  UNO_SPEED_RAMP_MS = 3000U,
  UNO_MAX_RAMP_HZ_PER_S = 5U,
  UNO_SOFTSTART_READY_V = 250U,
  UNO_SOFTSTART_HOLD_V = 200U,
  UNO_SOFTSTART_MAX_V = 385U,
  UNO_DIAG_NONE = 0U,
  UNO_DIAG_CRC = 1U,
  UNO_DIAG_VERSION = 2U,
  UNO_DIAG_REPLAY = 3U,
  UNO_DIAG_ESTOP = 4U,
  UNO_DIAG_SERVICE = 5U,
  UNO_DIAG_COMMAND = 6U,
  UNO_DIAG_FREQUENCY = 7U,
  UNO_DIAG_MCSDK = 8U,
  UNO_DIAG_BUS = 9U,
  UNO_DIAG_START = 10U,
  UNO_DIAG_TX = 11U,
  UNO_DIAG_UART = 12U,
  UNO_DIAG_TIMEOUT = 13U,
  UNO_DIAG_RX_BUFFER = 14U,
  UNO_DIAG_TAG = 0x90U,
};

#define MIC_NUCLEO_FW_BUILD_ID 2026102791UL

#define MIC_EXTERNAL_SOFTSTART_CONFIGURED 1
#define MIC_SOFTSTART_GPIO_CONTROLLED 0
#define MIC_EXTERNAL_SOFTSTART_HIL_VALIDATED 0
#define MIC_EXTERNAL_SOFTSTART_SETTLE_MS 3500U


static bool mic_bkin_dma_initialized;
static volatile uint32_t mic_bkin_completed;
static volatile uint32_t mic_bkin_has_history;
static volatile uint32_t mic_bkin_cursor;
static volatile uint32_t mic_bkin_stream_error;
static volatile uint32_t mic_bkin_triggered;
static bp_capture mic_bkin_pulse;
#ifndef MIC_BKIN_DMA_ACK
#define MIC_BKIN_DMA_ACK(mask) (DMA2->IFCR=(mask))
#endif

static void mic_bkin_freeze(void) {
  TIM2->DIER &= ~TIM_DIER_UDE;
  TIM2->CR1 &= ~TIM_CR1_CEN;
  __HAL_DMA_DISABLE(&hdma_mic_bkin);
  __DSB();
  mic_bkin_remaining=DMA2_Channel1->CNDTR;
  mic_bkin_dma_flags=DMA2->ISR & 0x0FU;
  __DMB();
  mic_bkin_capture_state=MIC_BKIN_CAPTURED;
}

static void mic_bkin_capture_init(void) {
  if (mic_bkin_dma_initialized) return;
  __HAL_RCC_TIM2_CLK_ENABLE();
  memset(&hdma_mic_bkin,0,sizeof(hdma_mic_bkin));
  hdma_mic_bkin.Instance=DMA2_Channel1;
  hdma_mic_bkin.Init.Request=DMA_REQUEST_TIM2_UP;
  hdma_mic_bkin.Init.Direction=DMA_PERIPH_TO_MEMORY;
  hdma_mic_bkin.Init.PeriphInc=DMA_PINC_DISABLE;
  hdma_mic_bkin.Init.MemInc=DMA_MINC_ENABLE;
  hdma_mic_bkin.Init.PeriphDataAlignment=DMA_PDATAALIGN_WORD;
  /* GPIO is read as a word; DMA stores its low 16 bits, including PA6. */
  hdma_mic_bkin.Init.MemDataAlignment=DMA_MDATAALIGN_HALFWORD;
  hdma_mic_bkin.Init.Mode=DMA_CIRCULAR;
  hdma_mic_bkin.Init.Priority=DMA_PRIORITY_LOW;
  if (HAL_DMA_Init(&hdma_mic_bkin)!=HAL_OK) {
    mic_bkin_capture_state=MIC_BKIN_CAPTURE_ERROR; return;
  }
  mic_bkin_dma_initialized=true;
}

static void mic_bkin_capture_start(void) {
  /* Immutable first event per boot, including across STOP/CLEAR/START. */
  if (mic_bkin_capture_state!=MIC_BKIN_CAPTURE_IDLE) return;
  mic_bkin_capture_init();
  if (!mic_bkin_dma_initialized) return;
  RCC_ClkInitTypeDef clocks={0}; uint32_t latency=0;
  HAL_RCC_GetClockConfig(&clocks,&latency);
  uint32_t hz=HAL_RCC_GetPCLK1Freq();
  if (clocks.APB1CLKDivider!=RCC_HCLK_DIV1) hz*=2U;
  if (hz<2U*MIC_BKIN_SAMPLE_HZ || hz%MIC_BKIN_SAMPLE_HZ) {
    mic_bkin_capture_state=MIC_BKIN_CAPTURE_ERROR; return;
  }
  /* MCSDK's one-shot boot synchronization has finished. ARR must be nonzero. */
  TIM2->CR2 &= ~TIM_CR2_MMS;
  TIM2->CR1=0; TIM2->DIER=0; TIM2->PSC=0;
  TIM2->ARR=hz/MIC_BKIN_SAMPLE_HZ-1U;
  TIM2->CNT=0; TIM2->EGR=TIM_EGR_UG; TIM2->SR=0;
  MIC_BKIN_DMA_ACK(0x0FU);
  /* Passive TP23 input. Never drive SD, no pull-up/down, no EXTI. */
  GPIO_InitTypeDef probe={0};
  probe.Pin=GPIO_PIN_4; probe.Mode=GPIO_MODE_INPUT; probe.Pull=GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA,&probe);
  if (((GPIOA->MODER>>8U)&3U)!=0U || ((GPIOA->PUPDR>>8U)&3U)!=0U) {
    mic_bkin_capture_state=MIC_BKIN_CAPTURE_ERROR; return;
  }
  bp_init(&mic_bkin_pulse);
  mic_bkin_completed=0; mic_bkin_has_history=0; mic_bkin_triggered=0; mic_bkin_stream_error=0;
  if (HAL_DMA_Start(&hdma_mic_bkin,(uint32_t)(uintptr_t)&GPIOA->IDR,
      (uint32_t)(uintptr_t)mic_bkin_ring,MIC_BKIN_SAMPLE_COUNT)!=HAL_OK) {
    mic_bkin_capture_state=MIC_BKIN_CAPTURE_ERROR; return;
  }
  /* Lower priority than Break (4), PWM (0), ADC (2), UART (3). */
  HAL_NVIC_SetPriority(DMA2_Channel1_IRQn,5,0);
  HAL_NVIC_ClearPendingIRQ(DMA2_Channel1_IRQn);
  mic_bkin_capture_state=MIC_BKIN_RUNNING;
  DMA2_Channel1->CCR |= DMA_CCR_HTIE|DMA_CCR_TCIE|DMA_CCR_TEIE;
  HAL_NVIC_EnableIRQ(DMA2_Channel1_IRQn);
  TIM2->DIER=TIM_DIER_UDE; TIM2->CR1=TIM_CR1_CEN;
}

void mic_bkin_capture_trigger_from_break(uint32_t tick_ms) {
  if (mic_bkin_capture_state!=MIC_BKIN_RUNNING || mic_bkin_triggered) return;
  /* Constant-time publication only. DMA continues after hardware shutdown;
     no scanning, waiting, UART or MCSDK operations in the Break handler. */
  const uint32_t completed=mic_bkin_completed;
  const uint32_t next=(MIC_BKIN_SAMPLE_COUNT-DMA2_Channel1->CNDTR)&8191U;
  const uint32_t pending=(next-(completed&8191U))&8191U;
  const uint32_t pre=(mic_bkin_has_history || pending>=BP_PRE) ? BP_PRE : pending;
  mic_bkin_cursor=completed+pending-pre;
  mic_bkin_pulse.trigger=pre;
  mic_bkin_event_tick_ms=tick_ms;
  __DMB(); mic_bkin_triggered=1;
}

void DMA2_Channel1_IRQHandler(void) {
  const uint32_t flags=DMA2->ISR&0x0FU;
  if (mic_bkin_capture_state!=MIC_BKIN_RUNNING) { MIC_BKIN_DMA_ACK(0x0FU); return; }
  const uint32_t expected=(mic_bkin_completed&4096U) ? 2U : 4U;
  if ((flags&8U) || (flags&6U)==6U || !(flags&expected)) {
    mic_bkin_stream_error |= (flags&8U) ? BP_DMA_ERROR : BP_OVERRUN;
    MIC_BKIN_DMA_ACK(0x0FU);
    /* Discard ambiguous history rather than inventing samples. */
    const uint32_t next=(8192U-DMA2_Channel1->CNDTR)&8191U;
    mic_bkin_completed=(mic_bkin_completed&~8191U)+(next&~4095U);
  } else {
    MIC_BKIN_DMA_ACK(expected);
    mic_bkin_completed+=4096U;
    mic_bkin_has_history=1;
  }
  if (!mic_bkin_triggered) return;
  if (mic_bkin_stream_error) {
    bp_finish(&mic_bkin_pulse,mic_bkin_stream_error); mic_bkin_freeze(); return;
  }
  const uint32_t end=mic_bkin_completed;
  /* Break can preempt this lower-priority handler after its boundary was
     published. Its prehistory may then start in the still-writing half. */
  if ((int32_t)(end-mic_bkin_cursor)<0) return;
  if ((uint32_t)(end-mic_bkin_cursor)>8192U) {
    bp_finish(&mic_bkin_pulse,BP_OVERRUN); mic_bkin_freeze(); return;
  }
  /* At most 6144 samples at first service, then 4096. Coalesce constant
     levels instead of running the state machine for every sample. A later
     DMA boundary during this scan invalidates the trace conservatively. */
  while (mic_bkin_cursor!=end && !(mic_bkin_pulse.flags&BP_FROZEN)) {
    const uint32_t high=mic_bkin_ring[mic_bkin_cursor&8191U] & (GPIO_PIN_4|GPIO_PIN_6);
    uint32_t count=1;
    while (count<(uint32_t)(end-mic_bkin_cursor) &&
        (mic_bkin_ring[(mic_bkin_cursor+count)&8191U] & (GPIO_PIN_4|GPIO_PIN_6))==high) ++count;
    mic_bkin_cursor+=bp_feed_span(&mic_bkin_pulse,bp_state(high),count);
  }
  __DMB();
  if ((DMA2->ISR&8U) || (DMA2->ISR&6U)) {
    /* Another half completed during scanning: data may have been overwritten. */
    bp_finish(&mic_bkin_pulse,(DMA2->ISR&8U) ? BP_DMA_ERROR : BP_OVERRUN);
  }
  if (mic_bkin_pulse.flags&BP_FROZEN) mic_bkin_freeze();
}

static void mic_bkin_put32(uint8_t *p,uint32_t value) {
  p[0]=(uint8_t)value; p[1]=(uint8_t)(value>>8);
  p[2]=(uint8_t)(value>>16); p[3]=(uint8_t)(value>>24);
}
static void mic_bkin_prepare_record(void) {
  /* Wall-clock fallback if the sampling timer/DMA stops after the trigger. */
  if (mic_bkin_capture_state==MIC_BKIN_RUNNING && mic_bkin_triggered &&
      (uint32_t)(HAL_GetTick()-mic_bkin_event_tick_ms)>110U) {
    HAL_NVIC_DisableIRQ(DMA2_Channel1_IRQn);
    if (mic_bkin_capture_state==MIC_BKIN_RUNNING) {
      bp_finish(&mic_bkin_pulse,BP_TIMEOUT|BP_DMA_ERROR);
      mic_bkin_freeze();
    }
  }
  if (mic_bkin_capture_state!=MIC_BKIN_CAPTURED || mic_bkin_record_ready) return;
  __DMB();
  const uint32_t h[16]={MIC_BKIN_RECORD_MAGIC,5U,MIC_BKIN_RECORD_BYTES,
    mic_bkin_event_tick_ms,200U,mic_bkin_pulse.flags,
    mic_bkin_pulse.trigger,mic_bkin_pulse.samples,mic_bkin_pulse.runs,
    0x50U,BP_LIMIT,BP_POST,BP_PRE,mic_bkin_dma_flags,mic_bkin_remaining,1U};
  memset(mic_bkin_record,0,sizeof(mic_bkin_record));
  for (unsigned i=0;i<16;++i) mic_bkin_put32(mic_bkin_record+4*i,h[i]);
  for (unsigned i=0;i<mic_bkin_pulse.runs;++i) {
    mic_bkin_put32(mic_bkin_record+64+8*i,mic_bkin_pulse.run[i].level);
    mic_bkin_put32(mic_bkin_record+68+8*i,mic_bkin_pulse.run[i].count);
  }
  mic_bkin_record_crc=uv3_crc32c(mic_bkin_record,MIC_BKIN_RECORD_BYTES);
  __DMB(); mic_bkin_record_ready=1;
}


static void mic_bkin_wave_packet(uint8_t *packet, unsigned page) {
  memset(packet, 0, UV3_FRAME);
  packet[0] = 0x55U;
  packet[1] = 0xAAU;
  packet[2] = MIC_BKIN_WIRE_VERSION;
  packet[3] = (uint8_t)page;
  packet[4] = MIC_BKIN_WIRE_PAGES;
  bw_put32(packet + 6U, MIC_NUCLEO_FW_BUILD_ID);
  bw_put32(packet + 10U, mic_bkin_record_crc);
  const unsigned offset = page * MIC_BKIN_WIRE_CHUNK;
  unsigned length = MIC_BKIN_RECORD_BYTES - offset;
  if (length > MIC_BKIN_WIRE_CHUNK) length = MIC_BKIN_WIRE_CHUNK;
  memcpy(packet + 14U, mic_bkin_record + offset, length);
  uv3_seal(packet);
}

typedef struct {
  uint8_t parser_state;
  uint8_t parser_index;
  uint8_t frame[UNO_FRAME_LEN];
  uint8_t last_seq;
  uint8_t last_mode;
  uint8_t fault_code;
  uint16_t good_count;
  uint16_t bad_count;
  uint8_t first_reason;
  uint8_t first_uart_errors;
  uint8_t first_motor_state;
  uint8_t first_tx_status;
  uint8_t first_sequence;
  uint8_t last_bad_reason;
  uint8_t last_uart_errors;
  uint8_t last_tx_status;
  uint16_t first_current_faults;
  uint16_t first_occurred_faults;
  uint32_t last_valid_ms;
  int16_t last_speed_unit;
  int16_t ramp_target_speed_unit;
  uint16_t ramp_rate_centi;
  bool coast_hold;
  bool manual_ramp_down;
  bool decel_bus_hold;
  bool link_seen;
  bool command_enabled;
  bool fault_latched;
  bool softstart_ready;
  bool softstart_tracking;
  uint32_t softstart_stable_since_ms;
} uno_link_state_t;

static uno_link_state_t uno_link;
static uv3_rx uno_transport;
static uint8_t mic_uart_reject_record[UR_BYTES];
static uint32_t mic_uart_reject_crc;
static bool mic_uart_reject_ready;
static void mic_uart_reject_packet(uint8_t *packet,unsigned page) {
  if(!mic_uart_reject_ready) {
    ur_serialize(mic_uart_reject_record,&uno_transport,MIC_NUCLEO_FW_BUILD_ID);
    mic_uart_reject_crc=uv3_crc32c(mic_uart_reject_record,UR_BYTES);mic_uart_reject_ready=true;
  }
  memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=UR_VERSION;
  packet[3]=(uint8_t)page;packet[4]=UR_PAGES;
  ur_put32(packet+6,MIC_NUCLEO_FW_BUILD_ID);ur_put32(packet+10,mic_uart_reject_crc);
  unsigned offset=page*24U,n=UR_BYTES-offset;if(n>24)n=24;
  memcpy(packet+14,mic_uart_reject_record+offset,n);uv3_seal(packet);
}

enum { UNO_RX_SIZE = 128U, UNO_RX_MASK = UNO_RX_SIZE - 1U };
static volatile uint8_t uno_rx_bytes[UNO_RX_SIZE];
static volatile uint8_t uno_rx_marks[UNO_RX_SIZE];
static volatile uint16_t uno_rx_head;
static volatile uint16_t uno_rx_tail;
static volatile uint8_t uno_rx_errors;
static volatile uint8_t uno_rx_overflow;

/* USART1 TX owns DMA1 channel 1, DMAMUX request USART1_TX. RX stays IRQ.
   DMA2 ch1 remains SD; DMA2 ch2/ch3 remain MCSDK USART2 RX/TX. */
enum { UNO_TX_SLOTS=4U, UNO_TX_TAG_DIAG=0U, UNO_TX_TAG_ON=1U, UNO_TX_TAG_OFF=2U };
typedef struct {
  uint32_t head,tail,active,started_ms,late_reported,hard_error;
  uint32_t queued,completed,timeouts,full_errors,dma_errors,last_status,early_tc;
  uint8_t bytes[UNO_TX_SLOTS][UV3_FRAME];
  uint8_t tags[UNO_TX_SLOTS];
} uno_tx_state_t;
volatile uno_tx_state_t mic_uart_tx;
static DMA_HandleTypeDef hdma_uno_tx;
void DMA1_Channel1_IRQHandler(void);
#ifndef MIC_UART_TX_DMA_ACK
#define MIC_UART_TX_DMA_ACK(mask) (DMA1->IFCR=(mask))
#endif

static void uno_tx_lock(void) {
  HAL_NVIC_DisableIRQ(USART1_IRQn);
  HAL_NVIC_DisableIRQ(DMA1_Channel1_IRQn);
}
static void uno_tx_unlock(void) {
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
  HAL_NVIC_EnableIRQ(USART1_IRQn);
}

static void uno_tx_begin_locked(uint32_t now_ms) {
  if(mic_uart_tx.active || mic_uart_tx.hard_error || mic_uart_tx.head==mic_uart_tx.tail) return;
  const unsigned slot=mic_uart_tx.tail&(UNO_TX_SLOTS-1U);
  huart1.Instance->CR1 &= ~USART_CR1_TCIE;
  huart1.Instance->CR3 &= ~USART_CR3_DMAT;
  DMA1_Channel1->CCR &= ~DMA_CCR_EN;
  MIC_UART_TX_DMA_ACK(0x0fU);
  huart1.Instance->ICR=USART_ICR_TCCF;
  DMA1_Channel1->CPAR=(uint32_t)(uintptr_t)&huart1.Instance->TDR;
  DMA1_Channel1->CMAR=(uint32_t)(uintptr_t)&mic_uart_tx.bytes[slot][0];
  DMA1_Channel1->CNDTR=UV3_FRAME;
  mic_uart_tx.started_ms=now_ms;
  mic_uart_tx.late_reported=0U;
  mic_uart_tx.active=1U;
  __DMB();
  DMA1_Channel1->CCR |= DMA_CCR_EN|DMA_CCR_TEIE;
  huart1.Instance->CR3 |= USART_CR3_DMAT;
  huart1.Instance->CR1 |= USART_CR1_TCIE;
}

static int uno_tx_submit(const uint8_t *frame,uint8_t tag) {
  int status=HAL_OK;
  uno_tx_lock();
  if(mic_uart_tx.hard_error) status=HAL_ERROR;
  else if((uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>=UNO_TX_SLOTS) {
    ++mic_uart_tx.full_errors;status=HAL_BUSY;
  } else {
    const unsigned slot=mic_uart_tx.head&(UNO_TX_SLOTS-1U);
    for(unsigned i=0;i<UV3_FRAME;++i) mic_uart_tx.bytes[slot][i]=frame[i];
    mic_uart_tx.tags[slot]=tag;
    __DMB();++mic_uart_tx.head;++mic_uart_tx.queued;
    uno_tx_begin_locked(HAL_GetTick());
  }
  uno_tx_unlock();
  return status;
}

/* Called after the unchanged RX/error drain, at the same IRQ priority 3.
   TC means the last stop bit left the UART, not just DMA memory copied. */
static void uno_tx_tc_isr(void) {
  if(!(huart1.Instance->CR1&USART_CR1_TCIE) || !(huart1.Instance->ISR&UART_FLAG_TC)) return;
  if(DMA1->ISR&8U) { DMA1_Channel1_IRQHandler();return; }
  huart1.Instance->ICR=USART_ICR_TCCF;
  if(!mic_uart_tx.active || mic_uart_tx.hard_error) {
    huart1.Instance->CR1 &= ~USART_CR1_TCIE;return;
  }
  if(DMA1_Channel1->CNDTR!=0U) {
    /* A delayed DMA request may leave an inter-byte idle. Never treat this
       as end of frame or advance to a new packet before all 43 bytes. */
    ++mic_uart_tx.early_tc;return;
  }
  huart1.Instance->CR1 &= ~USART_CR1_TCIE;
  huart1.Instance->CR3 &= ~USART_CR3_DMAT;
  DMA1_Channel1->CCR &= ~DMA_CCR_EN;
  MIC_UART_TX_DMA_ACK(0x0fU);
  const uint8_t tag=mic_uart_tx.tags[mic_uart_tx.tail&(UNO_TX_SLOTS-1U)];
  if(tag!=UNO_TX_TAG_DIAG) mic_last_control_reply_safe_off=(tag==UNO_TX_TAG_OFF);
  ++mic_uart_tx.tail;++mic_uart_tx.completed;mic_uart_tx.active=0U;
  uno_tx_begin_locked(HAL_GetTick());
}

void DMA1_Channel1_IRQHandler(void) {
  const uint32_t flags=DMA1->ISR&0x0fU;
  MIC_UART_TX_DMA_ACK(flags);
  if(!(flags&8U)) return;
  /* A real DMA bus error is fail-closed and never restarts half a packet.
     Do not call non-reentrant MCSDK routines from this ISR. */
  mic_uart_tx.hard_error=1U;
  ++mic_uart_tx.dma_errors;
  mic_uart_tx.last_status=HAL_ERROR;
  DMA1_Channel1->CCR &= ~DMA_CCR_EN;
  huart1.Instance->CR3 &= ~USART_CR3_DMAT;
  huart1.Instance->CR1 &= ~USART_CR1_TCIE;
  LL_TIM_DisableAllOutputs(TIM1);
}

static int uno_tx_watchdog(void) {
  int failure=HAL_OK;
  uno_tx_lock();
  /* TC may start the next frame immediately before this lock. Read the
     clock after masking its writer, never compare a newer start to an
     older caller timestamp (unsigned underflow looks like a huge delay). */
  const uint32_t now_ms=HAL_GetTick();
  if(mic_uart_tx.hard_error && !mic_uart_tx.late_reported) failure=HAL_ERROR;
  else if(mic_uart_tx.active && !mic_uart_tx.late_reported &&
      (uint32_t)(now_ms-mic_uart_tx.started_ms)>UNO_REPLY_TIMEOUT_MS) {
    ++mic_uart_tx.timeouts;failure=HAL_TIMEOUT;
  }
  if(failure!=HAL_OK) {
    mic_uart_tx.late_reported=1U;mic_uart_tx.last_status=(uint32_t)failure;
    /* Crucially, a wall-clock timeout does NOT abort DMA or change buffer,
       tail, CNDTR or TCIE. Main stops the motor; the current frame finishes. */
  }
  uno_tx_unlock();
  return failure;
}

static bool uno_tx_clear_ready(void) {
  return !mic_uart_tx.hard_error && !mic_uart_tx.active && mic_uart_tx.head==mic_uart_tx.tail;
}

static void uno_tx_init(void) {
  __HAL_RCC_DMA1_CLK_ENABLE();
  memset(&hdma_uno_tx,0,sizeof(hdma_uno_tx));
  hdma_uno_tx.Instance=DMA1_Channel1;
  hdma_uno_tx.Init.Request=DMA_REQUEST_USART1_TX;
  hdma_uno_tx.Init.Direction=DMA_MEMORY_TO_PERIPH;
  hdma_uno_tx.Init.PeriphInc=DMA_PINC_DISABLE;
  hdma_uno_tx.Init.MemInc=DMA_MINC_ENABLE;
  hdma_uno_tx.Init.PeriphDataAlignment=DMA_PDATAALIGN_BYTE;
  hdma_uno_tx.Init.MemDataAlignment=DMA_MDATAALIGN_BYTE;
  hdma_uno_tx.Init.Mode=DMA_NORMAL;
  hdma_uno_tx.Init.Priority=DMA_PRIORITY_HIGH;
  if(HAL_DMA_Init(&hdma_uno_tx)!=HAL_OK) Error_Handler();
  HAL_NVIC_SetPriority(DMA1_Channel1_IRQn,3U,0U);
  HAL_NVIC_ClearPendingIRQ(DMA1_Channel1_IRQn);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
}


static bool uno_rx_push(uint8_t byte, uint8_t flags) {
  const uint16_t next = (uno_rx_head + 1U) & UNO_RX_MASK;
  if (next == uno_rx_tail) return false;
  uno_rx_bytes[uno_rx_head] = byte;
  uno_rx_marks[uno_rx_head] = flags;
  uno_rx_head = next;
  return true;
}

static bool uno_rx_pop(uint8_t *byte, uint8_t *flags) {
  if (uno_rx_tail == uno_rx_head) return false;
  *byte = uno_rx_bytes[uno_rx_tail];
  *flags = uno_rx_marks[uno_rx_tail];
  uno_rx_tail = (uno_rx_tail + 1U) & UNO_RX_MASK;
  return true;
}

/* Hardware FIFO is disabled: one ISR snapshot and one RDR read form a
   sample. An NE without an available byte is not eligible for tolerance. */
void USART1_IRQHandler(void) {
  for (;;) {
    const uint32_t status = huart1.Instance->ISR;
    const uint32_t errors = status & (UART_FLAG_ORE | UART_FLAG_NE | UART_FLAG_FE | UART_FLAG_PE);
    const uint8_t marks =
        ((errors & UART_FLAG_PE) != 0U ? (uint8_t)UV3_PE : 0U) |
        ((errors & UART_FLAG_FE) != 0U ? (uint8_t)UV3_FE : 0U) |
        ((errors & UART_FLAG_NE) != 0U ? (uint8_t)UV3_NE : 0U) |
        ((errors & UART_FLAG_ORE) != 0U ? (uint8_t)UV3_ORE : 0U);
    if ((errors & UART_FLAG_ORE) != 0U) __HAL_UART_CLEAR_OREFLAG(&huart1);
    if ((errors & UART_FLAG_NE) != 0U) __HAL_UART_CLEAR_NEFLAG(&huart1);
    if ((errors & UART_FLAG_FE) != 0U) __HAL_UART_CLEAR_FEFLAG(&huart1);
    if ((errors & UART_FLAG_PE) != 0U) __HAL_UART_CLEAR_PEFLAG(&huart1);
    if ((marks & (UV3_PE | UV3_FE | UV3_ORE)) != 0U) uno_rx_errors |= marks;
    if ((status & UART_FLAG_RXNE) == 0U) {
      if ((marks & UV3_NE) != 0U) uno_rx_errors |= marks;
      break;
    }
    const uint8_t byte = (uint8_t)huart1.Instance->RDR;
    if (uno_rx_errors == 0U && uno_rx_overflow == 0U && !uno_rx_push(byte, marks)) uno_rx_overflow = 1U;
  }
  uno_tx_tc_isr();
}


static uint32_t uno_u32le(const uint8_t *data) {
  return (uint32_t)data[0] | ((uint32_t)data[1] << 8U) |
         ((uint32_t)data[2] << 16U) | ((uint32_t)data[3] << 24U);
}

static void uno_saturating_increment(uint16_t *value) {
  if (*value != UINT16_MAX) {
    ++(*value);
  }
}

static bool uno_mcsdk_fault_present(void) {
  const MCI_State_t state = MC_GetSTMStateMotor1();
  return MC_GetCurrentFaultsMotor1() != MC_NO_FAULTS ||
         state == FAULT_NOW || state == FAULT_OVER;
}

static void uno_stop_motor(void) {
  (void)MC_StopMotor1();
  mic_break_start_window = 0U;
  uno_link.command_enabled = false;
  uno_link.last_mode = UNO_MODE_OFF;
}

static bool uno_rearm_break_irq(void) {
  if (LL_TIM_IsEnabledAllOutputs(TIM1) ||
      HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_6) != GPIO_PIN_SET) return false;
  LL_TIM_ClearFlag_BRK(TIM1);
  LL_TIM_ClearFlag_BRK2(TIM1);
  if (LL_TIM_IsActiveFlag_BRK(TIM1) || LL_TIM_IsActiveFlag_BRK2(TIM1)) return false;
  LL_TIM_EnableIT_BRK(TIM1);
  return true;
}

static void uno_update_softstart_state(uint32_t now_ms) {
  const uint16_t vbus_v = VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);

  if (vbus_v < UNO_SOFTSTART_HOLD_V || vbus_v > UNO_SOFTSTART_MAX_V) {
    uno_link.softstart_ready = false;
    uno_link.softstart_tracking = false;
    uno_link.softstart_stable_since_ms = 0U;
    return;
  }
  if (uno_link.softstart_ready) {
    return;
  }
  if (vbus_v < UNO_SOFTSTART_READY_V) {
    uno_link.softstart_tracking = false;
    uno_link.softstart_stable_since_ms = 0U;
    return;
  }
  if (!uno_link.softstart_tracking) {
    uno_link.softstart_tracking = true;
    uno_link.softstart_stable_since_ms = now_ms;
    return;
  }
  if ((uint32_t)(now_ms - uno_link.softstart_stable_since_ms) >=
      MIC_EXTERNAL_SOFTSTART_SETTLE_MS) {
    uno_link.softstart_ready = true;
  }
}

static void uno_latch_fault(uint8_t fault_code) {
  uno_stop_motor();
  uno_link.fault_latched = true;
  uno_link.fault_code = fault_code;
}

static void uno_capture_diagnostics(uint8_t reason, uint8_t uart_errors, uint8_t tx_status) {
  if (uno_link.first_reason != UNO_DIAG_NONE) return;
  /* Snapshot before STOP/ESTOP changes the state or replaces the fault code. */
  uno_link.first_reason = reason;
  uno_link.first_uart_errors = uart_errors;
  uno_link.first_tx_status = tx_status;
  uno_link.first_motor_state = (uint8_t)MC_GetSTMStateMotor1();
  uno_link.first_current_faults = MC_GetCurrentFaultsMotor1();
  uno_link.first_occurred_faults = MC_GetOccurredFaultsMotor1();
  uno_link.first_sequence = uno_link.last_seq;
}

static void uno_latch_fault_reason(uint8_t fault_code, uint8_t reason) {
  uno_capture_diagnostics(reason, 0U, 0U);
  uno_latch_fault(fault_code);
}

static void uno_clear_diagnostics(void) {
  uno_link.first_reason = UNO_DIAG_NONE;
  uno_link.first_uart_errors = 0U;
  uno_link.first_motor_state = 0U;
  uno_link.first_tx_status = 0U;
  uno_link.first_sequence = 0U;
  uno_link.first_current_faults = 0U;
  uno_link.first_occurred_faults = 0U;
  uno_link.last_bad_reason = UNO_DIAG_NONE;
  uno_link.last_uart_errors = 0U;
  uno_link.last_tx_status = 0U;
}

static bool uno_clear_frame_is_safe(const uint8_t *frame) {
  if (frame[3] != UNO_FLAG_CLEAR_FAULT || frame[4] != UNO_MODE_OFF) {
    return false;
  }
  for (uint8_t index = 6U; index < UV3_PAYLOAD; ++index) {
    if (frame[index] != 0U) {
      return false;
    }
  }
  return true;
}

static bool uno_service_fields_are_zero(const uint8_t *frame) {
  for (uint8_t index = 14U; index < UV3_PAYLOAD; ++index) {
    if (frame[index] != 0U) {
      return false;
    }
  }
  return true;
}

static uint16_t uno_speed_ramp_ms(int16_t target) {
  // START clears the MCSDK ramp manager, so an IDLE start always begins at zero.
  const int32_t current = MC_GetSTMStateMotor1() == IDLE ? 0 :
      MC_GetMecSpeedReferenceMotor1();
  const int32_t difference = (int32_t)target - current;
  const uint32_t delta = (uint32_t)(difference < 0 ? -difference : difference);
  const uint32_t denominator = UNO_MAX_RAMP_HZ_PER_S * SPEED_UNIT;
  const uint32_t duration =
      (delta * POLE_PAIR_NUM * 1000U + denominator - 1U) / denominator;
  return (uint16_t)(duration < UNO_SPEED_RAMP_MS ? (uint32_t)UNO_SPEED_RAMP_MS :
      (duration > UINT16_MAX ? UINT16_MAX : duration));
}

static void mic_send_break_page(uint32_t now_ms) {
  static uint32_t last_ms;
  static uint8_t slot;
  mic_bkin_prepare_record();
  if (!mic_last_control_reply_safe_off || uno_link.command_enabled || mic_break_start_window != 0U ||
      LL_TIM_IsEnabledAllOutputs(TIM1) || MC_GetSTMStateMotor1() == RUN ||
      (uint32_t)(now_ms-last_ms) < 200U) return;
  last_ms = now_ms;
  if(slot>=2U*BW_PAGES+MIC_BKIN_WIRE_PAGES) {
    if(uno_transport.fatal_reject_valid) {
      uint8_t packet[UV3_FRAME];mic_uart_reject_packet(packet,slot-2U*BW_PAGES-MIC_BKIN_WIRE_PAGES);
      if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)!=HAL_OK)
        bw_increment(&mic_break_diag_tx_errors);
    }
    slot=(uint8_t)((slot+1U)%(2U*BW_PAGES+MIC_BKIN_WIRE_PAGES+UR_PAGES));return;
  }
  if (slot >= 2U * BW_PAGES) {
    if (mic_bkin_record_ready != 0U) {
      uint8_t packet[UV3_FRAME];
      mic_bkin_wave_packet(packet, slot - 2U * BW_PAGES);
      if (uno_tx_submit(packet,UNO_TX_TAG_DIAG) != HAL_OK)
        bw_increment(&mic_break_diag_tx_errors);
    }
    slot = (uint8_t)((slot + 1U) % (2U * BW_PAGES + MIC_BKIN_WIRE_PAGES + UR_PAGES));
    return;
  }
  const unsigned kind = slot / BW_PAGES;
  const unsigned page = slot % BW_PAGES;
  const volatile mic_break_snapshot_t *record = kind == 0U ? &mic_first_break : &mic_first_start_break;
  uint8_t raw[BW_BYTES] = {0};
  if (record->magic == MIC_BREAK_MAGIC) {
    __DMB();
    const volatile uint8_t *bytes = (const volatile uint8_t *)record;
    for (unsigned i=0;i<BW_BYTES;++i) raw[i]=bytes[i];
  }
  uint8_t packet[UV3_FRAME];
  bw_packet(packet,raw,kind,page);
  /* A diagnostic TX failure is counted separately; normal control TX fault
     handling remains unchanged. No START/CLEAR or retry loop occurs here. */
  if (uno_tx_submit(packet,UNO_TX_TAG_DIAG) != HAL_OK)
    bw_increment(&mic_break_diag_tx_errors);
  slot=(uint8_t)((slot+1U)%(2U*BW_PAGES + MIC_BKIN_WIRE_PAGES + UR_PAGES));
}

static void mic_send_current_page(uint32_t now_ms) {
  static uint32_t last_ms;
  static uint8_t slot;
  if((uint32_t)(now_ms-last_ms)<200U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error) return;
  uint8_t packet[UV3_FRAME];
  if(slot!=4U || !mic_zero_packet(packet,MIC_NUCLEO_FW_BUILD_ID))
    mic_current_packet(packet,(uint8_t)(slot==0U?1U:slot==2U?2U:0U),MIC_NUCLEO_FW_BUILD_ID);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK) {
    last_ms=now_ms;slot=(uint8_t)((slot+1U)%5U);
  }
}

static void mic_send_peak_page(uint32_t now_ms) {
  static uint32_t last_ms;static uint8_t page;
  if(LL_TIM_IsEnabledAllOutputs(TIM1) || (uint32_t)(now_ms-last_ms)<100U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_current_peak_packet(packet,page,MIC_NUCLEO_FW_BUILD_ID) &&
      uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){last_ms=now_ms;page=(uint8_t)((page+1U)%35U);}
}

static void mic_send_encoder_page(uint32_t now_ms) {
  static uint32_t last_ms;
  if(!uno_link.link_seen || (uint32_t)(now_ms-last_ms)<20U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];mic_encoder_packet(packet,MIC_NUCLEO_FW_BUILD_ID);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last_ms=now_ms;
}

static void mic_send_encoder_fault_page(uint32_t now_ms) {
  static uint32_t last_ms;static uint8_t page,slot;
  if(LL_TIM_IsEnabledAllOutputs(TIM1) || !uno_link.link_seen || (uint32_t)(now_ms-last_ms)<100U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_encoder_fault_packet(packet,slot,page)) {
    if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)!=HAL_OK)return;
    last_ms=now_ms;
  }
  if(++page==FC_PAGES){page=0;slot^=1U;}
}

static void mic_send_encoder_health_page(uint32_t now_ms){
  static uint32_t last_ms,values[14];static uint8_t page,gen;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)){page=0;return;}
  if(!uno_link.link_seen || (uint32_t)(now_ms-last_ms)<250U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  if(!page){mic_encoder_health_snapshot(values);++gen;}
  uint8_t packet[UV3_FRAME];eh_packet(packet,values,page,gen);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){last_ms=now_ms;page^=1U;}
}

static void mic_send_encoder_release_page(uint32_t now_ms){
  static uint32_t last_ms;static uint8_t page,slot;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||!uno_link.link_seen||(uint32_t)(now_ms-last_ms)<150U||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_encoder_release_packet(packet,slot,page)){
    if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)!=HAL_OK)return;
    last_ms=now_ms;
  }
  if(++page==PR_PAGES){page=0;slot^=1U;}
}

static void mic_send_bus_clear(uint32_t now_ms){
  static uint32_t last_ms;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||!uno_link.link_seen||(uint32_t)(now_ms-last_ms)<500U||
     (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_encoder_bus_clear_packet(packet)&&uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last_ms=now_ms;
}

static void uno_send_reply(void) {
  uint8_t reply[UNO_FRAME_LEN] = {0};
  const uint32_t now_ms = HAL_GetTick();
  const bool link_ok = uno_link.link_seen &&
                       (uint32_t)(now_ms - uno_link.last_valid_ms) <= UNO_LINK_TIMEOUT_MS;
  const MCI_State_t motor_state = MC_GetSTMStateMotor1();
  const bool mcsdk_fault = uno_mcsdk_fault_present();
  const bool local_stop = mic_local_stop_blocked();
  const bool fault = uno_link.fault_latched || mcsdk_fault || local_stop;
  const uint16_t vbus_v = VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  const uint16_t vbus_deci_v = (vbus_v <= (UINT16_MAX / 10U))
                                  ? (uint16_t)(vbus_v * 10U)
                                  : UINT16_MAX;
  const int16_t temp_deci_c = (int16_t)(NTC_GetAvTemp_C(&TempSensor_M1) * 10);
  const uint16_t mcsdk_faults = MC_GetCurrentFaultsMotor1();
  uint8_t fault_code = uno_link.fault_code;
  uint8_t status = 0U;

  /* Cached context is explicitly not an IRQ-time sensor sample. */
  const mic_break_context_t break_context = {
      now_ms, MC_GetMecSpeedReferenceMotor1(), (uint32_t)motor_state,
      mcsdk_faults, MC_GetOccurredFaultsMotor1(), vbus_v, temp_deci_c,
      uno_link.last_seq};
  mic_break_publish_context(&break_context);

  /* ACK clears the masks before the scheduler leaves FAULT_OVER. */
  if (mcsdk_fault && (motor_state != FAULT_OVER ||
      mcsdk_faults != MC_NO_FAULTS || MC_GetOccurredFaultsMotor1() != MC_NO_FAULTS)) {
    uno_capture_diagnostics(UNO_DIAG_MCSDK, 0U, 0U);
  }

  if (local_stop) { status |= 0x80U | UNO_STATUS_ESTOP; fault_code = UNO_FAULT_ESTOP; }
  if (link_ok) status |= UNO_STATUS_LINK_OK;
  if (uno_link.command_enabled && !fault) status |= UNO_STATUS_ENABLED;
  if (uno_link.fault_latched && uno_link.fault_code == UNO_FAULT_ESTOP) status |= UNO_STATUS_ESTOP;
  if (fault) status |= UNO_STATUS_FAULT;
  if (uno_link.fault_latched && uno_link.fault_code == UNO_FAULT_TIMEOUT) status |= UNO_STATUS_TIMEOUT;
  if (LL_TIM_IsEnabledAllOutputs(TIM1)) status |= UNO_STATUS_PWM_ACTIVE | UNO_STATUS_SHUTDOWN_RELEASED;
  if (mcsdk_fault && fault_code == UNO_FAULT_OK) fault_code = UNO_FAULT_INTERNAL;

  reply[0] = UNO_RSP_HDR0;
  reply[1] = UNO_RSP_HDR1;
  reply[2] = UNO_PROTOCOL_VERSION;
  reply[3] = status;
  reply[4] = uno_link.last_seq;
  reply[5] = (uint8_t)(uno_link.good_count & 0xFFU);
  reply[6] = (uint8_t)(uno_link.good_count >> 8U);
  reply[7] = (uint8_t)(uno_link.bad_count & 0xFFU);
  reply[8] = (uint8_t)(uno_link.bad_count >> 8U);
  reply[9] = fault_code;
  reply[10] = uno_link.last_mode;
  /* Tagged extension in unused MCSDK reply slots; command ABI stays unchanged. */
  reply[11] = UNO_DIAG_TAG | uno_link.first_reason;
  reply[12] = (uno_link.first_uart_errors & 0x0FU) | (uno_link.last_uart_errors << 4U);
  reply[13] = (uno_link.first_motor_state & 0x1FU) | ((uno_link.last_tx_status & 0x03U) << 5U);
  reply[15] = (uint8_t)uno_link.first_current_faults;
  reply[16] = (uint8_t)(uno_link.first_current_faults >> 8U);
  reply[22] = (uno_link.first_tx_status & 0x0FU) | (uno_link.last_bad_reason << 4U);
  reply[27] = (uint8_t)uno_link.first_occurred_faults;
  reply[28] = (uint8_t)(uno_link.first_occurred_faults >> 8U);
  reply[30] = uno_link.first_sequence;
  /* The legacy relay bit is reserved and must stay zero. The external AC
     soft-start module is autonomous and has no MCU control connection. */
  reply[14] = 0U;
  reply[17] = (uint8_t)(vbus_deci_v & 0xFFU);
  reply[18] = (uint8_t)(vbus_deci_v >> 8U);
  reply[19] = (uint8_t)(((uint16_t)temp_deci_c) & 0xFFU);
  reply[20] = (uint8_t)(((uint16_t)temp_deci_c) >> 8U);
  reply[21] = UNO_TEMP_VALID;
  /* Additive status only: read GPIO/timer registers, never drive SD or rearm.
     Upper temperature-flag bits were reserved in older peer identities. */
  const bool sd_config_ok =
      ((GPIOA->MODER >> 12U) & 3U) == 2U &&
      (GPIOA->OTYPER & GPIO_PIN_6) != 0U &&
      ((GPIOA->PUPDR >> 12U) & 3U) == 1U &&
      ((GPIOA->AFR[0] >> 24U) & 15U) == 6U &&
      (TIM1->AF1 & (TIM1_AF1_BKINE | TIM1_AF1_BKINP)) ==
          (TIM1_AF1_BKINE | TIM1_AF1_BKINP) &&
      (TIM1->BDTR & (TIM_BDTR_BKE | TIM_BDTR_BKP | TIM_BDTR_BKBID)) ==
          (TIM_BDTR_BKE | TIM_BDTR_BKP) &&
      (TIM1->BDTR & TIM_BDTR_BKF) == LL_TIM_BREAK_FILTER_FDIV8_N8 &&
      (TIM1->CR1 & TIM_CR1_CKD) == TIM_CLOCKDIVISION_DIV2 &&
      (TIM1->BDTR & TIM_BDTR_AOE) == 0U;
  reply[21] |= sd_live_encode((GPIOA->IDR & GPIO_PIN_6) != 0U,
      (TIM1->DIER & TIM_DIER_BIE) != 0U,
      mic_bkin_capture_state == MIC_BKIN_RUNNING,
      mic_bkin_record_ready != 0U, sd_config_ok);
  if ((mcsdk_faults & MC_OVER_TEMP) != 0U) reply[21] |= UNO_TEMP_FAULT;
  /* Phase-voltage samples are not implemented by this MCSDK image. Reuse
     their reserved bytes for an explicit firmware identity. The validity
     flag prevents older peers from interpreting the value as live ADC data. */
  reply[23] = (uint8_t)(MIC_NUCLEO_FW_BUILD_ID & 0xFFU);
  reply[24] = (uint8_t)((MIC_NUCLEO_FW_BUILD_ID >> 8U) & 0xFFU);
  reply[25] = (uint8_t)((MIC_NUCLEO_FW_BUILD_ID >> 16U) & 0xFFU);
  reply[26] = (uint8_t)((MIC_NUCLEO_FW_BUILD_ID >> 24U) & 0xFFU);
  reply[29] = UNO_TELEMETRY_FW_BUILD_VALID |
              UNO_TELEMETRY_MCSDK_UNITS |
              UNO_TELEMETRY_VBUS_VALID;
  if (uno_link.softstart_ready) reply[29] |= UNO_TELEMETRY_SOFTSTART_READY;
  // Live reference uses a new explicit tag only with no retained first fault.
  // Any fault keeps the original complete diagnostic snapshot layout.
  if (uno_link.first_reason==UNO_DIAG_NONE && !fault) {
    const int32_t value=(int32_t)MC_GetMecSpeedReferenceMotor1()*POLE_PAIR_NUM*100/SPEED_UNIT;
    const uint16_t reference=(uint16_t)(value<0 ? 0 : value);
    reply[11]=0xA0U | (uno_link.decel_bus_hold ? 1U : 0U);
    reply[12]=(uint8_t)reference;reply[13]=(uint8_t)(reference>>8);
  }
  uv3_reply_diagnostics(reply, &uno_transport);
  uv3_seal(reply);
  const int tx_status = uno_tx_submit(reply,(status&0x22U)==0U ? UNO_TX_TAG_OFF : UNO_TX_TAG_ON);
  /* Publish diagnostics only after an off reply, not an IRQ transition
     which occurred while a previous on reply was being transmitted. */
  /* OFF evidence is published only by the USART TC ISR after the last stop bit. */
  if (tx_status == HAL_OK) { mic_send_break_page(now_ms);mic_send_current_page(now_ms);mic_send_peak_page(now_ms); }
  if (tx_status != HAL_OK) {
    uno_capture_diagnostics(UNO_DIAG_TX, 0U, (uint8_t)tx_status);
    uno_link.last_bad_reason = UNO_DIAG_TX;
    uno_link.last_tx_status = (uint8_t)tx_status;
    uno_saturating_increment(&uno_link.bad_count);
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_TX);
  }
}

static bool uno_abort_pending_rx_fault(void);

static void uno_handle_valid_frame(const uint8_t *frame) {
  if (uno_abort_pending_rx_fault()) return;
  const uint32_t now_ms = HAL_GetTick();
  const uint8_t flags = frame[3];
  const uint8_t mode = frame[4];
  const uint32_t frequency_millihz = uno_u32le(&frame[6]);
  const uint32_t max_frequency_millihz =
      ((uint32_t)MOTOR_MAX_SPEED_RPM * (uint32_t)POLE_PAIR_NUM * 1000U) / 60U;
  const uint32_t min_frequency_millihz = (1000U * POLE_PAIR_NUM + SPEED_UNIT - 1U) / SPEED_UNIT;

  if (frame[2] != UNO_PROTOCOL_VERSION) {
    uno_link.last_bad_reason = UNO_DIAG_VERSION;
    uno_saturating_increment(&uno_link.bad_count);
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_VERSION);
    return;
  }

  /* A frozen transmitter must not keep the motor alive by replaying the last
     valid ENABLE frame. Repeated CLEAR remains legal so MCSDK faults can be
     acknowledged until the state machine accepts the request. */
  if (uno_link.link_seen && flags == UNO_FLAG_ENABLE &&
      mode == UNO_MODE_SCALAR && frame[5] == uno_link.last_seq) {
    uno_link.last_bad_reason = UNO_DIAG_REPLAY;
    uno_saturating_increment(&uno_link.bad_count);
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_REPLAY);
    return;
  }

  uno_link.link_seen = true;
  uno_link.last_valid_ms = now_ms;
  uno_link.last_seq = frame[5];
  uno_saturating_increment(&uno_link.good_count);

  /* Diagnostic image cannot accept any motor ENABLE request. */
  if ((flags & UNO_FLAG_ENABLE) != 0U) { uno_stop_motor(); return; }

  if (uno_clear_frame_is_safe(frame)) {
    if(!uno_tx_clear_ready()) {
      uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_TX);return;
    }
    uno_link.coast_hold=false;
    uno_stop_motor();
    if (!uno_rearm_break_irq()) {
      uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_MCSDK);
      return;
    }
    (void)MC_AcknowledgeFaultMotor1();
    if (mic_local_stop_latched != 0U && !mic_local_stop_clear()) {
      uno_latch_fault_reason(UNO_FAULT_ESTOP, UNO_DIAG_ESTOP);
      return;
    }
    uno_link.fault_latched = false;
    uno_link.fault_code = UNO_FAULT_OK;
    uno_link.bad_count = 0U;
    uno_clear_diagnostics();
    return;
  }

  if (mic_local_stop_blocked()) {
    uno_latch_fault_reason(UNO_FAULT_ESTOP, UNO_DIAG_ESTOP);
    return;
  }

  if ((flags & UNO_FLAG_ESTOP) != 0U) {
    uno_latch_fault_reason(UNO_FAULT_ESTOP, UNO_DIAG_ESTOP);
    return;
  }

  /* A latched transport or E-stop fault can only be released by the clean
     CLEAR frame handled above. STOP and ENABLE frames must never clear it. */
  if (uno_link.fault_latched) {
    uno_stop_motor();
    return;
  }

  if (!uno_service_fields_are_zero(frame) || (mode == UNO_MODE_SCALAR && !msc_wire_valid(frame))) {
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_SERVICE);
    return;
  }

  if (flags == 0U && mode == UNO_MODE_OFF) {
    uno_link.coast_hold=false;
    uno_stop_motor();
    return;
  }

  if (flags != UNO_FLAG_ENABLE || mode != UNO_MODE_SCALAR ||
      frequency_millihz < min_frequency_millihz || frequency_millihz > max_frequency_millihz ||
      uno_mcsdk_fault_present()) {
    const uint8_t reason = (flags != UNO_FLAG_ENABLE || mode != UNO_MODE_SCALAR)
        ? UNO_DIAG_COMMAND
        : ((frequency_millihz < min_frequency_millihz || frequency_millihz > max_frequency_millihz)
            ? UNO_DIAG_FREQUENCY : UNO_DIAG_MCSDK);
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, reason);
    return;
  }

  const uint16_t vbus_v = VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  uno_update_softstart_state(now_ms);
  if (vbus_v > UNO_SOFTSTART_MAX_V) {
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_BUS);
    return;
  }
  if (!uno_link.softstart_ready) {
    if (uno_link.command_enabled) uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_BUS);
    return;
  }

  const uint32_t target_rpm =
      (frequency_millihz * 60U) / ((uint32_t)POLE_PAIR_NUM * 1000U);
  const int16_t target_speed_unit = RPM_2_SPEED_UNIT((int32_t)target_rpm);
  bool update_ramp = !uno_link.command_enabled || target_speed_unit != uno_link.last_speed_unit;
  uint16_t ramp_ms = update_ramp ? uno_speed_ramp_ms(target_speed_unit) : 0U;
  int16_t programmed_speed_unit=target_speed_unit;
  uint16_t rate=0U;
  if (msc_wire_present(frame)) {
    rate=(uint16_t)(frame[10] | ((uint16_t)frame[11]<<8));
    if (frame[12]==MSC_TAG_COAST && uno_link.command_enabled && target_speed_unit<uno_link.last_speed_unit) {
      uno_link.coast_hold=true;uno_stop_motor();return;
    }
    if (uno_link.coast_hold) { uno_stop_motor();return; }
    const int16_t current=MC_GetSTMStateMotor1()==IDLE ? 0 : MC_GetMecSpeedReferenceMotor1();
    uno_link.manual_ramp_down=frame[12]==MSC_TAG_RAMP;
    if (uno_link.decel_bus_hold && target_speed_unit<current) {
      uno_link.last_speed_unit=target_speed_unit;return;
    }
    if (target_speed_unit>=current) uno_link.decel_bus_hold=false;
    update_ramp=update_ramp || rate!=uno_link.ramp_rate_centi ||
        (uno_link.ramp_target_speed_unit!=target_speed_unit && MC_HasRampCompletedMotor1());
    if (update_ramp) ramp_ms=msc_segment(current,target_speed_unit,rate,SPEED_UNIT,POLE_PAIR_NUM,&programmed_speed_unit);
  }
  const MCI_State_t start_state = MC_GetSTMStateMotor1();
  if (uno_abort_pending_rx_fault()) return;
  bool start_failed = false;
  /* The final RX check and command publication share one USART-only section.
     MCSDK APIs only enqueue commands; ADC/TIM protection IRQs remain enabled. */
  HAL_NVIC_DisableIRQ(USART1_IRQn);
  const bool rx_fault_pending = uno_rx_errors != 0U || uno_rx_overflow != 0U;
  if (!rx_fault_pending) {
    if (update_ramp) {
      MC_ProgramSpeedRampMotor1(programmed_speed_unit, ramp_ms);
      uno_link.ramp_target_speed_unit=programmed_speed_unit;
      uno_link.ramp_rate_centi=rate;
      uno_link.last_speed_unit = target_speed_unit;
    }
    if (start_state == IDLE) {
      mic_bkin_capture_start();
      mic_break_start_window = 1U;
      if (!MC_StartMotor1()) {
        mic_break_start_window = 0U;
        start_failed = true;
      }
    }
  }
  HAL_NVIC_EnableIRQ(USART1_IRQn);
  if (uno_abort_pending_rx_fault()) return;
  if (rx_fault_pending) return;
  if (start_failed) {
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_START);
    return;
  }

  uno_link.command_enabled = true;
  uno_link.last_mode = UNO_MODE_SCALAR;
  uno_link.fault_code = UNO_FAULT_OK;
}

static void uno_transport_result(uv3_result result) {
  if (result == UV3_WAIT || result == UV3_DROPPED) return;
  if (result != UV3_READY) {
    const uint8_t reason = result == UV3_BAD_CRC ? UNO_DIAG_CRC :
        result == UV3_BAD_VERSION ? UNO_DIAG_VERSION : result == UV3_BAD_SEQUENCE ? UNO_DIAG_REPLAY :
        result == UV3_LINK_TIMEOUT || result == UV3_FRAME_TIMEOUT ? UNO_DIAG_TIMEOUT : UNO_DIAG_UART;
    uno_capture_diagnostics(reason, uno_transport.last_uart_flags, 0U);
    uno_link.last_bad_reason = reason;
    uno_link.last_uart_errors = uno_transport.last_uart_flags;
    uno_saturating_increment(&uno_link.bad_count);
    const uint8_t code = result == UV3_BAD_CRC ? UNO_FAULT_BAD_CRC :
        result == UV3_LINK_TIMEOUT || result == UV3_FRAME_TIMEOUT ? UNO_FAULT_TIMEOUT : UNO_FAULT_INTERNAL;
    uno_latch_fault_reason(code, reason);
    return;
  }
  if (uno_abort_pending_rx_fault()) return;
  uno_handle_valid_frame(uno_transport.frame);
  uno_send_reply();
  bool clean_clear = uno_transport.frame[3] == UNO_FLAG_CLEAR_FAULT &&
                     uno_transport.frame[4] == UNO_MODE_OFF;
  for (unsigned i = 6U; i < UV3_PAYLOAD; ++i) clean_clear = clean_clear && uno_transport.frame[i] == 0U;
  uv3_commit(&uno_transport, HAL_GetTick(),
             uno_link.command_enabled && MC_GetSTMStateMotor1() == RUN,
             uno_link.fault_latched, clean_clear);
}

static void uno_consume_sample(uint8_t byte, uint8_t flags) {
  uno_transport_result(uv3_byte(&uno_transport, byte, flags, HAL_GetTick()));
}


static void uno_link_init(void) {
  memset(&uno_link, 0, sizeof(uno_link));
  uno_link.fault_code = UNO_FAULT_OK;
  uno_link.last_mode = UNO_MODE_OFF;
  uno_rx_head = uno_rx_tail = 0U;
  uno_rx_errors = uno_rx_overflow = 0U;
  uv3_init(&uno_transport, true);
}

static bool uno_abort_pending_rx_fault(void) {
  for (;;) {
    /* Mask only USART1; ADC/TIM protection IRQs stay enabled. */
    HAL_NVIC_DisableIRQ(USART1_IRQn);
    const uint8_t errors = uno_rx_errors;
    const uint8_t overflow = uno_rx_overflow;
    uno_rx_errors = uno_rx_overflow = 0U;
    if (errors != 0U || overflow != 0U) uno_rx_head = uno_rx_tail = 0U;
    HAL_NVIC_EnableIRQ(USART1_IRQn);
    if (errors != 0U || overflow != 0U) {
      const uint8_t reason = errors != 0U ? UNO_DIAG_UART : UNO_DIAG_RX_BUFFER;
      uno_capture_diagnostics(reason, errors, 0U);
      uno_link.last_bad_reason = reason;
      if (errors != 0U) uno_link.last_uart_errors = errors;
      uno_link.parser_state = 0U;
      uno_link.parser_index = 0U;
      uno_transport.last_uart_flags = errors;
      uv3_trip(&uno_transport, UV3_HARD_UART);
      uno_saturating_increment(&uno_link.bad_count);
      uno_latch_fault_reason(UNO_FAULT_INTERNAL, reason);
      return true;
    }
    /* A pending ISR can publish an error immediately when IRQs resume. */
    if (uno_rx_errors == 0U && uno_rx_overflow == 0U) return false;
  }
}

static void uno_manual_bus_control(void) {
  if (!uno_link.command_enabled || !uno_link.manual_ramp_down || !uno_link.ramp_rate_centi) return;
  const int16_t current=MC_GetMecSpeedReferenceMotor1();
  if (uno_link.last_speed_unit>=current) return;
  const uint16_t bus=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  if (bus>=360U) { uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_BUS);return; }
  if (bus>=350U && !uno_link.decel_bus_hold) {
    MC_ProgramSpeedRampMotor1(current,0U);
    uno_link.ramp_target_speed_unit=current;
    uno_link.decel_bus_hold=true;
  } else if (bus<=340U) uno_link.decel_bus_hold=false;
}
static void uno_link_poll(void) {
  const int tx_failure=uno_tx_watchdog();
  if(tx_failure!=HAL_OK) {
    uno_capture_diagnostics(UNO_DIAG_TX,0U,(uint8_t)tx_failure);
    uno_link.last_bad_reason=UNO_DIAG_TX;
    uno_link.last_tx_status=(uint8_t)tx_failure;
    uno_saturating_increment(&uno_link.bad_count);
    uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_TX);
  }
  uno_manual_bus_control();
  if (mic_local_stop_blocked()) uno_latch_fault_reason(UNO_FAULT_ESTOP, UNO_DIAG_ESTOP);
  uno_update_softstart_state(HAL_GetTick());
  if (uno_abort_pending_rx_fault()) return;
  uno_transport_result(uv3_tick(&uno_transport, HAL_GetTick()));
  uint8_t byte, flags;
  while (uno_rx_pop(&byte, &flags)) {
    if (uno_abort_pending_rx_fault()) return;
    uno_consume_sample(byte, flags);
  }
  if (uno_link.command_enabled && !uno_link.softstart_ready) {
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_BUS);
  }
  if (uno_link.link_seen && !uno_link.fault_latched &&
      (uint32_t)(HAL_GetTick() - uno_link.last_valid_ms) > UNO_LINK_TIMEOUT_MS) {
    uno_latch_fault_reason(UNO_FAULT_TIMEOUT, UNO_DIAG_TIMEOUT);
  }
  if (uno_link.command_enabled && uno_mcsdk_fault_present()) {
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_MCSDK);
  }
}

static void MX_USART1_UART_Init(void) {
  GPIO_InitTypeDef gpio = {0};

  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_USART1_CLK_ENABLE();
  gpio.Pin = GPIO_PIN_6 | GPIO_PIN_7;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_PULLUP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  gpio.Alternate = GPIO_AF7_USART1;
  HAL_GPIO_Init(GPIOB, &gpio);

  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  huart1.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  huart1.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  huart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&huart1) != HAL_OK ||
      HAL_UARTEx_DisableFifoMode(&huart1) != HAL_OK) {
    Error_Handler();
  }
  uno_tx_init();
  HAL_NVIC_SetPriority(USART1_IRQn, 3U, 0U);
  __HAL_UART_ENABLE_IT(&huart1, UART_IT_RXNE);
  __HAL_UART_ENABLE_IT(&huart1, UART_IT_ERR);
  HAL_NVIC_EnableIRQ(USART1_IRQn);
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_ADC1_Init();
  MX_ADC2_Init();
  MX_CORDIC_Init();
  MX_TIM1_Init();
  MX_USART2_UART_Init();
  /* Set phase GPIO LOW before MCSDK permanently locks its configuration. */
  mic_load_prepare_pins();
  MX_MotorControl_Init();

  /* Initialize interrupts */
  MX_NVIC_Init();
  /* USER CODE BEGIN 2 */

  /* Arm the passive BKIN trace after MCSDK boot synchronization, before any START. */
  mic_bkin_capture_start();

  mic_current_init();
  mic_encoder_init();
  /* Keep the external UNO Q transport outside generated peripheral lists. */
  uno_link_init();
  MX_USART1_UART_Init();

  /* USER CODE END 2 */

  mic_load_init();

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    uno_link_poll();
    mic_load_poll();
    mic_encoder_allow_bus_clear(!mic_load_active() && !uno_link.command_enabled && mic_break_start_window==0U &&
      !LL_TIM_IsEnabledAllOutputs(TIM1) &&
      (MC_GetSTMStateMotor1()==IDLE || MC_GetSTMStateMotor1()==FAULT_NOW || MC_GetSTMStateMotor1()==FAULT_OVER) &&
      VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)<20U);
    mic_encoder_poll();
    mic_send_encoder_page(HAL_GetTick());
    mic_send_encoder_fault_page(HAL_GetTick());
    mic_send_encoder_health_page(HAL_GetTick());
    mic_send_encoder_release_page(HAL_GetTick());
    mic_send_bus_clear(HAL_GetTick());
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV6;
  RCC_OscInitStruct.PLL.PLLN = 85;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV8;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }

  /** Enables the Clock Security System
  */
  HAL_RCC_EnableCSS();
}

/**
  * @brief NVIC Configuration.
  * @retval None
  */
static void MX_NVIC_Init(void)
{
  /* USART2_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(USART2_IRQn, 3, 1);
  HAL_NVIC_EnableIRQ(USART2_IRQn);
  /* TIM1_BRK_TIM15_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(TIM1_BRK_TIM15_IRQn, 4, 1);
  HAL_NVIC_EnableIRQ(TIM1_BRK_TIM15_IRQn);
  /* DMA2_Channel2_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA2_Channel2_IRQn, 3, 0);
  HAL_NVIC_EnableIRQ(DMA2_Channel2_IRQn);
  /* TIM1_UP_TIM16_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(TIM1_UP_TIM16_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(TIM1_UP_TIM16_IRQn);
  /* ADC1_2_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(ADC1_2_IRQn, 2, 0);
  HAL_NVIC_EnableIRQ(ADC1_2_IRQn);
  /* EXTI15_10_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(EXTI15_10_IRQn, 3, 0);
  HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
}

/**
  * @brief ADC1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_ADC1_Init(void)
{

  /* USER CODE BEGIN ADC1_Init 0 */

  /* USER CODE END ADC1_Init 0 */

  ADC_MultiModeTypeDef multimode = {0};
  ADC_InjectionConfTypeDef sConfigInjected = {0};
  ADC_ChannelConfTypeDef sConfig = {0};

  /* USER CODE BEGIN ADC1_Init 1 */

  /* USER CODE END ADC1_Init 1 */

  /** Common config
  */
  hadc1.Instance = ADC1;
  hadc1.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV1;
  hadc1.Init.Resolution = ADC_RESOLUTION_12B;
  hadc1.Init.DataAlign = ADC_DATAALIGN_LEFT;
  hadc1.Init.GainCompensation = 0;
  hadc1.Init.ScanConvMode = ADC_SCAN_ENABLE;
  hadc1.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  hadc1.Init.LowPowerAutoWait = DISABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.NbrOfConversion = 2;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
  hadc1.Init.DMAContinuousRequests = DISABLE;
  hadc1.Init.Overrun = ADC_OVR_DATA_PRESERVED;
  hadc1.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&hadc1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure the ADC multi-mode
  */
  multimode.Mode = ADC_MODE_INDEPENDENT;
  if (HAL_ADCEx_MultiModeConfigChannel(&hadc1, &multimode) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Injected Channel
  */
  sConfigInjected.InjectedChannel = ADC_CHANNEL_1;
  sConfigInjected.InjectedRank = ADC_INJECTED_RANK_1;
  sConfigInjected.InjectedSamplingTime = ADC_SAMPLETIME_24CYCLES_5;
  sConfigInjected.InjectedSingleDiff = ADC_SINGLE_ENDED;
  sConfigInjected.InjectedOffsetNumber = ADC_OFFSET_NONE;
  sConfigInjected.InjectedOffset = 0;
  sConfigInjected.InjectedNbrOfConversion = 2;
  sConfigInjected.InjectedDiscontinuousConvMode = DISABLE;
  sConfigInjected.AutoInjectedConv = DISABLE;
  sConfigInjected.QueueInjectedContext = DISABLE;
  sConfigInjected.ExternalTrigInjecConv = ADC_EXTERNALTRIGINJEC_T1_TRGO;
  sConfigInjected.ExternalTrigInjecConvEdge = ADC_EXTERNALTRIGINJECCONV_EDGE_RISING;
  sConfigInjected.InjecOversamplingMode = DISABLE;
  if (HAL_ADCEx_InjectedConfigChannel(&hadc1, &sConfigInjected) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Injected Channel
  */
  sConfigInjected.InjectedChannel = ADC_CHANNEL_7;
  sConfigInjected.InjectedRank = ADC_INJECTED_RANK_2;
  if (HAL_ADCEx_InjectedConfigChannel(&hadc1, &sConfigInjected) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_2;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  sConfig.SamplingTime = ADC_SAMPLETIME_47CYCLES_5;
  sConfig.SingleDiff = ADC_SINGLE_ENDED;
  sConfig.OffsetNumber = ADC_OFFSET_NONE;
  sConfig.Offset = 0;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_8;
  sConfig.Rank = ADC_REGULAR_RANK_2;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN ADC1_Init 2 */

  /* USER CODE END ADC1_Init 2 */

}

/**
  * @brief ADC2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_ADC2_Init(void)
{

  /* USER CODE BEGIN ADC2_Init 0 */

  /* USER CODE END ADC2_Init 0 */

  ADC_InjectionConfTypeDef sConfigInjected = {0};

  /* USER CODE BEGIN ADC2_Init 1 */

  /* USER CODE END ADC2_Init 1 */

  /** Common config
  */
  hadc2.Instance = ADC2;
  hadc2.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV1;
  hadc2.Init.Resolution = ADC_RESOLUTION_12B;
  hadc2.Init.DataAlign = ADC_DATAALIGN_LEFT;
  hadc2.Init.GainCompensation = 0;
  hadc2.Init.ScanConvMode = ADC_SCAN_ENABLE;
  hadc2.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  hadc2.Init.LowPowerAutoWait = DISABLE;
  hadc2.Init.ContinuousConvMode = DISABLE;
  hadc2.Init.NbrOfConversion = 1;
  hadc2.Init.DiscontinuousConvMode = DISABLE;
  hadc2.Init.DMAContinuousRequests = DISABLE;
  hadc2.Init.Overrun = ADC_OVR_DATA_PRESERVED;
  hadc2.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&hadc2) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Injected Channel
  */
  sConfigInjected.InjectedChannel = ADC_CHANNEL_7;
  sConfigInjected.InjectedRank = ADC_INJECTED_RANK_1;
  sConfigInjected.InjectedSamplingTime = ADC_SAMPLETIME_24CYCLES_5;
  sConfigInjected.InjectedSingleDiff = ADC_SINGLE_ENDED;
  sConfigInjected.InjectedOffsetNumber = ADC_OFFSET_NONE;
  sConfigInjected.InjectedOffset = 0;
  sConfigInjected.InjectedNbrOfConversion = 2;
  sConfigInjected.InjectedDiscontinuousConvMode = DISABLE;
  sConfigInjected.AutoInjectedConv = DISABLE;
  sConfigInjected.QueueInjectedContext = DISABLE;
  sConfigInjected.ExternalTrigInjecConv = ADC_EXTERNALTRIGINJEC_T1_TRGO;
  sConfigInjected.ExternalTrigInjecConvEdge = ADC_EXTERNALTRIGINJECCONV_EDGE_RISING;
  sConfigInjected.InjecOversamplingMode = DISABLE;
  if (HAL_ADCEx_InjectedConfigChannel(&hadc2, &sConfigInjected) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Injected Channel
  */
  sConfigInjected.InjectedChannel = ADC_CHANNEL_6;
  sConfigInjected.InjectedRank = ADC_INJECTED_RANK_2;
  if (HAL_ADCEx_InjectedConfigChannel(&hadc2, &sConfigInjected) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN ADC2_Init 2 */

  /* USER CODE END ADC2_Init 2 */

}

/**
  * @brief CORDIC Initialization Function
  * @param None
  * @retval None
  */
static void MX_CORDIC_Init(void)
{

  /* USER CODE BEGIN CORDIC_Init 0 */

  /* USER CODE END CORDIC_Init 0 */

  /* USER CODE BEGIN CORDIC_Init 1 */

  /* USER CODE END CORDIC_Init 1 */
  hcordic.Instance = CORDIC;
  if (HAL_CORDIC_Init(&hcordic) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN CORDIC_Init 2 */

  /* USER CODE END CORDIC_Init 2 */

}

/**
  * @brief TIM1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM1_Init(void)
{

  /* USER CODE BEGIN TIM1_Init 0 */

  /* USER CODE END TIM1_Init 0 */

  TIM_SlaveConfigTypeDef sSlaveConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIMEx_BreakInputConfigTypeDef sBreakInputConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};
  TIM_BreakDeadTimeConfigTypeDef sBreakDeadTimeConfig = {0};

  /* USER CODE BEGIN TIM1_Init 1 */

  /* USER CODE END TIM1_Init 1 */
  htim1.Instance = TIM1;
  htim1.Init.Prescaler = ((TIM_CLOCK_DIVIDER) - 1);
  htim1.Init.CounterMode = TIM_COUNTERMODE_CENTERALIGNED1;
  htim1.Init.Period = ((PWM_PERIOD_CYCLES) / 2);
  htim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV2;
  htim1.Init.RepetitionCounter = (REP_COUNTER);
  htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim1) != HAL_OK)
  {
    Error_Handler();
  }
  sSlaveConfig.SlaveMode = TIM_SLAVEMODE_TRIGGER;
  sSlaveConfig.InputTrigger = TIM_TS_ITR1;
  if (HAL_TIM_SlaveConfigSynchro(&htim1, &sSlaveConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_OC4REF;
  sMasterConfig.MasterOutputTrigger2 = TIM_TRGO2_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim1, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sBreakInputConfig.Source = TIM_BREAKINPUTSOURCE_BKIN;
  sBreakInputConfig.Enable = TIM_BREAKINPUTSOURCE_ENABLE;
  sBreakInputConfig.Polarity = TIM_BREAKINPUTSOURCE_POLARITY_LOW;
  if (HAL_TIMEx_ConfigBreakInput(&htim1, TIM_BREAKINPUT_BRK, &sBreakInputConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = ((PWM_PERIOD_CYCLES) / 4);
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCNPolarity = TIM_OCNPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  sConfigOC.OCIdleState = TIM_OCIDLESTATE_RESET;
  sConfigOC.OCNIdleState = TIM_OCNIDLESTATE_RESET;
  if (HAL_TIM_PWM_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_2) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_3) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM2;
  sConfigOC.Pulse = (((PWM_PERIOD_CYCLES) / 2) - (HTMIN));
  if (HAL_TIM_PWM_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_4) != HAL_OK)
  {
    Error_Handler();
  }
  sBreakDeadTimeConfig.OffStateRunMode = TIM_OSSR_ENABLE;
  sBreakDeadTimeConfig.OffStateIDLEMode = TIM_OSSI_ENABLE;
  sBreakDeadTimeConfig.LockLevel = TIM_LOCKLEVEL_OFF;
  sBreakDeadTimeConfig.DeadTime = ((DEAD_TIME_COUNTS) / 2);
  sBreakDeadTimeConfig.BreakState = TIM_BREAK_ENABLE;
  sBreakDeadTimeConfig.BreakPolarity = TIM_BREAKPOLARITY_HIGH;
  /* BKF=9: fDTS/8, eight consecutive samples. With TIM1=170 MHz,
   * CKD=2 this is 659..753 ns qualification (sampling phase dependent).
   * Reject sub-600 ns SD disturbances; retain BKE and hardware IPM shutdown.
   * This intentionally adds <1 us to MCU Break, not to internal IPM protection.
   * Do not replace by software debounce or automatic restart after a fault. */
  sBreakDeadTimeConfig.BreakFilter =
      LL_TIM_BREAK_FILTER_FDIV8_N8 >> TIM_BDTR_BKF_Pos;
  sBreakDeadTimeConfig.BreakAFMode = TIM_BREAK_AFMODE_INPUT;
  sBreakDeadTimeConfig.Break2State = TIM_BREAK2_DISABLE;
  sBreakDeadTimeConfig.Break2Polarity = TIM_BREAK2POLARITY_HIGH;
  sBreakDeadTimeConfig.Break2Filter = 3;
  sBreakDeadTimeConfig.Break2AFMode = TIM_BREAK_AFMODE_INPUT;
  sBreakDeadTimeConfig.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;
  if (HAL_TIMEx_ConfigBreakDeadTime(&htim1, &sBreakDeadTimeConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM1_Init 2 */

  /* USER CODE END TIM1_Init 2 */
  HAL_TIM_MspPostInit(&htim1);

}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 1843200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  huart2.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  huart2.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  huart2.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetTxFifoThreshold(&huart2, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetRxFifoThreshold(&huart2, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_DisableFifoMode(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * Enable DMA controller clock
  */
static void MX_DMA_Init(void)
{

  /* DMA controller clock enable */
  __HAL_RCC_DMAMUX1_CLK_ENABLE();
  __HAL_RCC_DMA2_CLK_ENABLE();

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin : Start_Stop_Pin */
  GPIO_InitStruct.Pin = Start_Stop_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(Start_Stop_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
