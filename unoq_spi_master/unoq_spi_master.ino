#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>
#include "Arduino_LED_Matrix.h"

#define USE_SOFTSERIAL 0
#define ARDUINO_ECHO 0
#define LINK_BLUEPILL 1
#define USE_TEXT_RPC 1
#define USE_MATRIX 1

#define RPC_SERIAL Serial1
#define RPC_BAUD 115200

#if USE_SOFTSERIAL
#include <SoftwareSerial.h>
static const uint8_t SOFT_RX_PIN = 10;
static const uint8_t SOFT_TX_PIN = 11;
SoftwareSerial SerialPort(SOFT_RX_PIN, SOFT_TX_PIN);
#else
#define SerialPort Serial
#endif

static const uint8_t RESP_PIN = 8; // toggles on any RX payload (D8)
static const uint8_t HB_PIN = 9;   // heartbeat 1 Hz (D9)

// MCU RGB LEDs (per UNO Q datasheet)
#ifndef LED3_R
#define LED3_R LED_BUILTIN
#endif
#ifndef LED3_G
#define LED3_G LED_BUILTIN
#endif
#ifndef LED3_B
#define LED3_B LED_BUILTIN
#endif
#ifndef LED4_R
#define LED4_R LED_BUILTIN
#endif
#ifndef LED4_G
#define LED4_G LED_BUILTIN
#endif
#ifndef LED4_B
#define LED4_B LED_BUILTIN
#endif

static const uint8_t HB_LED_R = LED3_R;
static const uint8_t HB_LED_G = LED3_G;
static const uint8_t HB_LED_B = LED3_B;
static const uint8_t RX_LED_R = LED4_R;
static const uint8_t RX_LED_G = LED4_G;
static const uint8_t RX_LED_B = LED4_B;

static const uint32_t UART_BAUD = 115200;

#if USE_MATRIX
Arduino_LED_Matrix matrix;
static uint8_t matrix_buf[8][13];
static uint32_t last_matrix_ms = 0;
static const uint8_t digit_rows[10][5] = {
  {0x7, 0x5, 0x5, 0x5, 0x7}, // 0
  {0x2, 0x6, 0x2, 0x2, 0x7}, // 1
  {0x7, 0x1, 0x7, 0x4, 0x7}, // 2
  {0x7, 0x1, 0x7, 0x1, 0x7}, // 3
  {0x5, 0x5, 0x7, 0x1, 0x1}, // 4
  {0x7, 0x4, 0x7, 0x1, 0x7}, // 5
  {0x7, 0x4, 0x7, 0x5, 0x7}, // 6
  {0x7, 0x1, 0x2, 0x2, 0x2}, // 7
  {0x7, 0x5, 0x7, 0x5, 0x7}, // 8
  {0x7, 0x5, 0x7, 0x1, 0x7}, // 9
};

static void matrix_clear_buf(void) {
  memset(matrix_buf, 0, sizeof(matrix_buf));
}

static void matrix_set_px(int x, int y, bool on) {
  if (x < 0 || x >= 13 || y < 0 || y >= 8) return;
  matrix_buf[y][x] = on ? 1 : 0;
}

static void matrix_draw_digit(int digit, int x, int y) {
  if (digit < 0 || digit > 9) return;
  for (int row = 0; row < 5; ++row) {
    uint8_t bits = digit_rows[digit][row];
    for (int col = 0; col < 3; ++col) {
      bool on = (bits & (1 << (2 - col))) != 0;
      matrix_set_px(x + col, y + row, on);
    }
  }
}

