#include "control.h"

#include <math.h>

#include "adc_currents.h"
#include "config.h"
#include "encoder_as5600.h"
#include "foc_controller.h"
#include "hall_sensor.h"
#include "pwm_tim1.h"
#include "proto.h"
#include "safety.h"
#include "stm32f1xx_hal.h"

#define MODE_SCALAR 3
#define MODE_VECTOR 4
#define MODE_FOC 5

typedef struct {
  uint8_t mode;
  uint8_t flags;
  uint16_t du_q15;
  uint16_t dv_q15;
  uint16_t dw_q15;
  uint32_t freq_millihz;
  uint32_t foc_freq_millihz;
  uint16_t vmag_q15;
  int16_t valpha_q15;
  int16_t vbeta_q15;
  int16_t id_q15;
  int16_t iq_q15;
} control_setpoint_t;

static control_setpoint_t s_sp;
static float s_angle = 0.0f;
static uint32_t s_last_tick = 0;
static uint8_t s_prev_mode = MODE_OFF;
static bool s_prev_vec_rotate = false;

static float q15_to_float(int16_t v) {
  return (float)v / 32767.0f;
}

static uint16_t u16le(const uint8_t *buf, uint8_t off) {
  return (uint16_t)buf[off] | ((uint16_t)buf[off + 1U] << 8);
}

static int16_t i16le(const uint8_t *buf, uint8_t off) {
  return (int16_t)u16le(buf, off);
}

static uint32_t u32le(const uint8_t *buf, uint8_t off) {
  return (uint32_t)buf[off] | ((uint32_t)buf[off + 1U] << 8) | ((uint32_t)buf[off + 2U] << 16) |
         ((uint32_t)buf[off + 3U] << 24);
}

static void limit_vector(float *alpha, float *beta) {
  const float max_mag = 0.95f;
  float a = *alpha;
  float b = *beta;
  float mag2 = a * a + b * b;
  if (mag2 > (max_mag * max_mag)) {
    float mag = sqrtf(mag2);
    float scale = max_mag / (mag > 0.0001f ? mag : 1.0f);
    a *= scale;
    b *= scale;
  }
  if (a > 1.0f) a = 1.0f;
  if (a < -1.0f) a = -1.0f;
  if (b > 1.0f) b = 1.0f;
  if (b < -1.0f) b = -1.0f;
  *alpha = a;
  *beta = b;
}

static uint16_t clamp_q15(float duty) {
  if (duty < 0.0f) duty = 0.0f;
  if (duty > 1.0f) duty = 1.0f;
  float pct = duty * 100.0f;
  if (pct < PWM_MIN_PERCENT) pct = PWM_MIN_PERCENT;
  if (pct > PWM_MAX_PERCENT) pct = PWM_MAX_PERCENT;
  return (uint16_t)(pct * 327.67f);
}

void control_init(void) {
  s_sp.mode = MODE_OFF;
  s_sp.flags = 0;
  s_sp.du_q15 = 0;
  s_sp.dv_q15 = 0;
  s_sp.dw_q15 = 0;
  s_sp.freq_millihz = 0;
  s_sp.vmag_q15 = 0;
  s_sp.valpha_q15 = 0;
  s_sp.vbeta_q15 = 0;
  s_sp.id_q15 = 0;
  s_sp.iq_q15 = 0;
  s_angle = 0.0f;
  s_last_tick = HAL_GetTick();
  s_prev_mode = MODE_OFF;
  s_prev_vec_rotate = false;
}

static void rotate_vector(float freq_hz, float mag, float dt_s, float *alpha, float *beta) {
  float omega = 2.0f * 3.1415926f * freq_hz;
  if (dt_s > 0.1f) dt_s = 0.001f;
  s_angle += omega * dt_s;
  if (s_angle > 2.0f * 3.1415926f) s_angle -= 2.0f * 3.1415926f;
  if (s_angle < -2.0f * 3.1415926f) s_angle += 2.0f * 3.1415926f;
  *alpha = mag * cosf(s_angle);
  *beta = mag * sinf(s_angle);
}

void control_update_from_cmd(const uint8_t *cmd) {
  uint8_t new_mode = cmd[CMD_OFF_MODE];
  uint8_t old_mode = s_prev_mode;
  bool new_vec_rotate = (cmd[CMD_OFF_FLAGS] & FLAG_VECTOR_ROTATE) != 0;
  if (new_mode == MODE_SCALAR && old_mode != MODE_SCALAR) {
    s_angle = 0.0f;
  }
  if (new_mode == MODE_VECTOR && new_vec_rotate && (!s_prev_vec_rotate || old_mode != MODE_VECTOR)) {
    s_angle = 0.0f;
  }
  s_sp.mode = new_mode;
  s_sp.flags = cmd[CMD_OFF_FLAGS];
  s_sp.du_q15 = u16le(cmd, CMD_OFF_DU);
  s_sp.dv_q15 = u16le(cmd, CMD_OFF_DV);
  s_sp.dw_q15 = u16le(cmd, CMD_OFF_DW);

  s_sp.freq_millihz = u32le(cmd, CMD_OFF_DU);
  s_sp.foc_freq_millihz = u32le(cmd, CMD_OFF_DW);
  s_sp.vmag_q15 = u16le(cmd, CMD_OFF_DW);
  if (s_sp.vmag_q15 > 32767U) {
    s_sp.vmag_q15 = 32767U;
  }
  s_sp.valpha_q15 = i16le(cmd, CMD_OFF_DU);
  s_sp.vbeta_q15 = i16le(cmd, CMD_OFF_DV);
  s_sp.id_q15 = i16le(cmd, CMD_OFF_DU);
  s_sp.iq_q15 = i16le(cmd, CMD_OFF_DV);

  if (new_mode == MODE_FOC && old_mode != MODE_FOC) {
    foc_reset();
  }
  s_prev_mode = new_mode;
  s_prev_vec_rotate = new_vec_rotate;
}

