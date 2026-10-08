
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
  const bool matrix_test = (int32_t)(g_matrix_test_until_ms - now) > 0;
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
  // SAFE shows the Wi-Fi frequency command immediately. While running, the
  // matrix alternates each second between electrical Hz and calculated RPM.
  float freq = g_pwm_enabled ? g_freq_ref : g_freq_cmd;
  if (fabsf(freq) < 0.05f) freq = 0.0f;
  if (freq < 0.0f) freq = 0.0f;
  bool show_rpm = g_pwm_enabled && !g_estop_latched && (((now / 1000U) & 1U) != 0U);
  memset(g_matrix_pixels, 0, sizeof(g_matrix_pixels));
  int x0 = 1;
  int y0 = 1;
  if (show_rpm) {
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

void check_digit(int x0, int d) {
  for(int y=0;y<5;++y) for(int x=0;x<3;++x)
    check(raw_pixel(x0+x,1+y) == bool((DIGIT_3X5[d][y] >> (2-x)) & 1));
}
int main() {
  matrix_init(); check(initialized && g_matrix_ready && writes==1);
  for(int tenths=0;tenths<=999;++tenths) {
    g_freq_cmd=tenths/10.0f; g_freq_ref=0; clock_ms+=200;
    unsigned old=writes; matrix_update(); check(writes==old+1);
    check_digit(5,(tenths/10)%10); check_digit(9,tenths%10);
    if(tenths>=100) check_digit(1,tenths/100);
    else for(int y=1;y<=5;++y) for(int x=1;x<=3;++x) check(!raw_pixel(x,y));
    check(raw_pixel(8,5) && raw_pixel(8,6));
    old=writes; matrix_update(); check(writes==old);
  }
  g_pwm_enabled=true; g_freq_cmd=20; g_freq_ref=5; clock_ms=202000;
  matrix_update(); check_digit(5,5); check_digit(9,0);
  clock_ms=203000; matrix_update(); check_digit(1,3); check_digit(5,0); check_digit(9,0);
  for(int x=10;x<13;++x) check(raw_pixel(x,7));
  g_pwm_enabled=false; g_bp_softstart_ready=true; g_bp_status=BP_STATUS_PWM_ACTIVE;
  clock_ms+=200; matrix_update(); check(raw_pixel(0,0) && raw_pixel(12,0));
  g_estop_latched=true; clock_ms+=200; matrix_update(); check(!raw_pixel(12,0));
  g_matrix_test_until_ms=clock_ms+15000;
  for(unsigned phase=0;phase<4;++phase) {
    clock_ms+=500; matrix_update();
    for(int i=0;i<4;++i) check(submitted[i]==(((clock_ms/500)&1)?0xffffffffU:0U));
  }
  // The deadline comparison and update interval must survive millis rollover.
  g_matrix_last_ms=0xffffff00U; g_matrix_test_until_ms=0x1000U; clock_ms=0x100U;
  matrix_update(); check(submitted[0]==0);
  g_matrix_test_until_ms=0; g_pwm_enabled=false; g_freq_cmd=20; clock_ms=0x1200;
  matrix_update(); check_digit(1,2); check_digit(5,0); check_digit(9,0);
  printf("{\"pass\":true,\"checks\":%u,\"frequency_values\":1000,\"frames\":{",checks);
  g_bp_softstart_ready=false; g_bp_status=0; g_estop_latched=false;
  bool first=true;
  for(int f : {0,5,20}) {
    g_freq_cmd=float(f); clock_ms+=200; matrix_update();
    printf("%s\"%d\":[%u,%u,%u,%u]",first?"":",",f,submitted[0],submitted[1],submitted[2],submitted[3]);
    first=false;
  }
  printf("}}");
}