static void matrix_draw_freq_tenths(uint16_t tenths) {
  const int digit_w = 3;
  const int digit_h = 5;
  const int gap = 1;
  const int total_w = digit_w * 3 + gap * 2;
  const int start_x = (13 - total_w) / 2;
  const int start_y = (8 - digit_h) / 2;

  if (tenths > 999) tenths = 999;
  uint16_t int_part = (uint16_t)(tenths / 10);
  uint8_t frac = (uint8_t)(tenths % 10);

  matrix_clear_buf();

  if (int_part >= 100) {
    uint8_t d0 = (uint8_t)(int_part / 100);
    uint8_t d1 = (uint8_t)((int_part / 10) % 10);
    uint8_t d2 = (uint8_t)(int_part % 10);
    matrix_draw_digit(d0, start_x, start_y);
    matrix_draw_digit(d1, start_x + digit_w + gap, start_y);
    matrix_draw_digit(d2, start_x + 2 * (digit_w + gap), start_y);
  } else {
    uint8_t d1 = (uint8_t)(int_part / 10);
    uint8_t d2 = (uint8_t)(int_part % 10);
    uint8_t d3 = frac;
    if (int_part >= 10) {
      matrix_draw_digit(d1, start_x, start_y);
    }
    matrix_draw_digit(d2, start_x + digit_w + gap, start_y);
    matrix_draw_digit(d3, start_x + 2 * (digit_w + gap), start_y);
    // decimal point between ones and tenths
    int dot_x = start_x + digit_w + gap + digit_w;
    int dot_y = start_y + digit_h - 1;
    matrix_set_px(dot_x, dot_y, true);
    matrix_set_px(dot_x, dot_y - 1, true);
  }

  matrix.loadPixels(&matrix_buf[0][0], sizeof(matrix_buf));
}
#endif

#if LINK_BLUEPILL
static const uint16_t FRAME_LEN = 32;
static const uint8_t CRC_OFF = FRAME_LEN - 1;
static const uint8_t CMD_HDR0 = 0xAA;
static const uint8_t CMD_HDR1 = 0x55;
static const uint8_t RSP_HDR0 = 0x55;
static const uint8_t RSP_HDR1 = 0xAA;
static const uint8_t FLAG_ENABLE = 0x01;
static const uint8_t FLAG_ESTOP = 0x02;
static const uint8_t FLAG_DIAG_PWM = 0x04;
static const uint8_t FLAG_CLEAR_FAULT = 0x08;
static const uint8_t FLAG_VECTOR_ROTATE = 0x10;
static const uint8_t FLAG_EXT_NTC = 0x01;
static const uint8_t FLAG_EXT_PFC = 0x02;
static const uint8_t FLAG_EXT_BRAKE_PWM = 0x04;
static const uint8_t MODE_OFF = 0;
static const uint8_t MODE_DIAG = 1;
static const uint8_t MODE_DUTY = 2;
static const uint8_t MODE_SCALAR = 3;
static const uint8_t MODE_VECTOR = 4;
static const uint8_t MODE_FOC = 5;
static const uint8_t STATUS_ENABLED = 0x02;
static const uint8_t STATUS_ESTOP = 0x04;
static const uint8_t STATUS_FAULT = 0x08;
static const uint8_t STATUS_TIMEOUT = 0x10;
static const uint8_t STATUS_PWM_ACTIVE = 0x20;
static const uint32_t TX_INTERVAL_MS = 20;
static const float DEFAULT_FREQ_HZ = 5.0f;

static uint8_t tx_frame[FRAME_LEN];
static uint8_t rx_frame[FRAME_LEN];
static uint8_t rx_state = 0;
static uint8_t rx_idx = 0;
static uint8_t seq = 0;
static bool sent_clear = false;
static uint32_t last_tx = 0;
static uint32_t last_rx_ms = 0;
static uint8_t last_status = 0;
static uint8_t last_fault = 0;
static uint8_t last_mode = MODE_OFF;
static uint8_t last_ext_flags = 0;
static uint16_t last_brake_q15 = 0;
static uint16_t last_temp_raw = 0;
static uint8_t last_temp_flags = 0;
static uint16_t last_phase_a_raw = 0;
static uint16_t last_phase_b_raw = 0;
static uint16_t last_phase_c_raw = 2048;
static uint8_t last_phase_flags = 0;
static uint16_t last_good = 0;
static uint16_t last_bad = 0;
static bool clear_fault_pending = false;
static bool have_reply = false;
static uint8_t cmd_flags = 0;
static uint8_t cmd_mode = MODE_OFF;
static uint32_t cmd_freq_millihz = 0;
static uint32_t cmd_foc_freq_millihz = 0;
static uint16_t cmd_vmag_q15 = 0;
static int16_t cmd_valpha_q15 = 0;
static int16_t cmd_vbeta_q15 = 0;
static int16_t cmd_id_q15 = 0;
static int16_t cmd_iq_q15 = 0;
static uint16_t cmd_du_q15 = 0;
static uint16_t cmd_dv_q15 = 0;
static uint16_t cmd_dw_q15 = 0;
static uint8_t cmd_ext_flags = 0;
static uint16_t cmd_brake_q15 = 0;
static float cmd_freq_hz = 0.0f;
static float cmd_mag = 0.3f;
static uint32_t last_cmd_ms = 0;
#else
static const uint32_t PING_INTERVAL_MS = 250;
static char rx_line[64];
static uint8_t rx_len = 0;
static uint32_t ping_counter = 0;
static uint32_t last_ping = 0;
#endif

