#define CANDIDATE 1

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
std::array<uint8_t, 32> reply;
uint32_t HAL_GetTick() { return now_ms; }
MCI_State_t MC_GetSTMStateMotor1() { return motor_state; }
int16_t MC_GetMecSpeedReferenceMotor1() { return ramp_target; }
uint16_t MC_GetCurrentFaultsMotor1() { return mc_fault; }
uint16_t MC_GetOccurredFaultsMotor1() { return mc_occurred; }
bool MC_StopMotor1() { ++stops; return true; }
bool MC_StartMotor1() { ++starts; if (start_succeeds) motor_state=RUN; return start_succeeds; }
bool MC_AcknowledgeFaultMotor1() { if (motor_state!=FAULT_OVER || mc_fault) return false; mc_occurred=0; return true; }
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

#define POLE_PAIR_NUM 1
#define MOTOR_MAX_SPEED_RPM 3000
#define U_01HZ 10
#define U_RPM 60
#define SPEED_UNIT U_01HZ
#define RPM_2_SPEED_UNIT(rpm) ((int16_t)(((rpm)*SPEED_UNIT)/U_RPM))
enum {
  UNO_FRAME_LEN = 32U,
  UNO_PROTOCOL_VERSION = 0x02U,
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

#define MIC_NUCLEO_FW_BUILD_ID 2026100708UL

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
/* Single ISR producer, main-loop consumer. Volatile 16-bit indices are atomic
   on Cortex-M4; queue bytes are published before advancing the head. */
enum { UNO_RX_SIZE = 128U, UNO_RX_MASK = UNO_RX_SIZE - 1U };
static volatile uint8_t uno_rx_bytes[UNO_RX_SIZE];
static volatile uint16_t uno_rx_head;
static volatile uint16_t uno_rx_tail;
static volatile uint8_t uno_rx_errors;
static volatile uint8_t uno_rx_overflow;

static bool uno_rx_push(uint8_t byte) {
  const uint16_t next = (uno_rx_head + 1U) & UNO_RX_MASK;
  if (next == uno_rx_tail) return false;
  uno_rx_bytes[uno_rx_head] = byte;
  uno_rx_head = next;
  return true;
}

static bool uno_rx_pop(uint8_t *byte) {
  if (uno_rx_tail == uno_rx_head) return false;
  *byte = uno_rx_bytes[uno_rx_tail];
  uno_rx_tail = (uno_rx_tail + 1U) & UNO_RX_MASK;
  return true;
}

void USART1_IRQHandler(void) {
  const uint32_t errors = huart1.Instance->ISR &
      (UART_FLAG_ORE | UART_FLAG_NE | UART_FLAG_FE | UART_FLAG_PE);
  if (errors != 0U) {
    uno_rx_errors |=
        ((errors & UART_FLAG_PE) != 0U ? 0x01U : 0U) |
        ((errors & UART_FLAG_FE) != 0U ? 0x02U : 0U) |
        ((errors & UART_FLAG_NE) != 0U ? 0x04U : 0U) |
        ((errors & UART_FLAG_ORE) != 0U ? 0x08U : 0U);
    if ((errors & UART_FLAG_ORE) != 0U) __HAL_UART_CLEAR_OREFLAG(&huart1);
    if ((errors & UART_FLAG_NE) != 0U) __HAL_UART_CLEAR_NEFLAG(&huart1);
    if ((errors & UART_FLAG_FE) != 0U) __HAL_UART_CLEAR_FEFLAG(&huart1);
    if ((errors & UART_FLAG_PE) != 0U) __HAL_UART_CLEAR_PEFLAG(&huart1);
  }
  while (__HAL_UART_GET_FLAG(&huart1, UART_FLAG_RXNE) != RESET) {
    const uint8_t byte = (uint8_t)huart1.Instance->RDR;
    if (uno_rx_errors == 0U && uno_rx_overflow == 0U && !uno_rx_push(byte)) uno_rx_overflow = 1U;
  }
}

static uint8_t uno_crc_xor(const uint8_t *frame) {
  uint8_t crc = 0U;
  for (uint8_t index = 0U; index < (UNO_FRAME_LEN - 1U); ++index) {
    crc ^= frame[index];
  }
  return crc;
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
  for (uint8_t index = 6U; index < (UNO_FRAME_LEN - 1U); ++index) {
    if (frame[index] != 0U) {
      return false;
    }
  }
  return true;
}

static bool uno_service_fields_are_zero(const uint8_t *frame) {
  for (uint8_t index = 14U; index < (UNO_FRAME_LEN - 1U); ++index) {
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
  reply[UNO_FRAME_LEN - 1U] = uno_crc_xor(reply);
  const int tx_status = HAL_UART_Transmit(&huart1, reply, UNO_FRAME_LEN, UNO_REPLY_TIMEOUT_MS);
  if (tx_status != HAL_OK) {
    uno_capture_diagnostics(UNO_DIAG_TX, 0U, (uint8_t)tx_status);
    uno_link.last_bad_reason = UNO_DIAG_TX;
    uno_link.last_tx_status = (uint8_t)tx_status;
    uno_saturating_increment(&uno_link.bad_count);
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_TX);
  }
}

static void uno_handle_valid_frame(const uint8_t *frame) {
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
  if (!uno_link.command_enabled || target_speed_unit != uno_link.last_speed_unit) {
    MC_ProgramSpeedRampMotor1(target_speed_unit, uno_speed_ramp_ms(target_speed_unit));
    uno_link.last_speed_unit = target_speed_unit;
  }
  if (MC_GetSTMStateMotor1() == IDLE && !MC_StartMotor1()) {
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_START);
    return;
  }

