// Arduino UNO Q motor control sketch (UART protocol via msgpack RPC)
// Target: arduino:zephyr:unoq (STM32U585)
//
// IMPORTANT (UNOQ): /dev/ttyHS1 on the Linux side is the control link to the MCU.
// The safest way is to use our msgpack RPC implementation on Serial1 and let
// arduino-router expose it to the HTTP UI.
#define USE_ROUTER_BRIDGE 0
#define USE_MSGPACK_RPC 1
#include <Arduino.h>
#include <Arduino_LED_Matrix.h>
#include <SPI.h>
#if USE_ROUTER_BRIDGE
#include <Arduino_RouterBridge.h>
#endif
#if defined(ARDUINO_ARCH_ZEPHYR)
#include <zephyr/kernel.h>
#endif
#include "id_ref_lut_motor1.h"

#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include "uno_q_control.h"
#if USE_ROUTER_BRIDGE
#define LOG_SERIAL Monitor
#elif USE_MSGPACK_RPC
// Router RPC link to the Linux side (/dev/ttyHS1).
#define LOG_SERIAL Serial1
#else
#define LOG_SERIAL Serial
#endif
// Serial1 is reserved for the Linux control link (/dev/ttyHS1).
// Use Serial (D0/D1) for the Blue Pill link.
#define NUCLEO_SERIAL Serial
#define UI_SERIAL Serial1
#define RPC_BAUD 115200
#define UART_ECHO_TEST 0
#define PIN_TOGGLE_TEST 0
// ----------------------- Pins -----------------------
// PWM pins for IPM (6 signals)
// J2: 3=PWM-1H, 5=PWM-1L, 7=PWM-2H, 9=PWM-2L, 11=PWM-3H, 13=PWM-3L
static const uint8_t PWM_UH_PIN = 3;   // D3  (TIM3_CH3) -> PWM-1H
static const uint8_t PWM_UL_PIN = 5;   // D5  (TIM1_CH4) -> PWM-1L (invert in overlay)
static const uint8_t PWM_VH_PIN = 6;   // D6  (TIM3_CH4) -> PWM-2H
static const uint8_t PWM_VL_PIN = 8;   // D8  (TIM3_CH1) -> PWM-2L (enable PWM)
static const uint8_t PWM_WH_PIN = 9;   // D9  (TIM4_CH3) -> PWM-3H
static const uint8_t PWM_WL_PIN = 10;  // D10 (TIM4_CH4) -> PWM-3L (invert in overlay)
static const bool PWM_LOW_INVERTED = true;
// Safety mode: drive only high-side PWM, keep low-sides OFF to avoid shoot-through.
static const bool PWM_THREE_PWM_MODE = true;
// External PWM bridge to Nucleo (SPI/UART) for hardware dead-time + complementary outputs.
static const bool USE_EXTERNAL_PWM = true;
static const bool USE_NUCLEO_SPI = false;
static const bool FORCE_SPI_BITBANG = false;
static const bool USE_NUCLEO_UART_FALLBACK = true;
static const uint32_t NUCLEO_UART_BAUD = 460800;
static const uint32_t NUCLEO_HEARTBEAT_MS = 50;
// Keep the UNO Q Zephyr Serial TX path comfortably below line rate.
// 20 bytes at 460800 baud takes ~0.43 ms on the wire; 2 ms gives headroom for
// scheduler jitter and prevents partial-frame drops that become CRC errors.
static const uint32_t NUCLEO_RUN_MIN_SEND_US = 2000;
static const uint32_t NUCLEO_RUN_REPLY_GUARD_US = 4000;
// Blue Pill UART protocol (see bluepill_uart_pwm_pio/include/proto.h)
static const uint8_t BP_VER = 0x01;
static const uint8_t BP_FLAG_ENABLE = 0x01;
static const uint8_t BP_FLAG_ESTOP = 0x02;
static const uint8_t BP_FLAG_DIAG_PWM = 0x04;
static const uint8_t BP_FLAG_CLEAR_FAULT = 0x08;
static const uint8_t BP_FLAG_VECTOR_ROTATE = 0x10;
static const uint8_t BP_MODE_OFF = 0;
static const uint8_t BP_MODE_DIAG = 1;
static const uint8_t BP_MODE_DUTY = 2;
static const uint8_t BP_MODE_SCALAR = 3;
static const uint8_t BP_MODE_VECTOR = 4;
static const uint8_t BP_MODE_FOC = 5;
static const uint8_t BP_EXT_NTC = 0x01;
static const uint8_t BP_EXT_PFC = 0x02;
static const uint8_t BP_EXT_BRAKE_PWM = 0x04;
// Calibrated from HV bus measurement: raw=3256 was 315 V on the meter.
static const float BP_VBUS_FULL_SCALE_V = 396.1f;
static const uint32_t BP_VBUS_STALE_MS = 500;
// SPI pins for UNOQ header
static const uint8_t NUCLEO_SPI_CS = 10;   // D10
static const uint8_t NUCLEO_SPI_SCK = 13;  // D13
static const uint8_t NUCLEO_SPI_MOSI = 11; // D11
static const uint8_t NUCLEO_SPI_MISO = 12; // D12
static SPISettings g_spi_settings(1000000, MSBFIRST, SPI_MODE0);
static const uint8_t PWM_MAX = 255;
static const uint16_t PWM_FULL = PWM_MAX + 1;
// Button input (external button to GND), internal pull-up enabled
static const uint8_t BUTTON_PIN = 2; // D2
// LED
static const uint8_t LED_PIN = LED_BUILTIN;
// Brake / enable output (to inverter brake/enable input)
static const uint8_t BRAKE_PIN = 4; // D4
static const bool BRAKE_ACTIVE_HIGH = true;
// Analog pins for sensing (optional)
static const uint8_t ADC_VDC_PIN = A0;
static const uint8_t ADC_IA_PIN  = A1;
static const uint8_t ADC_IB_PIN  = A2;
static const uint8_t ADC_IC_PIN  = A3;
static const bool USE_IC_SENSOR = true;
// ----------------------- Control constants -----------------------
static const uint32_t CONTROL_HZ = 1000;                  // 1 kHz control loop (PWM stays 10 kHz)
static const uint32_t CONTROL_US = 1000000UL / CONTROL_HZ;
static const uint32_t TELEMETRY_MS = 20;                  // 50 Hz telemetry
#define LOG_TELEMETRY_DATA 0
static const float POLE_PAIRS = 2.0f;
static const float VDC_NOMINAL = 24.0f;
static const float VDC_ADC_VREF = 3.3f;
static const float VDC_ADC_DIVIDER = 11.0f;
static const float VDC_ADC_MIN_V = 5.0f;
static const float VDC_ADC_MAX_V = 60.0f;
static const float CURRENT_GAIN_A_PER_LSB = 0.004f;
static const float ADC_OFFSET_DEFAULT = 2048.0f;
static const uint32_t OFFSET_CAL_SAMPLES = 1024;
static const float DUTY_MIN = 0.03f;
static const float DUTY_MAX = 0.97f;
static const float PWM_DEADTIME_DUTY = 0.02f;
static const float ALIGN_TIME_MS = 400.0f;
static const float ALIGN_ID_REF_A = 1.0f;
static const float RUN_ID_REF_A = 1.0f;
static const float RUN_IQ_REF_A = 1.5f;
static const float IQ_RAMP_A_PER_S = 5.0f;
static const float FREQ_RAMP_HZ_PER_S = 5.0f; // scalar open-loop startup must not outrun the rotor
static const float CONTROL_DT = 1.0f / CONTROL_HZ;
static const float IQ_RAMP_STEP = IQ_RAMP_A_PER_S * CONTROL_DT;
static const float FREQ_RAMP_STEP = FREQ_RAMP_HZ_PER_S * CONTROL_DT;
static const float MIC_FREQ_TOL_HZ = 0.2f;
static const float MIC_FREQ_TOL_REL = 0.05f;
static const float MIC_FREQ_MIN_HZ = 1.0f;
static const float MIC_IQ_NOM_A = RUN_IQ_REF_A;
static const float MIC_ID_MIN_A = 0.5f * RUN_ID_REF_A;
static const float MIC_ID_MAX_A = 1.2f * RUN_ID_REF_A;
static const float MIC_ID_RATE_LIMIT_A_PER_S = 0.8f;
static const uint32_t MIC_ENC_STALE_MS = 500;
static const float MIC_SLIP_GATE_HZ = 0.5f;
static const float MIC_SLIP_GATE_REL = 0.02f;
static const float MIC_RS = 3.2f;
static const float MIC_LM = 0.25f;
static const float MIC_K_FE = 1e-4f;
static const float MIC_K_SW = 1e-5f;
static const float MIC_F_SW = 10000.0f;
static const uint32_t MODE_SWITCH_DEADTIME_MS = 500;
// ESTOP must stay latched until an explicit CLEAR/ESTOP CLEAR command.
static const uint32_t ESTOP_AUTO_CLEAR_MS = 0;
static const uint32_t BP_REPLY_TIMEOUT_MS = 500;
static const float CURRENT_LIMIT_A = 6.0f;
static const float VF_BASE_FREQ_HZ = 50.0f;
static const float VF_VOLT_PER_HZ_RATIO = 0.5f;
// Low-frequency scalar boost: enough startup voltage to overcome stiction
// without changing the high-frequency V/Hz slope.
static const float VF_START_BOOST_V = 24.0f;
static const float VF_START_BOOST_TAPER_HZ = 10.0f;
static const float VF_START_BOOST_MIN_FREQ_HZ = 0.1f;
static const float CTRL_PI = 3.1415926f;
static const float CTRL_TWO_PI = 6.2831852f;
static const float INV_SQRT3 = 0.5773503f;
// ----------------------- Types -----------------------
typedef enum {
  STATE_SAFE = 0,
  STATE_VF_RUN,
  STATE_FOC_ALIGN,
  STATE_FOC_RUN,
  STATE_FAULT
} ControlState;
typedef enum {
  MODE_VF = 0,
  MODE_FOC,
  MODE_MIC
} ControlMode;
typedef struct {
  float kp;
  float ki;
  float integrator;
  float out_min;
  float out_max;
} PIController;
static void pwm_force_off();
static void schedule_mode_switch(ControlMode next_mode, bool restart_after_switch);
static void request_mode(ControlMode next_mode, bool duty_mode, bool diag_pwm);
static void matrix_init();
static void matrix_update();
static void matrix_set_pixel(int x, int y);
static void matrix_draw_digit(int x0, int y0, int digit);
static void hard_stop(bool clear_cmd);
static void nucleo_uart_init();
static void nucleo_send_pwm(float d_u, float d_v, float d_w, bool enable, bool force = false);
static void nucleo_send_stop(bool force = false);
// ----------------------- Globals -----------------------
static ControlState g_state = STATE_SAFE;
static ControlMode g_mode = MODE_FOC;
static ControlMode g_mode_pending = MODE_FOC;
static bool g_mode_change_pending = false;
static bool g_pwm_enabled = false;
static bool g_pwm_outputs_active = false;
static bool g_pwm_forced_gpio = false;
static bool g_stop_requested = false;
static bool g_start_req = false;
static bool g_stop_req = false;
static bool g_toggle_req = false;
static float g_vdc = VDC_NOMINAL;
static float g_v_limit = 12.0f;
static float g_vf_v_per_hz = 0.0f;
static float g_vf_volt_per_hz_ratio = VF_VOLT_PER_HZ_RATIO;
static float g_vf_start_boost_v = VF_START_BOOST_V;
static float g_theta = 0.0f;
static float g_omega_ref = 0.0f;
static float g_freq_cmd = 0.0f;
static float g_freq_ref = 0.0f;
static float g_id_ref = 0.0f;
static float g_iq_ref = 0.0f;
static float g_id_target = 0.0f;
static float g_iq_target = 0.0f;
static float g_offset_a = ADC_OFFSET_DEFAULT;
static float g_offset_b = ADC_OFFSET_DEFAULT;
static float g_offset_c = ADC_OFFSET_DEFAULT;
static uint32_t g_offset_count = 0;
static float g_offset_acc_a = 0.0f;
static float g_offset_acc_b = 0.0f;
static float g_offset_acc_c = 0.0f;
static bool g_offset_ready = false;
static PIController g_pi_id;
static PIController g_pi_iq;
static uint32_t g_align_ticks = 0;
static uint32_t g_last_control_us = 0;
static uint32_t g_last_telem_ms = 0;
static uint32_t g_last_button_ms = 0;
static bool g_led_on = false;
static uint32_t g_led_tick = 0;
static uint32_t g_link_led_ms = 0;
static bool g_link_led_state = false;
static uint32_t g_nucleo_last_rx_ms = 0;
static uint16_t g_nucleo_rx_good = 0;
static uint16_t g_nucleo_rx_bad = 0;
static uint32_t g_nucleo_last_tx_ms = 0;
static uint16_t g_bp_enc_raw = 0;
static bool g_bp_enc_ok = false;
static uint32_t g_bp_enc_ms = 0;
// Encoder speed estimate computed on UNOQ from Blue Pill AS5600 samples.
// Units: RPM is mechanical (shaft) rpm. Electrical Hz assumes POLE_PAIRS.
static float g_enc_rpm = 0.0f;
static float g_enc_mech_hz = 0.0f;
static float g_enc_elec_hz = 0.0f;
static bool g_enc_speed_valid = false;
static uint16_t g_enc_prev_raw = 0;
static uint32_t g_enc_prev_ms = 0;
static int32_t g_enc_accum_counts = 0;
static uint32_t g_enc_accum_ms = 0;
// Blue Pill reply fields (decoded from the UART reply frame).
static uint8_t g_bp_status = 0;
static uint8_t g_bp_fault_code = 0;
static uint8_t g_bp_last_mode = 0;
static uint8_t g_bp_ext_flags = 0;
static uint16_t g_bp_brake_q15 = 0;
static uint16_t g_bp_vbus_raw = 0;
static float g_bp_vdc = 0.0f;
static uint32_t g_bp_vbus_ms = 0;
static uint16_t g_bp_good_cnt = 0;
static uint16_t g_bp_bad_cnt = 0;
static uint8_t g_bp_last_seq = 0;
static uint32_t g_bp_last_rsp_ms = 0;
// Blue Pill boot ping (0x5A 0xA5 ...) detector, helps diagnose wiring/baud before the link is up.
static uint32_t g_bp_ping_pairs = 0;
static uint32_t g_bp_ping_ms = 0;
static uint8_t g_bp_ping_prev = 0;
static const bool SELFTEST_ON_BOOT = false;
static uint8_t g_selftest_step = 0;
static uint32_t g_selftest_ms = 0;
static bool g_scope_test = false;
static bool g_scope_u = false;
static bool g_scope_v = false;
static bool g_scope_w = false;
static uint32_t g_scope_last_u_us = 0;
static uint32_t g_scope_last_v_us = 0;
static uint32_t g_scope_last_w_us = 0;
static bool g_pwm_test = false;
static float g_pwm_test_duty = 0.5f;
static bool g_diag_pwm = false;
static bool g_duty_mode = false;
static float g_duty_u = 0.2f;
static float g_duty_v = 0.4f;
static float g_duty_w = 0.6f;
static char g_line_buf[96];
static uint8_t g_line_len = 0;
static char g_line_buf_ui[96];
static uint8_t g_line_len_ui = 0;
static ControlState g_last_state = STATE_SAFE;
static uint8_t g_last_fault = 0;
static bool g_last_pwm = false;
static uint32_t g_last_reg_ms = 0;
static float g_last_ia = 0.0f;
static float g_last_ib = 0.0f;
static float g_last_ic = 0.0f;
static float g_last_id = 0.0f;
static float g_last_iq = 0.0f;
static float g_last_i_rms = 0.0f;
static float g_last_vd = 0.0f;
static float g_last_vq = 0.0f;
static uint8_t g_fault = 0;
static bool g_mic_active = false;
static float g_mic_id_ref = RUN_ID_REF_A;
static float g_mic_saving_pct = 0.0f;
static float g_mic_p_loss = 0.0f;
static float g_mic_p_loss_base = 0.0f;
static int16_t g_mic_id_ref_q10 = (int16_t)(RUN_ID_REF_A * 1024.0f);
static uint8_t g_mic_gated = 0;
static uint8_t g_mic_enable_ai = 0;
static bool g_mic_enc_used = false;
static float g_mic_freq_meas_hz = 0.0f;
static float g_mic_speed_err_hz = 0.0f;
static float g_mic_speed_tol_hz = 0.0f;
static uint16_t g_mic_link_flags = 0u;
static uint16_t g_mic_status_flags = 0u;
static bool g_estop_latched = false;
static uint32_t g_estop_auto_clear_deadline_ms = 0;
static bool g_mode_switch_pending = false;
static uint32_t g_mode_switch_deadline_ms = 0;
static bool g_restart_after_mode_switch = false;
static float g_last_nonzero_freq = 10.0f;
static bool g_last_mic_active = false;
static bool g_brake_on = false;
static uint8_t g_ext_flags = 0;
static uint16_t g_brake_q15 = 0;
static bool g_clear_fault_req = false;
static uint8_t g_nucleo_seq = 0;
static uint32_t g_nucleo_last_send_ms = 0;
static uint32_t g_nucleo_last_send_us = 0;
static bool g_nucleo_waiting_rsp = false;
static uint8_t g_nucleo_waiting_seq = 0;
static uint32_t g_nucleo_last_ack_us = 0;
static uint32_t g_nucleo_keepalive_ms = 0;
static uint32_t g_uart_bridge_ms = 0;
static Arduino_LED_Matrix g_matrix;
static bool g_matrix_ready = false;
static uint32_t g_matrix_last_ms = 0;
static uint8_t g_matrix_pixels[104];
static uint32_t g_matrix_frame[4];
static const uint8_t MATRIX_W = 13;
static const uint8_t MATRIX_H = 8;
static const uint8_t DIGIT_3X5[10][5] = {
  {0x7, 0x5, 0x5, 0x5, 0x7},
  {0x2, 0x6, 0x2, 0x2, 0x7},
  {0x7, 0x1, 0x7, 0x4, 0x7},
  {0x7, 0x1, 0x7, 0x1, 0x7},
  {0x5, 0x5, 0x7, 0x1, 0x1},
  {0x7, 0x4, 0x7, 0x1, 0x7},
  {0x7, 0x4, 0x7, 0x5, 0x7},
  {0x7, 0x1, 0x2, 0x2, 0x2},
  {0x7, 0x5, 0x7, 0x5, 0x7},
  {0x7, 0x5, 0x7, 0x1, 0x7}
};
#if USE_ROUTER_BRIDGE
static bool g_bridge_ready = false;
static bool g_bridge_cmd_ready = false;
static bool g_bridge_get_ready = false;
static bool g_monitor_ready = false;
static uint32_t g_bridge_last_ms = 0;
#endif
// ----------------------- MsgPack RPC -----------------------
#define RX_BUF_SIZE 256
#define TX_BUF_SIZE 256
static uint8_t g_rx_buf[RX_BUF_SIZE];
static size_t g_rx_len = 0;
static uint8_t g_tx_buf[TX_BUF_SIZE];
static size_t g_tx_len = 0;
static int32_t g_rpc_msgid = 1;
static void mp_tx_reset(void) {
  g_tx_len = 0;
}
static bool mp_tx_u8(uint8_t v) {
  if (g_tx_len >= TX_BUF_SIZE) {
    return false;
  }
  g_tx_buf[g_tx_len++] = v;
  return true;
}
static bool mp_tx_bytes(const void *data, size_t len) {
  if ((g_tx_len + len) > TX_BUF_SIZE) {
    return false;
  }
  memcpy(&g_tx_buf[g_tx_len], data, len);
  g_tx_len += len;
  return true;
}
static bool mp_tx_u16(uint16_t v) {
  uint8_t b[2];
  b[0] = (uint8_t)((v >> 8) & 0xFF);
  b[1] = (uint8_t)(v & 0xFF);
  return mp_tx_bytes(b, 2);
}
static bool mp_tx_u32(uint32_t v) {
  uint8_t b[4];
  b[0] = (uint8_t)((v >> 24) & 0xFF);
  b[1] = (uint8_t)((v >> 16) & 0xFF);
  b[2] = (uint8_t)((v >> 8) & 0xFF);
  b[3] = (uint8_t)(v & 0xFF);
  return mp_tx_bytes(b, 4);
}
static bool mp_tx_int(int32_t v) {
  if (v >= 0 && v <= 127) {
    return mp_tx_u8((uint8_t)v);
  }
  if (v >= -32 && v < 0) {
    return mp_tx_u8((uint8_t)v);
  }
  if (v >= -128 && v <= 127) {
    if (!mp_tx_u8(0xD0)) return false;
    return mp_tx_u8((uint8_t)v);
  }
  if (v >= -32768 && v <= 32767) {
    if (!mp_tx_u8(0xD1)) return false;
    return mp_tx_u16((uint16_t)v);
  }
  if (!mp_tx_u8(0xD2)) return false;
  return mp_tx_u32((uint32_t)v);
}
static bool mp_tx_bool(bool v) {
  return mp_tx_u8(v ? 0xC3 : 0xC2);
}
static bool mp_tx_nil(void) {
  return mp_tx_u8(0xC0);
}
static bool mp_tx_float(float f) {
  union { float f; uint32_t u; } u;
  u.f = f;
  if (!mp_tx_u8(0xCA)) return false;
  return mp_tx_u32(u.u);
}
static bool mp_tx_array(uint32_t n) {
  if (n < 16) {
    return mp_tx_u8(0x90 | (uint8_t)n);
  }
  if (n < 65536) {
    if (!mp_tx_u8(0xDC)) return false;
    return mp_tx_u16((uint16_t)n);
  }
  return false;
}
static bool mp_tx_str(const char *s) {
  size_t n = strlen(s);
  if (n < 32) {
    if (!mp_tx_u8(0xA0 | (uint8_t)n)) return false;
    return mp_tx_bytes(s, n);
  }
  if (n < 256) {
    if (!mp_tx_u8(0xD9)) return false;
    if (!mp_tx_u8((uint8_t)n)) return false;
    return mp_tx_bytes(s, n);
  }
  return false;
}
static void mp_tx_send(void) {
  if (g_tx_len > 0) {
    LOG_SERIAL.write(g_tx_buf, g_tx_len);
  }
}

