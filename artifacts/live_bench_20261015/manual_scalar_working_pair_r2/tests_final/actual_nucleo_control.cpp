#include "uart_v3_transport.h"
#include "manual_scalar_control.h"
void peer_receive(const uint8_t *,unsigned);

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
 std::memcpy(reply.data(), data, size); if(tx_succeeds) peer_receive(data,size); return tx_succeeds ? HAL_OK : 1;
}
#define __HAL_UART_GET_FLAG(h, flag) (false)
#define __HAL_UART_CLEAR_OREFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_ORE)
#define __HAL_UART_CLEAR_NEFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_NE)
#define __HAL_UART_CLEAR_FEFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_FE)
#define __HAL_UART_CLEAR_PEFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_PE)

#include <deque>
#include "nucleo_fault_diagnostics.h"
#include "link_timing.h"
#include "break_wire.h"
#include "superseded_reply.h"
#include "uno_q_control.h"
namespace peer {
struct SerialStub { std::deque<uint8_t> bytes;
 int available(){return (int)bytes.size();} int read(){auto b=bytes.front();bytes.pop_front();return b;} } NUCLEO_SERIAL;
unsigned irq_lock(){return 0;} void irq_unlock(unsigned){}
uint32_t millis(){return ::now_ms;} uint32_t micros(){return ::now_ms*1000U;}
void enc_speed_update(uint16_t,bool,uint32_t){}
float bp_vdc_from_raw(uint16_t){return 0;} float bp_temp_voltage_from_raw(uint16_t){return 0;}
bool bp_temp_c_from_raw(uint16_t,float*){return false;} float bp_phase_voltage_from_raw(uint16_t){return 0;}
static const float BP_FAN_TACH_RPM_STEP = 30.0f;
static const size_t BP_FRAME_LEN = UV3_FRAME;
static const uint8_t BP_PHASE_FLAG_VALID = 0x01;
static const uint32_t BP_REPLY_TIMEOUT_MS = 500;
static const uint8_t BP_RSP_FAN_DUTY_Q8 = 22;
static const uint8_t BP_RSP_FAN_TACH_X30 = 30;
static const uint8_t BP_STATUS_PWM_ACTIVE = 0x20;
static const uint8_t BP_TEMP_FLAG_VALID = 0x01;
static const uint8_t BP_VER = UV3_VERSION;
static const uint8_t MC_TELEMETRY_FLAG_FW_BUILD_VALID = 0x10;
static const uint8_t MC_TELEMETRY_FLAG_MCSDK_UNITS = 0x80;
static const uint8_t MC_TELEMETRY_FLAG_SOFTSTART_READY = 0x20;
static const uint8_t MC_TELEMETRY_FLAG_VBUS_VALID = 0x40;
static const bool NUCLEO_MCSDK_ACIM_BACKEND = true;
static uint16_t g_bp_bad_cnt = 0;
static uint16_t g_bp_brake_q15 = 0;
static uint32_t g_bp_enc_ms = 0;
static bool g_bp_enc_ok = false;
static uint16_t g_bp_enc_raw = 0;
static uint8_t g_bp_ext_flags = 0;
static float g_bp_fan_duty = 0.0f;
static uint8_t g_bp_fan_duty_q8 = 0;
static float g_bp_fan_rpm = 0.0f;
static uint8_t g_bp_fan_tach_x30 = 0;
static uint8_t g_bp_fault_code = 0;
static uint32_t g_bp_fw_build = 0;
static uint16_t g_bp_good_cnt = 0;
static uint8_t g_bp_last_mode = 0;
static uint32_t g_bp_last_rsp_ms = 0;
static uint8_t g_bp_last_seq = 0;
static bool g_bp_mcsdk_telemetry = false;
static uint16_t g_bp_ne_accepted = 0;
static uint8_t g_bp_ne_flags = 0;
static uint16_t g_bp_ne_observed = 0;
static uint16_t g_bp_phase_a_raw = 0;
static float g_bp_phase_a_v = 0.0f;
static uint16_t g_bp_phase_b_raw = 0;
static float g_bp_phase_b_v = 0.0f;
static uint16_t g_bp_phase_c_raw = 2048;
static float g_bp_phase_c_v = 0.0f;
static uint8_t g_bp_phase_flags = 0;
static uint32_t g_bp_phase_ms = 0;
static uint32_t g_bp_ping_ms = 0;
static uint32_t g_bp_ping_pairs = 0;
static uint8_t g_bp_ping_prev = 0;
static uint16_t g_bp_recovered_drops = 0;
static bool g_bp_softstart_ready = false;
static uint8_t g_bp_status = 0;
static float g_bp_temp_c = 0.0f;
static uint8_t g_bp_temp_flags = 0;
static uint32_t g_bp_temp_ms = 0;
static uint16_t g_bp_temp_raw = 0;
static float g_bp_temp_v = 0.0f;
static uint8_t g_bp_transport_fault = 0;
static uint32_t g_bp_vbus_ms = 0;
static uint16_t g_bp_vbus_raw = 0;
static bool g_bp_vbus_valid = false;
static float g_bp_vdc = 0.0f;
static bw_receiver g_break_wire;
static bool g_clear_fault_req = false;
static uint32_t g_link_led_ms = 0;
static LinkTiming g_link_timing;
static bool g_manual_bus_hold = false;
static float g_manual_reference_hz = 0.0f;
static bool g_manual_reference_valid = false;
static NucleoFaultDiagnostics g_mc_diagnostics;
static uint32_t g_nucleo_last_ack_us = 0;
static uint32_t g_nucleo_last_rx_ms = 0;
static uint16_t g_nucleo_rx_bad = 0;
static uint16_t g_nucleo_rx_bad_integrity = 0;
static uint16_t g_nucleo_rx_bad_sequence = 0;
static uint16_t g_nucleo_rx_good = 0;
static uint16_t g_nucleo_rx_superseded = 0;
static SupersededReplies g_nucleo_superseded;
static bool g_nucleo_waiting_clear = false;
static bool g_nucleo_waiting_rsp = false;
static uint8_t g_nucleo_waiting_seq = 0;
static bool g_pwm_enabled = false;
static uint32_t g_rx_rejected_ms, g_rx_poll_ms, g_rx_poll_gap_max_ms;
static uint8_t g_rx_rejected[UV3_FRAME];
static bool nucleo_check_reply(const uint8_t *rx, bool require_sequence, uint8_t expected_sequence) {
  if (!rx) return false;
  if (rx[0] != 0x55 || rx[1] != 0xAA) return false;
  if (rx[2] != BP_VER) return false;
  if (!uv3_crc_ok(rx)) return false;
  if (require_sequence && rx[4] != expected_sequence) return false;
  const bool clear_ack = unoq_clear_reply_ack(
      require_sequence && g_nucleo_waiting_rsp && rx[4] == g_nucleo_waiting_seq,
      g_nucleo_waiting_clear, rx[10], rx[3]);
  uint32_t now_ms = millis();
  const uint32_t previous_build = g_bp_fw_build;
  const uint16_t previous_good = g_bp_good_cnt;
  const uint32_t previous_age = now_ms - g_bp_last_rsp_ms;
  g_bp_ne_accepted = (uint16_t)rx[31] | ((uint16_t)rx[32] << 8);
  g_bp_ne_observed = (uint16_t)rx[33] | ((uint16_t)rx[34] << 8);
  g_bp_recovered_drops = (uint16_t)rx[35] | ((uint16_t)rx[36] << 8);
  g_bp_ne_flags = rx[37];
  g_bp_transport_fault = rx[38];
  g_bp_status = rx[3];
  g_bp_last_seq = rx[4];
  g_bp_good_cnt = (uint16_t)rx[5] | ((uint16_t)rx[6] << 8);
  g_bp_bad_cnt = (uint16_t)rx[7] | ((uint16_t)rx[8] << 8);
  g_bp_fault_code = rx[9];
  g_bp_last_mode = rx[10];
  if (!NUCLEO_MCSDK_ACIM_BACKEND) {
    g_bp_enc_raw = (uint16_t)rx[11] | ((uint16_t)rx[12] << 8);
    g_bp_enc_ok = (rx[13] != 0);
    g_bp_enc_ms = now_ms;
    enc_speed_update(g_bp_enc_raw, g_bp_enc_ok, now_ms);
  }
  g_bp_ext_flags = rx[14];
  g_bp_brake_q15 = (uint16_t)rx[15] | ((uint16_t)rx[16] << 8);
  g_bp_phase_flags = rx[29];
  g_bp_mcsdk_telemetry = (g_bp_phase_flags & MC_TELEMETRY_FLAG_MCSDK_UNITS) != 0U;
  g_bp_vbus_valid = (g_bp_phase_flags & MC_TELEMETRY_FLAG_VBUS_VALID) != 0U;
  g_bp_softstart_ready = (g_bp_phase_flags & MC_TELEMETRY_FLAG_SOFTSTART_READY) != 0U;
  if ((g_bp_phase_flags & MC_TELEMETRY_FLAG_FW_BUILD_VALID) != 0U &&
      (g_bp_phase_flags & BP_PHASE_FLAG_VALID) == 0U) {
    g_bp_fw_build = (uint32_t)rx[23] |
                    ((uint32_t)rx[24] << 8U) |
                    ((uint32_t)rx[25] << 16U) |
                    ((uint32_t)rx[26] << 24U);
  } else {
    g_bp_fw_build = 0U;
  }
  if (bw_peer_reset_required(previous_build,g_bp_fw_build,previous_good,g_bp_good_cnt,previous_age))
    bw_reset(&g_break_wire);
  g_manual_reference_valid=g_bp_mcsdk_telemetry && g_bp_fw_build==2026101502U && (rx[11]&0xFEU)==0xA0U;
  if (g_manual_reference_valid) {
    const uint16_t reference=(uint16_t)(rx[12] | ((uint16_t)rx[13]<<8));
    if (reference>5000U) return false;
    g_manual_reference_hz=reference*0.01f;
    g_manual_bus_hold=(rx[11]&1U)!=0;
  } else g_manual_bus_hold=false;
  g_mc_diagnostics = decode_nucleo_fault_diagnostics(rx, g_bp_mcsdk_telemetry, g_bp_fw_build);
  if (g_mc_diagnostics.valid) g_bp_brake_q15 = 0U;
  g_bp_vbus_raw = (uint16_t)rx[17] | ((uint16_t)rx[18] << 8);
  if (g_bp_mcsdk_telemetry) {
    g_bp_vdc = (float)g_bp_vbus_raw * 0.1f;
  } else {
    if (g_bp_vbus_raw > 4095U) {
      g_bp_vbus_raw = 4095U;
    }
    g_bp_vdc = bp_vdc_from_raw(g_bp_vbus_raw);
  }
  g_bp_vbus_ms = now_ms;
  g_bp_temp_raw = (uint16_t)rx[19] | ((uint16_t)rx[20] << 8);
  g_bp_temp_flags = rx[21];
  if (g_bp_mcsdk_telemetry) {
    g_bp_temp_v = 0.0f;
    g_bp_temp_c = ((float)(int16_t)g_bp_temp_raw) * 0.1f;
  } else {
    if (g_bp_temp_raw > 4095U) {
      g_bp_temp_raw = 4095U;
    }
    g_bp_temp_v = bp_temp_voltage_from_raw(g_bp_temp_raw);
    float temp_c = 0.0f;
    if ((g_bp_temp_flags & BP_TEMP_FLAG_VALID) != 0 && bp_temp_c_from_raw(g_bp_temp_raw, &temp_c)) {
      g_bp_temp_c = temp_c;
    } else {
      g_bp_temp_c = 0.0f;
    }
  }
  g_bp_temp_ms = now_ms;
  g_bp_fan_duty_q8 = g_mc_diagnostics.valid ? 0U : rx[BP_RSP_FAN_DUTY_Q8];
  g_bp_fan_tach_x30 = g_mc_diagnostics.valid ? 0U : rx[BP_RSP_FAN_TACH_X30];
  g_bp_fan_duty = (float)g_bp_fan_duty_q8 / 255.0f;
  g_bp_fan_rpm = (float)g_bp_fan_tach_x30 * BP_FAN_TACH_RPM_STEP;
  if ((g_bp_phase_flags & BP_PHASE_FLAG_VALID) != 0U) {
    g_bp_phase_a_raw = (uint16_t)rx[23] | ((uint16_t)rx[24] << 8);
    g_bp_phase_b_raw = (uint16_t)rx[25] | ((uint16_t)rx[26] << 8);
    g_bp_phase_c_raw = (uint16_t)rx[27] | ((uint16_t)rx[28] << 8);
  } else {
    g_bp_phase_a_raw = 0U;
    g_bp_phase_b_raw = 0U;
    g_bp_phase_c_raw = 0U;
  }
  if (g_bp_phase_a_raw > 4095U) g_bp_phase_a_raw = 4095U;
  if (g_bp_phase_b_raw > 4095U) g_bp_phase_b_raw = 4095U;
  if (g_bp_phase_c_raw > 4095U) g_bp_phase_c_raw = 4095U;
  g_bp_phase_a_v = bp_phase_voltage_from_raw(g_bp_phase_a_raw);
  g_bp_phase_b_v = bp_phase_voltage_from_raw(g_bp_phase_b_raw);
  g_bp_phase_c_v = bp_phase_voltage_from_raw(g_bp_phase_c_raw);
  g_bp_phase_ms = now_ms;
  g_bp_last_rsp_ms = now_ms;
  const unsigned int timing_rx_key = irq_lock();
  g_link_timing.rx(micros(), g_pwm_enabled || ((rx[3] & BP_STATUS_PWM_ACTIVE) != 0U));
  irq_unlock(timing_rx_key);
  if (g_nucleo_waiting_rsp && g_bp_last_seq == g_nucleo_waiting_seq) {
    g_nucleo_waiting_rsp = false;
    g_nucleo_last_ack_us = micros();
  }
  // A correlated safe-off reply acknowledges delivery, not removal of a
  // physical fault. Never keep resetting Nucleo's counters during undervoltage.
  if (g_clear_fault_req) {
    bool fault = (g_bp_fault_code != 0) || ((g_bp_status & 0x08u) != 0u);
    if (clear_ack || (!require_sequence && !fault)) {
      g_clear_fault_req = false;
    }
  }
  return true;
}
static void nucleo_uart_poll() {
  static uint8_t st = 0;
  static uint8_t idx = 0;
  static uint8_t buf[BP_FRAME_LEN];
  const uint32_t poll_ms = millis();
  if (g_rx_poll_ms) LinkTiming::maximum(g_rx_poll_gap_max_ms, poll_ms-g_rx_poll_ms);
  g_rx_poll_ms = poll_ms;
  while (NUCLEO_SERIAL.available() > 0) {
    uint8_t b = (uint8_t)NUCLEO_SERIAL.read();
    // Detect the motor controller's boot ping (0x5A 0xA5 ...) to diagnose RX wiring/baud
    // even when no valid reply frames are received yet.
    if (g_bp_ping_prev == 0x5A && b == 0xA5) {
      if (g_bp_ping_pairs < 0xFFFFFFFFu) g_bp_ping_pairs++;
      g_bp_ping_ms = millis();
    }
    g_bp_ping_prev = b;
    if (st == 0) {
      if (b == 0x55) {
        buf[0] = b;
        st = 1;
      }
      continue;
    }
    if (st == 1) {
      if (b == 0xAA) {
        buf[1] = b;
        idx = 2;
        st = 2;
      } else if (b == 0x55) {
        buf[0] = b;
        st = 1;
      } else {
        st = 0;
      }
      continue;
    }
    // st == 2
    buf[idx++] = b;
    if (idx >= sizeof(buf)) {
      st = 0;
      idx = 0;
      if (!uv3_crc_ok(buf)) {
        memcpy(g_rx_rejected,buf,sizeof(buf)); g_rx_rejected_ms=millis();
      }
      if (buf[2] == BW_VERSION) {
        const bool had_rejection=g_break_wire.first_reject.valid;
        const uint32_t observed_ms=millis();
        const uint32_t observed_age=(uint32_t)(observed_ms-g_bp_last_rsp_ms);
        const bool fresh_off = g_bp_mcsdk_telemetry && !g_pwm_enabled &&
            (g_bp_status & 0x22U) == 0U && observed_age < 300U;
        if (!uv3_crc_ok(buf)) {
          (void)bw_note_reject(&g_break_wire,BW_REJECT_FRAME_CRC,buf,g_bp_fw_build,fresh_off,observed_ms);
          if (g_nucleo_rx_bad < 0xFFFFU) ++g_nucleo_rx_bad;
          if (g_nucleo_rx_bad_integrity < 0xFFFFU) ++g_nucleo_rx_bad_integrity;
        } else {
          (void)bw_receive(&g_break_wire,buf,g_bp_fw_build,fresh_off,observed_ms);
        }
        if (!had_rejection && g_break_wire.first_reject.valid) {
          g_break_wire.first_reject.bp_status=g_bp_status;
          g_break_wire.first_reject.pwm_enabled=g_pwm_enabled;
          g_break_wire.first_reject.rsp_age_ms=observed_age;
        }
        continue;
      }
      const bool integrity_ok = buf[0] == 0x55 && buf[1] == 0xAA &&
          buf[2] == BP_VER && uv3_crc_ok(buf);
      if (integrity_ok && g_nucleo_superseded.consume(
              buf[4], micros(), BP_REPLY_TIMEOUT_MS * 1000U)) {
        if (g_nucleo_rx_superseded < 0xFFFFu) g_nucleo_rx_superseded++;
      } else if (g_nucleo_waiting_rsp &&
          nucleo_check_reply(buf, true, g_nucleo_waiting_seq)) {
        if (g_nucleo_rx_good < 0xFFFFu) g_nucleo_rx_good++;
        g_nucleo_last_rx_ms = millis();
        g_link_led_ms = g_nucleo_last_rx_ms;
      } else {
        if (g_nucleo_rx_bad < 0xFFFFu) g_nucleo_rx_bad++;
        if (!integrity_ok) {
          if (g_nucleo_rx_bad_integrity < 0xFFFFu) g_nucleo_rx_bad_integrity++;
        } else if (g_nucleo_rx_bad_sequence < 0xFFFFu) {
          g_nucleo_rx_bad_sequence++;
        }
      }
    }
  }
}
}
void peer_expect(uint8_t seq,bool clear){peer::g_nucleo_waiting_seq=seq;peer::g_nucleo_waiting_rsp=true;peer::g_nucleo_waiting_clear=clear;}
void peer_receive(const uint8_t *data,unsigned size){
 for(unsigned i=0;i<size;++i) { peer::NUCLEO_SERIAL.bytes.push_back(data[i]); }
 peer::nucleo_uart_poll();
}

