#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "motor_control_benchmark.h"

static void assert_duty(float duty) {
  assert(isfinite(duty));
  assert(duty >= 0.02f);
  assert(duty <= 0.98f);
}

static void assert_output_cleared(const motor_control_benchmark_output_t &output) {
  const float *values = reinterpret_cast<const float *>(&output);
  for (size_t i = 0; i < sizeof(output) / sizeof(float); ++i) {
    assert(values[i] == 0.0f);
  }
}

static void test_long_run_is_bounded(void) {
  motor_control_benchmark_state_t state;
  motor_control_benchmark_init(&state);
  motor_control_benchmark_output_t output = {};
  motor_control_benchmark_input_t input = {
      0.2f, -0.1f, 0.0f, 30.0f, 0.8f, 0.4f, 24.0f, 1.0f / 20000.0f};
  uint32_t deadbeat_saturated = 0U;
  const float voltage_limit = 0.9f * input.vbus / sqrtf(3.0f);

  for (uint32_t i = 0; i < 100000U; ++i) {
    input.electrical_angle_rad += 0.001f;
    if (input.electrical_angle_rad > 6.28318530718f) {
      input.electrical_angle_rad -= 6.28318530718f;
    }
    input.ia = 0.7f * sinf(input.electrical_angle_rad);
    input.ib = 0.7f * sinf(input.electrical_angle_rad - 2.09439510239f);
    assert(motor_control_benchmark_step(&state, &input, &output));
    assert_duty(output.duty_u);
    assert_duty(output.duty_v);
    assert_duty(output.duty_w);
    if (fabsf(output.vd_deadbeat) > 0.99f * voltage_limit ||
        fabsf(output.vq_deadbeat) > 0.99f * voltage_limit) {
      ++deadbeat_saturated;
    }
  }
  assert(state.steps == 100000U);
  assert(deadbeat_saturated < 1000U);
}

static void test_invalid_input_and_state_fail_closed(void) {
  motor_control_benchmark_state_t state;
  motor_control_benchmark_init(&state);
  motor_control_benchmark_output_t output;
  memset(&output, 0xA5, sizeof(output));
  motor_control_benchmark_input_t input = {
      0.2f, -0.1f, 0.0f, 30.0f, 0.8f, 0.4f, 0.0f, 1.0f / 20000.0f};
  assert(!motor_control_benchmark_step(&state, &input, &output));
  assert_output_cleared(output);

  input.vbus = 24.0f;
  input.dt = NAN;
  memset(&output, 0xA5, sizeof(output));
  assert(!motor_control_benchmark_step(&state, &input, &output));
  assert_output_cleared(output);

  input.dt = 1.0f / 20000.0f;
  state.disturbance_q = NAN;
  memset(&output, 0xA5, sizeof(output));
  assert(!motor_control_benchmark_step(&state, &input, &output));
  assert_output_cleared(output);
}

static void test_current_noise_is_attenuated(void) {
  motor_control_benchmark_state_t state;
  motor_control_benchmark_init(&state);
  motor_control_benchmark_output_t output = {};
  motor_control_benchmark_input_t input = {
      0.4f, -0.2f, 0.0f, 0.0f, 0.4f, 0.0f, 24.0f, 1.0f / 20000.0f};
  double raw_energy = 0.0;
  double filtered_energy = 0.0;
  uint32_t samples = 0U;
  for (uint32_t i = 0; i < 20000U; ++i) {
    const float noise = (i & 1U) ? 0.08f : -0.08f;
    input.ia = 0.4f + noise;
    input.ib = -0.2f - 0.5f * noise;
    if ((i % 997U) == 0U) {
      input.ia += 0.5f;
    }
    assert(motor_control_benchmark_step(&state, &input, &output));
    if (i > 100U) {
      const float raw_error = input.ia - 0.4f;
      const float filtered_error = output.i_alpha_filtered - 0.4f;
      raw_energy += raw_error * raw_error;
      filtered_energy += filtered_error * filtered_error;
      ++samples;
    }
  }
  assert(samples > 0U);
  assert(filtered_energy < 0.35 * raw_energy);
}

static void test_known_park_transform(void) {
  motor_control_benchmark_state_t state;
  motor_control_benchmark_init(&state);
  motor_control_benchmark_output_t output = {};
  const float theta = 0.7f;
  motor_control_benchmark_input_t input = {
      0.6f * cosf(theta),
      0.6f * cosf(theta - 2.09439510239f),
      theta,
      0.0f,
      0.6f,
      0.0f,
      24.0f,
      1.0f / 20000.0f};
  assert(motor_control_benchmark_step(&state, &input, &output));
  assert(fabsf(output.id - 0.6f) < 1e-5f);
  assert(fabsf(output.iq) < 1e-5f);
}

int main(void) {
  test_long_run_is_bounded();
  test_invalid_input_and_state_fail_closed();
  test_current_noise_is_attenuated();
  test_known_park_transform();
  puts("NUCLEO_CONTROL_BENCHMARK_SELFTEST PASS");
  return 0;
}