static bool mp_rx_u8(const uint8_t *buf, size_t len, size_t *idx, uint8_t *out) {
  if (*idx >= len) return false;
  *out = buf[(*idx)++];
  return true;
}
static bool mp_rx_u16(const uint8_t *buf, size_t len, size_t *idx, uint16_t *out) {
  if ((*idx + 1) >= len) return false;
  uint16_t v = ((uint16_t)buf[*idx] << 8) | buf[*idx + 1];
  *idx += 2;
  *out = v;
  return true;
}
static bool mp_rx_u32(const uint8_t *buf, size_t len, size_t *idx, uint32_t *out) {
  if ((*idx + 3) >= len) return false;
  uint32_t v = ((uint32_t)buf[*idx] << 24) | ((uint32_t)buf[*idx + 1] << 16) |
               ((uint32_t)buf[*idx + 2] << 8) | buf[*idx + 3];
  *idx += 4;
  *out = v;
  return true;
}
static bool mp_rx_int(const uint8_t *buf, size_t len, size_t *idx, int32_t *out) {
  if (*idx >= len) return false;
  uint8_t t = buf[*idx];
  if (t <= 0x7F) {
    *out = t;
    (*idx)++;
    return true;
  }
  if (t >= 0xE0) {
    *out = (int8_t)t;
    (*idx)++;
    return true;
  }
  (*idx)++;
  if (t == 0xD0) {
    if (*idx >= len) return false;
    *out = (int8_t)buf[*idx];
    (*idx)++;
    return true;
  }
  if (t == 0xD1) {
    uint16_t v;
    if (!mp_rx_u16(buf, len, idx, &v)) return false;
    *out = (int16_t)v;
    return true;
  }
  if (t == 0xD2) {
    uint32_t v;
    if (!mp_rx_u32(buf, len, idx, &v)) return false;
    *out = (int32_t)v;
    return true;
  }
  if (t == 0xCC) {
    if (*idx >= len) return false;
    *out = buf[(*idx)++];
    return true;
  }
  if (t == 0xCD) {
    uint16_t v;
    if (!mp_rx_u16(buf, len, idx, &v)) return false;
    *out = v;
    return true;
  }
  if (t == 0xCE) {
    uint32_t v;
    if (!mp_rx_u32(buf, len, idx, &v)) return false;
    *out = (int32_t)v;
    return true;
  }
  return false;
}
static bool mp_rx_array(const uint8_t *buf, size_t len, size_t *idx, uint32_t *out) {
  if (*idx >= len) return false;
  uint8_t t = buf[*idx];
  if ((t & 0xF0) == 0x90) {
    *out = (uint32_t)(t & 0x0F);
    (*idx)++;
    return true;
  }
  (*idx)++;
  if (t == 0xDC) {
    uint16_t v;
    if (!mp_rx_u16(buf, len, idx, &v)) return false;
    *out = v;
    return true;
  }
  if (t == 0xDD) {
    uint32_t v;
    if (!mp_rx_u32(buf, len, idx, &v)) return false;
    *out = v;
    return true;
  }
  return false;
}
static bool mp_rx_map(const uint8_t *buf, size_t len, size_t *idx, uint32_t *out) {
  if (*idx >= len) return false;
  uint8_t t = buf[*idx];
  if ((t & 0xF0) == 0x80) {
    *out = (uint32_t)(t & 0x0F);
    (*idx)++;
    return true;
  }
  (*idx)++;
  if (t == 0xDE) {
    uint16_t v;
    if (!mp_rx_u16(buf, len, idx, &v)) return false;
    *out = v;
    return true;
  }
  if (t == 0xDF) {
    uint32_t v;
    if (!mp_rx_u32(buf, len, idx, &v)) return false;
    *out = v;
    return true;
  }
  return false;
}
static bool mp_rx_str(const uint8_t *buf, size_t len, size_t *idx, char *out, size_t out_len) {
  if (*idx >= len) return false;
  uint8_t t = buf[*idx];
  uint32_t n = 0;
  if ((t & 0xE0) == 0xA0) {
    n = (uint32_t)(t & 0x1F);
    (*idx)++;
  } else {
    (*idx)++;
    if (t == 0xD9) {
      if (*idx >= len) return false;
      n = buf[(*idx)++];
    } else if (t == 0xDA) {
      uint16_t v;
      if (!mp_rx_u16(buf, len, idx, &v)) return false;
      n = v;
    } else if (t == 0xDB) {
      uint32_t v;
      if (!mp_rx_u32(buf, len, idx, &v)) return false;
      n = v;
    } else if (t == 0xC4) { // bin8
      if (*idx >= len) return false;
      n = buf[(*idx)++];
    } else if (t == 0xC5) { // bin16
      uint16_t v;
      if (!mp_rx_u16(buf, len, idx, &v)) return false;
      n = v;
    } else if (t == 0xC6) { // bin32
      uint32_t v;
      if (!mp_rx_u32(buf, len, idx, &v)) return false;
      n = v;
    } else {
      return false;
    }
  }
  if ((*idx + n) > len) return false;
  uint32_t copy = (n < (out_len - 1)) ? n : (out_len - 1);
  memcpy(out, &buf[*idx], copy);
  out[copy] = '\0';
  *idx += n;
  return true;
}
static bool mp_rx_cmd_string(const uint8_t *buf, size_t len, size_t *idx, char *out, size_t out_len);
static bool mp_skip(const uint8_t *buf, size_t len, size_t *idx);
static bool mp_skip_array(const uint8_t *buf, size_t len, size_t *idx, uint32_t count) {
  for (uint32_t i = 0; i < count; i++) {
    if (!mp_skip(buf, len, idx)) return false;
  }
  return true;
}
static bool mp_skip_map(const uint8_t *buf, size_t len, size_t *idx, uint32_t count) {
  for (uint32_t i = 0; i < count; i++) {
    if (!mp_skip(buf, len, idx)) return false; // key
    if (!mp_skip(buf, len, idx)) return false; // value
  }
  return true;
}
static bool mp_skip(const uint8_t *buf, size_t len, size_t *idx) {
  if (*idx >= len) return false;
  uint8_t t = buf[(*idx)++];
  if (t <= 0x7F || t >= 0xE0) {
    return true;
  }
  if ((t & 0xE0) == 0xA0) {
    uint32_t n = (uint32_t)(t & 0x1F);
    if ((*idx + n) > len) return false;
    *idx += n;
    return true;
  }
  if (t == 0xC4) { // bin8
    if (*idx >= len) return false;
    uint32_t n = buf[(*idx)++];
    if ((*idx + n) > len) return false;
    *idx += n;
    return true;
  }
  if (t == 0xC5) { // bin16
    uint16_t n;
    if (!mp_rx_u16(buf, len, idx, &n)) return false;
    if ((*idx + n) > len) return false;
    *idx += n;
    return true;
  }
  if (t == 0xC6) { // bin32
    uint32_t n;
    if (!mp_rx_u32(buf, len, idx, &n)) return false;
    if ((*idx + n) > len) return false;
    *idx += n;
    return true;
  }
  if ((t & 0xF0) == 0x90) {
    uint32_t n = (uint32_t)(t & 0x0F);
    return mp_skip_array(buf, len, idx, n);
  }
  if ((t & 0xF0) == 0x80) {
    uint32_t n = (uint32_t)(t & 0x0F);
    return mp_skip_map(buf, len, idx, n);
  }
  if (t == 0xCC || t == 0xD0) {
    if (*idx >= len) return false;
    (*idx)++;
    return true;
  }
  if (t == 0xCD || t == 0xD1) {
    if ((*idx + 1) >= len) return false;
    *idx += 2;
    return true;
  }
  if (t == 0xCE || t == 0xD2 || t == 0xCA) {
    if ((*idx + 3) >= len) return false;
    *idx += 4;
    return true;
  }
  if (t == 0xCB) {
    if ((*idx + 7) >= len) return false;
    *idx += 8;
    return true;
  }
  if (t == 0xC0 || t == 0xC2 || t == 0xC3) {
    return true;
  }
  if (t == 0xD9) {
    if (*idx >= len) return false;
    uint32_t n = buf[(*idx)++];
    if ((*idx + n) > len) return false;
    *idx += n;
    return true;
  }
  if (t == 0xDA) {
    uint16_t n;
    if (!mp_rx_u16(buf, len, idx, &n)) return false;
    if ((*idx + n) > len) return false;
    *idx += n;
    return true;
  }
  if (t == 0xDB) {
    uint32_t n;
    if (!mp_rx_u32(buf, len, idx, &n)) return false;
    if ((*idx + n) > len) return false;
    *idx += n;
    return true;
  }
  if (t == 0xDC) {
    uint16_t n;
    if (!mp_rx_u16(buf, len, idx, &n)) return false;
    return mp_skip_array(buf, len, idx, n);
  }
  if (t == 0xDD) {
    uint32_t n;
    if (!mp_rx_u32(buf, len, idx, &n)) return false;
    return mp_skip_array(buf, len, idx, n);
  }
  if (t == 0xDE) {
    uint16_t n;
    if (!mp_rx_u16(buf, len, idx, &n)) return false;
    return mp_skip_map(buf, len, idx, n);
  }
  if (t == 0xDF) {
    uint32_t n;
    if (!mp_rx_u32(buf, len, idx, &n)) return false;
    return mp_skip_map(buf, len, idx, n);
  }
  return false;
}
static bool mp_rx_cmd_string(const uint8_t *buf, size_t len, size_t *idx, char *out, size_t out_len) {
  if (*idx >= len) return false;
  size_t start = *idx;
  if (mp_rx_str(buf, len, idx, out, out_len)) {
    return true;
  }
  // Reset and try container types.
  *idx = start;
  uint8_t t = buf[*idx];
  // Array: try first element as string, then skip the rest.
  if ((t & 0xF0) == 0x90 || t == 0xDC || t == 0xDD) {
    uint32_t n = 0;
    if (!mp_rx_array(buf, len, idx, &n)) return false;
    bool ok = false;
    if (n > 0) {
      ok = mp_rx_cmd_string(buf, len, idx, out, out_len);
      for (uint32_t i = 1; i < n; i++) {
        if (!mp_skip(buf, len, idx)) {
          *idx = len;
          break;
        }
      }
    }
    return ok;
  }
  // Map: accept {"cmd": "..."} as a convenience.
  if ((t & 0xF0) == 0x80 || t == 0xDE || t == 0xDF) {
    uint32_t n = 0;
    if (!mp_rx_map(buf, len, idx, &n)) return false;
    bool found = false;
    for (uint32_t i = 0; i < n; i++) {
      char key[16];
      size_t k0 = *idx;
      if (!mp_rx_str(buf, len, idx, key, sizeof(key))) {
        *idx = k0;
        if (!mp_skip(buf, len, idx)) { *idx = len; break; }
        if (!mp_skip(buf, len, idx)) { *idx = len; break; }
        continue;
      }
      if (strcmp(key, "cmd") == 0) {
        found = mp_rx_str(buf, len, idx, out, out_len);
        if (!found) {
          // Consume value even if we couldn't decode it as a string.
          (void)mp_skip(buf, len, idx);
        }
      } else {
        if (!mp_skip(buf, len, idx)) { *idx = len; break; }
      }
    }
    return found;
  }

  // Unknown type: consume it and report failure.
  if (!mp_skip(buf, len, idx)) {
    *idx = len;
  }
  return false;
}
static void rpc_send_response_bool(int32_t msgid, bool ok) {
  mp_tx_reset();
  mp_tx_array(4);
  mp_tx_int(1);       // response
  mp_tx_int(msgid);
  mp_tx_nil();
  mp_tx_bool(ok);
  mp_tx_send();
}
static void rpc_send_response_error(int32_t msgid, const char *err) {
  mp_tx_reset();
  mp_tx_array(4);
  mp_tx_int(1);
  mp_tx_int(msgid);
  mp_tx_str(err);
  mp_tx_nil();
  mp_tx_send();
}
static void rpc_send_response_get(int32_t msgid) {
  float ia = g_last_ia;
  float ib = g_last_ib;
  float ic = g_last_ic;
  mp_tx_reset();
  mp_tx_array(4);
  mp_tx_int(1);
  mp_tx_int(msgid);
  mp_tx_nil();
  // Keep this in sync with web_hmi/server.py (array result mapping).
  mp_tx_array(50);
  mp_tx_int((int32_t)g_state);
  mp_tx_int((int32_t)g_mode);
  mp_tx_int(g_pwm_enabled ? 1 : 0);
  mp_tx_float(g_freq_ref);
  mp_tx_float((g_freq_ref * 60.0f) / POLE_PAIRS);
  mp_tx_float(ia);
  mp_tx_float(ib);
  mp_tx_float(ic);
  mp_tx_float(g_vdc);
  mp_tx_float(g_last_id);
  mp_tx_float(g_last_iq);
  mp_tx_float(g_last_i_rms);
  mp_tx_int(g_mic_active ? 1 : 0);
  mp_tx_float(g_mic_id_ref);
  mp_tx_float(g_mic_saving_pct);
  mp_tx_float(g_freq_cmd);
  mp_tx_int(g_estop_latched ? 1 : 0);
  mp_tx_int((g_ext_flags & BP_EXT_NTC) ? 1 : 0);
  mp_tx_int((g_ext_flags & BP_EXT_PFC) ? 1 : 0);
  mp_tx_int((g_ext_flags & BP_EXT_BRAKE_PWM) ? 1 : 0);
  float brake = (g_ext_flags & BP_EXT_BRAKE_PWM) ? ((float)g_brake_q15 / 32767.0f) : 0.0f;
  mp_tx_float(brake);

  // Encoder telemetry (from Blue Pill reply)
  bool enc_recent = (uint32_t)(millis() - g_bp_enc_ms) < 500U;
  int enc_ok = (g_bp_enc_ok && enc_recent) ? 1 : 0;
  float enc_deg = ((float)g_bp_enc_raw * 360.0f) / 4096.0f;
  mp_tx_int((int32_t)g_bp_enc_raw);
  mp_tx_int(enc_ok);
  mp_tx_float(enc_deg);

  // Blue Pill link stats (UNOQ-side counters + ages).
  uint32_t bp_age = (g_nucleo_last_rx_ms == 0) ? 999999U : (uint32_t)(millis() - g_nucleo_last_rx_ms);
  mp_tx_int((int32_t)g_nucleo_rx_good);
  mp_tx_int((int32_t)g_nucleo_rx_bad);
  mp_tx_int((int32_t)bp_age);

  // Decoded fields from the last Blue Pill reply.
  mp_tx_int((int32_t)g_bp_status);
  mp_tx_int((int32_t)g_bp_fault_code);
  mp_tx_int((int32_t)g_bp_last_mode);
  mp_tx_int((int32_t)g_bp_last_seq);

  // Boot ping detector (0x5A 0xA5 ...) ages.
  uint32_t ping_age = (g_bp_ping_ms == 0) ? 999999U : (uint32_t)(millis() - g_bp_ping_ms);
  mp_tx_int((int32_t)g_bp_ping_pairs);
  mp_tx_int((int32_t)ping_age);

  uint32_t rsp_age = (g_bp_last_rsp_ms == 0) ? 999999U : (uint32_t)(millis() - g_bp_last_rsp_ms);
  mp_tx_int((int32_t)rsp_age);
  // Extended encoder telemetry (append-only).
  mp_tx_float(enc_ok ? g_enc_rpm : 0.0f);
  mp_tx_float(enc_ok ? g_enc_mech_hz : 0.0f);
  mp_tx_float(enc_ok ? g_enc_elec_hz : 0.0f);
  mp_tx_int((int32_t)g_mic_gated);
  mp_tx_int((int32_t)g_mic_enable_ai);
  mp_tx_int(g_mic_enc_used ? 1 : 0);
  mp_tx_float(g_mic_freq_meas_hz);
  mp_tx_float(g_mic_speed_err_hz);
  mp_tx_float(g_mic_speed_tol_hz);
  mp_tx_int((int32_t)g_mic_link_flags);
  mp_tx_int((int32_t)g_mic_status_flags);
  mp_tx_int(g_diag_pwm ? 1 : 0);
  mp_tx_int(g_duty_mode ? 1 : 0);
  uint32_t bp_vbus_age = (g_bp_vbus_ms == 0) ? 999999U : (uint32_t)(millis() - g_bp_vbus_ms);
  mp_tx_int((int32_t)g_bp_vbus_raw);
  mp_tx_float(g_bp_vdc);
  mp_tx_int((int32_t)bp_vbus_age);
  mp_tx_send();
}
static void rpc_send_register(const char *name) {
  mp_tx_reset();
  const int32_t msgid = g_rpc_msgid++;
  mp_tx_array(4);
  mp_tx_int(0);  // request
  mp_tx_int(msgid);
  mp_tx_str("$/register");
  mp_tx_array(1);
  mp_tx_str(name);
  mp_tx_send();
}
static void rpc_send_reset(void) {
  mp_tx_reset();
  mp_tx_array(3);
  mp_tx_int(2);
  mp_tx_str("$/reset");
  mp_tx_array(0);
  mp_tx_send();
}
static void rpc_send_mon_write(const char *line) {
  mp_tx_reset();
  mp_tx_array(3);
  mp_tx_int(2);
  mp_tx_str("mon/write");
  mp_tx_array(1);
  mp_tx_str(line);
  mp_tx_send();
}
static bool icmp(const char *a, const char *b) {
  while (*a && *b) {
    char ca = (char)tolower(*a++);
    char cb = (char)tolower(*b++);
    if (ca != cb) return false;
  }
  return (*a == '\0' && *b == '\0');
}
static bool starts_ci(const char *s, const char *prefix) {
  while (*prefix) {
    char cs = (char)tolower(*s++);
    char cp = (char)tolower(*prefix++);
    if (cs != cp) return false;
  }
  return true;
}
static bool is_digit_char(char c) {
  return c >= '0' && c <= '9';
}
static bool parse_float_token(const char **p, float *out) {
  while (**p == ' ' || **p == '\t') (*p)++;
  if (**p == '\0') return false;
  const char *start = *p;
  const char *s = start;
  if (*s == '+' || *s == '-') s++;
  bool any_digit = false;
  while (is_digit_char(*s)) {
    any_digit = true;
    s++;
  }
  if (*s == '.') {
    s++;
    while (is_digit_char(*s)) {
      any_digit = true;
      s++;
    }
  }
  if (!any_digit) return false;
  if (*s == 'e' || *s == 'E') {
    s++;
    if (*s == '+' || *s == '-') s++;
    bool exp_digit = false;
    while (is_digit_char(*s)) {
      exp_digit = true;
      s++;
    }
    if (!exp_digit) return false;
  }
  if (*s != '\0' && *s != ' ' && *s != '\t') return false;
  float v = (float)atof(start);
  if (isnan(v) || isinf(v)) return false;
  *out = v;
  *p = s;
  return true;
}
static bool parse_single_float_arg(const char *p, float *out) {
  if (!parse_float_token(&p, out)) return false;
  while (*p == ' ' || *p == '\t') p++;
  return *p == '\0';
}
static int parse_duty_triple(const char *p, float *a, float *b, float *c) {
  float vals[3] = {0};
  int count = 0;
  while (*p && count < 3) {
    float v = 0.0f;
    if (!parse_float_token(&p, &v)) {
      return 0;
    }
    vals[count++] = v;
  }
  while (*p == ' ' || *p == '\t') p++;
  if (*p != '\0') return 0;
  if (count == 1) {
    *a = vals[0];
    *b = vals[0];
    *c = vals[0];
    return 1;
  }
  if (count >= 3) {
    *a = vals[0];
    *b = vals[1];
    *c = vals[2];
    return 3;
  }
  return 0;
}
static void clear_estop_latch() {
  g_estop_latched = false;
  g_fault = 0;
  g_clear_fault_req = true;
  g_estop_auto_clear_deadline_ms = 0;
  hard_stop(false);
  brake_set(false);
  ext_brake_set(0.0f);
}
static void request_estop_stop() {
  g_estop_latched = true;
  g_fault = 2;
  // Emergency stop wins over any pending Blue Pill CLEAR handshake.
  g_clear_fault_req = false;
  g_estop_auto_clear_deadline_ms = (ESTOP_AUTO_CLEAR_MS > 0) ? (millis() + ESTOP_AUTO_CLEAR_MS) : 0;
  hard_stop(false);
  brake_set(false);
  ext_brake_set(0.0f);
  pwm_write(0, 0, 0);
}
static void handle_estop_command(const char *arg) {
  while (*arg == ' ' || *arg == '\t') arg++;
  if (icmp(arg, "CLEAR") || icmp(arg, "OFF") || icmp(arg, "RESET")) {
    clear_estop_latch();
  } else {
    request_estop_stop();
  }
}
static void estop_auto_clear_tick() {
  if (!g_estop_latched) {
    return;
  }
  if (g_estop_auto_clear_deadline_ms == 0) {
    return;
  }
  if (g_state != STATE_SAFE || g_pwm_enabled) {
    return;
  }
  uint32_t now = millis();
  if ((int32_t)(now - g_estop_auto_clear_deadline_ms) < 0) {
    return;
  }
  clear_estop_latch();
}
static bool bp_fault_or_timeout(uint32_t now_ms) {
  bool bp_fault = (g_bp_fault_code != 0) ||
                  ((g_bp_status & 0x08u) != 0u) ||
                  ((g_bp_status & 0x10u) != 0u);
  bool bp_stale = false;
  if (g_pwm_enabled) {
    if (g_bp_last_rsp_ms == 0) {
      if (g_nucleo_last_tx_ms != 0) {
        bp_stale = (uint32_t)(now_ms - g_nucleo_last_tx_ms) > BP_REPLY_TIMEOUT_MS;
      }
    } else {
      bp_stale = (uint32_t)(now_ms - g_bp_last_rsp_ms) > BP_REPLY_TIMEOUT_MS;
    }
  }
  return bp_fault || bp_stale;
}
class NullStream : public Stream {
 public:
  int available() override { return 0; }
  int read() override { return -1; }
  int peek() override { return -1; }
  void flush() override {}
  size_t write(uint8_t) override { return 1; }
};
static NullStream g_null_stream;
static void rpc_process_request(int32_t msgid, const char *method, const uint8_t *buf, size_t len, size_t *idx, uint32_t param_count) {
  if (strcmp(method, "cmd") == 0) {
    char cmd_buf[80];
    if (param_count < 1) {
      rpc_send_response_error(msgid, "bad params");
      return;
    }
    // Consume the full request even on parse errors to avoid desyncing the stream.
    if (!mp_rx_cmd_string(buf, len, idx, cmd_buf, sizeof(cmd_buf))) {
      for (uint32_t i = 1; i < param_count; i++) {
        (void)mp_skip(buf, len, idx);
      }
      rpc_send_response_error(msgid, "bad params");
      return;
    }
    for (uint32_t i = 1; i < param_count; i++) {
      if (!mp_skip(buf, len, idx)) {
        // Drop remaining payload on failure.
        *idx = len;
        rpc_send_response_error(msgid, "bad params");
        return;
      }
    }
    const char *cmd = cmd_buf;
    while (*cmd == ' ' || *cmd == '\t') cmd++;
    bool handled = true;
    if (icmp(cmd, "START")) {
      if (g_estop_latched) {
        rpc_send_response_error(msgid, "estop latched");
        return;
      }
      if (g_mode == MODE_MIC && g_freq_cmd < 0.1f) {
        g_freq_cmd = (g_last_nonzero_freq > 0.1f) ? g_last_nonzero_freq : 10.0f;
      }
      g_start_req = true;
    } else if (icmp(cmd, "STOP")) {
      g_stop_req = true;
      g_restart_after_mode_switch = false;
      g_mode_switch_pending = false;
      ext_brake_set(0.0f);
    } else if (icmp(cmd, "CLEAR") || icmp(cmd, "RESET")) {
      clear_estop_latch();
    } else if (starts_ci(cmd, "MODE")) {
      const char *p = cmd + 4;
      while (*p == ' ' || *p == '\t') p++;
      if (icmp(p, "VF")) {
        request_mode(MODE_VF, false, false);
      } else if (icmp(p, "FOC")) {
        request_mode(MODE_FOC, false, false);
      } else if (icmp(p, "MIC")) {
        request_mode(MODE_MIC, false, false);
      } else if (icmp(p, "DUTY")) {
        request_mode(MODE_VF, true, false);
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "DIAG")) {
      const char *p = cmd + 4;
      while (*p == ' ' || *p == '\t') p++;
      if (icmp(p, "ON") || icmp(p, "1")) {
        request_mode(MODE_VF, false, true);
      } else if (icmp(p, "OFF") || icmp(p, "0")) {
        g_diag_pwm = false;
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "DUTY")) {
      const char *p = cmd + 4;
      float du = g_duty_u;
      float dv = g_duty_v;
      float dw = g_duty_w;
      if (parse_duty_triple(p, &du, &dv, &dw) > 0) {
        g_duty_u = clampf(du, 0.0f, 1.0f);
        g_duty_v = clampf(dv, 0.0f, 1.0f);
        g_duty_w = clampf(dw, 0.0f, 1.0f);
        g_duty_mode = true;
        g_diag_pwm = false;
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "SET FREQ")) {
      const char *p = cmd + 8;
      float f = 0.0f;
      if (parse_single_float_arg(p, &f)) {
        f = clampf(f, 0.0f, 50.0f);
        g_freq_cmd = f;
        if (f > 0.1f) g_last_nonzero_freq = f;
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "SET VFBOOST")) {
      const char *p = cmd + 11;
      float v = 0.0f;
      if (parse_single_float_arg(p, &v)) {
        g_vf_start_boost_v = clampf(v, 0.0f, 120.0f);
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "SET VFRATIO")) {
      const char *p = cmd + 11;
      float r = 0.0f;
      if (parse_single_float_arg(p, &r)) {
        g_vf_volt_per_hz_ratio = clampf(r, 0.0f, 1.0f);
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "ESTOP")) {
      const char *p = cmd + 5;
      handle_estop_command(p);
    } else if (starts_ci(cmd, "SCOPE")) {
      const char *p = cmd + 5;
      while (*p == ' ' || *p == '\t') p++;
      if (icmp(p, "ON") || icmp(p, "1")) {
        scope_set(true);
      } else if (icmp(p, "OFF") || icmp(p, "0")) {
        scope_set(false);
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "PWMTEST")) {
      const char *p = cmd + 7;
      while (*p == ' ' || *p == '\t') p++;
      if (icmp(p, "ON") || icmp(p, "1")) {
        pwm_test_set(true);
      } else if (icmp(p, "OFF") || icmp(p, "0")) {
        pwm_test_set(false);
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "NTC")) {
      const char *p = cmd + 3;
      while (*p == ' ' || *p == '\t') p++;
      if (icmp(p, "ON") || icmp(p, "1")) {
        ext_flag_set(BP_EXT_NTC, true);
      } else if (icmp(p, "OFF") || icmp(p, "0")) {
        ext_flag_set(BP_EXT_NTC, false);
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "PFC")) {
      const char *p = cmd + 3;
      while (*p == ' ' || *p == '\t') p++;
      if (icmp(p, "ON") || icmp(p, "1")) {
        ext_flag_set(BP_EXT_PFC, true);
      } else if (icmp(p, "OFF") || icmp(p, "0")) {
        ext_flag_set(BP_EXT_PFC, false);
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "BRAKE")) {
      const char *p = cmd + 5;
      while (*p == ' ' || *p == '\t') p++;
      if (starts_ci(p, "PWM")) {
        p += 3;
        float duty = 0.0f;
        if (parse_single_float_arg(p, &duty)) {
          ext_brake_set(clampf(duty, 0.0f, 1.0f));
        } else {
          handled = false;
        }
      } else if (icmp(p, "OFF") || icmp(p, "0")) {
        brake_set(false);
        ext_brake_set(0.0f);
      } else if (icmp(p, "ON") || icmp(p, "1")) {
        brake_set(true);
        ext_brake_set(0.0f);
      } else {
        handled = false;
      }
    } else {
      handled = false;
    }
    if (!handled) {
      rpc_send_response_error(msgid, "unknown cmd");
      return;
    }
    rpc_send_response_bool(msgid, true);
    return;
  }
  if (strcmp(method, "get") == 0) {
    for (uint32_t i = 0; i < param_count; i++) {
      if (!mp_skip(buf, len, idx)) {
        rpc_send_response_error(msgid, "bad params");
        return;
      }
    }
    rpc_send_response_get(msgid);
    return;
  }
  for (uint32_t i = 0; i < param_count; i++) {
    if (!mp_skip(buf, len, idx)) {
      return;
    }
  }
  rpc_send_response_error(msgid, "no method");
}
static bool rpc_try_parse_one(size_t *consumed) {
  size_t idx = 0;
  uint32_t arr_len = 0;
  if (!mp_rx_array(g_rx_buf, g_rx_len, &idx, &arr_len)) {
    return false;
  }
  if (arr_len < 3) {
    *consumed = idx;
    return true;
  }
  int32_t msg_type = 0;
  if (!mp_rx_int(g_rx_buf, g_rx_len, &idx, &msg_type)) return false;
  if (msg_type == 0) {
    int32_t msgid = 0;
    if (!mp_rx_int(g_rx_buf, g_rx_len, &idx, &msgid)) return false;
    char method[32];
    if (!mp_rx_str(g_rx_buf, g_rx_len, &idx, method, sizeof(method))) return false;
    uint32_t param_count = 0;
    if (!mp_rx_array(g_rx_buf, g_rx_len, &idx, &param_count)) return false;
    // arduino-router may deliver the request over UART in multiple chunks (e.g. up to the
    // params array header first, then the actual string bytes). Do not dispatch until the
    // full params payload is present, otherwise we'll incorrectly answer "bad params" and
    // break framing.
    size_t idx_check = idx;
    for (uint32_t i = 0; i < param_count; i++) {
      if (!mp_skip(g_rx_buf, g_rx_len, &idx_check)) {
        return false; // need more bytes
      }
    }
    rpc_process_request(msgid, method, g_rx_buf, g_rx_len, &idx, param_count);
    idx = idx_check;
  } else if (msg_type == 1) {
    int32_t msgid = 0;
    if (!mp_rx_int(g_rx_buf, g_rx_len, &idx, &msgid)) return false;
    if (!mp_skip(g_rx_buf, g_rx_len, &idx)) return false; // error
    if (!mp_skip(g_rx_buf, g_rx_len, &idx)) return false; // result
  } else if (msg_type == 2) {
    char method[32];
    if (!mp_rx_str(g_rx_buf, g_rx_len, &idx, method, sizeof(method))) return false;
    uint32_t param_count = 0;
    if (!mp_rx_array(g_rx_buf, g_rx_len, &idx, &param_count)) return false;
    for (uint32_t i = 0; i < param_count; i++) {
      if (!mp_skip(g_rx_buf, g_rx_len, &idx)) {
        return false;
      }
    }
  } else {
    // Unknown message type: try to skip remaining elements
    for (uint32_t i = 1; i < arr_len; i++) {
      if (!mp_skip(g_rx_buf, g_rx_len, &idx)) {
        return false;
      }
    }
  }
  *consumed = idx;
  return true;
}
static void rpc_poll(void) {
  while (LOG_SERIAL.available() > 0) {
    if (g_rx_len >= RX_BUF_SIZE) {
      g_rx_len = 0;
      break;
    }
    g_rx_buf[g_rx_len++] = (uint8_t)LOG_SERIAL.read();
  }
  while (g_rx_len > 0) {
    size_t consumed = 0;
    if (!rpc_try_parse_one(&consumed)) {
      break;
    }
    if (consumed == 0 || consumed > g_rx_len) {
      g_rx_len = 0;
      break;
    }
    memmove(g_rx_buf, &g_rx_buf[consumed], g_rx_len - consumed);
    g_rx_len -= consumed;
  }
}
// ----------------------- Helpers -----------------------
static const char *state_name(ControlState s) {
  switch (s) {
    case STATE_SAFE: return "SAFE";
    case STATE_VF_RUN: return "VF_RUN";
    case STATE_FOC_ALIGN: return "FOC_ALIGN";
    case STATE_FOC_RUN: return "FOC_RUN";
    case STATE_FAULT: return "FAULT";
    default: return "UNKNOWN";
  }
}
static const char *mode_name(ControlMode m) {
  if (m == MODE_VF) return "VF";
  if (m == MODE_MIC) return "MIC";
  return "FOC";
}
static void bridge_notify_line(const String &line) {
#if USE_ROUTER_BRIDGE
  if (Monitor) {
    Monitor.println(line);
  }
#elif USE_MSGPACK_RPC
  rpc_send_mon_write(line.c_str());
#else
  LOG_SERIAL.println(line);
#endif
}
static String format_fixed(float value, uint8_t decimals) {
  if (isnan(value)) return String("nan");
  if (isinf(value)) return value < 0.0f ? String("-inf") : String("inf");

  bool negative = value < 0.0f;
  float mag = negative ? -value : value;
  uint32_t scale = 1U;
  for (uint8_t i = 0; i < decimals; ++i) {
    scale *= 10U;
  }
  uint32_t scaled = (uint32_t)(mag * (float)scale + 0.5f);
  uint32_t whole = (scale > 0U) ? (scaled / scale) : scaled;
  uint32_t frac = (scale > 0U) ? (scaled % scale) : 0U;

  String out;
  out.reserve(20);
  if (negative && (whole != 0U || frac != 0U)) {
    out += '-';
  }
  out += String((unsigned long)whole);
  if (decimals == 0U) {
    return out;
  }
  out += '.';
  uint32_t div = scale / 10U;
  while (div > 0U) {
    out += (char)('0' + ((frac / div) % 10U));
    div /= 10U;
  }
  return out;
}
static float mic_estimate_p_loss(float id, float iq, float omega_e) {
  float i2 = (id * id) + (iq * iq);
  float p_cu = 1.5f * MIC_RS * i2;
  float psi = MIC_LM * id;
  float p_fe = MIC_K_FE * omega_e * omega_e * psi * psi;
  float p_sw = MIC_K_SW * MIC_F_SW * sqrtf(i2);
  return p_cu + p_fe + p_sw;
}
static uint16_t mic_link_flags(uint32_t now_ms) {
  uint16_t flags = 0u;
  if (g_nucleo_last_rx_ms == 0) {
    flags |= 0x01u;
  } else {
    uint32_t age = (uint32_t)(now_ms - g_nucleo_last_rx_ms);
    if (age > BP_REPLY_TIMEOUT_MS) {
      flags |= 0x01u;
    }
  }
  if ((g_bp_status & 0x01u) == 0u) {
    flags |= 0x02u;
  }
  if (g_pwm_enabled && ((g_bp_status & 0x20u) == 0u)) {
    flags |= 0x04u;
  }
  return flags;
}
static float mic_feedback_elec_hz(uint32_t now_ms, bool *enc_used) {
  bool enc_recent = g_bp_enc_ok &&
                    g_enc_speed_valid &&
                    ((uint32_t)(now_ms - g_bp_enc_ms) < MIC_ENC_STALE_MS);
  if (enc_used) {
    *enc_used = enc_recent;
  }
  if (enc_recent) {
    return fabsf(g_enc_elec_hz);
  }
  return fabsf(g_freq_ref);
}
static void mic_update_metrics() {
  float omega_e = CTRL_TWO_PI * g_freq_ref;
  float p_loss = mic_estimate_p_loss(g_last_id, g_last_iq, omega_e);
  float p_loss_base = mic_estimate_p_loss(RUN_ID_REF_A, g_last_iq, omega_e);
  float saving = 0.0f;
  if (p_loss_base > 1e-6f) {
    saving = (p_loss_base - p_loss) / p_loss_base * 100.0f;
  }
  if (!g_mic_active) {
    saving = 0.0f;
  }
  g_mic_p_loss = p_loss;
  g_mic_p_loss_base = p_loss_base;
  g_mic_saving_pct = saving;
}
static void mic_diag_reset() {
  g_mic_active = false;
  g_mic_id_ref = RUN_ID_REF_A;
  g_mic_saving_pct = 0.0f;
  g_mic_id_ref_q10 = (int16_t)(RUN_ID_REF_A * 1024.0f);
  g_mic_gated = 0;
  g_mic_enable_ai = 0;
  g_mic_enc_used = false;
  g_mic_freq_meas_hz = 0.0f;
  g_mic_speed_err_hz = 0.0f;
  g_mic_speed_tol_hz = 0.0f;
  g_mic_link_flags = 0u;
  g_mic_status_flags = 0u;
}
static void scope_set(bool enabled) {
  if (USE_EXTERNAL_PWM && enabled) {
    bridge_notify_line(String("LOG SCOPE IGNORED (EXT PWM)"));
    return;
  }
  if (enabled == g_scope_test) return;
  g_scope_test = enabled;
  g_start_req = false;
  g_stop_req = false;
  g_stop_requested = false;
  g_freq_cmd = 0.0f;
  g_freq_ref = 0.0f;
  g_pwm_enabled = false;
  g_state = STATE_SAFE;
  g_scope_u = false;
  g_scope_v = false;
  g_scope_w = false;
  g_scope_last_u_us = micros();
  g_scope_last_v_us = g_scope_last_u_us;
  g_scope_last_w_us = g_scope_last_u_us;
  pwm_force_off();
  bridge_notify_line(enabled ? String("LOG SCOPE ON") : String("LOG SCOPE OFF"));
}
static void scope_tick() {
  if (USE_EXTERNAL_PWM) {
    return;
  }
  uint32_t now = micros();
  if ((uint32_t)(now - g_scope_last_u_us) >= 500U) { // ~1 kHz
    g_scope_last_u_us = now;
    g_scope_u = !g_scope_u;
    analogWrite(PWM_UH_PIN, pwm_level(g_scope_u, false));
    analogWrite(PWM_UL_PIN, PWM_THREE_PWM_MODE ? (PWM_LOW_INVERTED ? PWM_FULL : 0)
                                               : pwm_level(!g_scope_u, PWM_LOW_INVERTED));
  }
  if ((uint32_t)(now - g_scope_last_v_us) >= 800U) { // ~625 Hz
    g_scope_last_v_us = now;
    g_scope_v = !g_scope_v;
    analogWrite(PWM_VH_PIN, pwm_level(g_scope_v, false));
    analogWrite(PWM_VL_PIN, PWM_THREE_PWM_MODE ? (PWM_LOW_INVERTED ? PWM_FULL : 0)
                                               : pwm_level(!g_scope_v, PWM_LOW_INVERTED));
  }
  if ((uint32_t)(now - g_scope_last_w_us) >= 1200U) { // ~416 Hz
    g_scope_last_w_us = now;
    g_scope_w = !g_scope_w;
    analogWrite(PWM_WH_PIN, pwm_level(g_scope_w, false));
    analogWrite(PWM_WL_PIN, PWM_THREE_PWM_MODE ? (PWM_LOW_INVERTED ? PWM_FULL : 0)
                                               : pwm_level(!g_scope_w, PWM_LOW_INVERTED));
  }
}
static void pwm_test_set(bool enabled) {
  if (enabled == g_pwm_test) return;
  if (USE_EXTERNAL_PWM && enabled) {
    bridge_notify_line(String("LOG PWMTEST IGNORED (EXT PWM)"));
    return;
  }
  g_pwm_test = enabled;
  g_scope_test = false;
  g_start_req = false;
  g_stop_req = false;
  g_stop_requested = false;
  g_freq_cmd = 0.0f;
  g_freq_ref = 0.0f;
  g_state = STATE_SAFE;
  g_pwm_enabled = enabled;
  bridge_notify_line(enabled ? String("LOG PWMTEST ON") : String("LOG PWMTEST OFF"));
  if (!enabled) {
    pwm_force_off();
  }
}
static void handle_command_line_stream(const char *cmd, Stream &out) {
  while (*cmd == ' ' || *cmd == '	') cmd++;
  if (*cmd == '\0') {
    return;
  }
  String line;
  line.reserve(96);
  line += "LOG CMD ";
  line += cmd;
  bridge_notify_line(line);
  bool handled = true;
  if (icmp(cmd, "START")) {
    if (g_estop_latched) {
      out.println("ERR estop latched");
      return;
    }
    if (g_mode == MODE_MIC && g_freq_cmd < 0.1f) {
      g_freq_cmd = (g_last_nonzero_freq > 0.1f) ? g_last_nonzero_freq : 10.0f;
    }
    g_start_req = true;
  } else if (icmp(cmd, "STOP")) {
    g_stop_req = true;
    g_restart_after_mode_switch = false;
    g_mode_switch_pending = false;
    ext_brake_set(0.0f);
  } else if (icmp(cmd, "CLEAR") || icmp(cmd, "RESET")) {
    clear_estop_latch();
  } else if (starts_ci(cmd, "MODE")) {
    const char *p = cmd + 4;
    while (*p == ' ' || *p == '	') p++;
    if (icmp(p, "VF")) {
      request_mode(MODE_VF, false, false);
    } else if (icmp(p, "FOC")) {
      request_mode(MODE_FOC, false, false);
    } else if (icmp(p, "MIC")) {
      request_mode(MODE_MIC, false, false);
    } else if (icmp(p, "DUTY")) {
      request_mode(MODE_VF, true, false);
    } else {
      handled = false;
    }
  } else if (starts_ci(cmd, "DIAG")) {
    const char *p = cmd + 4;
    while (*p == ' ' || *p == '\t') p++;
    if (icmp(p, "ON") || icmp(p, "1")) {
      request_mode(MODE_VF, false, true);
    } else if (icmp(p, "OFF") || icmp(p, "0")) {
      g_diag_pwm = false;
    } else {
      handled = false;
    }
  } else if (starts_ci(cmd, "DUTY")) {
    const char *p = cmd + 4;
    float du = g_duty_u;
    float dv = g_duty_v;
    float dw = g_duty_w;
    if (parse_duty_triple(p, &du, &dv, &dw) > 0) {
      g_duty_u = clampf(du, 0.0f, 1.0f);
      g_duty_v = clampf(dv, 0.0f, 1.0f);
      g_duty_w = clampf(dw, 0.0f, 1.0f);
      g_duty_mode = true;
      g_diag_pwm = false;
    } else {
      handled = false;
    }
  } else if (starts_ci(cmd, "SET FREQ")) {
    const char *p = cmd + 8;
    float f = 0.0f;
    if (parse_single_float_arg(p, &f)) {
      f = clampf(f, 0.0f, 50.0f);
      g_freq_cmd = f;
      if (f > 0.1f) g_last_nonzero_freq = f;
    } else {
      handled = false;
    }
  } else if (starts_ci(cmd, "SET VFBOOST")) {
    const char *p = cmd + 11;
    float v = 0.0f;
    if (parse_single_float_arg(p, &v)) {
      g_vf_start_boost_v = clampf(v, 0.0f, 120.0f);
    } else {
      handled = false;
    }
  } else if (starts_ci(cmd, "SET VFRATIO")) {
    const char *p = cmd + 11;
    float r = 0.0f;
    if (parse_single_float_arg(p, &r)) {
      g_vf_volt_per_hz_ratio = clampf(r, 0.0f, 1.0f);
    } else {
      handled = false;
    }
  } else if (starts_ci(cmd, "ESTOP")) {
    const char *p = cmd + 5;
    handle_estop_command(p);
  } else if (starts_ci(cmd, "NTC")) {
    const char *p = cmd + 3;
    while (*p == ' ' || *p == '	') p++;
    if (icmp(p, "ON") || icmp(p, "1")) {
      ext_flag_set(BP_EXT_NTC, true);
    } else if (icmp(p, "OFF") || icmp(p, "0")) {
      ext_flag_set(BP_EXT_NTC, false);
    } else {
      handled = false;
    }
  } else if (starts_ci(cmd, "PFC")) {
    const char *p = cmd + 3;
    while (*p == ' ' || *p == '	') p++;
    if (icmp(p, "ON") || icmp(p, "1")) {
      ext_flag_set(BP_EXT_PFC, true);
    } else if (icmp(p, "OFF") || icmp(p, "0")) {
      ext_flag_set(BP_EXT_PFC, false);
    } else {
      handled = false;
    }
  } else if (starts_ci(cmd, "SCOPE")) {
    const char *p = cmd + 5;
    while (*p == ' ' || *p == '	') p++;
    if (icmp(p, "ON") || icmp(p, "1")) {
      scope_set(true);
    } else if (icmp(p, "OFF") || icmp(p, "0")) {
      scope_set(false);
    } else {
      handled = false;
    }
    } else if (starts_ci(cmd, "PWMTEST")) {
      const char *p = cmd + 7;
      while (*p == ' ' || *p == '	') p++;
      if (icmp(p, "ON") || icmp(p, "1")) {
        pwm_test_set(true);
      } else if (icmp(p, "OFF") || icmp(p, "0")) {
        pwm_test_set(false);
      } else {
        handled = false;
      }
    } else if (starts_ci(cmd, "BRAKE")) {
      const char *p = cmd + 5;
      while (*p == ' ' || *p == '	') p++;
      if (starts_ci(p, "PWM")) {
        p += 3;
        float duty = 0.0f;
        if (parse_single_float_arg(p, &duty)) {
          ext_brake_set(clampf(duty, 0.0f, 1.0f));
        } else {
          handled = false;
        }
      } else if (icmp(p, "OFF") || icmp(p, "0")) {
        brake_set(false);
        ext_brake_set(0.0f);
      } else if (icmp(p, "ON") || icmp(p, "1")) {
        brake_set(true);
        ext_brake_set(0.0f);
      } else {
        handled = false;
      }
    } else if (icmp(cmd, "GET") || icmp(cmd, "STATUS")) {
      out.println(rpc_get());
      return;
    } else {
      handled = false;
    }
    if (!handled) {
      out.println("ERR unknown cmd");
      return;
    }
    out.println("OK");
}
static bool rpc_cmd(String cmd) {
  handle_command_line_stream(cmd.c_str(), g_null_stream);
  return true;
}