void control_tick(void) {
  const safety_state_t *st = safety_state();

  if (!st->enabled || st->fault_latched || st->timeout_active) {
    pwm_safe_idle();
    safety_set_pwm_active(false);
    return;
  }

  uint32_t now = HAL_GetTick();
  uint32_t dt_ms = now - s_last_tick;
  if (dt_ms == 0U) {
    return;
  }
  s_last_tick = now;

  if (s_sp.mode == MODE_DIAG) {
    if (s_sp.flags & FLAG_DIAG_PWM) {
      pwm_apply_diag();
      pwm_outputs_enable(true);
      safety_set_pwm_active(true);
    } else {
      pwm_safe_idle();
      safety_set_pwm_active(false);
    }
    return;
  }

  if (s_sp.mode == MODE_DUTY) {
    pwm_set_duty_q15(s_sp.du_q15, s_sp.dv_q15, s_sp.dw_q15);
    pwm_outputs_enable(true);
    safety_set_pwm_active(true);
    return;
  }

  float v_alpha = 0.0f;
  float v_beta = 0.0f;

  if (s_sp.mode == MODE_SCALAR) {
    float freq_hz = ((int32_t)s_sp.freq_millihz) / 1000.0f;
    float dt_s = ((float)dt_ms) * 0.001f;
    float mag = q15_to_float((int16_t)s_sp.vmag_q15);
    rotate_vector(freq_hz, mag, dt_s, &v_alpha, &v_beta);
  } else if (s_sp.mode == MODE_VECTOR) {
    if (s_sp.flags & FLAG_VECTOR_ROTATE) {
      float freq_hz = ((int32_t)s_sp.freq_millihz) / 1000.0f;
      float dt_s = ((float)dt_ms) * 0.001f;
      float mag = q15_to_float((int16_t)s_sp.vmag_q15);
      rotate_vector(freq_hz, mag, dt_s, &v_alpha, &v_beta);
    } else {
      v_alpha = q15_to_float(s_sp.valpha_q15);
      v_beta = q15_to_float(s_sp.vbeta_q15);
    }
  } else if (s_sp.mode == MODE_FOC) {
    float ia = 0.0f, ib = 0.0f, ic = 0.0f, vbus = 0.0f;
    adc_currents_get(&ia, &ib, &ic, &vbus);

    float theta = 0.0f;
    float enc_theta = 0.0f;
    float hall_theta = 0.0f;
    float omega = 0.0f;
    bool enc_ok = false;
#if USE_AS5600
    enc_ok = encoder_as5600_get_theta(&enc_theta);
#endif
    bool hall_ok = hall_get_theta(&hall_theta, &omega);
    bool sensor_ok = enc_ok || hall_ok;
    if (!sensor_ok && FOC_REQUIRE_HALL) {
      pwm_safe_idle();
      safety_set_pwm_active(false);
      return;
    }

    if (enc_ok) {
      theta = enc_theta;
    } else if (hall_ok) {
      theta = hall_theta;
    } else {
      // Fallback to open-loop angle only when the configured safety policy allows it.
      float freq_hz = ((int32_t)s_sp.foc_freq_millihz) / 1000.0f;
      float omega_ol = 2.0f * 3.1415926f * freq_hz;
      float dt_s = ((float)dt_ms) * 0.001f;
      if (dt_s > 0.1f) dt_s = 0.001f;
      s_angle += omega_ol * dt_s;
      if (s_angle > 2.0f * 3.1415926f) s_angle -= 2.0f * 3.1415926f;
      if (s_angle < -2.0f * 3.1415926f) s_angle += 2.0f * 3.1415926f;
      theta = s_angle;
    }

    float id_ref = q15_to_float(s_sp.id_q15);
    float iq_ref = q15_to_float(s_sp.iq_q15);
    foc_run(id_ref, iq_ref, theta, ia, ib, ic, vbus, &v_alpha, &v_beta);
  } else {
    pwm_safe_idle();
    safety_set_pwm_active(false);
    return;
  }

  limit_vector(&v_alpha, &v_beta);

  float v_a = v_alpha;
  float v_b = -0.5f * v_alpha + 0.8660254f * v_beta;
  float v_c = -0.5f * v_alpha - 0.8660254f * v_beta;

  // SVPWM-style common-mode injection for better utilization and balanced duty
  float v_max = v_a;
  if (v_b > v_max) v_max = v_b;
  if (v_c > v_max) v_max = v_c;
  float v_min = v_a;
  if (v_b < v_min) v_min = v_b;
  if (v_c < v_min) v_min = v_c;
  float v_offset = 0.5f * (v_max + v_min);
  v_a -= v_offset;
  v_b -= v_offset;
  v_c -= v_offset;

  float duty_a = 0.5f + 0.5f * v_a;
  float duty_b = 0.5f + 0.5f * v_b;
  float duty_c = 0.5f + 0.5f * v_c;

  pwm_set_duty_q15(clamp_q15(duty_a), clamp_q15(duty_b), clamp_q15(duty_c));
  pwm_outputs_enable(true);
  safety_set_pwm_active(true);
}
