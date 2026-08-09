#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef struct {
  float pi_id_integrator;
  float pi_iq_integrator;
  float disturbance_d;
  float disturbance_q;
  float i_alpha_filtered;
  float i_beta_filtered;
  bool current_filter_initialized;
  uint32_t steps;
} motor_control_benchmark_state_t;

typedef struct {
  float ia;
  float ib;
  float electrical_angle_rad;
  float electrical_speed_rad_s;
  float id_ref;
  float iq_ref;
  float vbus;
  float dt;
} motor_control_benchmark_input_t;

typedef struct {
  float id;
  float iq;
  float vd_pi;
  float vq_pi;
  float vd_deadbeat;
  float vq_deadbeat;
  float i_alpha_filtered;
  float i_beta_filtered;
  float duty_u;
  float duty_v;
  float duty_w;
} motor_control_benchmark_output_t;

void motor_control_benchmark_init(motor_control_benchmark_state_t *state);
bool motor_control_benchmark_step(
    motor_control_benchmark_state_t *state,
    const motor_control_benchmark_input_t *input,
    motor_control_benchmark_output_t *output);