static String rpc_get() {
  float ia = g_last_ia;
  float ib = g_last_ib;
  float ic = g_last_ic;
  float speed_rpm = (g_freq_ref * 60.0f) / POLE_PAIRS;
  String s;
  s.reserve(160);
  s += "DATA freq="; s += format_fixed(g_freq_ref, 2);
  s += " speed="; s += format_fixed(speed_rpm, 1);
  s += " ia="; s += format_fixed(ia, 2);
  s += " ib="; s += format_fixed(ib, 2);
  s += " ic="; s += format_fixed(ic, 2);
  s += " vdc="; s += format_fixed(g_vdc, 2);
  s += " state="; s += String(state_name(g_state));
  s += " mode="; s += String(mode_name(g_mode));
  s += " pwm="; s += String(g_pwm_enabled ? 1 : 0);
  s += " id="; s += format_fixed(g_last_id, 2);
  s += " iq="; s += format_fixed(g_last_iq, 2);
  s += " irm="; s += format_fixed(g_last_i_rms, 2);
  s += " mic="; s += String(g_mic_active ? 1 : 0);
  s += " idref="; s += format_fixed(g_mic_id_ref, 2);
  s += " save="; s += format_fixed(g_mic_saving_pct, 2);
  s += " freqcmd="; s += format_fixed(g_freq_cmd, 2);
  s += " estop="; s += String(g_estop_latched ? 1 : 0);
  s += " ntc="; s += String((g_ext_flags & BP_EXT_NTC) ? 1 : 0);
  s += " pfc="; s += String((g_ext_flags & BP_EXT_PFC) ? 1 : 0);
  float brake = (g_ext_flags & BP_EXT_BRAKE_PWM) ? ((float)g_brake_q15 / 32767.0f) : 0.0f;
  s += " brake="; s += String((g_ext_flags & BP_EXT_BRAKE_PWM) ? 1 : 0);
  s += " brake_duty="; s += format_fixed(brake, 2);
  s += " diag="; s += String(g_diag_pwm ? 1 : 0);
  s += " duty="; s += String(g_duty_mode ? 1 : 0);
  bool enc_recent = (uint32_t)(millis() - g_bp_enc_ms) < 500U;
  float enc_deg = ((float)g_bp_enc_raw * 360.0f) / 4096.0f;
  s += " enc_raw="; s += String((int)g_bp_enc_raw);
  s += " enc_ok="; s += String((g_bp_enc_ok && enc_recent) ? 1 : 0);
  s += " enc_deg="; s += format_fixed(enc_deg, 1);
  s += " enc_rpm="; s += format_fixed((g_bp_enc_ok && enc_recent) ? g_enc_rpm : 0.0f, 1);
  s += " enc_mech_hz="; s += format_fixed((g_bp_enc_ok && enc_recent) ? g_enc_mech_hz : 0.0f, 2);
  s += " enc_elec_hz="; s += format_fixed((g_bp_enc_ok && enc_recent) ? g_enc_elec_hz : 0.0f, 2);
  s += " mic_gated="; s += String((int)g_mic_gated);
  s += " mic_enable_ai="; s += String((int)g_mic_enable_ai);
  s += " mic_enc_used="; s += String(g_mic_enc_used ? 1 : 0);
  s += " mic_fmeas="; s += format_fixed(g_mic_freq_meas_hz, 2);
  s += " mic_ferr="; s += format_fixed(g_mic_speed_err_hz, 2);
  s += " mic_ftol="; s += format_fixed(g_mic_speed_tol_hz, 2);
  s += " mic_lflags="; s += String((int)g_mic_link_flags);
  s += " mic_sflags="; s += String((int)g_mic_status_flags);
  uint32_t bp_age = (g_nucleo_last_rx_ms == 0) ? 999999U : (uint32_t)(millis() - g_nucleo_last_rx_ms);
  s += " bp_good="; s += String((int)g_nucleo_rx_good);
  s += " bp_bad="; s += String((int)g_nucleo_rx_bad);
  s += " bp_age_ms="; s += String((int)bp_age);
  // Low-level Blue Pill link observability.
  s += " bp_status="; s += String((int)g_bp_status);
  s += " bp_fault="; s += String((int)g_bp_fault_code);
  s += " bp_mode="; s += String((int)g_bp_last_mode);
  s += " bp_seq="; s += String((int)g_bp_last_seq);
  s += " bp_good_cnt="; s += String((int)g_bp_good_cnt);
  s += " bp_bad_cnt="; s += String((int)g_bp_bad_cnt);
  s += " bp_ext="; s += String((int)g_bp_ext_flags);
  float bp_brake = (float)g_bp_brake_q15 / 32767.0f;
  s += " bp_brake_duty="; s += format_fixed(bp_brake, 2);
  s += " bp_vbus_raw="; s += String((int)g_bp_vbus_raw);
  s += " bp_vdc="; s += format_fixed(g_bp_vdc, 2);
  uint32_t bp_vbus_age = (g_bp_vbus_ms == 0) ? 999999U : (uint32_t)(millis() - g_bp_vbus_ms);
  s += " bp_vbus_age_ms="; s += String((int)bp_vbus_age);
  uint32_t bp_rsp_age = (g_bp_last_rsp_ms == 0) ? 999999U : (uint32_t)(millis() - g_bp_last_rsp_ms);
  s += " bp_rsp_age_ms="; s += String((int)bp_rsp_age);
  uint32_t ping_age = (g_bp_ping_ms == 0) ? 999999U : (uint32_t)(millis() - g_bp_ping_ms);
  s += " bp_ping_pairs="; s += String((unsigned long)g_bp_ping_pairs);
  s += " bp_ping_age_ms="; s += String((int)ping_age);
  return s;
}

