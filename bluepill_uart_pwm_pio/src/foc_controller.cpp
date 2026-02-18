#include "foc_controller.h"

#include <math.h>

#include "config.h"
#include "stm32f1xx_hal.h"

typedef struct {
  float id_int;
  float iq_int;
} foc_state_t;

static foc_state_t s_foc;
static uint32_t s_last_ms = 0;

void foc_init(void) {
  s_foc.id_int = 0.0f;
  s_foc.iq_int = 0.0f;
  s_last_ms = HAL_GetTick();
}

void foc_reset(void) {
  s_foc.id_int = 0.0f;
  s_foc.iq_int = 0.0f;
  s_last_ms = HAL_GetTick();
}

static void clarke(float ia, float ib, float *i_alpha, float *i_beta) {
  // Assuming ia + ib + ic = 0
  *i_alpha = ia;
  *i_beta = (ia + 2.0f * ib) * 0.577350269f; // 1/sqrt(3)
}

static void park(float alpha, float beta, float sin_t, float cos_t, float *d, float *q) {
  *d = alpha * cos_t + beta * sin_t;
  *q = -alpha * sin_t + beta * cos_t;
}

static void inv_park(float d, float q, float sin_t, float cos_t, float *alpha, float *beta) {
  *alpha = d * cos_t - q * sin_t;
  *beta = d * sin_t + q * cos_t;
}

void foc_run(float id_ref, float iq_ref, float theta_elec,
             float ia, float ib, float ic, float vbus,
             float *v_alpha, float *v_beta) {
  (void)ic;
  (void)vbus;

  uint32_t now = HAL_GetTick();
  float dt = (now - s_last_ms) * 0.001f;
  if (dt <= 0.0f || dt > 0.05f) dt = 0.001f;
  s_last_ms = now;

  float sin_t = sinf(theta_elec);
  float cos_t = cosf(theta_elec);

  float i_alpha = 0.0f;
  float i_beta = 0.0f;
  clarke(ia, ib, &i_alpha, &i_beta);

  float id = 0.0f;
  float iq = 0.0f;
  park(i_alpha, i_beta, sin_t, cos_t, &id, &iq);

  float err_d = id_ref - id;
  float err_q = iq_ref - iq;

  s_foc.id_int += FOC_ID_KI * err_d * dt;
  s_foc.iq_int += FOC_IQ_KI * err_q * dt;

  if (s_foc.id_int > FOC_V_LIMIT) s_foc.id_int = FOC_V_LIMIT;
  if (s_foc.id_int < -FOC_V_LIMIT) s_foc.id_int = -FOC_V_LIMIT;
  if (s_foc.iq_int > FOC_V_LIMIT) s_foc.iq_int = FOC_V_LIMIT;
  if (s_foc.iq_int < -FOC_V_LIMIT) s_foc.iq_int = -FOC_V_LIMIT;

  float vd = FOC_ID_KP * err_d + s_foc.id_int;
  float vq = FOC_IQ_KP * err_q + s_foc.iq_int;

  if (vd > FOC_V_LIMIT) vd = FOC_V_LIMIT;
  if (vd < -FOC_V_LIMIT) vd = -FOC_V_LIMIT;
  if (vq > FOC_V_LIMIT) vq = FOC_V_LIMIT;
  if (vq < -FOC_V_LIMIT) vq = -FOC_V_LIMIT;

  inv_park(vd, vq, sin_t, cos_t, v_alpha, v_beta);
}