  uno_link.command_enabled = true;
  uno_link.last_mode = UNO_MODE_SCALAR;
  uno_link.fault_code = UNO_FAULT_OK;
}

static void uno_consume_byte(uint8_t byte) {
  if (uno_link.parser_state == 0U) {
    if (byte == UNO_CMD_HDR0) {
      uno_link.frame[0] = byte;
      uno_link.parser_state = 1U;
    }
    return;
  }
  if (uno_link.parser_state == 1U) {
    if (byte == UNO_CMD_HDR1) {
      uno_link.frame[1] = byte;
      uno_link.parser_index = 2U;
      uno_link.parser_state = 2U;
    } else if (byte == UNO_CMD_HDR0) {
      uno_link.frame[0] = byte;
    } else {
      uno_link.parser_state = 0U;
    }
    return;
  }

  uno_link.frame[uno_link.parser_index++] = byte;
  if (uno_link.parser_index < UNO_FRAME_LEN) {
    return;
  }
  uno_link.parser_state = 0U;
  uno_link.parser_index = 0U;
  if (uno_link.frame[UNO_FRAME_LEN - 1U] != uno_crc_xor(uno_link.frame)) {
    uno_link.last_bad_reason = UNO_DIAG_CRC;
    uno_saturating_increment(&uno_link.bad_count);
    uno_latch_fault_reason(UNO_FAULT_BAD_CRC, UNO_DIAG_CRC);
    return;
  }
  uno_handle_valid_frame(uno_link.frame);
  uno_send_reply();
}

static void uno_link_init(void) {
  memset(&uno_link, 0, sizeof(uno_link));
  uno_link.fault_code = UNO_FAULT_OK;
  uno_link.last_mode = UNO_MODE_OFF;
  uno_rx_head = uno_rx_tail = 0U;
  uno_rx_errors = uno_rx_overflow = 0U;
}

static void uno_link_poll(void) {
  uno_update_softstart_state(HAL_GetTick());
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
    uno_saturating_increment(&uno_link.bad_count);
    uno_latch_fault_reason(UNO_FAULT_INTERNAL, reason);
    return;
  }
  uint8_t byte;
  while (uno_rx_pop(&byte)) uno_consume_byte(byte);
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


void check(bool ok, const char *name) {
 ++tests;
 if (!ok) { std::fprintf(stderr, "FAIL %s\n", name); std::exit(1); }
}
using Frame = std::array<uint8_t, UNO_FRAME_LEN>;
Frame frame(uint8_t flags, uint8_t mode, uint8_t seq) {
 Frame f{}; f[0]=UNO_CMD_HDR0; f[1]=UNO_CMD_HDR1; f[2]=UNO_PROTOCOL_VERSION;
 f[3]=flags; f[4]=mode; f[5]=seq; f.back()=uno_crc_xor(f.data()); return f;
}
void feed(const Frame &f) { for (auto b : f) uno_consume_byte(b); }
void reset() {
 now_ms=3500; bus_v=310; mc_fault=mc_occurred=0; motor_state=IDLE;
 starts=stops=ramps=0; start_succeeds=tx_succeeds=true; test_timer={};
 uart_registers={}; reply={}; uno_link_init();
}
int main() {
 reset(); motor_state=FAULT_OVER; mc_occurred=4;
 feed(frame(UNO_FLAG_CLEAR_FAULT, UNO_MODE_OFF, 32));
 check(motor_state==FAULT_OVER && mc_occurred==0, "ACK is asynchronous, masks clear");
 check(reply[3]&UNO_STATUS_FAULT, "state guard still blocks during ACK transition");
#if CANDIDATE
 check(uno_link.first_reason==UNO_DIAG_NONE, "no empty post-ACK fault snapshot");
#else
 check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_current_faults==0
       && uno_link.first_occurred_faults==0, "reproduce empty stale snapshot");
#endif
 motor_state=IDLE; uno_send_reply();
 check(!(reply[3]&UNO_STATUS_FAULT), "scheduler completes ACK, fault inactive");
 motor_state=RUN; uno_link.command_enabled=true; uno_rx_errors=4;
 uno_link_poll(); uno_send_reply();
 check(uno_link.fault_latched && !uno_link.command_enabled, "NE still stops and latches");
 check(uno_link.last_bad_reason==UNO_DIAG_UART && uno_link.last_uart_errors==4,
       "last cause records NE in both versions");
#if CANDIDATE
 check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_uart_errors==4,
       "candidate preserves actual first cause after ACK");
#else
 check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_uart_errors==0,
       "original masks actual first cause after ACK");
#endif
 for (uint16_t mask : {1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192,16384,32768}) {
  reset(); motor_state=FAULT_OVER; mc_fault=mask; uno_send_reply();
  check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_current_faults==mask,
        "real current faults remain captured");
  reset(); motor_state=FAULT_OVER; mc_occurred=mask; uno_send_reply();
  check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_occurred_faults==mask,
        "real occurred faults remain captured");
 }
 reset(); motor_state=FAULT_OVER; feed(frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 1));
 check(uno_link.fault_latched && starts==0, "ENABLE cannot bypass FAULT_OVER");
 reset(); motor_state=FAULT_NOW; uno_send_reply();
 check(uno_link.first_reason==UNO_DIAG_MCSDK, "FAULT_NOW diagnostics retained");
 std::printf("{\"pass\":true,\"checks\":%u}\n", tests); return 0;
}