static void serial_poll() {
#if !USE_MSGPACK_RPC
  while (LOG_SERIAL.available() > 0) {
    char c = (char)LOG_SERIAL.read();
    if (c == '\n' || c == '\r') {
      if (g_line_len > 0) {
        g_line_buf[g_line_len] = '\0';
        handle_command_line_stream(g_line_buf, LOG_SERIAL);
        g_line_len = 0;
      }
    } else {
      if (g_line_len < (sizeof(g_line_buf) - 1)) {
        g_line_buf[g_line_len++] = c;
      }
    }
  }
#endif
  while (UI_SERIAL.available() > 0) {
    char c = (char)UI_SERIAL.read();
    if (c == '\n' || c == '\r') {
      if (g_line_len_ui > 0) {
        g_line_buf_ui[g_line_len_ui] = '\0';
        handle_command_line_stream(g_line_buf_ui, UI_SERIAL);
        g_line_len_ui = 0;
      }
    } else {
      if (g_line_len_ui < (sizeof(g_line_buf_ui) - 1)) {
        g_line_buf_ui[g_line_len_ui++] = c;
      }
    }
  }
}
#if USE_ROUTER_BRIDGE
static void bridge_tick() {
  uint32_t now = millis();
  if ((uint32_t)(now - g_bridge_last_ms) < 1000U) {
    return;
  }
  g_bridge_last_ms = now;
  if (!Bridge) {
    g_bridge_ready = Bridge.begin(RPC_BAUD);
    g_bridge_cmd_ready = false;
    g_bridge_get_ready = false;
    g_monitor_ready = false;
    return;
  }
  if (!g_monitor_ready) {
    g_monitor_ready = Monitor.begin();
  }
  if (!g_bridge_cmd_ready) {
    g_bridge_cmd_ready = Bridge.provide("cmd", rpc_cmd);
  }
  if (!g_bridge_get_ready) {
    g_bridge_get_ready = Bridge.provide("get", rpc_get);
  }
  if (!g_bridge_ready && g_bridge_cmd_ready && g_bridge_get_ready && g_monitor_ready) {
    g_bridge_ready = true;
    Monitor.println("LOG BRIDGE READY");
    LOG_SERIAL.println("LOG BRIDGE READY");
  }
}
#endif
static void send_telemetry() {
  uint32_t now = millis();
  if ((uint32_t)(now - g_last_telem_ms) < TELEMETRY_MS) {
    return;
  }
  g_last_telem_ms = now;
  mic_update_metrics();

  if (g_state != g_last_state) {
    String line;
    line.reserve(32);
    line += "STAT ";
    line += state_name(g_state);
    bridge_notify_line(line);
    g_last_state = g_state;
  }

  if (g_fault != g_last_fault) {
    if (g_fault != 0) {
      String line;
      line.reserve(24);
      line += "FAULT ";
      line += g_fault;
      bridge_notify_line(line);
    }
    g_last_fault = g_fault;
  }

  if (g_pwm_enabled != g_last_pwm) {
    String line;
    line.reserve(24);
    line += "LOG PWM ";
    line += (g_pwm_enabled ? "ON" : "OFF");
    bridge_notify_line(line);
    g_last_pwm = g_pwm_enabled;
  }

  if (g_mic_active != g_last_mic_active) {
    String line;
    line.reserve(20);
    line += "LOG MIC ";
    line += (g_mic_active ? "ON" : "OFF");
    bridge_notify_line(line);
    g_last_mic_active = g_mic_active;
  }

#if LOG_TELEMETRY_DATA
  float speed_rpm = (g_freq_ref * 60.0f) / POLE_PAIRS;
  String line;
  line.reserve(192);
  line += "DATA freq=";
  line += format_fixed(g_freq_ref, 2);
  line += " speed=";
  line += format_fixed(speed_rpm, 1);
  line += " ia=";
  line += format_fixed(g_last_ia, 2);
  line += " ib=";
  line += format_fixed(g_last_ib, 2);
  line += " ic=";
  line += format_fixed(g_last_ic, 2);
  line += " vdc=";
  line += format_fixed(g_vdc, 2);
  line += " id=";
  line += format_fixed(g_last_id, 2);
  line += " iq=";
  line += format_fixed(g_last_iq, 2);
  line += " vd=";
  line += format_fixed(g_last_vd, 2);
  line += " vq=";
  line += format_fixed(g_last_vq, 2);
  line += " pwm=";
  line += (g_pwm_enabled ? 1 : 0);
  bridge_notify_line(line);
#endif
}
static void rpc_service() {
  uint32_t now = millis();
  if ((uint32_t)(now - g_last_reg_ms) >= 1000U) {
    g_last_reg_ms = now;
    rpc_send_register("cmd");
    rpc_send_register("get");
  }
}
static float clampf(float v, float lo, float hi) {
  if (isnan(v) || isinf(v)) return lo;
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}
static float sanitize_small_float(float v, float eps = 1e-6f) {
  if (!isfinite(v) || fabsf(v) < eps) {
    return 0.0f;
  }
  return v;
}
static float ramp_toward(float v, float target, float step) {
  if (v < target) {
    v += step;
    if (v > target) v = target;
  } else if (v > target) {
    v -= step;
    if (v < target) v = target;
  }
  return v;
}
static void pi_init(PIController *pi, float kp, float ki, float out_min, float out_max) {
  pi->kp = kp;
  pi->ki = ki;
  pi->integrator = 0.0f;
  pi->out_min = out_min;
  pi->out_max = out_max;
}
static float pi_run(PIController *pi, float error, float ts) {
  pi->integrator += pi->ki * error * ts;
  pi->integrator = clampf(pi->integrator, pi->out_min, pi->out_max);
  float out = pi->kp * error + pi->integrator;
  return clampf(out, pi->out_min, pi->out_max);
}
static uint8_t duty_u8(float duty) {
  return (uint8_t)(clampf(duty, 0.0f, 1.0f) * PWM_MAX);
}
static uint16_t q15_unit(float duty) {
  duty = clampf(duty, 0.0f, 1.0f);
  return (uint16_t)(duty * 32767.0f);
}
static void ext_flag_set(uint8_t flag, bool on) {
  if (on) {
    g_ext_flags |= flag;
  } else {
    g_ext_flags &= (uint8_t)(~flag);
  }
}
static void ext_brake_set(float duty) {
  if (duty <= 0.0001f) {
    g_brake_q15 = 0;
    g_ext_flags &= (uint8_t)(~BP_EXT_BRAKE_PWM);
    return;
  }
  g_brake_q15 = q15_unit(duty);
  g_ext_flags |= BP_EXT_BRAKE_PWM;
}
static uint8_t nucleo_crc8(const uint8_t *buf, size_t len) {
  uint8_t c = 0;
  for (size_t i = 0; i < len; i++) {
    c ^= buf[i];
  }
  return c;
}
static void enc_speed_update(uint16_t raw, bool ok, uint32_t now_ms) {
  if (!ok) {
    g_enc_speed_valid = false;
    g_enc_accum_counts = 0;
    g_enc_accum_ms = 0;
    g_enc_rpm = 0.0f;
    g_enc_mech_hz = 0.0f;
    g_enc_elec_hz = 0.0f;
    return;
  }
  if (!g_enc_speed_valid) {
    g_enc_speed_valid = true;
    g_enc_prev_raw = raw;
    g_enc_prev_ms = now_ms;
    g_enc_accum_counts = 0;
    g_enc_accum_ms = 0;
    return;
  }
  uint32_t dt_ms = now_ms - g_enc_prev_ms;
  if (dt_ms == 0 || dt_ms > 250U) {
    // Large gaps or duplicate timestamps: re-sync without producing a spike.
    g_enc_prev_raw = raw;
    g_enc_prev_ms = now_ms;
    g_enc_accum_counts = 0;
    g_enc_accum_ms = 0;
    return;
  }
  int32_t dr = (int32_t)raw - (int32_t)g_enc_prev_raw;
  // 12-bit wrap handling: choose the shortest path.
  if (dr > 2048) dr -= 4096;
  if (dr < -2048) dr += 4096;
  g_enc_prev_raw = raw;
  g_enc_prev_ms = now_ms;
  g_enc_accum_counts += dr;
  g_enc_accum_ms += dt_ms;

  // Accumulate over >=20ms to reduce quantization noise on small dt.
  if (g_enc_accum_ms < 20U) {
    return;
  }
  float dt_s = (float)g_enc_accum_ms * 0.001f;
  float rev = (float)g_enc_accum_counts / 4096.0f;
  float rpm_inst = (dt_s > 1e-6f) ? (rev / dt_s) * 60.0f : 0.0f;
  // 1st order low-pass: alpha tuned for 20..50ms updates.
  const float alpha = 0.25f;
  g_enc_rpm = g_enc_rpm + alpha * (rpm_inst - g_enc_rpm);
  g_enc_mech_hz = g_enc_rpm / 60.0f;
  g_enc_elec_hz = (g_enc_rpm * POLE_PAIRS) / 60.0f;
  g_enc_rpm = sanitize_small_float(g_enc_rpm);
  g_enc_mech_hz = sanitize_small_float(g_enc_mech_hz);
  g_enc_elec_hz = sanitize_small_float(g_enc_elec_hz);
  g_enc_accum_counts = 0;
  g_enc_accum_ms = 0;
}
static bool nucleo_check_reply(const uint8_t *rx) {
  if (!rx) return false;
  if (rx[0] != 0x55 || rx[1] != 0xAA) return false;
  uint8_t crc = nucleo_crc8(rx, 19);
  if (crc != rx[19]) return false;
  uint32_t now_ms = millis();
  g_bp_status = rx[3];
  g_bp_last_seq = rx[4];
  g_bp_good_cnt = (uint16_t)rx[5] | ((uint16_t)rx[6] << 8);
  g_bp_bad_cnt = (uint16_t)rx[7] | ((uint16_t)rx[8] << 8);
  g_bp_fault_code = rx[9];
  g_bp_last_mode = rx[10];
  g_bp_enc_raw = (uint16_t)rx[11] | ((uint16_t)rx[12] << 8);
  g_bp_enc_ok = (rx[13] != 0);
  g_bp_enc_ms = now_ms;
  enc_speed_update(g_bp_enc_raw, g_bp_enc_ok, now_ms);
  g_bp_ext_flags = rx[14];
  g_bp_brake_q15 = (uint16_t)rx[15] | ((uint16_t)rx[16] << 8);
  g_bp_vbus_raw = (uint16_t)rx[17] | ((uint16_t)rx[18] << 8);
  if (g_bp_vbus_raw > 4095U) {
    g_bp_vbus_raw = 4095U;
  }
  g_bp_vdc = ((float)g_bp_vbus_raw * BP_VBUS_FULL_SCALE_V) / 4095.0f;
  g_bp_vbus_ms = now_ms;
  g_bp_last_rsp_ms = now_ms;
  if (g_nucleo_waiting_rsp && g_bp_last_seq == g_nucleo_waiting_seq) {
    g_nucleo_waiting_rsp = false;
    g_nucleo_last_ack_us = micros();
  }
  // Clear is held until we observe "no fault" from the Blue Pill.
  if (g_clear_fault_req) {
    bool fault = (g_bp_fault_code != 0) || ((g_bp_status & 0x08u) != 0u);
    if (!fault) {
      g_clear_fault_req = false;
    }
  }
  return true;
}

