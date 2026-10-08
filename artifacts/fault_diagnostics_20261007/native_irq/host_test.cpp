
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
int16_t ramp_target;
uint16_t ramp_duration;
std::array<uint8_t, 32> reply;
uint32_t HAL_GetTick() { return now_ms; }
MCI_State_t MC_GetSTMStateMotor1() { return motor_state; }
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

#define MIC_NUCLEO_FW_BUILD_ID 2026100703UL

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

  if (mcsdk_fault) uno_capture_diagnostics(UNO_DIAG_MCSDK, 0U, 0U);

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
      frequency_millihz == 0U || frequency_millihz > max_frequency_millihz ||
      uno_mcsdk_fault_present()) {
    const uint8_t reason = (flags != UNO_FLAG_ENABLE || mode != UNO_MODE_SCALAR)
        ? UNO_DIAG_COMMAND
        : ((frequency_millihz == 0U || frequency_millihz > max_frequency_millihz)
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
    return;
  }

  const uint32_t target_rpm =
      (frequency_millihz * 60U) / ((uint32_t)POLE_PAIR_NUM * 1000U);
  const int16_t target_speed_unit = RPM_2_SPEED_UNIT((int32_t)target_rpm);
  if (!uno_link.command_enabled || target_speed_unit != uno_link.last_speed_unit) {
    MC_ProgramSpeedRampMotor1(target_speed_unit, UNO_SPEED_RAMP_MS);
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
void checksum(Frame &f) { f.back()=uno_crc_xor(f.data()); }
Frame frame(uint8_t flags, uint8_t mode, uint32_t freq=0, uint8_t seq=1) {
 Frame f{}; f[0]=UNO_CMD_HDR0; f[1]=UNO_CMD_HDR1; f[2]=UNO_PROTOCOL_VERSION;
 f[3]=flags; f[4]=mode; f[5]=seq;
 for (unsigned i=0; i<4; ++i) f[6+i]=(uint8_t)(freq>>(8*i));
 checksum(f); return f;
}
void feed(const Frame &f) { for (auto b : f) uno_consume_byte(b); }
void reset(bool ready=false) {
 now_ms=0; bus_v=ready ? 310 : 0; mc_fault=mc_occurred=0; motor_state=IDLE;
 starts=stops=ramps=0; ramp_target=0; ramp_duration=0;
 start_succeeds=tx_succeeds=true; uart_registers={}; reply={}; uno_link_init();
 if (ready) { uno_update_softstart_state(0); now_ms=3500; uno_update_softstart_state(now_ms); }
}
void scenarios() {
 reset(); feed(frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 5000));
 check(starts==0 && !uno_link.command_enabled, "zero bus no start");
 bus_v=310; uno_update_softstart_state(0);
 now_ms=3499; feed(frame(1,3,5000,2)); check(starts==0, "settle not early");
 now_ms=3500; feed(frame(1,3,5000,3));
 check(starts==1 && uno_link.command_enabled && motor_state==RUN, "start after 3500 ms");
 check(ramp_target==RPM_2_SPEED_UNIT(300) && ramp_duration==3000, "5 Hz ramp units");
 feed(frame(1,3,20000,4));
 check(starts==1 && ramps==2 && ramp_target==RPM_2_SPEED_UNIT(1200), "20 Hz no restart");
 feed(frame(1,3,20000,5)); check(ramps==2, "same speed no duplicate ramp");
 feed(frame(0,0,0,6)); check(!uno_link.command_enabled && motor_state==IDLE, "STOP");
 reset(true); feed(frame(1,3,5000)); feed(frame(UNO_FLAG_ESTOP,0,0,2));
 check(uno_link.fault_latched && uno_link.fault_code==UNO_FAULT_ESTOP && motor_state==IDLE, "ESTOP stops");
 feed(frame(1,3,5000,3)); check(starts==1, "ESTOP blocks restart");
 feed(frame(0,0,0,4)); check(uno_link.fault_latched, "STOP does not clear ESTOP");
 feed(frame(UNO_FLAG_CLEAR_FAULT,0,0,5)); check(!uno_link.fault_latched, "clean CLEAR releases latch");
 reset(true); feed(frame(1,3,5000)); now_ms+=300; uno_link_poll();
 check(!uno_link.fault_latched, "watchdog accepts 300 ms");
 ++now_ms; uno_link_poll();
 check(uno_link.fault_code==UNO_FAULT_TIMEOUT && motor_state==IDLE, "watchdog stops at 301 ms");
 reset(true); feed(frame(1,3,5000,255)); feed(frame(1,3,5000,0));
 check(!uno_link.fault_latched, "sequence wraps");
 feed(frame(1,3,5000,0)); check(uno_link.fault_latched && motor_state==IDLE, "frozen ENABLE stops");
 reset(true); start_succeeds=false; feed(frame(1,3,5000));
 check(uno_link.fault_latched && !uno_link.command_enabled, "MCSDK start failure latches");
 reset(true); feed(frame(1,3,5000)); mc_fault=0x400; motor_state=FAULT_NOW; uno_link_poll();
 check(uno_link.fault_latched && !uno_link.command_enabled, "MCSDK DP stops command");
 for (auto state : {FAULT_NOW, FAULT_OVER}) {
  reset(true); motor_state=state; feed(frame(1,3,5000));
  check(starts==0 && uno_link.fault_latched, "fault state rejects start");
 }
 reset(true); tx_succeeds=false; feed(frame(1,3,5000));
 check(uno_link.fault_latched && motor_state==IDLE, "reply TX failure stops");
 for (unsigned flag=1; flag<=8; flag<<=1) {
  reset(true); feed(frame(1,3,5000)); uart_registers.ISR=flag; USART1_IRQHandler(); uno_link_poll();
  check(uno_link.fault_latched && motor_state==IDLE && uart_registers.ISR==0, "UART hardware error stops");
 }
 reset(true); uno_link.good_count=UINT16_MAX; feed(frame(0,0));
 check(uno_link.good_count==UINT16_MAX, "counter saturates");
 reset(true); feed(frame(1,3,5000));
 check(reply[3] & UNO_STATUS_PWM_ACTIVE, "RUN telemetry PWM bit");
 check(reply[31]==uno_crc_xor(reply.data()) && reply[14]==0, "reply CRC and no relay");
 uint32_t build=uno_u32le(&reply[23]);
 check(build==MIC_NUCLEO_FW_BUILD_ID && (reply[29]&UNO_TELEMETRY_FW_BUILD_VALID), "reply build identity");
 for (uint16_t v : {0,199,200,249,250,310,385,386}) {
  reset(); bus_v=v; uno_update_softstart_state(0); uno_update_softstart_state(3500);
  check(uno_link.softstart_ready==(v>=250 && v<=385), "initial bus threshold");
  reset(true); bus_v=v; uno_update_softstart_state(3501);
  check(uno_link.softstart_ready==(v>=200 && v<=385), "hold bus hysteresis");
 }
 reset(); bus_v=310; now_ms=UINT32_MAX-1000; uno_update_softstart_state(now_ms);
 now_ms+=3499; uno_update_softstart_state(now_ms); check(!uno_link.softstart_ready, "settle wrap before boundary");
 ++now_ms; uno_update_softstart_state(now_ms); check(uno_link.softstart_ready, "settle uint32 wrap");
 reset(true); now_ms=UINT32_MAX-100; feed(frame(1,3,5000)); now_ms+=301; uno_link_poll();
 check(uno_link.fault_code==UNO_FAULT_TIMEOUT, "watchdog uint32 wrap");
}
void exhaustive_commands() {
 const uint32_t max_freq=MOTOR_MAX_SPEED_RPM*POLE_PAIR_NUM*1000U/60U;
 for (unsigned flags=0; flags<256; ++flags) for (unsigned mode=0; mode<256; ++mode)
  for (uint32_t freq : {0U, 1U, max_freq, max_freq+1U}) {
   reset(true); feed(frame((uint8_t)flags,(uint8_t)mode,freq));
   bool valid=flags==UNO_FLAG_ENABLE && mode==UNO_MODE_SCALAR && freq>0 && freq<=max_freq;
   check(starts==(valid ? 1U : 0U), "all 256 flags x 256 modes x 4 frequencies");
  }
 for (unsigned byte=0; byte<UNO_FRAME_LEN; ++byte) for (unsigned bit=0; bit<8; ++bit) {
  reset(true); Frame f=frame(1,3,5000); f[byte]^=(uint8_t)(1U<<bit); feed(f);
  check(starts==0, "each single-bit corruption cannot start");
 }
 for (unsigned byte=14; byte<31; ++byte) {
  reset(true); Frame f=frame(1,3,5000); f[byte]=1; checksum(f); feed(f);
  check(starts==0 && uno_link.fault_latched, "service fields reject ENABLE");
 }
 for (unsigned byte=6; byte<31; ++byte) {
  reset(true); uno_latch_fault(UNO_FAULT_ESTOP);
  Frame f=frame(UNO_FLAG_CLEAR_FAULT,0); f[byte]=1; checksum(f); feed(f);
  check(uno_link.fault_latched && starts==0, "dirty CLEAR cannot release latch");
 }
}
void diagnostic_scenarios() {
 reset(true); feed(frame(1,3,5000)); uart_registers.ISR=UART_FLAG_ORE | UART_FLAG_FE;
 mc_fault=0x40; mc_occurred=0x440; USART1_IRQHandler(); uno_link_poll();
 check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_uart_errors==0x0a,
       "UART flags captured before hardware clear");
 check(uno_link.first_current_faults==0x40 && uno_link.first_occurred_faults==0x440,
       "first current and occurred MCSDK masks retained");
 const auto first_state=uno_link.first_motor_state;
 feed(frame(UNO_FLAG_ESTOP,0,0,2)); feed(frame(0,0,0,3));
 check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_motor_state==first_state,
       "STOP and ESTOP cannot overwrite first cause");
 check(reply[11]==(UNO_DIAG_TAG|UNO_DIAG_UART) && reply[12]==0xaa
       && ((reply[15] | (reply[16]<<8))==0x40)
       && ((reply[27] | (reply[28]<<8))==0x440) && reply[14]==0,
       "diagnostic reply layout preserves reserved relay and masks");
 mc_fault=0; motor_state=FAULT_OVER; feed(frame(UNO_FLAG_CLEAR_FAULT,0,0,4));
 check(uno_link.first_reason==0 && reply[11]==UNO_DIAG_TAG,
       "only clean CLEAR releases stored diagnostics");
 for (unsigned mask=1; mask<16; ++mask) {
  reset(true);
  uart_registers.ISR=((mask&1)?UART_FLAG_PE:0)|((mask&2)?UART_FLAG_FE:0)
    |((mask&4)?UART_FLAG_NE:0)|((mask&8)?UART_FLAG_ORE:0);
  USART1_IRQHandler(); uno_link_poll();
  check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_uart_errors==mask,
        "all UART flag combinations distinguished");
 }
 reset(true); tx_succeeds=false; feed(frame(1,3,5000));
 check(uno_link.first_reason==UNO_DIAG_TX && uno_link.first_tx_status==1,
       "transmit failure retains HAL status");
 reset(true); Frame f=frame(1,3,5000); f[31]^=1; feed(f);
 check(uno_link.first_reason==UNO_DIAG_CRC, "CRC reason");
 reset(true); f=frame(1,3,5000); f[2]=3; checksum(f); feed(f);
 check(uno_link.first_reason==UNO_DIAG_VERSION, "version reason");
 reset(true); feed(frame(1,3,5000)); feed(frame(1,3,5000));
 check(uno_link.first_reason==UNO_DIAG_REPLAY, "replay reason");
 reset(true); feed(frame(UNO_FLAG_ESTOP,0));
 check(uno_link.first_reason==UNO_DIAG_ESTOP, "ESTOP reason");
 reset(true); f=frame(1,3,5000); f[14]=1; checksum(f); feed(f);
 check(uno_link.first_reason==UNO_DIAG_SERVICE, "service reason");
 reset(true); feed(frame(1,2,5000));
 check(uno_link.first_reason==UNO_DIAG_COMMAND, "command reason");
 reset(true); feed(frame(1,3,0));
 check(uno_link.first_reason==UNO_DIAG_FREQUENCY, "frequency reason");
 reset(true); mc_fault=4; mc_occurred=4; motor_state=FAULT_NOW;
 uno_send_reply();
 check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_current_faults==4,
       "MCSDK fault visible even with no ENABLE command");
 reset(true); bus_v=386; feed(frame(1,3,5000));
 check(uno_link.first_reason==UNO_DIAG_BUS, "bus guard reason");
 reset(true); start_succeeds=false; feed(frame(1,3,5000));
 check(uno_link.first_reason==UNO_DIAG_START, "start API reason");
 reset(true); feed(frame(1,3,5000)); now_ms+=301; uno_link_poll();
 check(uno_link.first_reason==UNO_DIAG_TIMEOUT, "watchdog reason");
 reset(true); uno_capture_diagnostics(UNO_DIAG_UART,8,0);
 f=frame(UNO_FLAG_CLEAR_FAULT,0); f[6]=1; checksum(f); feed(f);
 check(uno_link.first_reason==UNO_DIAG_UART, "dirty CLEAR cannot erase evidence");
 reset(true); mc_fault=4; mc_occurred=4; motor_state=FAULT_NOW; uno_send_reply();
 uart_registers.ISR=UART_FLAG_ORE; USART1_IRQHandler(); uno_link_poll(); uno_send_reply();
 check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.last_bad_reason==UNO_DIAG_UART,
       "new bad counter cause not hidden behind earlier MCSDK fault");
 check((reply[12]>>4)==8 && (reply[22]>>4)==UNO_DIAG_UART,
       "last UART flags and counter cause exported independently");
 reset(true);
 for (unsigned i=0; i<127; ++i) check(uno_rx_push((uint8_t)i), "RX ring capacity");
 check(!uno_rx_push(128), "RX ring never overwrites unread bytes");
 for (unsigned i=0; i<127; ++i) { uint8_t b=255; check(uno_rx_pop(&b)&&b==i,"RX order"); }
 for (unsigned cycle=0; cycle<1000; ++cycle) {
  for (unsigned i=0; i<64; ++i) check(uno_rx_push((uint8_t)i), "ring wrap producer");
  for (unsigned i=0; i<64; ++i) { uint8_t b=255; check(uno_rx_pop(&b)&&b==i,"ring wrap consumer"); }
 }
 reset(true);
 for (unsigned seq=1; seq<=3; ++seq) for(auto b:frame(1,3,5000,seq))
  check(uno_rx_push(b), "buffer frames while main is delayed");
 uno_link_poll();
 check(starts==1 && uno_link.good_count==3 && !uno_link.fault_latched,
       "main consumes delayed complete frames without loss or duplicate start");
 uno_rx_overflow=1; uno_link_poll();
 check(uno_link.fault_latched && motor_state==IDLE && uno_link.last_bad_reason==UNO_DIAG_RX_BUFFER,
       "software RX overflow remains fail closed and diagnosed");
}
int main() {
 scenarios(); diagnostic_scenarios(); exhaustive_commands();
 std::printf("{\"pass\":true,\"assertions\":%u,\"command_combinations\":262144,\"single_bit_corruptions\":256}\n", tests);
}
