
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
using byte = uint8_t;
using voidFuncPtr = void(*)();
static uint32_t clock_ms;
uint32_t millis() { return clock_ms; }
void delay(uint32_t) {}
static uint32_t submitted[4];
static unsigned writes;
static bool initialized;
extern "C" {
void matrixBegin() { initialized = true; }
void matrixWrite(const uint32_t* frame) { memcpy(submitted, frame, 16); ++writes; }
}
#include "Arduino_LED_Matrix.h"
static bool g_pwm_enabled, g_estop_latched, g_bp_softstart_ready;
static float g_freq_cmd, g_freq_ref;
static const float POLE_PAIRS = 1;
static const bool NUCLEO_MCSDK_ACIM_BACKEND = true;
static uint8_t g_bp_status;
static const uint8_t BP_STATUS_PWM_ACTIVE = 0x20;
static void matrix_set_pixel(int, int);
static void matrix_draw_digit(int, int, int);
static unsigned checks;
void check(bool condition) { ++checks; if (!condition) { fprintf(stderr,"check %u failed\n",checks); exit(1); } }
bool raw_pixel(int x, int y) {
  int i = y*13 + (12-x);
  return (submitted[i/32] >> (i%32)) & 1;
}
static Arduino_LED_Matrix g_matrix;
static bool g_matrix_ready = false;
static uint32_t g_matrix_last_ms = 0;
static uint32_t g_matrix_test_until_ms = 0;
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

using std::isfinite;
static bool g_bp_mcsdk_telemetry=true, g_bp_vbus_valid=true;
static uint32_t g_bp_fw_build=2026102402U, g_bp_vbus_ms, g_bp_last_rsp_ms;
static const uint32_t BP_VBUS_STALE_MS=500, BP_REPLY_TIMEOUT_MS=500;
static float g_bp_vdc;

