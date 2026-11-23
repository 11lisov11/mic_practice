#define UV3_INTEGRATED_TEST 1
#include "uart_v3_transport.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#define MC_NO_FAULTS 0U
#define MC_OVER_TEMP 0x08U
#define HAL_OK 0
#define RESET 0
#define UART_FLAG_ORE 1U
#define UART_FLAG_NE 2U
#define UART_FLAG_FE 4U
#define UART_FLAG_PE 8U
#define UART_FLAG_RXNE 16U
#define USART1_IRQn 37
void HAL_NVIC_DisableIRQ(int) {}
void HAL_NVIC_EnableIRQ(int) {}
enum MCI_State_t { IDLE, RUN, FAULT_NOW, FAULT_OVER };
struct { struct { int unused; } _Super; } BusVoltageSensor_M1;
struct { int unused; } TempSensor_M1;
struct UART_Registers { uint32_t ISR, RDR; } uart_registers;
struct { UART_Registers *Instance; } huart1 = { &uart_registers };
uint32_t now_ms;
uint16_t bus_v, mc_fault, mc_occurred;
MCI_State_t motor_state;
bool start_succeeds = true, tx_succeeds = true;
unsigned starts, stops, ramps, tests;
struct { bool moe, bie, level_low; unsigned flags; } test_timer;
#define TIM1 (&test_timer)
#define GPIOA 0
#define GPIO_PIN_6 64
#define GPIO_PIN_SET 1
bool LL_TIM_IsEnabledAllOutputs(decltype(TIM1) t) { return t->moe; }
int HAL_GPIO_ReadPin(int, int) { return test_timer.level_low ? 0 : 1; }
void LL_TIM_ClearFlag_BRK(decltype(TIM1) t) { if (!t->level_low) t->flags &= ~1U; }
void LL_TIM_ClearFlag_BRK2(decltype(TIM1) t) { if (!t->level_low) t->flags &= ~2U; }
bool LL_TIM_IsActiveFlag_BRK(decltype(TIM1) t) { return t->flags & 1U; }
bool LL_TIM_IsActiveFlag_BRK2(decltype(TIM1) t) { return t->flags & 2U; }
void LL_TIM_EnableIT_BRK(decltype(TIM1) t) { t->bie = true; }
int16_t ramp_target;
uint16_t ramp_duration;
std::array<uint8_t, UV3_FRAME> reply;
uint32_t HAL_GetTick() { return now_ms; }
MCI_State_t MC_GetSTMStateMotor1() { return motor_state; }
int16_t MC_GetMecSpeedReferenceMotor1() { return ramp_target; }
uint16_t MC_GetCurrentFaultsMotor1() { return mc_fault; }
uint16_t MC_GetOccurredFaultsMotor1() { return mc_occurred; }
bool MC_StopMotor1() { ++stops; if (!mc_fault) motor_state=IDLE; return true; }
bool MC_StartMotor1() { ++starts; if (start_succeeds) motor_state=RUN; return start_succeeds; }
bool MC_AcknowledgeFaultMotor1() { if (!mc_fault) motor_state=IDLE; return !mc_fault; }
void MC_ProgramSpeedRampMotor1(int16_t target, uint16_t duration) {
 ++ramps; ramp_target=target; ramp_duration=duration;
}
template<class T> uint16_t VBS_GetAvBusVoltage_V(T *) { return bus_v; }
template<class T> int16_t NTC_GetAvTemp_C(T *) { return 25; }
template<class T> int HAL_UART_Transmit(T *, uint8_t *data, unsigned size, unsigned) {
 if (size!=reply.size()) std::abort();
 std::memcpy(reply.data(), data, size); return tx_succeeds ? HAL_OK : 1;
}
#define __HAL_UART_GET_FLAG(h, flag) (false)
#define __HAL_UART_CLEAR_OREFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_ORE)
#define __HAL_UART_CLEAR_NEFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_NE)
#define __HAL_UART_CLEAR_FEFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_FE)
#define __HAL_UART_CLEAR_PEFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_PE)
uint8_t mock_read_rdr() { uart_registers.ISR &= ~UART_FLAG_RXNE; return (uint8_t)uart_registers.RDR; }