#if USE_TEXT_RPC
static char rpc_line[128];
static uint8_t rpc_len = 0;
#endif

static void blink_rx_led(void) {
  static uint8_t s = 0;
  s ^= 1;
  digitalWrite(RESP_PIN, s);
  digitalWrite(RX_LED_R, s);
  digitalWrite(RX_LED_G, s);
  digitalWrite(RX_LED_B, s);
}

#if LINK_BLUEPILL
static uint8_t crc_xor(const uint8_t *buf, uint8_t len) {
  uint8_t c = 0;
  for (uint8_t i = 0; i < len; ++i) c ^= buf[i];
  return c;
}

static int16_t q15_from_float(float v) {
  if (v < -1.0f) v = -1.0f;
  if (v > 1.0f) v = 1.0f;
  int32_t q = (int32_t)(v * 32767.0f);
  if (q < -32768) q = -32768;
  if (q > 32767) q = 32767;
  return (int16_t)q;
}

static uint16_t q15_from_unit(float v) {
  if (v < 0.0f) v = 0.0f;
  if (v > 1.0f) v = 1.0f;
  int32_t q = (int32_t)(v * 32767.0f);
  if (q < 0) q = 0;
  if (q > 32767) q = 32767;
  return (uint16_t)q;
}

static void set_u16(uint8_t *buf, uint16_t v) {
  buf[0] = (uint8_t)(v & 0xFF);
  buf[1] = (uint8_t)((v >> 8) & 0xFF);
}

static void set_u32(uint8_t *buf, uint32_t v) {
  buf[0] = (uint8_t)(v & 0xFF);
  buf[1] = (uint8_t)((v >> 8) & 0xFF);
  buf[2] = (uint8_t)((v >> 16) & 0xFF);
  buf[3] = (uint8_t)((v >> 24) & 0xFF);
}

static void build_cmd(uint8_t flags, uint8_t mode) {
  memset(tx_frame, 0, sizeof(tx_frame));
  tx_frame[0] = CMD_HDR0;
  tx_frame[1] = CMD_HDR1;
  tx_frame[2] = 0x01;
  tx_frame[3] = flags;
  tx_frame[4] = mode;
  tx_frame[5] = seq++;
  if (mode == MODE_DUTY) {
    set_u16(&tx_frame[6], cmd_du_q15);
    set_u16(&tx_frame[8], cmd_dv_q15);
    set_u16(&tx_frame[10], cmd_dw_q15);
  } else if (mode == MODE_SCALAR) {
    set_u32(&tx_frame[6], cmd_freq_millihz);
    set_u16(&tx_frame[10], cmd_vmag_q15);
  } else if (mode == MODE_VECTOR) {
    if (flags & FLAG_VECTOR_ROTATE) {
      set_u32(&tx_frame[6], cmd_freq_millihz);
      set_u16(&tx_frame[10], cmd_vmag_q15);
    } else {
      set_u16(&tx_frame[6], (uint16_t)cmd_valpha_q15);
      set_u16(&tx_frame[8], (uint16_t)cmd_vbeta_q15);
    }
  } else if (mode == MODE_FOC) {
    set_u16(&tx_frame[6], (uint16_t)cmd_id_q15);
    set_u16(&tx_frame[8], (uint16_t)cmd_iq_q15);
    set_u32(&tx_frame[10], cmd_foc_freq_millihz);
  }
  tx_frame[14] = cmd_ext_flags;
  set_u16(&tx_frame[15], cmd_brake_q15);
  tx_frame[17] = 0;
  tx_frame[18] = 0;
  tx_frame[CRC_OFF] = crc_xor(tx_frame, CRC_OFF);
}

