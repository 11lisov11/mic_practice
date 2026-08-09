#include "motor_control_benchmark.h"

#include <math.h>
#include <string.h>

static constexpr float INV_SQRT3 = 0.57735026919f;
static constexpr float SQRT3_OVER_2 = 0.86602540378f;
static constexpr float PI_KP = 0.35f;
static constexpr float PI_KI = 45.0f;
static constexpr float ANTI_WINDUP_GAIN = 0.25f;
// Representative low-voltage benchmark plant only. The real Rs/Lsigma values
// must come from motor identification before this code can drive PWM.
static constexpr float MOTOR_R_BENCH_OHM = 1.2f;
static constexpr float MOTOR_L_BENCH_H = 0.0004f;
static constexpr float OBSERVER_GAIN = 120.0f;
static constexpr float DEADBEAT_BLEND = 0.35f;
static constexpr float CURRENT_FILTER_TAU_S = 0.00006366198f;  // 2.5 kHz.
static constexpr float CURRENT_MAX_SLEW_PER_S = 4000.0f;
static constexpr float MAX_ABS_CURRENT = 1000.0f;
static constexpr float MAX_ABS_SPEED_RAD_S = 1000000.0f;
static constexpr float MAX_VBUS = 1000.0f;
static constexpr float MAX_DT = 0.01f;