static bool matrix_test_active() {
  if (g_matrix_test_until_ms == 0U) return false;
  if ((int32_t)(g_matrix_test_until_ms - millis()) <= 0) {
    g_matrix_test_until_ms = 0U;
    return false;
  }
  return true;
}
static void matrix_start_test(uint32_t duration_ms) {
  g_matrix_test_until_ms = millis() + duration_ms;
  // Zero is the inactive sentinel, including at the millis rollover boundary.
  if (g_matrix_test_until_ms == 0U) g_matrix_test_until_ms = 1U;
}
static void matrix_init() {
  if (g_matrix_ready) {
    return;
  }
  g_matrix.begin();
  memset(g_matrix_pixels, 0, sizeof(g_matrix_pixels));
  memset(g_matrix_frame, 0, sizeof(g_matrix_frame));
  g_matrix.loadFrame(g_matrix_frame);
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
  // Keep the display self-test independent from the custom digit renderer.
  // Alternating every LED makes a stale/failed matrix update unmistakable.
  const bool matrix_test = matrix_test_active();
  if (matrix_test) {
    static const uint32_t all_on[4] = {
      0xFFFFFFFFU, 0xFFFFFFFFU, 0xFFFFFFFFU, 0xFFFFFFFFU
    };
    static const uint32_t all_off[4] = {
      0x00000000U, 0x00000000U, 0x00000000U, 0x00000000U
    };
    g_matrix.loadFrame(((now / 500U) & 1U) ? all_on : all_off);
    return;
  }
  // Stopped: DC bus in whole volts with a V marker, or --- if stale.
  // Running: retain the existing alternating electrical Hz / calculated RPM.
  float freq = g_pwm_enabled ? g_freq_ref : g_freq_cmd;
  if (fabsf(freq) < 0.05f) freq = 0.0f;
  if (freq < 0.0f) freq = 0.0f;
  bool show_rpm = g_pwm_enabled && !g_estop_latched && (((now / 1000U) & 1U) != 0U);
  memset(g_matrix_pixels, 0, sizeof(g_matrix_pixels));
  int x0 = 1;
  int y0 = 1;
  if (!g_pwm_enabled) {
    // Display the accepted Nucleo bus measurement even at zero Hz, ESTOP
    // or an idle fault. Never use the default/stale g_vdc as a zero indication.
    const bool voltage_fresh = NUCLEO_MCSDK_ACIM_BACKEND && g_bp_mcsdk_telemetry &&
      g_bp_fw_build == 2026102402U && g_bp_vbus_valid &&
      g_bp_vbus_ms != 0U && g_bp_last_rsp_ms != 0U &&
      (uint32_t)(now - g_bp_vbus_ms) <= BP_VBUS_STALE_MS &&
      (uint32_t)(now - g_bp_last_rsp_ms) <= BP_REPLY_TIMEOUT_MS &&
      isfinite(g_bp_vdc) && g_bp_vdc >= 0.0f && g_bp_vdc <= 999.0f;
    if (voltage_fresh) {
      const int volts = (int)(g_bp_vdc + 0.5f);
      if (volts >= 100) matrix_draw_digit(x0, y0, volts / 100);
      if (volts >= 10) matrix_draw_digit(x0 + 4, y0, (volts / 10) % 10);
      matrix_draw_digit(x0 + 8, y0, volts % 10);
    } else {
      // Three dashes mean unavailable, never a measured zero.
      for (int digit = 0; digit < 3; ++digit)
        for (int x = 0; x < 3; ++x) matrix_set_pixel(x0 + 4*digit + x, y0 + 2);
    }
    // Small V below the digits identifies DC-bus volts, without a decimal.
    matrix_set_pixel(0, 6);
    matrix_set_pixel(2, 6);
    matrix_set_pixel(1, 7);
  } else if (show_rpm) {
    int rpm = (int)((freq * 60.0f) / POLE_PAIRS + 0.5f);
    if (rpm < 0) rpm = 0;
    if (rpm > 999) rpm = 999;
    if (rpm >= 100) matrix_draw_digit(x0, y0, (rpm / 100) % 10);
    if (rpm >= 10) matrix_draw_digit(x0 + 4, y0, (rpm / 10) % 10);
    matrix_draw_digit(x0 + 8, y0, rpm % 10);
    // Bottom marker distinguishes RPM from the alternating frequency value.
    matrix_set_pixel(MATRIX_W - 3, MATRIX_H - 1);
    matrix_set_pixel(MATRIX_W - 2, MATRIX_H - 1);
    matrix_set_pixel(MATRIX_W - 1, MATRIX_H - 1);
  } else {
    int freq10 = (int)(freq * 10.0f + 0.5f);
    if (freq10 < 0) freq10 = 0;
    if (freq10 > 999) freq10 = 999;
    int tens = (freq10 / 100) % 10;
    int ones = (freq10 / 10) % 10;
    int tenths = freq10 % 10;
    if (freq10 >= 100) matrix_draw_digit(x0, y0, tens);
    matrix_draw_digit(x0 + 4, y0, ones);
    matrix_draw_digit(x0 + 8, y0, tenths);
    matrix_set_pixel(x0 + 7, y0 + 4);
    matrix_set_pixel(x0 + 7, y0 + 5);
  }
  // Left marker confirms that the autonomous AC soft-start has produced a
  // stable DC bus; right marker follows actual MCSDK PWM feedback.
  if (g_bp_softstart_ready) {
    matrix_set_pixel(0, 0);
    matrix_set_pixel(0, 1);
  }
  bool pwm_feedback = NUCLEO_MCSDK_ACIM_BACKEND
                        ? ((g_bp_status & BP_STATUS_PWM_ACTIVE) != 0U)
                        : g_pwm_enabled;
  if (pwm_feedback && !g_estop_latched) {
    matrix_set_pixel(MATRIX_W - 1, 0);
    matrix_set_pixel(MATRIX_W - 1, 1);
  }
  Arduino_LED_Matrix::loadPixelsToBuffer(g_matrix_pixels, sizeof(g_matrix_pixels), g_matrix_frame);
  // Use the core wrapper so the sketch stays ABI-compatible with the Zephyr
  // image installed on UNO Q. Direct matrixWrite() addresses differ by core.
  g_matrix.loadFrame(g_matrix_frame);
}
static void matrix_set_pixel(int x, int y) {
  if (x < 0 || x >= MATRIX_W || y < 0 || y >= MATRIX_H) {
    return;
  }
  // UNO Q's physical matrix is wired right-to-left relative to the raw pixel
  // buffer. Mirror X so values such as 5.0 do not appear as 0.5.
  g_matrix_pixels[y * MATRIX_W + (MATRIX_W - 1 - x)] = 1;
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

// Independent glyph oracle: corrupted production digit tables must not pass.
static const uint8_t expected_digits[10][5] = {
  {7,5,5,5,7}, {2,6,2,2,7}, {7,1,7,4,7}, {7,1,7,1,7}, {5,5,7,1,1},
  {7,4,7,1,7}, {7,4,7,5,7}, {7,1,2,2,2}, {7,5,7,5,7}, {7,5,7,1,7}
};
void check_digit(int x0, int d) {
  for(int y=0;y<5;++y) for(int x=0;x<3;++x)
    check(raw_pixel(x0+x,1+y) == bool((expected_digits[d][y] >> (2-x)) & 1));
}

void fresh(float v) {
  clock_ms+=1000; g_bp_vdc=v; g_bp_vbus_ms=clock_ms; g_bp_last_rsp_ms=clock_ms;
  g_bp_vbus_valid=true; g_bp_mcsdk_telemetry=true; g_bp_fw_build=2026102402U;
  g_pwm_enabled=false; g_freq_cmd=25; g_estop_latched=false;
}
void expect_volts(int n) {
  for(int pos=0;pos<3;++pos) {
    int x0=1+4*pos;
    if ((pos==0 && n<100) || (pos==1 && n<10)) {
      for(int y=1;y<=5;++y)for(int x=x0;x<x0+3;++x)check(!raw_pixel(x,y));
    } else check_digit(x0, pos==0?n/100:pos==1?(n/10)%10:n%10);
  }
  check(raw_pixel(0,6) && raw_pixel(2,6) && raw_pixel(1,7));
  check(!raw_pixel(8,6)); // no frequency decimal point
}
void expect_missing() {
  for(int pos=0;pos<3;++pos)for(int y=1;y<=5;++y)for(int x=0;x<3;++x)
    check(raw_pixel(1+4*pos+x,y)==(y==3));
  check(raw_pixel(0,6) && raw_pixel(2,6) && raw_pixel(1,7));
}
int main() {
  matrix_init(); check(initialized && writes==1);
  for(int v=0;v<=999;++v) {
    fresh(float(v)); unsigned old=writes; matrix_update();
    check(writes==old+1); expect_volts(v);
    old=writes; matrix_update(); check(writes==old);
  }
  fresh(.32f); matrix_update(); expect_volts(0);
  fresh(19.6f); matrix_update(); expect_volts(20);
  fresh(322.7f); matrix_update(); expect_volts(323);
  fresh(323); g_estop_latched=true; matrix_update(); expect_volts(323);
  for(float v : {-1.0f,1000.0f,NAN,INFINITY}) {
    fresh(v); matrix_update(); expect_missing();
  }
  fresh(323); g_bp_vbus_valid=false; matrix_update(); expect_missing();
  fresh(323); g_bp_mcsdk_telemetry=false; matrix_update(); expect_missing();
  fresh(323); g_bp_fw_build=0; matrix_update(); expect_missing();
  fresh(323); g_bp_vbus_ms=0; matrix_update(); expect_missing();
  fresh(323); g_bp_last_rsp_ms=0; matrix_update(); expect_missing();
  fresh(323); clock_ms+=500; matrix_update(); expect_volts(323);
  fresh(323); clock_ms+=501; matrix_update(); expect_missing();
  fresh(323); g_bp_vbus_ms-=501; matrix_update(); expect_missing();
  fresh(323); g_bp_last_rsp_ms-=501; matrix_update(); expect_missing();
  fresh(323); g_bp_vbus_ms=0xfffffff0U; g_bp_last_rsp_ms=g_bp_vbus_ms;
  g_matrix_last_ms=0xfffffe00U; clock_ms=0x100U; matrix_update(); expect_volts(323);
  clock_ms=0x400U; matrix_update(); expect_missing();
  fresh(323); matrix_update(); expect_volts(323); // recover after stale
  g_pwm_enabled=true; g_estop_latched=false;
  for(int tenths=0;tenths<=999;++tenths) {
    g_freq_ref=tenths/10.0f; clock_ms=2000000U+tenths*2000U;
    matrix_update(); check_digit(5,(tenths/10)%10); check_digit(9,tenths%10);
    if(tenths>=100)check_digit(1,tenths/100);
    check(raw_pixel(8,5) && raw_pixel(8,6));
  }
  g_freq_ref=5; clock_ms=4001000; matrix_update();
  check_digit(1,3);check_digit(5,0);check_digit(9,0);
  for(int x=10;x<13;++x)check(raw_pixel(x,7));
  g_pwm_enabled=false; matrix_start_test(15000);
  for(int i=0;i<4;++i) {
    clock_ms+=500;matrix_update();
    for(int w=0;w<4;++w)check(submitted[w]==(((clock_ms/500)&1)?0xffffffffU:0U));
  }
  g_matrix_test_until_ms=0;fresh(323);matrix_update();expect_volts(323);
  printf("{\"passed\":true,\"checks\":%u,\"voltage_values\":1000,\"running_frequency_values\":1000}",checks);
}