static void handle_reply(void) {
  if (rx_frame[0] != RSP_HDR0 || rx_frame[1] != RSP_HDR1) return;
  if (crc_xor(rx_frame, CRC_OFF) != rx_frame[CRC_OFF]) return;
  last_status = rx_frame[3];
  last_good = (uint16_t)rx_frame[5] | ((uint16_t)rx_frame[6] << 8);
  last_bad = (uint16_t)rx_frame[7] | ((uint16_t)rx_frame[8] << 8);
  last_fault = rx_frame[9];
  last_mode = rx_frame[10];
  last_ext_flags = rx_frame[14];
  last_brake_q15 = (uint16_t)rx_frame[15] | ((uint16_t)rx_frame[16] << 8);
  last_temp_raw = (uint16_t)rx_frame[19] | ((uint16_t)rx_frame[20] << 8);
  last_temp_flags = rx_frame[21];
  last_phase_a_raw = (uint16_t)rx_frame[23] | ((uint16_t)rx_frame[24] << 8);
  last_phase_b_raw = (uint16_t)rx_frame[25] | ((uint16_t)rx_frame[26] << 8);
  last_phase_c_raw = (uint16_t)rx_frame[27] | ((uint16_t)rx_frame[28] << 8);
  last_phase_flags = rx_frame[29];
  last_rx_ms = millis();
  have_reply = true;
  blink_rx_led();
}

static bool icmp(const char *a, const char *b) {
  while (*a && *b) {
    char ca = (char)tolower(*a++);
    char cb = (char)tolower(*b++);
    if (ca != cb) return false;
  }
  return (*a == '\0' && *b == '\0');
}

static void set_default_mag_if_zero(void) {
  if (cmd_vmag_q15 == 0) {
    cmd_vmag_q15 = q15_from_unit(cmd_mag);
  }
}

static char *next_token(char *&p) {
  while (*p == ' ' || *p == '\t') {
    p++;
  }
  if (*p == '\0') return nullptr;
  char *start = p;
  while (*p && *p != ' ' && *p != '\t') {
    p++;
  }
  if (*p) {
    *p = '\0';
    p++;
  }
  return start;
}