static float clampf(float value, float low, float high) {
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

static bool finite_input(const motor_control_benchmark_input_t *input) {
  return isfinite(input->ia) && isfinite(input->ib) &&
         isfinite(input->electrical_angle_rad) &&
         isfinite(input->electrical_speed_rad_s) &&
         isfinite(input->id_ref) && isfinite(input->iq_ref) &&
         isfinite(input->vbus) && isfinite(input->dt) &&
         input->vbus > 0.1f && input->vbus <= MAX_VBUS &&
         input->dt > 0.0f && input->dt <= MAX_DT &&
         fabsf(input->ia) <= MAX_ABS_CURRENT &&
         fabsf(input->ib) <= MAX_ABS_CURRENT &&
         fabsf(input->id_ref) <= MAX_ABS_CURRENT &&
         fabsf(input->iq_ref) <= MAX_ABS_CURRENT &&
         fabsf(input->electrical_speed_rad_s) <= MAX_ABS_SPEED_RAD_S;
}

static bool finite_state(const motor_control_benchmark_state_t *state) {
  return isfinite(state->pi_id_integrator) &&
         isfinite(state->pi_iq_integrator) &&
         isfinite(state->disturbance_d) &&
         isfinite(state->disturbance_q) &&
         isfinite(state->i_alpha_filtered) &&
         isfinite(state->i_beta_filtered);
}

static float slew_limited_low_pass(float previous, float sample, float dt) {
  const float max_step = CURRENT_MAX_SLEW_PER_S * dt;
  const float limited_sample = previous + clampf(sample - previous, -max_step, max_step);
  const float alpha = dt / (CURRENT_FILTER_TAU_S + dt);
  return previous + alpha * (limited_sample - previous);
}

static void svm(float alpha, float beta, float vbus, float *du, float *dv, float *dw) {
  const float va = alpha;
  const float vb = -0.5f * alpha + SQRT3_OVER_2 * beta;
  const float vc = -0.5f * alpha - SQRT3_OVER_2 * beta;
  const float vmax = fmaxf(va, fmaxf(vb, vc));
  const float vmin = fminf(va, fminf(vb, vc));
  const float common = -0.5f * (vmax + vmin);
  const float inv_vbus = 1.0f / vbus;
  *du = clampf(0.5f + (va + common) * inv_vbus, 0.02f, 0.98f);
  *dv = clampf(0.5f + (vb + common) * inv_vbus, 0.02f, 0.98f);
  *dw = clampf(0.5f + (vc + common) * inv_vbus, 0.02f, 0.98f);
}

void motor_control_benchmark_init(motor_control_benchmark_state_t *state) {
  if (state != nullptr) {
    memset(state, 0, sizeof(*state));
  }
}

bool motor_control_benchmark_step(
    motor_control_benchmark_state_t *state,
    const motor_control_benchmark_input_t *input,
    motor_control_benchmark_output_t *output) {
  if (output != nullptr) {
    memset(output, 0, sizeof(*output));
  }
  if (state == nullptr || input == nullptr || output == nullptr ||
      !finite_input(input) || !finite_state(state)) {
    return false;
  }

  const float sin_theta = sinf(input->electrical_angle_rad);
  const float cos_theta = cosf(input->electrical_angle_rad);
  const float i_alpha_raw = input->ia;
  const float i_beta_raw = (input->ia + 2.0f * input->ib) * INV_SQRT3;
  if (!state->current_filter_initialized) {
    state->i_alpha_filtered = i_alpha_raw;
    state->i_beta_filtered = i_beta_raw;
    state->current_filter_initialized = true;
  } else {
    state->i_alpha_filtered = slew_limited_low_pass(
        state->i_alpha_filtered, i_alpha_raw, input->dt);
    state->i_beta_filtered = slew_limited_low_pass(
        state->i_beta_filtered, i_beta_raw, input->dt);
  }
  const float i_alpha = state->i_alpha_filtered;
  const float i_beta = state->i_beta_filtered;
  const float id = i_alpha * cos_theta + i_beta * sin_theta;
  const float iq = -i_alpha * sin_theta + i_beta * cos_theta;
  const float err_d = input->id_ref - id;
  const float err_q = input->iq_ref - iq;
  const float voltage_limit = 0.90f * input->vbus * INV_SQRT3;

  state->pi_id_integrator += PI_KI * err_d * input->dt;
  state->pi_iq_integrator += PI_KI * err_q * input->dt;
  state->pi_id_integrator = clampf(state->pi_id_integrator, -voltage_limit, voltage_limit);
  state->pi_iq_integrator = clampf(state->pi_iq_integrator, -voltage_limit, voltage_limit);

  const float vd_pi_unclamped = PI_KP * err_d + state->pi_id_integrator;
  const float vq_pi_unclamped = PI_KP * err_q + state->pi_iq_integrator;
  const float vd_pi = clampf(vd_pi_unclamped, -voltage_limit, voltage_limit);
  const float vq_pi = clampf(vq_pi_unclamped, -voltage_limit, voltage_limit);
  state->pi_id_integrator += ANTI_WINDUP_GAIN * (vd_pi - vd_pi_unclamped);
  state->pi_iq_integrator += ANTI_WINDUP_GAIN * (vq_pi - vq_pi_unclamped);
  state->pi_id_integrator = clampf(state->pi_id_integrator, -voltage_limit, voltage_limit);
  state->pi_iq_integrator = clampf(state->pi_iq_integrator, -voltage_limit, voltage_limit);

  const float model_d = MOTOR_R_BENCH_OHM * id -
                        input->electrical_speed_rad_s * MOTOR_L_BENCH_H * iq;
  const float model_q = MOTOR_R_BENCH_OHM * iq +
                        input->electrical_speed_rad_s * MOTOR_L_BENCH_H * id;
  const float vd_deadbeat = clampf(
      model_d + MOTOR_L_BENCH_H * err_d / input->dt - state->disturbance_d,
      -voltage_limit,
      voltage_limit);
  const float vq_deadbeat = clampf(
      model_q + MOTOR_L_BENCH_H * err_q / input->dt - state->disturbance_q,
      -voltage_limit,
      voltage_limit);

  state->disturbance_d += OBSERVER_GAIN * (vd_pi - model_d - state->disturbance_d) * input->dt;
  state->disturbance_q += OBSERVER_GAIN * (vq_pi - model_q - state->disturbance_q) * input->dt;
  state->disturbance_d = clampf(state->disturbance_d, -voltage_limit, voltage_limit);
  state->disturbance_q = clampf(state->disturbance_q, -voltage_limit, voltage_limit);

  float vd = (1.0f - DEADBEAT_BLEND) * vd_pi + DEADBEAT_BLEND * vd_deadbeat;
  float vq = (1.0f - DEADBEAT_BLEND) * vq_pi + DEADBEAT_BLEND * vq_deadbeat;
  const float magnitude = sqrtf(vd * vd + vq * vq);
  if (magnitude > voltage_limit && magnitude > 0.0f) {
    const float scale = voltage_limit / magnitude;
    vd *= scale;
    vq *= scale;
  }

  const float alpha = vd * cos_theta - vq * sin_theta;
  const float beta = vd * sin_theta + vq * cos_theta;
  svm(alpha, beta, input->vbus, &output->duty_u, &output->duty_v, &output->duty_w);

  output->id = id;
  output->iq = iq;
  output->vd_pi = vd_pi;
  output->vq_pi = vq_pi;
  output->vd_deadbeat = vd_deadbeat;
  output->vq_deadbeat = vq_deadbeat;
  output->i_alpha_filtered = i_alpha;
  output->i_beta_filtered = i_beta;
  if (state->steps != UINT32_MAX) {
    ++state->steps;
  }

  const bool output_ok = isfinite(output->id) && isfinite(output->iq) &&
                         isfinite(output->vd_pi) && isfinite(output->vq_pi) &&
                         isfinite(output->vd_deadbeat) && isfinite(output->vq_deadbeat) &&
                         isfinite(output->i_alpha_filtered) &&
                         isfinite(output->i_beta_filtered) &&
                         isfinite(output->duty_u) && isfinite(output->duty_v) &&
                         isfinite(output->duty_w);
  if (!output_ok) {
    memset(output, 0, sizeof(*output));
  }
  return output_ok;
}