#define POLE_PAIR_NUM 1
#define MOTOR_MAX_SPEED_RPM 3000
#define U_01HZ 10
#define U_RPM 60
#define SPEED_UNIT U_01HZ
#define RPM_2_SPEED_UNIT(rpm) ((int16_t)(((rpm)*SPEED_UNIT)/U_RPM))
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

#define MIC_NUCLEO_FW_BUILD_ID 2026101003UL

#define MIC_EXTERNAL_SOFTSTART_CONFIGURED 1
#define MIC_SOFTSTART_GPIO_CONTROLLED 0
#define MIC_EXTERNAL_SOFTSTART_HIL_VALIDATED 0
#define MIC_EXTERNAL_SOFTSTART_SETTLE_MS 3500U

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
  bool link_seen;
  bool command_enabled;
  bool fault_latched;
  bool softstart_ready;
  bool softstart_tracking;
  uint32_t softstart_stable_since_ms;
} uno_link_state_t;

static uno_link_state_t uno_link;
static uv3_rx uno_transport;
enum { UNO_RX_SIZE = 128U, UNO_RX_MASK = UNO_RX_SIZE - 1U };
static volatile uint8_t uno_rx_bytes[UNO_RX_SIZE];
static volatile uint8_t uno_rx_marks[UNO_RX_SIZE];
static volatile uint16_t uno_rx_head;
static volatile uint16_t uno_rx_tail;
static volatile uint8_t uno_rx_errors;
static volatile uint8_t uno_rx_overflow;

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
    const uint8_t byte = mock_read_rdr();
    if (uno_rx_errors == 0U && uno_rx_overflow == 0U && !uno_rx_push(byte, marks)) uno_rx_overflow = 1U;
  }
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