static void apply_cmd(const char *cmd_line) {
  char buf[96];
  strncpy(buf, cmd_line, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';
  char *p = buf;
  char *tok = next_token(p);
  if (!tok) return;

  if (icmp(tok, "START") || icmp(tok, "ENABLE")) {
    cmd_flags |= FLAG_ENABLE;
    cmd_flags &= ~FLAG_ESTOP;
    clear_fault_pending = true;
    if (cmd_mode == MODE_OFF) cmd_mode = MODE_SCALAR;
    if (cmd_freq_hz < 0.1f) {
      cmd_freq_hz = DEFAULT_FREQ_HZ;
      cmd_freq_millihz = (uint32_t)(cmd_freq_hz * 1000.0f);
    }
    set_default_mag_if_zero();
  } else if (icmp(tok, "STOP") || icmp(tok, "DISABLE")) {
    cmd_flags &= ~FLAG_ENABLE;
    cmd_mode = MODE_OFF;
    cmd_ext_flags = 0;
    cmd_brake_q15 = 0;
  } else if (icmp(tok, "ESTOP")) {
    char *arg = next_token(p);
    if (arg && (icmp(arg, "CLEAR") || icmp(arg, "OFF") || icmp(arg, "RESET"))) {
      cmd_flags &= ~FLAG_ESTOP;
      clear_fault_pending = true;
      cmd_flags &= ~FLAG_ENABLE;
      cmd_mode = MODE_OFF;
    } else {
      cmd_flags |= FLAG_ESTOP;
      cmd_flags &= ~FLAG_ENABLE;
      cmd_mode = MODE_OFF;
    }
    cmd_ext_flags = 0;
    cmd_brake_q15 = 0;
  } else if (icmp(tok, "CLEAR")) {
    clear_fault_pending = true;
    cmd_flags &= ~FLAG_ENABLE;
    cmd_flags &= ~FLAG_ESTOP;
    cmd_mode = MODE_OFF;
    cmd_ext_flags = 0;
    cmd_brake_q15 = 0;
  } else if (icmp(tok, "MODE")) {
    char *mode = next_token(p);
    if (!mode) return;
    if (icmp(mode, "VF")) {
      cmd_mode = MODE_SCALAR;
      cmd_flags &= ~FLAG_VECTOR_ROTATE;
      set_default_mag_if_zero();
    } else if (icmp(mode, "FOC")) {
      cmd_mode = MODE_VECTOR;
      cmd_flags |= FLAG_VECTOR_ROTATE;
      set_default_mag_if_zero();
    } else if (icmp(mode, "MIC")) {
      cmd_mode = MODE_VECTOR;
      cmd_flags |= FLAG_VECTOR_ROTATE;
      set_default_mag_if_zero();
    } else if (icmp(mode, "DUTY")) {
      cmd_mode = MODE_DUTY;
    } else if (icmp(mode, "DIAG")) {
      cmd_mode = MODE_DIAG;
      cmd_flags |= FLAG_DIAG_PWM;
    } else if (icmp(mode, "OFF")) {
      cmd_mode = MODE_OFF;
      cmd_flags &= ~FLAG_ENABLE;
    }
  } else if (icmp(tok, "SET")) {
    char *what = next_token(p);
    char *val = next_token(p);
    if (!what || !val) return;
    if (icmp(what, "FREQ")) {
      cmd_freq_hz = (float)atof(val);
      if (cmd_freq_hz < 0.0f) cmd_freq_hz = 0.0f;
      cmd_freq_millihz = (uint32_t)(cmd_freq_hz * 1000.0f);
    } else if (icmp(what, "MAG")) {
      cmd_mag = (float)atof(val);
      if (cmd_mag < 0.0f) cmd_mag = 0.0f;
      if (cmd_mag > 1.0f) cmd_mag = 1.0f;
      cmd_vmag_q15 = q15_from_unit(cmd_mag);
    }
  } else if (icmp(tok, "DUTY")) {
    char *u = next_token(p);
    char *v = next_token(p);
    char *w = next_token(p);
    if (!u || !v || !w) return;
    cmd_du_q15 = q15_from_unit((float)atof(u));
    cmd_dv_q15 = q15_from_unit((float)atof(v));
    cmd_dw_q15 = q15_from_unit((float)atof(w));
    cmd_mode = MODE_DUTY;
  } else if (icmp(tok, "VECTOR")) {
    char *sub = next_token(p);
    if (!sub) return;
    if (icmp(sub, "ROT")) {
      char *f = next_token(p);
      char *m = next_token(p);
      if (!f || !m) return;
      cmd_freq_hz = (float)atof(f);
      if (cmd_freq_hz < 0.0f) cmd_freq_hz = 0.0f;
      cmd_freq_millihz = (uint32_t)(cmd_freq_hz * 1000.0f);
      cmd_mag = (float)atof(m);
      if (cmd_mag < 0.0f) cmd_mag = 0.0f;
      if (cmd_mag > 1.0f) cmd_mag = 1.0f;
      cmd_vmag_q15 = q15_from_unit(cmd_mag);
      cmd_mode = MODE_VECTOR;
      cmd_flags |= FLAG_VECTOR_ROTATE;
    } else if (icmp(sub, "AB")) {
      char *a = next_token(p);
      char *b = next_token(p);
      if (!a || !b) return;
      cmd_valpha_q15 = q15_from_float((float)atof(a));
      cmd_vbeta_q15 = q15_from_float((float)atof(b));
      cmd_mode = MODE_VECTOR;
      cmd_flags &= ~FLAG_VECTOR_ROTATE;
    }
  } else if (icmp(tok, "DIAG")) {
    char *arg = next_token(p);
    if (!arg || icmp(arg, "ON") || icmp(arg, "1")) {
      cmd_mode = MODE_DIAG;
      cmd_flags |= FLAG_DIAG_PWM;
    } else {
      cmd_flags &= ~FLAG_DIAG_PWM;
      if (cmd_mode == MODE_DIAG) cmd_mode = MODE_OFF;
    }
  } else if (icmp(tok, "NTC")) {
    char *arg = next_token(p);
    if (!arg) return;
    if (icmp(arg, "ON") || icmp(arg, "1")) {
      cmd_ext_flags |= FLAG_EXT_NTC;
    } else {
      cmd_ext_flags &= ~FLAG_EXT_NTC;
    }
  } else if (icmp(tok, "PFC")) {
    char *arg = next_token(p);
    if (!arg) return;
    if (icmp(arg, "ON") || icmp(arg, "1")) {
      cmd_ext_flags |= FLAG_EXT_PFC;
    } else {
      cmd_ext_flags &= ~FLAG_EXT_PFC;
    }
  } else if (icmp(tok, "BRAKE")) {
    char *arg = next_token(p);
    if (!arg) return;
    if (icmp(arg, "OFF") || icmp(arg, "0")) {
      cmd_ext_flags &= ~FLAG_EXT_BRAKE_PWM;
      cmd_brake_q15 = 0;
    } else if (icmp(arg, "ON")) {
      cmd_ext_flags |= FLAG_EXT_BRAKE_PWM;
      cmd_brake_q15 = q15_from_unit(1.0f);
    } else if (icmp(arg, "PWM")) {
      char *val = next_token(p);
      if (!val) return;
      float duty = (float)atof(val);
      if (duty < 0.0f) duty = 0.0f;
      if (duty > 1.0f) duty = 1.0f;
      cmd_brake_q15 = q15_from_unit(duty);
      if (duty > 0.0f) {
        cmd_ext_flags |= FLAG_EXT_BRAKE_PWM;
      } else {
        cmd_ext_flags &= ~FLAG_EXT_BRAKE_PWM;
      }
    }
  }
}

static String rpc_get() {
  String s;
  s.reserve(160);
  const bool link_ok = have_reply && ((uint32_t)(millis() - last_rx_ms) < 500U);
  const bool estop = (last_status & STATUS_ESTOP) != 0 || (cmd_flags & FLAG_ESTOP) != 0;
  const bool fault = (last_status & STATUS_FAULT) != 0 || (last_status & STATUS_TIMEOUT) != 0;
  const bool pwm = (last_status & STATUS_PWM_ACTIVE) != 0;
  const uint8_t ext_flags = link_ok ? last_ext_flags : cmd_ext_flags;
  const uint16_t brake_q15 = link_ok ? last_brake_q15 : cmd_brake_q15;
  const char *state = "SAFE";
  if (fault || estop) {
    state = "FAULT";
  } else if (link_ok && pwm) {
    state = (cmd_mode == MODE_SCALAR) ? "VF_RUN" : "FOC_RUN";
  }
  const char *mode = "VF";
  if (cmd_mode == MODE_SCALAR) mode = "VF";
  else if (cmd_mode == MODE_VECTOR || cmd_mode == MODE_FOC) mode = "FOC";
  else if (cmd_mode == MODE_DIAG) mode = "VF";

  float freq = cmd_freq_hz;
  float speed = freq * 60.0f;
  s += "DATA freq="; s += String(freq, 2);
  s += " speed="; s += String(speed, 1);
  s += " ia=0 ib=0 ic=0 vdc=24.0";
  s += " state="; s += String(state);
  s += " mode="; s += String(mode);
  s += " pwm="; s += String(pwm ? 1 : 0);
  s += " id=0 iq=0 irm=0 mic=0 idref=0 save=0";
  s += " freqcmd="; s += String(freq, 2);
  s += " estop="; s += String(estop ? 1 : 0);
  s += " ntc="; s += String((ext_flags & FLAG_EXT_NTC) ? 1 : 0);
  s += " pfc="; s += String((ext_flags & FLAG_EXT_PFC) ? 1 : 0);
  float brake = (ext_flags & FLAG_EXT_BRAKE_PWM) ? ((float)brake_q15 / 32767.0f) : 0.0f;
  s += " brake="; s += String((ext_flags & FLAG_EXT_BRAKE_PWM) ? 1 : 0);
  s += " brake_duty="; s += String(brake, 2);
  s += " bp_temp_raw="; s += String((int)last_temp_raw);
  s += " bp_temp_flags="; s += String((int)last_temp_flags);
  s += " bp_temp_valid="; s += String((last_temp_flags & 0x01) ? 1 : 0);
  s += " bp_temp_fault="; s += String((last_temp_flags & 0x02) ? 1 : 0);
  s += " bp_phase_a_raw="; s += String((int)last_phase_a_raw);
  s += " bp_phase_b_raw="; s += String((int)last_phase_b_raw);
  s += " bp_phase_c_raw="; s += String((int)last_phase_c_raw);
  s += " bp_phase_flags="; s += String((int)last_phase_flags);
  s += " bp_phase_valid="; s += String((last_phase_flags & 0x01) ? 1 : 0);
  s += " bp_phase_c_virtual="; s += String((last_phase_flags & 0x02) ? 1 : 0);
  return s;
}
#endif

#if USE_TEXT_RPC
static void handle_rpc_line(const char *line) {
  if (!line || !line[0]) return;
  if (strncmp(line, "CMD ", 4) == 0) {
    apply_cmd(line + 4);
    last_cmd_ms = millis();
    last_tx = 0;
    RPC_SERIAL.println("OK");
    return;
  }
  if (icmp(line, "GET")) {
    RPC_SERIAL.println(rpc_get());
    return;
  }
  if (icmp(line, "PING")) {
    RPC_SERIAL.println("OK");
    return;
  }
  apply_cmd(line);
  last_cmd_ms = millis();
  last_tx = 0;
  RPC_SERIAL.println("OK");
}

static void rpc_serial_poll(void) {
  while (RPC_SERIAL.available() > 0) {
    int c = RPC_SERIAL.read();
    if (c < 0) break;
    char ch = (char)c;
    if (ch == '\n' || ch == '\r') {
      if (rpc_len > 0) {
        rpc_line[rpc_len] = '\0';
        handle_rpc_line(rpc_line);
        rpc_len = 0;
      }
    } else {
      if (rpc_len < sizeof(rpc_line) - 1) {
        rpc_line[rpc_len++] = ch;
      }
    }
  }
}
#endif

#if !LINK_BLUEPILL
static void handle_line(void) {
  if (rx_len == 0) return;
  rx_line[rx_len] = '\0';
  if (strncmp(rx_line, "PONG", 4) == 0 || strncmp(rx_line, "PING", 4) == 0) {
    blink_rx_led();
  } else {
    blink_rx_led();
  }
  rx_len = 0;
}
#endif

void setup() {
  SerialPort.begin(UART_BAUD);
  RPC_SERIAL.begin(RPC_BAUD);
  pinMode(HB_PIN, OUTPUT);
  pinMode(RESP_PIN, OUTPUT);
  pinMode(HB_LED_R, OUTPUT);
  pinMode(HB_LED_G, OUTPUT);
  pinMode(HB_LED_B, OUTPUT);
  pinMode(RX_LED_R, OUTPUT);
  pinMode(RX_LED_G, OUTPUT);
  pinMode(RX_LED_B, OUTPUT);
#if USE_MATRIX
  matrix.begin();
  matrix.clear();
#endif
#if LINK_BLUEPILL
  cmd_freq_hz = 0.0f;
  cmd_freq_millihz = 0;
  cmd_vmag_q15 = q15_from_unit(cmd_mag);
#endif
}

void loop() {
  // Heartbeat so we can verify sketch is running
  static uint32_t hb_last = 0;
  static uint8_t hb_state = 0;
  if (millis() - hb_last >= 500) {
    hb_last = millis();
    hb_state ^= 1;
    digitalWrite(HB_PIN, hb_state);
    digitalWrite(HB_LED_R, hb_state);
    digitalWrite(HB_LED_G, hb_state);
    digitalWrite(HB_LED_B, hb_state);
  }

#if LINK_BLUEPILL
  if (!sent_clear) {
    clear_fault_pending = true;
    cmd_flags &= ~FLAG_ENABLE;
    cmd_flags &= ~FLAG_ESTOP;
    cmd_mode = MODE_OFF;
    build_cmd(FLAG_CLEAR_FAULT, MODE_OFF);
    SerialPort.write(tx_frame, sizeof(tx_frame));
    sent_clear = true;
    last_tx = millis();
  }
  if (millis() - last_tx >= TX_INTERVAL_MS) {
    uint8_t flags = cmd_flags;
    uint8_t mode = cmd_mode;
    if (clear_fault_pending) {
      flags &= ~FLAG_ENABLE;
      flags &= ~FLAG_ESTOP;
      flags |= FLAG_CLEAR_FAULT;
      mode = MODE_OFF;
      clear_fault_pending = false;
    }
    build_cmd(flags, mode);
    SerialPort.write(tx_frame, sizeof(tx_frame));
    last_tx = millis();
  }

  while (SerialPort.available()) {
    int c = SerialPort.read();
    if (c < 0) break;
    uint8_t b = (uint8_t)c;
#if ARDUINO_ECHO
    SerialPort.write(b);
#endif
    switch (rx_state) {
      case 0:
        if (b == RSP_HDR0) {
          rx_frame[0] = b;
          rx_state = 1;
        }
        break;
      case 1:
        if (b == RSP_HDR1) {
          rx_frame[1] = b;
          rx_idx = 2;
          rx_state = 2;
        } else if (b == RSP_HDR0) {
          rx_frame[0] = b;
          rx_state = 1;
        } else {
          rx_state = 0;
        }
        break;
      case 2:
        rx_frame[rx_idx++] = b;
        if (rx_idx >= FRAME_LEN) {
          handle_reply();
          rx_state = 0;
          rx_idx = 0;
        }
        break;
      default:
        rx_state = 0;
        rx_idx = 0;
        break;
    }
  }
#else
  if (millis() - last_ping >= PING_INTERVAL_MS) {
    last_ping = millis();
    char buf[32];
    int n = snprintf(buf, sizeof(buf), "PING %lu\n", (unsigned long)ping_counter++);
    SerialPort.write((const uint8_t *)buf, (size_t)n);
  }
  while (SerialPort.available()) {
    int c = SerialPort.read();
    if (c < 0) break;
    char ch = (char)c;
#if ARDUINO_ECHO
    SerialPort.write((uint8_t)ch);
#endif
    if (rx_len < sizeof(rx_line) - 1) {
      rx_line[rx_len++] = ch;
      if (ch == '\n') {
        handle_line();
      }
    } else {
      rx_len = 0;
    }
  }
#endif

#if USE_TEXT_RPC
  rpc_serial_poll();
#endif

#if USE_MATRIX
  static uint16_t last_disp = 0xFFFF;
  if ((uint32_t)(millis() - last_matrix_ms) >= 200U) {
    last_matrix_ms = millis();
    uint16_t disp = 0;
#if LINK_BLUEPILL
    float hz = cmd_freq_hz;
    if ((cmd_flags & FLAG_ENABLE) == 0 || cmd_mode == MODE_OFF) {
      hz = 0.0f;
    }
    if (hz < 0.0f) hz = 0.0f;
    if (hz > 99.9f) hz = 99.9f;
    disp = (uint16_t)(hz * 10.0f + 0.5f);
#else
    disp = (uint16_t)((ping_counter % 1000) * 10);
#endif
    if (disp != last_disp) {
      last_disp = disp;
      matrix_draw_freq_tenths(disp);
    }
  }
#endif
}