bool local_stop = false;
volatile unsigned mic_local_stop_latched, mic_break_start_window;
bool mic_last_control_reply_safe_off;
bool mic_local_stop_blocked() { return local_stop; }
bool mic_local_stop_clear() { if(local_stop) return false; return true; }
struct mic_break_context_t { uint32_t tick; int16_t ref; uint32_t state;
  uint16_t current, occurred, bus; int16_t temp; uint8_t seq; };
void mic_break_publish_context(const mic_break_context_t *) {}
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

#define MIC_NUCLEO_FW_BUILD_ID 2026101502UL

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

static void mic_send_break_page(uint32_t) {}

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
  const int tx_status = HAL_UART_Transmit(&huart1, reply, UNO_FRAME_LEN, UNO_REPLY_TIMEOUT_MS);
  /* Publish diagnostics only after an off reply, not an IRQ transition
     which occurred while a previous on reply was being transmitted. */
  mic_last_control_reply_safe_off = (tx_status == HAL_OK) && ((status & 0x22U) == 0U);
  if (tx_status == HAL_OK) mic_send_break_page(now_ms);
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
        (uno_link.ramp_target_speed_unit!=target_speed_unit && current==uno_link.ramp_target_speed_unit);
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


void check(bool v,const char *name) { ++tests;if(!v){std::fprintf(stderr,"FAIL %s\n",name);std::exit(1);} }
using Frame = std::array<uint8_t,UV3_FRAME>;
Frame packet(unsigned seq,uint8_t flags=0,uint8_t mode=0,unsigned hz=0) {
 Frame f{};f[0]=0xaa;f[1]=0x55;f[2]=UV3_VERSION;f[3]=flags;f[4]=mode;f[5]=(uint8_t)seq;
 for(unsigned i=0;i<4;++i) { f[6+i]=(uint8_t)(hz>>(8*i)); }
 uv3_seal(f.data());return f;
}
void feed(Frame f,int ne=-1) {
 peer_expect(f[5],f[3]==8);
 for(unsigned i=0;i<f.size();++i) {
  uart_registers.ISR=UART_FLAG_RXNE|((int)i==ne ? UART_FLAG_NE : 0);
  uart_registers.RDR=f[i];USART1_IRQHandler();
 }
 uno_link_poll();
}
void reset(bool warm=true,unsigned seq=1,uint32_t tick=100) {
 now_ms=tick;bus_v=310;mc_fault=mc_occurred=0;motor_state=IDLE;
 test_timer={};local_stop=false;mic_local_stop_latched=0;mic_break_start_window=0;
 start_succeeds=tx_succeeds=true;starts=stops=ramps=0;ramp_target=0;
 uno_link_init();uno_link.softstart_ready=true;
 if(warm)for(unsigned i=0;i<3;++i){now_ms+=50;feed(packet(seq+i));}
}
void running() {reset();now_ms+=50;feed(packet(4,1,3,5000));check(motor_state==RUN,"start");}
void run() {

 // CRC-correct single-NE packets must not spend damaged-packet recovery budget.
 running();
 for(unsigned seq=5;seq<=44;++seq){
  now_ms+=50;feed(packet(seq,1,3,5000),6);
  check(!uno_link.fault_latched && motor_state==RUN,"verified NE burst keeps validated command link alive");
 }
 check(uno_transport.accepted_noise_frames==40 && uno_transport.noise_used==0 && uno_transport.dropped_frames==0,
       "verified NE metadata remains visible and distinct from discarded data");
 now_ms+=50;auto corrupt=packet(45,1,3,6000);corrupt[8]^=1;feed(corrupt);
 check(!uno_link.fault_latched && uno_transport.dropped_frames==1,"true corruption retains its separate budget after NE burst");
 now_ms+=50;feed(packet(46,1,3,6000),10);
 check(!uno_link.fault_latched && uno_link.last_seq==46,"verified NE can recover an observed lost packet");
 auto committed=uno_transport.last_valid_ms;
 for(unsigned i=0;i<5;++i){now_ms=committed+50*(i+1);uno_consume_sample(0x42,UV3_NE);}
 now_ms=committed+301;uno_link_poll();
 check(uno_link.fault_latched && motor_state==IDLE,"unframed noise never becomes a verified command heartbeat");

 // Per-byte flags travel through the ACTUAL ISR and ring, not directly to the parser.
 for(unsigned pos=0;pos<UV3_FRAME;++pos) {
  reset();now_ms+=50;feed(packet(4,1,3,5000),(int)pos);
  check(starts==1 && !uno_link.fault_latched && uno_transport.accepted_noise_frames==1,"intact NE START at every byte");
  check(uno_link.bad_count==0,"accepted NE never presented as fatal bad frame");
  check(peer::g_bp_ne_accepted==1 && peer::g_bp_fault_code==0,"Uno receives intact NE START reply");
 }
 running();for(unsigned seq=5;seq<=7;++seq){now_ms+=50;feed(packet(seq,1,3,5000));}
 now_ms+=50;feed(packet(8,1,3,6000),6);
 check(!uno_link.fault_latched && ramp_target==RPM_2_SPEED_UNIT(360),"intact NE frequency change");
 running();auto last=uno_transport.last_valid_ms;
 uno_consume_sample(0x42,UV3_NE);
 check(!uno_link.fault_latched && uno_transport.last_valid_ms==last,"stray NE does not refresh watchdog");
 now_ms+=50;feed(packet(5,1,3,5000));check(!uno_link.fault_latched,"next fresh command after stray NE");
 // Finite exhaustive sweep of all single-bit edits in payload and CRC.
 for(unsigned pos=0;pos<UV3_FRAME;++pos)for(unsigned bit=0;bit<8;++bit) {
  running();Frame bad=packet(5,1,3,6000);bad[pos]^=(uint8_t)(1U<<bit);
  const auto before_ramps=ramps;const auto deadline=uno_transport.last_valid_ms;
  now_ms+=50;feed(bad);
  check(!uno_link.fault_latched && ramps==before_ramps && uno_transport.last_valid_ms==deadline,"corruption cannot apply a command or feed watchdog");
  check(uno_transport.dropped_frames==1 && uno_link.bad_count==0,"discard has separate visible counter");
  now_ms+=50;feed(packet(6,1,3,6000));
  check(!uno_link.fault_latched && uno_link.last_seq==6,"one observed loss permits bounded fresh sequence gap");
  check(peer::g_bp_recovered_drops==1 && peer::g_bp_bad_cnt==0,"Uno decodes recovery counter separately from fatal errors");
 }
 running();now_ms+=50;Frame bad=packet(5,1,3,6000);bad[8]^=1;feed(bad);
 now_ms+=50;feed(packet(4,1,3,5000));check(uno_link.fault_latched,"loss never permits duplicate/replay");
 running();now_ms+=50;bad=packet(5,1,3,6000);bad[8]^=1;feed(bad);
 now_ms+=50;feed(packet(7,1,3,6000));check(uno_link.fault_latched,"one loss cannot permit a two-frame gap");
 running();now_ms+=50;feed(packet(6,1,3,6000));check(uno_link.fault_latched,"unobserved sequence gap is rejected");
 // Sliding window is shared by accepted noise and discarded packets.
 running();for(unsigned seq=5;seq<=7;++seq){now_ms+=50;bad=packet(seq,1,3,6000);bad[8]^=1;feed(bad);}
 check(uno_link.fault_latched && motor_state==IDLE,"third damaged packet in 1s latches off");
 now_ms+=50;feed(packet(8,1,3,5000));check(starts==1 && uno_link.fault_latched,"clean ENABLE cannot restart a latched failure");
 running();last=uno_transport.last_valid_ms;now_ms=last+300;
 uno_link_poll();check(!uno_link.fault_latched,"watchdog at 300ms");
 ++now_ms;uno_link_poll();check(uno_link.fault_latched && motor_state==IDLE,"watchdog at 301ms");
 for(unsigned flags:{UV3_PE,UV3_FE,UV3_ORE}) {
  running();uno_consume_sample(0,flags);
  check(uno_link.fault_latched && motor_state==IDLE,"hard UART errors still immediate");
 }
 running();uart_registers.ISR=UART_FLAG_NE;USART1_IRQHandler();uno_link_poll();
 check(uno_link.fault_latched,"NE with no associated RX byte remains hard failure");
 running();local_stop=true;uno_link_poll();check(uno_link.fault_latched && motor_state==IDLE,"local stop wins over transport recovery");
 // Actual MCSDK/bus branches keep UART alive after losing high voltage.
 running();mc_fault=mc_occurred=4;motor_state=FAULT_NOW;bus_v=10;uno_link_poll();
 auto before=uno_link.good_count;now_ms+=50;feed(packet(5));
 check(uno_link.good_count==before+1 && uv3_crc_ok(reply.data()),"STOP reply continues after loss of power");
 check(uno_link.first_current_faults==4 && uno_link.first_uart_errors==0 && reply[9]!=0,"undervoltage visible separately from UART");
 check(peer::g_mc_diagnostics.valid && peer::g_mc_diagnostics.current_faults==4 && peer::g_mc_diagnostics.uart_errors==0 && peer::g_bp_vdc==10,"Uno receives real undervoltage diagnostic reply");
 check(uno_transport.fault==UV3_WAIT && !uno_link.command_enabled,"power loss does not invent transport failure");
 mc_fault=0;motor_state=FAULT_OVER;bus_v=310;now_ms+=4000;feed(packet(6,1,3,5000));
 check(starts==1 && uno_link.fault_latched,"power restoration never silently restarts");
 for(unsigned pos=0;pos<UV3_FRAME;++pos) {
  running();now_ms+=50;auto damaged=packet(5,1,3,6000);
  for(unsigned i=0;i<UV3_FRAME;++i)if(i!=pos)uno_consume_sample(damaged[i],0);
  now_ms+=50;feed(packet(6,1,3,6000));
  check(!uno_link.fault_latched && uno_link.last_seq==6,"one deleted byte resynchronizes next command");
  running();now_ms+=50;damaged=packet(5,1,3,6000);
  for(unsigned i=0;i<UV3_FRAME;++i){if(i==pos)uno_consume_sample(0x42,0);uno_consume_sample(damaged[i],0);}
  now_ms+=50;feed(packet(6,1,3,6000));
  check(!uno_link.fault_latched && uno_link.last_seq==6,"one inserted byte resynchronizes next command");
 }
 // Partial packets never feed either watchdog; next clean packet may recover.
 running();auto f=packet(5,1,3,5000);for(unsigned i=0;i<12;++i)uno_consume_sample(f[i],0);
 last=uno_transport.last_valid_ms;now_ms+=16;uno_link_poll();
 check(!uno_link.fault_latched && uno_transport.last_valid_ms==last,"partial packet expires without feeding watchdog");
 now_ms+=34;feed(packet(6,1,3,5000));check(!uno_link.fault_latched,"clean recovery after partial deadline");
 // Noise on CLEAR may never acknowledge a physical/transport fault.
 running();uno_latch_fault_reason(UNO_FAULT_ESTOP,UNO_DIAG_ESTOP);
 now_ms+=50;feed(packet(5,8,0,0),6);check(uno_link.fault_latched,"noisy CLEAR cannot release latch");
 now_ms+=50;feed(packet(6,8,0,0));check(!uno_link.fault_latched && !uno_link.command_enabled,"clean explicit CLEAR releases without START");
 // Timer wrap and sequence wrap retain the same recovery semantics.
 reset(true,252,UINT32_MAX-300);now_ms+=50;feed(packet(255,1,3,5000));
 now_ms+=50;bad=packet(0,1,3,6000);bad[8]^=1;feed(bad);
 now_ms+=50;feed(packet(1,1,3,6000));check(!uno_link.fault_latched,"loss across sequence/time wrap");
 std::printf("{\"pass\":true,\"assertions\":%u,\"single_bit_corruptions\":%u,\"ne_byte_positions\":%u,\"hardware_commands\":0}\n",tests,UV3_FRAME*8,UV3_FRAME);
}
int main(){run();}