// Non-blocking UART reply parser (Blue Pill -> UNOQ).
// We keep it simple: sync to 0x55 0xAA header, then collect 20 bytes.
static void nucleo_uart_poll() {
  static uint8_t st = 0;
  static uint8_t idx = 0;
  static uint8_t buf[20];
  while (NUCLEO_SERIAL.available() > 0) {
    uint8_t b = (uint8_t)NUCLEO_SERIAL.read();
    // Detect the Blue Pill's boot ping (0x5A 0xA5 ...) to diagnose RX wiring/baud
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
      if (nucleo_check_reply(buf)) {
        if (g_nucleo_rx_good < 0xFFFFu) g_nucleo_rx_good++;
        g_nucleo_last_rx_ms = millis();
        g_link_led_ms = g_nucleo_last_rx_ms;
      } else {
        if (g_nucleo_rx_bad < 0xFFFFu) g_nucleo_rx_bad++;
      }
    }
  }
}
static void nucleo_spi_init() {
  if (!USE_NUCLEO_SPI) {
    return;
  }
  pinMode(NUCLEO_SPI_CS, OUTPUT);
  digitalWrite(NUCLEO_SPI_CS, HIGH);
  if (FORCE_SPI_BITBANG) {
    pinMode(NUCLEO_SPI_SCK, OUTPUT);
    pinMode(NUCLEO_SPI_MOSI, OUTPUT);
    pinMode(NUCLEO_SPI_MISO, INPUT);
    digitalWrite(NUCLEO_SPI_SCK, LOW);
    digitalWrite(NUCLEO_SPI_MOSI, LOW);
    return;
  }
  SPI.begin();
}
static void nucleo_uart_init() {
  if (!USE_EXTERNAL_PWM) {
    return;
  }
  if (USE_NUCLEO_SPI) {
    nucleo_spi_init();
    if (USE_NUCLEO_UART_FALLBACK) {
      NUCLEO_SERIAL.begin(NUCLEO_UART_BAUD);
    }
    return;
  }
  NUCLEO_SERIAL.begin(NUCLEO_UART_BAUD);
  while (NUCLEO_SERIAL.available() > 0) {
    (void)NUCLEO_SERIAL.read();
  }
}
static void nucleo_spi_transfer(const uint8_t *tx, uint8_t *rx, size_t len) {
  if (!USE_NUCLEO_SPI || tx == nullptr || rx == nullptr || len == 0) {
    return;
  }
  if (FORCE_SPI_BITBANG) {
    digitalWrite(NUCLEO_SPI_CS, LOW);
    delayMicroseconds(2);
    for (size_t i = 0; i < len; ++i) {
      uint8_t t = tx[i];
      uint8_t r = 0;
      for (int bit = 7; bit >= 0; --bit) {
        digitalWrite(NUCLEO_SPI_MOSI, (t & (1U << bit)) ? HIGH : LOW);
        digitalWrite(NUCLEO_SPI_SCK, HIGH);
        delayMicroseconds(2);
        if (digitalRead(NUCLEO_SPI_MISO)) {
          r |= (uint8_t)(1U << bit);
        }
        digitalWrite(NUCLEO_SPI_SCK, LOW);
        delayMicroseconds(2);
      }
      rx[i] = r;
    }
    digitalWrite(NUCLEO_SPI_CS, HIGH);
    return;
  }
  SPI.beginTransaction(g_spi_settings);
  digitalWrite(NUCLEO_SPI_CS, LOW);
  delayMicroseconds(2);
  for (size_t i = 0; i < len; ++i) {
    rx[i] = SPI.transfer(tx[i]);
  }
  delayMicroseconds(2);
  digitalWrite(NUCLEO_SPI_CS, HIGH);
  SPI.endTransaction();
}
static void nucleo_send_pwm(float d_u, float d_v, float d_w, bool enable, bool force) {
  if (!USE_EXTERNAL_PWM) {
    return;
  }
  uint32_t now = millis();
  uint32_t now_us = micros();
  // When outputs are off we throttle updates to a heartbeat rate,
  // but if a CLEAR is pending we keep sending until it is acknowledged.
  if (!force && !enable && !g_clear_fault_req && (uint32_t)(now - g_nucleo_last_send_ms) < NUCLEO_HEARTBEAT_MS) {
    return;
  }
  if (!force && enable && !g_clear_fault_req && !g_estop_latched && USE_NUCLEO_UART_FALLBACK) {
    nucleo_uart_poll();
    if (g_nucleo_waiting_rsp) {
      if ((uint32_t)(now_us - g_nucleo_last_send_us) < NUCLEO_RUN_REPLY_GUARD_US) {
        return;
      }
      g_nucleo_waiting_rsp = false;
    }
  }
  if (!force && enable && !g_clear_fault_req &&
      (uint32_t)(now_us - g_nucleo_last_send_us) < NUCLEO_RUN_MIN_SEND_US) {
    return;
  }
  uint8_t pkt[20] = {0};
  uint8_t seq = g_nucleo_seq++;
  bool enable_eff = enable;
  bool estop_eff = g_estop_latched;
  bool diag_eff = g_diag_pwm;
  bool clear_eff = g_clear_fault_req;
  uint8_t mode = BP_MODE_OFF;
  uint8_t ext_flags = g_ext_flags;
  uint16_t brake_q15 = g_brake_q15;
  float du_eff = d_u;
  float dv_eff = d_v;
  float dw_eff = d_w;

  // For CLEAR we must send a "safe" frame: MODE OFF + ENABLE=0 + ESTOP=0
  // (see Blue Pill can_clear_fault()).
  if (clear_eff) {
    enable_eff = false;
    estop_eff = false;
    diag_eff = false;
    mode = BP_MODE_OFF;
    ext_flags = 0;
    brake_q15 = 0;
    du_eff = 0.0f;
    dv_eff = 0.0f;
    dw_eff = 0.0f;
  } else if (enable_eff && !estop_eff) {
    mode = diag_eff ? BP_MODE_DIAG : BP_MODE_DUTY;
  }

  uint8_t flags = 0;
  if (enable_eff) flags |= BP_FLAG_ENABLE;
  if (estop_eff) flags |= BP_FLAG_ESTOP;
  if (clear_eff) flags |= BP_FLAG_CLEAR_FAULT;
  if (diag_eff) flags |= BP_FLAG_DIAG_PWM;

  uint16_t du_q15 = q15_unit(du_eff);
  uint16_t dv_q15 = q15_unit(dv_eff);
  uint16_t dw_q15 = q15_unit(dw_eff);

  pkt[0] = 0xAA;
  pkt[1] = 0x55;
  pkt[2] = BP_VER;
  pkt[3] = flags;
  pkt[4] = mode;
  pkt[5] = seq;
  pkt[6] = (uint8_t)(du_q15 & 0xFF);
  pkt[7] = (uint8_t)((du_q15 >> 8) & 0xFF);
  pkt[8] = (uint8_t)(dv_q15 & 0xFF);
  pkt[9] = (uint8_t)((dv_q15 >> 8) & 0xFF);
  pkt[10] = (uint8_t)(dw_q15 & 0xFF);
  pkt[11] = (uint8_t)((dw_q15 >> 8) & 0xFF);
  pkt[12] = 0;
  pkt[13] = 0;
  pkt[14] = ext_flags;
  pkt[15] = (uint8_t)(brake_q15 & 0xFF);
  pkt[16] = (uint8_t)((brake_q15 >> 8) & 0xFF);
  pkt[17] = 0;
  pkt[18] = 0;
  pkt[19] = nucleo_crc8(pkt, 19);
  if (USE_NUCLEO_SPI) {
    uint8_t rx[20] = {0};
    nucleo_spi_transfer(pkt, rx, sizeof(pkt));
    if (nucleo_check_reply(rx)) {
      if (g_nucleo_rx_good < 0xFFFFu) g_nucleo_rx_good++;
      g_nucleo_last_rx_ms = now;
      g_link_led_ms = now;
    } else {
      if (g_nucleo_rx_bad < 0xFFFFu) g_nucleo_rx_bad++;
    }
  }
  if (USE_NUCLEO_UART_FALLBACK) {
    NUCLEO_SERIAL.write(pkt, sizeof(pkt));
    if (enable_eff && !estop_eff && !clear_eff) {
      g_nucleo_waiting_rsp = true;
      g_nucleo_waiting_seq = seq;
    } else {
      g_nucleo_waiting_rsp = false;
    }
    nucleo_uart_poll();
  }
  g_nucleo_last_send_ms = now;
  g_nucleo_last_send_us = now_us;
  g_nucleo_last_tx_ms = now;
}
static void nucleo_send_stop(bool force) {
  nucleo_send_pwm(0.0f, 0.0f, 0.0f, false, force);
}
static void pwm_force_off() {
  if (USE_EXTERNAL_PWM) {
    nucleo_send_stop(true);
    g_pwm_outputs_active = false;
    g_pwm_forced_gpio = false;
    return;
  }
  analogWrite(PWM_UH_PIN, 0);
  analogWrite(PWM_UL_PIN, PWM_LOW_INVERTED ? PWM_FULL : 0);
  analogWrite(PWM_VH_PIN, 0);
  analogWrite(PWM_VL_PIN, PWM_LOW_INVERTED ? PWM_FULL : 0);
  analogWrite(PWM_WH_PIN, 0);
  analogWrite(PWM_WL_PIN, PWM_LOW_INVERTED ? PWM_FULL : 0);
  g_pwm_outputs_active = false;
  g_pwm_forced_gpio = false;
}
static void brake_set(bool on) {
  g_brake_on = on;
  if (BRAKE_ACTIVE_HIGH) {
    digitalWrite(BRAKE_PIN, on ? HIGH : LOW);
  } else {
    digitalWrite(BRAKE_PIN, on ? LOW : HIGH);
  }
}
static void pwm_restore() {
  if (USE_EXTERNAL_PWM) {
    return;
  }
  if (!g_pwm_forced_gpio) {
    return;
  }
  analogWrite(PWM_UH_PIN, 0);
  analogWrite(PWM_UL_PIN, PWM_LOW_INVERTED ? PWM_FULL : 0);
  analogWrite(PWM_VH_PIN, 0);
  analogWrite(PWM_VL_PIN, PWM_LOW_INVERTED ? PWM_FULL : 0);
  analogWrite(PWM_WH_PIN, 0);
  analogWrite(PWM_WL_PIN, PWM_LOW_INVERTED ? PWM_FULL : 0);
  g_pwm_forced_gpio = false;
}
static void pwm_write_phase(uint8_t pin_hi, uint8_t pin_lo, float duty) {
  float hi_on = clampf(duty, 0.0f, 1.0f);
  float hi_pwm = hi_on;
  if (PWM_THREE_PWM_MODE) {
    // High-side PWM only; low-side forced off for safety.
    analogWrite(pin_hi, duty_u8(hi_pwm));
    analogWrite(pin_lo, PWM_LOW_INVERTED ? PWM_FULL : 0);
    return;
  }
  float lo_on = 1.0f - hi_on;
  hi_on = clampf(hi_on - PWM_DEADTIME_DUTY, 0.0f, 1.0f);
  lo_on = clampf(lo_on - PWM_DEADTIME_DUTY, 0.0f, 1.0f);
  hi_pwm = hi_on;
  float lo_pwm = PWM_LOW_INVERTED ? (1.0f - lo_on) : lo_on;
  analogWrite(pin_hi, duty_u8(hi_pwm));
  analogWrite(pin_lo, duty_u8(lo_pwm));
}
static void pwm_write(float d_u, float d_v, float d_w) {
  if (!g_pwm_enabled) {
    if (g_pwm_outputs_active) {
      pwm_force_off();
    }
    // Keep SPI heartbeat even when outputs are disabled.
    if (USE_EXTERNAL_PWM) {
      nucleo_send_pwm(0.0f, 0.0f, 0.0f, false);
    }
    return;
  }
  if (g_duty_mode || g_diag_pwm) {
    d_u = g_duty_u;
    d_v = g_duty_v;
    d_w = g_duty_w;
  }
  if (USE_EXTERNAL_PWM) {
    g_pwm_outputs_active = true;
    nucleo_send_pwm(d_u, d_v, d_w, true);
    return;
  }
  pwm_restore();
  g_pwm_outputs_active = true;
  d_u = clampf(d_u, 0.0f, 1.0f);
  d_v = clampf(d_v, 0.0f, 1.0f);
  d_w = clampf(d_w, 0.0f, 1.0f);
  pwm_write_phase(PWM_UH_PIN, PWM_UL_PIN, d_u);
  pwm_write_phase(PWM_VH_PIN, PWM_VL_PIN, d_v);
  pwm_write_phase(PWM_WH_PIN, PWM_WL_PIN, d_w);
}
static void hard_stop(bool clear_cmd) {
  g_pwm_enabled = false;
  g_state = STATE_SAFE;
  g_stop_requested = false;
  g_start_req = false;
  g_stop_req = false;
  g_mode_switch_pending = false;
  g_restart_after_mode_switch = false;
  g_align_ticks = 0;
  g_freq_ref = 0.0f;
  g_omega_ref = 0.0f;
  g_id_ref = 0.0f;
  g_iq_ref = 0.0f;
  g_id_target = 0.0f;
  g_iq_target = 0.0f;
  g_theta = 0.0f;
  mic_diag_reset();
  g_last_vd = 0.0f;
  g_last_vq = 0.0f;
  if (clear_cmd) {
    g_freq_cmd = 0.0f;
  }
  pwm_force_off();
}
static uint8_t pwm_level(bool on, bool inverted) {
  if (inverted) {
    return on ? 0 : PWM_MAX;
  }
  return on ? PWM_MAX : 0;
}
static void svm(float v_alpha, float v_beta, float vdc, float *d_a, float *d_b, float *d_c) {
  float v_a = v_alpha;
  float v_b = (-0.5f * v_alpha) + (0.8660254f * v_beta);
  float v_c = (-0.5f * v_alpha) - (0.8660254f * v_beta);
  float v_max = v_a;
  if (v_b > v_max) v_max = v_b;
  if (v_c > v_max) v_max = v_c;
  float v_min = v_a;
  if (v_b < v_min) v_min = v_b;
  if (v_c < v_min) v_min = v_c;
  float v_offset = -0.5f * (v_max + v_min);
  v_a += v_offset;
  v_b += v_offset;
  v_c += v_offset;
  float inv_vdc = (vdc > 0.1f) ? (1.0f / vdc) : 0.0f;
  *d_a = 0.5f + (v_a * inv_vdc);
  *d_b = 0.5f + (v_b * inv_vdc);
  *d_c = 0.5f + (v_c * inv_vdc);
  float duty_min = DUTY_MIN;
  float duty_max = DUTY_MAX;
  if (g_stop_requested) {
    duty_min = 0.0f;
    duty_max = 1.0f;
  }
  *d_a = clampf(*d_a, duty_min, duty_max);
  *d_b = clampf(*d_b, duty_min, duty_max);
  *d_c = clampf(*d_c, duty_min, duty_max);
}
static void apply_mode_if_safe() {
  if (g_mode_change_pending && g_state == STATE_SAFE) {
    g_mode = g_mode_pending;
    g_mode_change_pending = false;
  }
}
static void cancel_mode_switch() {
  g_mode_pending = g_mode;
  g_mode_change_pending = false;
  g_mode_switch_pending = false;
  g_mode_switch_deadline_ms = 0;
  g_restart_after_mode_switch = false;
}
static bool should_restart_after_mode_switch() {
  return g_pwm_enabled && !g_stop_req && !g_stop_requested && !g_estop_latched;
}
static void request_mode(ControlMode next_mode, bool duty_mode, bool diag_pwm) {
  bool same_mode = (g_mode == next_mode);
  bool same_flags = (g_duty_mode == duty_mode && g_diag_pwm == diag_pwm);
  g_duty_mode = duty_mode;
  g_diag_pwm = diag_pwm;
  if (g_state == STATE_SAFE) {
    cancel_mode_switch();
    g_mode = next_mode;
    return;
  }
  if (same_mode && same_flags) {
    cancel_mode_switch();
    return;
  }
  schedule_mode_switch(next_mode, should_restart_after_mode_switch());
}
static void schedule_mode_switch(ControlMode next_mode, bool restart_after_switch) {
  g_mode_pending = next_mode;
  g_mode_change_pending = true;
  g_mode_switch_pending = true;
  g_restart_after_mode_switch = restart_after_switch;
  g_mode_switch_deadline_ms = 0;
  g_stop_requested = false;
  g_start_req = false;
  g_stop_req = false;
  g_pwm_enabled = false;
  g_state = STATE_SAFE;
  g_freq_ref = 0.0f;
  g_iq_ref = 0.0f;
  g_id_ref = 0.0f;
  g_theta = 0.0f;
  g_omega_ref = 0.0f;
  mic_diag_reset();
  pwm_force_off();
  apply_mode_if_safe();
}
static float read_vdc() {
  if (USE_EXTERNAL_PWM && g_bp_vbus_ms != 0 &&
      (uint32_t)(millis() - g_bp_vbus_ms) <= BP_VBUS_STALE_MS) {
    return g_bp_vdc;
  }
  uint16_t raw = analogRead(ADC_VDC_PIN);
  float vdc = ((float)raw * VDC_ADC_VREF * VDC_ADC_DIVIDER) / 4095.0f;
  if (vdc < VDC_ADC_MIN_V || vdc > VDC_ADC_MAX_V) {
    return g_vdc;
  }
  return vdc;
}
// ----------------------- Control loop -----------------------
static void control_step() {
  // ADC offsets calibration in SAFE
  if (!g_offset_ready && g_state == STATE_SAFE && !g_pwm_enabled) {
    float ra = (float)analogRead(ADC_IA_PIN);
    float rb = (float)analogRead(ADC_IB_PIN);
    float rc = (float)analogRead(ADC_IC_PIN);
    g_offset_acc_a += ra;
    g_offset_acc_b += rb;
    g_offset_acc_c += rc;
    g_offset_count++;
    if (g_offset_count >= OFFSET_CAL_SAMPLES) {
      g_offset_a = g_offset_acc_a / (float)g_offset_count;
      g_offset_b = g_offset_acc_b / (float)g_offset_count;
      g_offset_c = g_offset_acc_c / (float)g_offset_count;
      g_offset_ready = true;
    }
  }
  float ia = ((float)analogRead(ADC_IA_PIN) - g_offset_a) * CURRENT_GAIN_A_PER_LSB;
  float ib = ((float)analogRead(ADC_IB_PIN) - g_offset_b) * CURRENT_GAIN_A_PER_LSB;
  float ic = 0.0f;
  if (USE_IC_SENSOR) {
    ic = ((float)analogRead(ADC_IC_PIN) - g_offset_c) * CURRENT_GAIN_A_PER_LSB;
  } else {
    ic = -ia - ib;
  }
  g_last_ia = ia;
  g_last_ib = ib;
  g_last_ic = ic;
  g_last_i_rms = sqrtf((ia * ia + ib * ib + ic * ic) / 3.0f);
  if (g_offset_ready && g_pwm_enabled) {
    if (fabsf(ia) > CURRENT_LIMIT_A || fabsf(ib) > CURRENT_LIMIT_A || fabsf(ic) > CURRENT_LIMIT_A) {
      g_fault = 1;
      hard_stop(false);
      ext_brake_set(0.0f);
      pwm_write(0, 0, 0);
      return;
    }
  }
  if (g_estop_latched) {
    brake_set(false);
    hard_stop(false);
    ext_brake_set(0.0f);
    estop_auto_clear_tick();
    pwm_write(0, 0, 0);
    return;
  }
  uint32_t now_ms = millis();
  if (bp_fault_or_timeout(now_ms)) {
    g_fault = (g_bp_fault_code != 0) ? g_bp_fault_code : 3;
    brake_set(false);
    hard_stop(false);
    ext_brake_set(0.0f);
    pwm_write(0, 0, 0);
    return;
  }
  if (g_toggle_req) {
    g_toggle_req = false;
    if (g_state == STATE_SAFE) g_start_req = true;
    else g_stop_req = true;
  }
  if (g_stop_req) {
    g_stop_req = false;
    g_stop_requested = true;
    g_freq_cmd = 0.0f;
    g_iq_target = 0.0f;
  }
  // Auto-stop if target frequency is zero while PWM is enabled
  if (g_pwm_enabled && g_freq_cmd < 0.1f && !g_duty_mode && !g_diag_pwm) {
    g_stop_requested = true;
  }
  if (g_start_req) {
    g_start_req = false;
    if (g_state == STATE_SAFE) {
      brake_set(true);
      g_stop_requested = false;
      g_freq_ref = 0.0f;
      g_theta = 0.0f;
      g_pwm_enabled = true;
      if (g_mode == MODE_VF) {
        g_state = STATE_VF_RUN;
      } else {
        g_state = STATE_FOC_ALIGN;
        g_align_ticks = (uint32_t)((ALIGN_TIME_MS * CONTROL_HZ) / 1000.0f);
        g_id_target = ALIGN_ID_REF_A;
        g_iq_target = 0.0f;
        g_id_ref = 0.0f;
        g_iq_ref = 0.0f;
      }
    }
  }
  apply_mode_if_safe();
  if (g_state == STATE_SAFE && !g_pwm_enabled) {
    if (g_stop_requested) {
      brake_set(true);
    }
    if (g_pwm_outputs_active) {
      pwm_force_off();
    }
    if (g_mode_switch_pending) {
      if (g_mode_switch_deadline_ms == 0) {
        g_mode_switch_deadline_ms = now_ms + MODE_SWITCH_DEADTIME_MS;
      }
      if ((int32_t)(now_ms - g_mode_switch_deadline_ms) >= 0) {
        g_mode_switch_pending = false;
        g_mode_switch_deadline_ms = 0;
        if (g_restart_after_mode_switch && !g_estop_latched) {
          if (g_freq_cmd < 0.1f && g_last_nonzero_freq > 0.1f) {
            g_freq_cmd = g_last_nonzero_freq;
          }
          g_start_req = true;
        }
        g_restart_after_mode_switch = false;
      }
    }
    g_freq_ref = 0.0f;
    g_omega_ref = 0.0f;
    g_id_ref = 0.0f;
    g_iq_ref = 0.0f;
    mic_diag_reset();
    g_last_vd = 0.0f;
    g_last_vq = 0.0f;
    return;
  }
  float i_alpha = ia;
  float i_beta = (ia + (2.0f * ib)) * INV_SQRT3;
  float sin_t = sinf(g_theta);
  float cos_t = cosf(g_theta);
  float id = (i_alpha * cos_t) + (i_beta * sin_t);
  float iq = (-i_alpha * sin_t) + (i_beta * cos_t);
  g_last_id = id;
  g_last_iq = iq;
  float vd = 0.0f;
  float vq = 0.0f;
  float v_alpha = 0.0f;
  float v_beta = 0.0f;
  if (g_state == STATE_FOC_ALIGN) {
    mic_diag_reset();
    if (g_align_ticks > 0) g_align_ticks--;
    if (g_align_ticks == 0) {
      g_state = STATE_FOC_RUN;
      g_id_target = RUN_ID_REF_A;
      g_iq_target = RUN_IQ_REF_A;
    }
    g_theta = 0.0f;
    g_omega_ref = 0.0f;
    g_id_ref = ramp_toward(g_id_ref, g_id_target, IQ_RAMP_STEP);
    g_iq_ref = 0.0f;
    vd = pi_run(&g_pi_id, g_id_ref - id, CONTROL_DT);
    vq = pi_run(&g_pi_iq, g_iq_ref - iq, CONTROL_DT);
    float v_mag = sqrtf(vd * vd + vq * vq);
    if (v_mag > g_v_limit && v_mag > 0.0f) {
      float scale = g_v_limit / v_mag;
      vd *= scale;
      vq *= scale;
    }
    v_alpha = (vd * cos_t) - (vq * sin_t);
    v_beta = (vd * sin_t) + (vq * cos_t);
  } else if (g_state == STATE_FOC_RUN) {
    g_freq_ref = ramp_toward(g_freq_ref, g_freq_cmd, FREQ_RAMP_STEP);
    g_omega_ref = CTRL_TWO_PI * g_freq_ref;
    if (g_stop_requested) {
      mic_diag_reset();
      g_id_target = 0.0f;
      g_iq_target = 0.0f;
    } else if (g_mode == MODE_MIC) {
      float load_pu = fabsf(g_last_iq) / (MIC_IQ_NOM_A > 1e-6f ? MIC_IQ_NOM_A : 1.0f);
      if (load_pu > 1.0f) load_pu = 1.0f;
      uint32_t now_ms = millis();
      bool enc_used = false;
      float freq_meas = mic_feedback_elec_hz(now_ms, &enc_used);
      float freq_ref_abs = fabsf(g_freq_ref);
      float freq_ramp_err = fabsf(g_freq_cmd - g_freq_ref);
      float freq_track_err = fabsf(freq_ref_abs - freq_meas);
      float freq_err = (freq_track_err > freq_ramp_err) ? freq_track_err : freq_ramp_err;
      float speed_tol = MIC_FREQ_TOL_HZ;
      float rel_tol = fabsf(g_freq_ref) * MIC_FREQ_TOL_REL;
      if (rel_tol > speed_tol) {
        speed_tol = rel_tol;
      }
      if (enc_used) {
        float slip_tol = MIC_SLIP_GATE_HZ + (fabsf(g_freq_ref) * MIC_SLIP_GATE_REL);
        if (slip_tol > speed_tol) {
          speed_tol = slip_tol;
        }
      }
      int16_t speed_err_q10 = (int16_t)(freq_err * 1024.0f);
      int16_t speed_tol_q10 = (int16_t)(speed_tol * 1024.0f);
      int16_t id_ref_cmd_q10 = (int16_t)unoq_motor1_id_ref_query(g_omega_ref, load_pu);
      int16_t id_ref_base_q10 = (int16_t)(RUN_ID_REF_A * 1024.0f);
      uint16_t status = (uint16_t)g_fault;
      uint16_t link_flags = mic_link_flags(now_ms);
      unoq_gate_result_t gate = unoq_apply_gates(
          speed_err_q10,
          speed_tol_q10,
          status,
          link_flags,
          id_ref_base_q10,
          id_ref_cmd_q10,
          1u,
          1u);
      g_mic_enc_used = enc_used;
      g_mic_freq_meas_hz = freq_meas;
      g_mic_speed_err_hz = freq_err;
      g_mic_speed_tol_hz = speed_tol;
      g_mic_link_flags = link_flags;
      g_mic_status_flags = status;
      g_mic_gated = gate.gated;
      g_mic_enable_ai = gate.enable_ai;
      int16_t id_ref_target_q10 = gate.id_ref_q10;
      int16_t step_q10 = (int16_t)(MIC_ID_RATE_LIMIT_A_PER_S * CONTROL_DT * 1024.0f);
      if (step_q10 < 1) step_q10 = 1;
      g_mic_id_ref_q10 = unoq_rate_limit(g_mic_id_ref_q10, id_ref_target_q10, step_q10);
      float id_ref_cmd = (float)g_mic_id_ref_q10 / 1024.0f;
      id_ref_cmd = clampf(id_ref_cmd, MIC_ID_MIN_A, MIC_ID_MAX_A);
      g_mic_id_ref = id_ref_cmd;
      g_mic_active = (gate.enable_ai != 0u) && (gate.gated == 0u) && (fabsf(g_freq_ref) >= MIC_FREQ_MIN_HZ);
      g_id_target = id_ref_cmd;
      g_iq_target = RUN_IQ_REF_A;
    } else {
      mic_diag_reset();
      g_id_target = RUN_ID_REF_A;
      g_iq_target = RUN_IQ_REF_A;
    }
    g_id_ref = ramp_toward(g_id_ref, g_id_target, IQ_RAMP_STEP);
    g_iq_ref = ramp_toward(g_iq_ref, g_iq_target, IQ_RAMP_STEP);
    g_theta += g_omega_ref * CONTROL_DT;
    if (g_theta > CTRL_TWO_PI) g_theta -= CTRL_TWO_PI;
    if (g_theta < 0.0f) g_theta += CTRL_TWO_PI;
    if (g_stop_requested) {
      if (fabsf(g_iq_ref) < 0.05f && g_freq_ref < 0.5f) {
        g_state = STATE_SAFE;
        g_stop_requested = false;
        g_pwm_enabled = false;
        g_id_ref = 0.0f;
        g_iq_ref = 0.0f;
        g_theta = 0.0f;
      }
    }
    vd = pi_run(&g_pi_id, g_id_ref - id, CONTROL_DT);
    vq = pi_run(&g_pi_iq, g_iq_ref - iq, CONTROL_DT);
    float v_mag = sqrtf(vd * vd + vq * vq);
    if (v_mag > g_v_limit && v_mag > 0.0f) {
      float scale = g_v_limit / v_mag;
      vd *= scale;
      vq *= scale;
    }
    v_alpha = (vd * cos_t) - (vq * sin_t);
    v_beta = (vd * sin_t) + (vq * cos_t);
  } else if (g_state == STATE_VF_RUN) {
    mic_diag_reset();
    g_freq_ref = ramp_toward(g_freq_ref, g_freq_cmd, FREQ_RAMP_STEP);
    g_omega_ref = CTRL_TWO_PI * g_freq_ref;
    g_theta += g_omega_ref * CONTROL_DT;
    if (g_theta > CTRL_TWO_PI) g_theta -= CTRL_TWO_PI;
    if (g_theta < 0.0f) g_theta += CTRL_TWO_PI;
    float freq_abs = fabsf(g_freq_ref);
    float boost_v = 0.0f;
    if (freq_abs >= VF_START_BOOST_MIN_FREQ_HZ) {
      float boost_taper = 1.0f - clampf(freq_abs / VF_START_BOOST_TAPER_HZ, 0.0f, 1.0f);
      boost_v = g_vf_start_boost_v * boost_taper;
    }
    float v_mag = (g_vf_v_per_hz * g_freq_ref) + boost_v;
    v_mag = clampf(v_mag, 0.0f, g_v_limit);
    v_alpha = v_mag * cos_t;
    v_beta = v_mag * sin_t;
    if (g_stop_requested && g_freq_ref < 0.5f) {
      g_state = STATE_SAFE;
      g_stop_requested = false;
      g_pwm_enabled = false;
      g_theta = 0.0f;
      g_omega_ref = 0.0f;
    }
  } else if (g_state == STATE_SAFE) {
    mic_diag_reset();
    g_id_ref = 0.0f;
    g_iq_ref = 0.0f;
    g_omega_ref = 0.0f;
    g_theta = 0.0f;
    g_freq_ref = 0.0f;
  }
  float d_a = 0.5f, d_b = 0.5f, d_c = 0.5f;
  if (g_state == STATE_FOC_ALIGN || g_state == STATE_FOC_RUN || g_state == STATE_VF_RUN) {
    svm(v_alpha, v_beta, g_vdc, &d_a, &d_b, &d_c);
  }
  if (g_stop_requested && g_freq_ref < 1.0f) {
    d_a = 0.5f;
    d_b = 0.5f;
    d_c = 0.5f;
  }
  if (g_pwm_enabled && (g_state == STATE_FOC_ALIGN || g_state == STATE_FOC_RUN || g_state == STATE_VF_RUN)) {
    pwm_write(d_a, d_b, d_c);
  } else {
    pwm_write(0, 0, 0);
  }
  g_last_vd = vd;
  g_last_vq = vq;
  (void)ic;
}
static void update_led() {
  bool running = g_pwm_enabled && (fabsf(g_freq_ref) > 0.5f) && !g_estop_latched;
  if (!running) {
    if (g_led_on) {
      g_led_on = false;
      digitalWrite(LED_PIN, LOW);
    }
    return;
  }
  uint32_t now = millis();
  uint32_t period_ms = 250; // run blink only
  if ((uint32_t)(now - g_led_tick) >= period_ms) {
    g_led_tick = now;
    g_led_on = !g_led_on;
    digitalWrite(LED_PIN, g_led_on ? HIGH : LOW);
  }
}
static void matrix_init() {
  if (g_matrix_ready) {
    return;
  }
  g_matrix.begin();
  memset(g_matrix_pixels, 0, sizeof(g_matrix_pixels));
  memset(g_matrix_frame, 0, sizeof(g_matrix_frame));
  matrixWrite(g_matrix_frame);
  g_matrix_ready = true;
}
static void matrix_update() {
  if (!g_matrix_ready) {
    return;
  }
  uint32_t now = millis();
  if ((uint32_t)(now - g_matrix_last_ms) < 200U) {
    return;
  }
  g_matrix_last_ms = now;
    float freq = g_freq_ref;
    if (fabsf(freq) < 0.05f) {
      freq = 0.0f;
    }
    if (freq < 0.0f) {
      freq = 0.0f;
    }
  int freq10 = (int)(freq * 10.0f + 0.5f);
  if (freq10 < 0) freq10 = 0;
  if (freq10 > 999) freq10 = 999;
  int tens = (freq10 / 100) % 10;
  int ones = (freq10 / 10) % 10;
  int tenths = freq10 % 10;
  memset(g_matrix_pixels, 0, sizeof(g_matrix_pixels));
  int x0 = 1;
  int y0 = 1;
  if (freq10 >= 100) {
    matrix_draw_digit(x0, y0, tens);
  }
  matrix_draw_digit(x0 + 4, y0, ones);
  matrix_draw_digit(x0 + 8, y0, tenths);
  // Decimal point between ones and tenths (make it 2 pixels tall for visibility).
  matrix_set_pixel(x0 + 7, y0 + 4);
  matrix_set_pixel(x0 + 7, y0 + 5);
  Arduino_LED_Matrix::loadPixelsToBuffer(g_matrix_pixels, sizeof(g_matrix_pixels), g_matrix_frame);
  uint32_t out[4] = {
    reverse(g_matrix_frame[0]),
    reverse(g_matrix_frame[1]),
    reverse(g_matrix_frame[2]),
    reverse(g_matrix_frame[3])
  };
  matrixWrite(out);
}
static void matrix_set_pixel(int x, int y) {
  if (x < 0 || x >= MATRIX_W || y < 0 || y >= MATRIX_H) {
    return;
  }
  g_matrix_pixels[y * MATRIX_W + x] = 1;
}
static void matrix_draw_digit(int x0, int y0, int digit) {
  if (digit < 0 || digit > 9) {
    return;
  }
  for (int y = 0; y < 5; y++) {
    uint8_t row = DIGIT_3X5[digit][y];
    for (int x = 0; x < 3; x++) {
      if (row & (1 << (2 - x))) {
        matrix_set_pixel(x0 + x, y0 + y);
      }
    }
  }
}
static void handle_button() {
  bool pressed = (digitalRead(BUTTON_PIN) == LOW);
  uint32_t now = millis();
  if (pressed && (now - g_last_button_ms) > 150) {
    g_last_button_ms = now;
    g_toggle_req = true;
    bridge_notify_line(String("LOG BUTTON"));
  }
}
// ----------------------- Setup / Loop -----------------------
#if UART_ECHO_TEST
void setup() {
#if PIN_TOGGLE_TEST
  pinMode(0, OUTPUT);   // D0 / PB7
  pinMode(1, OUTPUT);   // D1 / PB6
  pinMode(3, OUTPUT);   // D3 / PB0
  pinMode(6, OUTPUT);   // D6 / PB1
  pinMode(9, OUTPUT);   // D9 / PB8
  pinMode(10, OUTPUT);  // D10 / PB9
  pinMode(13, OUTPUT);  // D13 / PB13
  pinMode(LED3_R, OUTPUT);
  pinMode(LED3_G, OUTPUT);
  pinMode(LED3_B, OUTPUT);
  pinMode(LED4_R, OUTPUT);
  pinMode(LED4_G, OUTPUT);
  pinMode(LED4_B, OUTPUT);
#else
  Serial.begin(RPC_BAUD);
#endif
#if UART_TEST_SERIAL1
  LOG_SERIAL.begin(RPC_BAUD);
#endif
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
}
void loop() {
  static uint32_t last_ping = 0;
  static uint32_t last_uart1 = 0;
  static uint32_t last_blink = 0;
  static bool led_state = false;
  static uint32_t last_d1 = 0;
  static uint32_t last_d3 = 0;
  static uint32_t last_d6 = 0;
  static uint32_t last_d9 = 0;
  static uint32_t last_d10 = 0;
  static uint32_t last_d0 = 0;
  static uint32_t last_d13 = 0;
  static bool d0_state = false;
  static bool d1_state = false;
  static bool d3_state = false;
  static bool d6_state = false;
  static bool d9_state = false;
  static bool d10_state = false;
  static bool d13_state = false;
  static uint32_t last_rgb = 0;
  static uint8_t rgb_idx = 0;
  uint32_t now = millis();
#if UART_TEST_SERIAL1
  if ((uint32_t)(now - last_uart1) >= 1000U) {
    last_uart1 = now;
    LOG_SERIAL.println("S1");
  }
#endif
#if !PIN_TOGGLE_TEST
  if ((uint32_t)(now - last_ping) >= 1000U) {
    last_ping = now;
    Serial.println("S0");
  }
#endif
  if ((uint32_t)(now - last_blink) >= 500U) {
    last_blink = now;
    led_state = !led_state;
    digitalWrite(LED_PIN, led_state ? HIGH : LOW);
  }
#if PIN_TOGGLE_TEST
  if ((uint32_t)(now - last_d1) >= 200U) {
    last_d1 = now;
    d1_state = !d1_state;
    digitalWrite(1, d1_state ? HIGH : LOW);
  }
  if ((uint32_t)(now - last_d0) >= 150U) {
    last_d0 = now;
    d0_state = !d0_state;
    digitalWrite(0, d0_state ? HIGH : LOW);
  }
  if ((uint32_t)(now - last_d3) >= 300U) {
    last_d3 = now;
    d3_state = !d3_state;
    digitalWrite(3, d3_state ? HIGH : LOW);
  }
  if ((uint32_t)(now - last_d6) >= 800U) {
    last_d6 = now;
    d6_state = !d6_state;
    digitalWrite(6, d6_state ? HIGH : LOW);
  }
  if ((uint32_t)(now - last_d9) >= 650U) {
    last_d9 = now;
    d9_state = !d9_state;
    digitalWrite(9, d9_state ? HIGH : LOW);
  }
  if ((uint32_t)(now - last_d10) >= 900U) {
    last_d10 = now;
    d10_state = !d10_state;
    digitalWrite(10, d10_state ? HIGH : LOW);
  }
  if ((uint32_t)(now - last_d13) >= 1000U) {
    last_d13 = now;
    d13_state = !d13_state;
    digitalWrite(13, d13_state ? HIGH : LOW);
  }
  if ((uint32_t)(now - last_rgb) >= 300U) {
    last_rgb = now;
    digitalWrite(LED3_R, LOW);
    digitalWrite(LED3_G, LOW);
    digitalWrite(LED3_B, LOW);
    digitalWrite(LED4_R, LOW);
    digitalWrite(LED4_G, LOW);
    digitalWrite(LED4_B, LOW);
    switch (rgb_idx % 6) {
      case 0: digitalWrite(LED3_R, HIGH); break;
      case 1: digitalWrite(LED3_G, HIGH); break;
      case 2: digitalWrite(LED3_B, HIGH); break;
      case 3: digitalWrite(LED4_R, HIGH); break;
      case 4: digitalWrite(LED4_G, HIGH); break;
      default: digitalWrite(LED4_B, HIGH); break;
    }
    rgb_idx++;
  }
#else
  if (Serial.available() > 0) {
    int c = Serial.read();
    Serial.write((uint8_t)c);
  }
#endif
}
#else
// ----------------------- Setup / Loop -----------------------
void setup() {
#if USE_ROUTER_BRIDGE
    delay(6000);
    Bridge.begin(RPC_BAUD);
    LOG_SERIAL.begin(RPC_BAUD);
    LOG_SERIAL.println("LOG BOOT");
#else
    LOG_SERIAL.begin(RPC_BAUD);
#if USE_MSGPACK_RPC
    rpc_send_reset();
    rpc_send_register("cmd");
    rpc_send_register("get");
    rpc_send_mon_write("LOG BOOT");
#endif
#endif
  // Serial1 is owned by RouterBridge (/dev/ttyHS1). Do not re-init it here.
  // When RouterBridge is disabled, we can use UI_SERIAL as a plain-text command port.
#if !USE_ROUTER_BRIDGE && !USE_MSGPACK_RPC
    UI_SERIAL.begin(RPC_BAUD);
#endif
    nucleo_uart_init();
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  // Kick a first SPI TX so we can see activity immediately.
  if (USE_EXTERNAL_PWM) {
    nucleo_send_pwm(0.0f, 0.0f, 0.0f, false);
    g_nucleo_last_tx_ms = millis();
  }
  pinMode(BRAKE_PIN, OUTPUT);
  brake_set(true);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
#if defined(ARDUINO_ARCH_ZEPHYR)
  analogReadResolution(12);
  analogWriteResolution(8);
#endif
  matrix_init();
  pwm_force_off();
  g_vdc = VDC_NOMINAL;
  g_v_limit = 0.577f * g_vdc;
  g_vf_v_per_hz = (g_vdc * g_vf_volt_per_hz_ratio) / VF_BASE_FREQ_HZ;
  pi_init(&g_pi_id, 2.0f, 200.0f, -g_v_limit, g_v_limit);
  pi_init(&g_pi_iq, 2.0f, 200.0f, -g_v_limit, g_v_limit);
  g_last_control_us = micros();
}
void loop() {
  handle_button();
  if (USE_EXTERNAL_PWM && !USE_NUCLEO_SPI && USE_NUCLEO_UART_FALLBACK) {
    nucleo_uart_poll();
  }
  // One-shot selftest: VF -> FOC -> STOP
  if (SELFTEST_ON_BOOT && g_selftest_step < 3) {
    uint32_t now = millis();
    if (g_selftest_step == 0) {
      g_estop_latched = false;
      g_mode = MODE_VF;
      g_freq_cmd = 10.0f;
      g_pwm_enabled = true;
      g_state = STATE_VF_RUN;
      g_selftest_ms = now;
      g_selftest_step = 1;
    } else if (g_selftest_step == 1 && (uint32_t)(now - g_selftest_ms) > 1500U) {
      g_mode = MODE_FOC;
      g_state = STATE_FOC_ALIGN;
      g_align_ticks = (uint32_t)((ALIGN_TIME_MS * CONTROL_HZ) / 1000.0f);
      g_id_target = ALIGN_ID_REF_A;
      g_iq_target = 0.0f;
      g_id_ref = 0.0f;
      g_iq_ref = 0.0f;
      g_selftest_ms = now;
      g_selftest_step = 2;
    } else if (g_selftest_step == 2 && (uint32_t)(now - g_selftest_ms) > 1500U) {
      g_pwm_enabled = false;
      g_state = STATE_SAFE;
      g_selftest_step = 3;
    }
  }
  // Link LED: fast blink on valid RX, slow blink on TX only.
  uint32_t now_ms = millis();
  if ((uint32_t)(now_ms - g_nucleo_last_rx_ms) < 500U) {
    if ((uint32_t)(now_ms - g_led_tick) >= 150U) {
      g_led_tick = now_ms;
      g_link_led_state = !g_link_led_state;
      digitalWrite(LED_PIN, g_link_led_state ? HIGH : LOW);
    }
  } else if ((uint32_t)(now_ms - g_nucleo_last_tx_ms) < 500U) {
    if ((uint32_t)(now_ms - g_led_tick) >= 500U) {
      g_led_tick = now_ms;
      g_link_led_state = !g_link_led_state;
      digitalWrite(LED_PIN, g_link_led_state ? HIGH : LOW);
    }
  } else {
    digitalWrite(LED_PIN, LOW);
  }
  if (g_pwm_test) {
    g_pwm_enabled = true;
    pwm_write(g_pwm_test_duty, g_pwm_test_duty, g_pwm_test_duty);
  } else if (!g_scope_test) {
    uint32_t now_us = micros();
    if ((uint32_t)(now_us - g_last_control_us) >= CONTROL_US) {
      g_last_control_us += CONTROL_US;
      g_vdc = read_vdc();
      g_v_limit = 0.577f * g_vdc;
      g_vf_v_per_hz = (g_vdc * g_vf_volt_per_hz_ratio) / VF_BASE_FREQ_HZ;
      control_step();
    }
    }
    update_led();
    matrix_update();
    if (USE_EXTERNAL_PWM) {
      uint32_t now = millis();
      if (!g_pwm_enabled && (uint32_t)(now - g_nucleo_keepalive_ms) >= 100) {
        g_nucleo_keepalive_ms = now;
        // Keepalive only when PWM disabled (do not spam disable while running).
        nucleo_send_pwm(0.0f, 0.0f, 0.0f, false);
      }
      if (!USE_NUCLEO_SPI && USE_NUCLEO_UART_FALLBACK) {
        nucleo_uart_poll();
      }
    }
    if (g_scope_test) {
      scope_tick();
    }
  #if USE_ROUTER_BRIDGE
  bridge_tick();
  #endif
  #if !USE_ROUTER_BRIDGE
#if USE_MSGPACK_RPC
  rpc_poll();
  rpc_service();
#else
  rpc_service();
  serial_poll();
#endif
  #endif
  send_telemetry();
#if defined(ARDUINO_ARCH_ZEPHYR)
  k_yield();
#endif
}
#endif