static void uno_send_reply(void) {
  uint8_t reply[UNO_FRAME_LEN] = {0};
  const uint32_t now_ms = HAL_GetTick();
  const bool link_ok = uno_link.link_seen &&
                       (uint32_t)(now_ms - uno_link.last_valid_ms) <= UNO_LINK_TIMEOUT_MS;
  const MCI_State_t motor_state = MC_GetSTMStateMotor1();
  const bool mcsdk_fault = uno_mcsdk_fault_present();
  const bool fault = uno_link.fault_latched || mcsdk_fault;
  const uint16_t vbus_v = VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  const uint16_t vbus_deci_v = (vbus_v <= (UINT16_MAX / 10U))
                                  ? (uint16_t)(vbus_v * 10U)
                                  : UINT16_MAX;
  const int16_t temp_deci_c = (int16_t)(NTC_GetAvTemp_C(&TempSensor_M1) * 10);
  const uint16_t mcsdk_faults = MC_GetCurrentFaultsMotor1();
  uint8_t fault_code = uno_link.fault_code;
  uint8_t status = 0U;

  /* ACK clears the masks before the scheduler leaves FAULT_OVER. */
  if (mcsdk_fault && (motor_state != FAULT_OVER ||
      mcsdk_faults != MC_NO_FAULTS || MC_GetOccurredFaultsMotor1() != MC_NO_FAULTS)) {
    uno_capture_diagnostics(UNO_DIAG_MCSDK, 0U, 0U);
  }

  if (link_ok) status |= UNO_STATUS_LINK_OK;
  if (uno_link.command_enabled && !fault) status |= UNO_STATUS_ENABLED;
  if (uno_link.fault_latched && uno_link.fault_code == UNO_FAULT_ESTOP) status |= UNO_STATUS_ESTOP;
  if (fault) status |= UNO_STATUS_FAULT;
  if (uno_link.fault_latched && uno_link.fault_code == UNO_FAULT_TIMEOUT) status |= UNO_STATUS_TIMEOUT;
  if (motor_state == RUN) status |= UNO_STATUS_PWM_ACTIVE | UNO_STATUS_SHUTDOWN_RELEASED;
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
  uv3_reply_diagnostics(reply, &uno_transport);
  uv3_seal(reply);
  const int tx_status = HAL_UART_Transmit(&huart1, reply, UNO_FRAME_LEN, UNO_REPLY_TIMEOUT_MS);
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

  if (uno_clear_frame_is_safe(frame)) {
    uno_stop_motor();
    if (!uno_rearm_break_irq()) {
      uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_MCSDK);
      return;
    }
    (void)MC_AcknowledgeFaultMotor1();
    uno_link.fault_latched = false;
    uno_link.fault_code = UNO_FAULT_OK;
    uno_link.bad_count = 0U;
    uno_clear_diagnostics();
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

  if (!uno_service_fields_are_zero(frame)) {
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_SERVICE);
    return;
  }

  if (flags == 0U && mode == UNO_MODE_OFF) {
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
  const bool update_ramp = !uno_link.command_enabled || target_speed_unit != uno_link.last_speed_unit;
  const uint16_t ramp_ms = update_ramp ? uno_speed_ramp_ms(target_speed_unit) : 0U;
  const MCI_State_t start_state = MC_GetSTMStateMotor1();
  if (uno_abort_pending_rx_fault()) return;
  bool start_failed = false;
  /* The final RX check and command publication share one USART-only section.
     MCSDK APIs only enqueue commands; ADC/TIM protection IRQs remain enabled. */
  HAL_NVIC_DisableIRQ(USART1_IRQn);
  const bool rx_fault_pending = uno_rx_errors != 0U || uno_rx_overflow != 0U;
  if (!rx_fault_pending) {
    if (update_ramp) {
      MC_ProgramSpeedRampMotor1(target_speed_unit, ramp_ms);
      uno_link.last_speed_unit = target_speed_unit;
    }
    if (start_state == IDLE && !MC_StartMotor1()) start_failed = true;
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
  if (result == UV3_WAIT) return;
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

static void uno_link_poll(void) {
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


void check(bool condition, const char *name) {
 ++tests;
 if (!condition) { std::fprintf(stderr, "FAIL %s (check %u)\n", name, tests); std::exit(1); }
}
using Frame = std::array<uint8_t, UNO_FRAME_LEN>;
void checksum(Frame &f) { uv3_seal(f.data()); }
Frame frame(uint8_t flags, uint8_t mode, uint32_t freq=0, uint8_t seq=1) {
 Frame f{}; f[0]=UNO_CMD_HDR0; f[1]=UNO_CMD_HDR1; f[2]=UNO_PROTOCOL_VERSION;
 f[3]=flags; f[4]=mode; f[5]=seq;
 for (unsigned i=0; i<4; ++i) f[6+i]=(uint8_t)(freq>>(8*i));
 checksum(f); return f;
}
void feed(const Frame &f) { for (auto b : f) uno_consume_sample(b, 0); }
void reset(bool ready=false) {
 now_ms=0; bus_v=ready ? 310 : 0; mc_fault=mc_occurred=0; motor_state=IDLE;
 starts=stops=ramps=0; ramp_target=0; ramp_duration=0;
 start_succeeds=tx_succeeds=true; uart_registers={}; test_timer={}; reply={}; uno_link_init();
 if (ready) { uno_update_softstart_state(0); now_ms=3500; uno_update_softstart_state(now_ms); }
}
// Included after the extracted production MCSDK control functions and mocks.
#include "uart_v3_transport.h"

using V3Frame = std::array<uint8_t, UV3_FRAME>;
#if defined(UV3_INTEGRATED_TEST)
uv3_rx &candidate = uno_transport;
#else
uv3_rx candidate;
#endif
unsigned cases = 0;
unsigned isolated_accepted = 0, strict_rejected = 0;

V3Frame v3_frame(uint8_t flags = 1, uint8_t mode = 3, uint32_t freq = 10000,
                 uint8_t seq = 81) {
  Frame legacy = frame(flags, mode, freq, seq);
  V3Frame result{};
  std::memcpy(result.data(), legacy.data(), UV3_BASE_PAYLOAD);
  result[2] = UV3_VERSION;
  uv3_seal(result.data());
  return result;
}

void dispatch_result(uv3_result result) {
#if defined(UV3_INTEGRATED_TEST)
  uno_transport_result(result);
#else
  if (result == UV3_WAIT) return;
  if (result != UV3_READY) {
    const uint8_t reason = result == UV3_BAD_CRC ? UNO_DIAG_CRC :
        result == UV3_BAD_VERSION ? UNO_DIAG_VERSION : result == UV3_BAD_SEQUENCE ? UNO_DIAG_REPLAY :
        result == UV3_LINK_TIMEOUT || result == UV3_FRAME_TIMEOUT ? UNO_DIAG_TIMEOUT : UNO_DIAG_UART;
    uno_capture_diagnostics(reason, candidate.last_uart_flags, 0);
    uno_link.last_bad_reason = reason;
    uno_link.last_uart_errors = candidate.last_uart_flags;
    uno_saturating_increment(&uno_link.bad_count);
    const uint8_t code = result == UV3_BAD_CRC ? UNO_FAULT_BAD_CRC :
        result == UV3_LINK_TIMEOUT || result == UV3_FRAME_TIMEOUT ? UNO_FAULT_TIMEOUT : UNO_FAULT_INTERNAL;
    uno_latch_fault_reason(code, reason);
    return;
  }
  // Offline adapter to the unchanged production semantic handler, NOT an
  // on-wire v2 fallback. Recreate its expected internal checksum/layout.
  Frame legacy{};
  std::memcpy(legacy.data(), candidate.frame, UV3_BASE_PAYLOAD);
  legacy[2] = UNO_PROTOCOL_VERSION;
  checksum(legacy);
  uno_handle_valid_frame(legacy.data());
  uno_send_reply();
  bool clean_clear = legacy[3] == UNO_FLAG_CLEAR_FAULT && legacy[4] == UNO_MODE_OFF;
  for (unsigned i = 6; i < UV3_BASE_PAYLOAD; ++i) clean_clear = clean_clear && legacy[i] == 0;
  uv3_commit(&candidate, now_ms,
             uno_link.command_enabled && motor_state == RUN,
             uno_link.fault_latched, clean_clear);
#endif
}

uv3_result consume(uint8_t byte, uint8_t flags = 0) {
#if defined(UV3_INTEGRATED_TEST)
  uno_consume_sample(byte, flags);
  return candidate.fault;
#else
  uv3_result result = uv3_byte(&candidate, byte, flags, now_ms);
  dispatch_result(result);
  return result;
#endif
}

void send(const V3Frame &f, int noisy = -1, int noisy2 = -1, uint8_t flags = UV3_NE) {
  for (unsigned i = 0; i < f.size(); ++i)
    consume(f[i], ((int)i == noisy || (int)i == noisy2) ? flags : 0);
}

void tick(uint32_t delta) {
  now_ms += delta;
  dispatch_result(uv3_tick(&candidate, now_ms));
  uno_link_poll();
}

void begin(bool bounded = true, uint32_t start_ms = 4000, uint8_t seq = 78) {
  reset(true);
  now_ms = start_ms;
  uv3_init(&candidate, bounded);
  for (unsigned i = 0; i < 3; ++i) {
    now_ms = start_ms + i * 20U;
    send(v3_frame(1, 3, 10000, (uint8_t)(seq + i)));
  }
  check(starts == 1 && motor_state == RUN && !uno_link.fault_latched,
        "three clean commands establish real mocked MCSDK RUN");
  check(candidate.clean_run_frames == 3 && candidate.run_anchor, "clean anchor established");
}

void assert_stopped(const char *name) {
  check(uno_link.fault_latched && !uno_link.command_enabled && motor_state != RUN, name);
}

void crc_vectors_and_corruption() {
  uint8_t data[32] = {};
  check(uv3_crc32c(data, 32) == 0x8a9136aaU, "RFC3720 zero vector");
  std::memset(data, 255, 32);
  check(uv3_crc32c(data, 32) == 0x62a8ab43U, "RFC3720 ones vector");
  for (unsigned i = 0; i < 32; ++i) data[i] = (uint8_t)i;
  check(uv3_crc32c(data, 32) == 0x46dd794eU, "RFC3720 increasing vector");
  for (unsigned i = 0; i < 32; ++i) data[i] = (uint8_t)(31 - i);
  check(uv3_crc32c(data, 32) == 0x113fdb5cU, "RFC3720 decreasing vector");
  const uint8_t digits[] = "123456789";
  check(uv3_crc32c(digits, 9) == 0xe3069283U, "CRC32C check string");
  check(uv3_crc32c(data, 0) == 0, "empty CRC");
  V3Frame original = v3_frame();
  for (unsigned a = 0; a < UV3_FRAME * 8; ++a) {
    V3Frame bad = original;
    bad[a / 8] ^= (uint8_t)(1U << (a % 8));
    check(!uv3_crc_ok(bad.data()), "all single bit changes detected by CRC");
    ++cases;
    for (unsigned b = a + 1; b < UV3_FRAME * 8; ++b) {
      bad = original;
      bad[a / 8] ^= (uint8_t)(1U << (a % 8));
      bad[b / 8] ^= (uint8_t)(1U << (b % 8));
      check(!uv3_crc_ok(bad.data()), "all double bit changes detected by CRC");
      ++cases;
    }
  }
  // Exhaust all burst placements/lengths <=32 with three deterministic shapes.
  // This finite sweep is NOT enumeration of every possible burst interior.
  for (unsigned length = 1; length <= 32; ++length) {
    for (unsigned first = 0; first + length <= UV3_FRAME * 8; ++first) {
      for (unsigned shape = 0; shape < 3; ++shape) {
        V3Frame bad = original;
        for (unsigned i = 0; i < length; ++i)
          if (i == 0 || i == length - 1 || shape == 0 || (shape == 1 && i % 2 == 0))
            bad[(first + i) / 8] ^= (uint8_t)(1U << ((first + i) % 8));
        check(!uv3_crc_ok(bad.data()), "short burst sweep detected");
        ++cases;
      }
    }
  }
  for (unsigned seq = 0; seq < 256; ++seq) {
    V3Frame bad = v3_frame(1, 3, 10000, (uint8_t)seq);
    bad[6] ^= 0x40; bad[7] ^= 0x40;
    check(!uv3_crc_ok(bad.data()), "paired XOR collision rejected for every sequence");
    ++cases;
  }
  for (unsigned pos = 0; pos < UV3_FRAME; ++pos) {
    for (unsigned bit = 0; bit < 8; ++bit) {
      for (int mark : {-1, 10}) {
        begin(); V3Frame bad = original;
        bad[pos] ^= (uint8_t)(1U << bit);
        unsigned before = ramps;
        send(bad, mark);
        check(ramps == before && starts == 1, "corruption cannot change ramp or start");
        if (pos >= 2) check(candidate.fault == UV3_BAD_CRC, "parser CRC rejects even unmarked corruption");
        tick(301);
        assert_stopped("corrupted frame stops by parser deadline or watchdog");
        ++cases;
      }
    }
  }
}

void noise_matrix() {
  for (unsigned seq = 0; seq < 256; ++seq) {
    for (unsigned pos = 0; pos < UV3_FRAME; ++pos) {
      begin(true, 4000, (uint8_t)(seq - 3));
      unsigned before = ramps;
      send(v3_frame(1, 3, 10000, (uint8_t)seq), (int)pos);
      check(!uno_link.fault_latched && motor_state == RUN && ramps == before && starts == 1,
            "isolated intact NE cannot cause restart or ramp change");
      check(candidate.accepted_noise_frames == 1 && candidate.observed_noise_bytes == 1,
            "accepted NE remains observable");
      check(candidate.marks[pos] == UV3_NE && candidate.clean_run_frames == 0,
            "byte mark retained and clean recovery required");
      ++isolated_accepted; ++cases;
      begin(false, 4000, (uint8_t)(seq - 3));
      send(v3_frame(1, 3, 10000, (uint8_t)seq), (int)pos);
      assert_stopped("strict CRC32C baseline rejects same intact NE frame");
      ++strict_rejected; ++cases;
    }
  }
  for (unsigned pos = 0; pos < UV3_FRAME; ++pos) {
    for (unsigned mask = 1; mask < 256; ++mask) {
      if (mask == UV3_NE) continue;
      begin(); send(v3_frame(), (int)pos, -1, (uint8_t)mask);
      assert_stopped("all hard UART/unknown flag combinations rejected at every byte");
      check(candidate.fault == UV3_HARD_UART, "hard flag diagnosis retained");
      ++cases;
    }
    for (unsigned other = pos + 1; other < UV3_FRAME; ++other) {
      begin(); send(v3_frame(), (int)pos, (int)other);
      assert_stopped("two noisy bytes exceed per-frame budget");
      ++cases;
    }
    // Every command field differs under a freshly recomputed valid CRC.
    for (unsigned field = 3; field < UV3_PAYLOAD; ++field) {
      if (field == 5) continue;
      begin(); V3Frame changed = v3_frame(); changed[field] ^= 1;
      uv3_seal(changed.data()); send(changed, (int)pos);
      assert_stopped("NE cannot authorize any changed command field");
      ++cases;
    }
    reset(true); uv3_init(&candidate, true); send(v3_frame(), (int)pos);
    check(starts == 0 && uno_link.fault_latched, "NE first start is forbidden");
    ++cases;
    begin(); send(v3_frame(8, 0, 0), (int)pos);
    assert_stopped("noisy CLEAR cannot clear fault or continue run");
    send(v3_frame(1, 3, 10000, 82));
    assert_stopped("clean ENABLE after fault cannot restart");
    send(v3_frame(8, 0, 0, 83));
    check(!uno_link.fault_latched && !candidate.fault_latched && motor_state == IDLE,
          "explicit clean CLEAR may release latch but not restart");
    ++cases;
  }
  begin(); send(v3_frame(), 8);
  send(v3_frame(1, 3, 10000, 82), 8);
  assert_stopped("adjacent noise frames forbidden until three clean commands"); ++cases;
  for (unsigned count = 0; count < 3; ++count) {
    begin(); send(v3_frame(), 8);
    for (unsigned i = 0; i < count; ++i) send(v3_frame(1, 3, 10000, (uint8_t)(82 + i)));
    send(v3_frame(1, 3, 10000, (uint8_t)(82 + count)), 8);
    assert_stopped("fewer than three clean recovery commands cannot authorize NE"); ++cases;
  }
  for (uint32_t origin : {4000U, UINT32_MAX - 70U}) {
    begin(true, origin);
    send(v3_frame(), 8);
    for (unsigned i = 0; i < 3; ++i) { now_ms += 20; send(v3_frame(1,3,10000,(uint8_t)(82+i))); }
    send(v3_frame(1,3,10000,85), 8);
    check(motor_state == RUN && candidate.accepted_noise_frames == 2, "second separated NE accepted");
    for (unsigned i = 0; i < 3; ++i) { now_ms += 20; send(v3_frame(1,3,10000,(uint8_t)(86+i))); }
    send(v3_frame(1,3,10000,89), 8);
    assert_stopped("third NE inside sliding second rejected including tick wrap"); ++cases;
  }
  begin(); send(v3_frame(), 8);
  for (unsigned i=0; i<51; ++i) { now_ms+=20; send(v3_frame(1,3,10000,(uint8_t)(82+i))); }
  send(v3_frame(1,3,10000,133), 8);
  check(motor_state == RUN && !candidate.fault_latched, "budget ages out after real elapsed second"); ++cases;
}

void framing_and_protections() {
  for (unsigned previous=0;previous<256;++previous) {
    for (unsigned incoming=0;incoming<256;++incoming) {
      begin(true,4000,(uint8_t)(previous-2));
      send(v3_frame(1,3,10000,(uint8_t)incoming));
      if((uint8_t)incoming==(uint8_t)(previous+1))
        check(motor_state==RUN && !uno_link.fault_latched,"sequential clean command including wrap accepted");
      else {
        assert_stopped("CRC-valid out-of-order RUN command rejected");
        check(candidate.fault==UV3_BAD_SEQUENCE && uno_link.first_reason==UNO_DIAG_REPLAY,
              "sequence error retains explicit replay diagnosis");
      }
      ++cases;
    }
  }
  for (unsigned prefix = 1; prefix < UV3_FRAME; ++prefix) {
    begin(); V3Frame f = v3_frame();
    for (unsigned i=0; i<prefix; ++i) consume(f[i], i == 0 ? UV3_NE : 0);
    tick(15);
    check(!uno_link.fault_latched, "partial frame allowed exactly 15 ms");
    tick(1); assert_stopped("partial frame stopped at 16 ms without refreshing watchdog"); ++cases;
  }
  for (unsigned pos = 0; pos < UV3_FRAME; ++pos) {
    begin(); auto f=v3_frame();
    for (unsigned i=0; i<f.size(); ++i) if(i!=pos) consume(f[i]);
    tick(301); assert_stopped("deleted byte cannot keep run alive"); ++cases;
    for (unsigned value=0; value<256; ++value) {
      begin();
      for (unsigned i=0; i<f.size(); ++i) {
        if (i==pos) consume((uint8_t)value);
        consume(f[i]);
      }
      tick(301); assert_stopped("inserted byte cannot keep run alive"); ++cases;
    }
  }
  begin(); send(v3_frame(1,3,10000,80), 9);
  assert_stopped("noisy duplicate sequence rejected"); ++cases;
  begin(); send(v3_frame(1,3,10000,79), 9);
  assert_stopped("noisy backwards sequence rejected"); ++cases;
  begin(); send(v3_frame(1,3,10000,82), 9);
  assert_stopped("noisy skipped sequence rejected"); ++cases;
  begin(); tick(300); check(motor_state==RUN,"watchdog boundary 300 ms");
  tick(1); assert_stopped("watchdog boundary 301 ms"); ++cases;
  begin(); consume(0x00,UV3_NE); assert_stopped("orphan NE without header rejected"); ++cases;
  begin(); auto old=v3_frame(); old[2]=2; uv3_seal(old.data()); send(old);
  assert_stopped("version 2 forbidden even with valid v3 CRC"); ++cases;
  begin(); send(v3_frame(0,0,0));
  check(motor_state==IDLE && !uno_link.command_enabled,"clean STOP unaffected"); ++cases;
  begin(); send(v3_frame(2,0,0)); assert_stopped("clean ESTOP unaffected"); ++cases;
  begin(); bus_v=386; send(v3_frame()); assert_stopped("real production overvoltage guard unchanged"); ++cases;
  begin(); mc_fault=0x400; motor_state=FAULT_NOW; send(v3_frame());
  assert_stopped("real production MCSDK fault stops"); ++cases;
  begin(); tx_succeeds=false; send(v3_frame()); assert_stopped("reply failure still stops"); ++cases;
  reset(true); uv3_init(&candidate,true); test_timer.level_low=true; test_timer.flags=1;
  send(v3_frame(8,0,0));
  check(uno_link.fault_latched && !test_timer.bie && starts==0,"physical sustained break cannot be ACKed"); ++cases;
  reset(); uv3_init(&candidate,true); send(v3_frame());
  check(starts==0 && !uno_link.command_enabled,"zero bus still cannot start"); ++cases;
  begin(); send(v3_frame(),8); send(v3_frame(1,3,10000,82),8);
  assert_stopped("prepare a latched transport error before discharged-bus CLEAR");
  bus_v=0; mc_fault=4; mc_occurred=4; motor_state=FAULT_NOW;
  send(v3_frame(8,0,0,83));
  check(!candidate.fault_latched && !uno_link.fault_latched && starts==1
        && mc_fault==4 && !uno_link.command_enabled,
        "clean CLEAR resets transport without hiding persistent undervoltage or starting");
  send(v3_frame(1,3,10000,84));
  assert_stopped("MCSDK undervoltage still rejects ENABLE after transport CLEAR"); ++cases;
}

#if defined(UV3_INTEGRATED_TEST)
void irq_sample(uint8_t byte, uint8_t marks = 0) {
  uart_registers.RDR = byte;
  uart_registers.ISR = UART_FLAG_RXNE | ((marks & UV3_PE) ? UART_FLAG_PE : 0U)
      | ((marks & UV3_FE) ? UART_FLAG_FE : 0U) | ((marks & UV3_NE) ? UART_FLAG_NE : 0U)
      | ((marks & UV3_ORE) ? UART_FLAG_ORE : 0U);
  USART1_IRQHandler();
  check(uart_registers.ISR == 0, "IRQ read and clear mocked sample flags");
}
void irq_and_fifo() {
  for (unsigned pos=0; pos<UV3_FRAME; ++pos) {
    begin(); auto f=v3_frame();
    for (unsigned i=0; i<f.size(); ++i) irq_sample(f[i], i==pos ? UV3_NE : 0);
    check(uno_rx_errors==0, "NE byte retained without global hard fault");
    uno_link_poll();
    check(candidate.marks[pos]==UV3_NE && candidate.accepted_noise_frames==1
          && motor_state==RUN && starts==1, "IRQ publishes NE beside exact queued byte");
    ++cases;
    for (unsigned marks=1; marks<16; ++marks) {
      if(marks==UV3_NE) continue;
      begin();
      for (unsigned i=0; i<f.size(); ++i) irq_sample(f[i], i==pos ? (uint8_t)marks : 0);
      uno_link_poll(); assert_stopped("hard IRQ invalidates all queued commands");
      check(uno_link.first_uart_errors==marks, "combined UART flags retained in first fault"); ++cases;
    }
  }
  begin(); uart_registers.ISR=UART_FLAG_NE; USART1_IRQHandler(); uno_link_poll();
  assert_stopped("IRQ NE without RDR is never tolerated"); ++cases;
  begin();
  for(unsigned i=0; i<127; ++i) check(uno_rx_push((uint8_t)i, (uint8_t)(i%8)), "ring capacity");
  check(!uno_rx_push(255,4), "ring overflow never overwrites old data");
  for(unsigned i=0; i<127; ++i) {
    uint8_t byte,marks; check(uno_rx_pop(&byte,&marks) && byte==i && marks==i%8,"byte/mark order exact");
  }
  for(unsigned round=0; round<300; ++round) {
    for(unsigned i=0; i<100; ++i) check(uno_rx_push((uint8_t)i,(uint8_t)(i%8)),"wrap push");
    for(unsigned i=0; i<100; ++i) {
      uint8_t byte,marks; check(uno_rx_pop(&byte,&marks) && byte==i && marks==i%8,"wrap byte/mark preserved");
    }
  }
  uno_rx_overflow=1; uno_link_poll(); assert_stopped("overflow stops real handler"); ++cases;
  begin(); send(v3_frame(),8); uno_send_reply();
  check(uv3_crc_ok(reply.data()) && reply[31]==1 && reply[32]==0 && reply[33]==1
        && reply[34]==0 && reply[37]==UV3_NE, "CRC protected accepted-noise telemetry"); ++cases;
  candidate.accepted_noise_frames=UINT32_MAX; candidate.observed_noise_bytes=UINT32_MAX;
  uno_send_reply();
  check(reply[31]==255 && reply[32]==255 && reply[33]==255 && reply[34]==255,
        "diagnostic counters saturate instead of wrapping"); ++cases;
}
#endif

int main() {
  crc_vectors_and_corruption(); noise_matrix(); framing_and_protections();
#if defined(UV3_INTEGRATED_TEST)
  irq_and_fifo();
#endif
  std::printf("{\"pass\":true,\"cases\":%u,\"assertions\":%u,"
              "\"intact_isolated_NE_accepted\":%u,\"strict_baseline_NE_rejected\":%u,"
              "\"hardware_commands\":0}\n", cases,tests,isolated_accepted,strict_rejected);
}
