#pragma once

#include <math.h>
#include <stdint.h>

static inline float unoq_lerp(float a, float b, float t) {
  if (t <= 0.0f) return a;
  if (t >= 1.0f) return b;
  return a + (b - a) * t;
}

static inline float unoq_interp_1d(const float *x, const float *y, uint8_t n, float v) {
  if (n == 0) return 0.0f;
  if (v <= x[0]) return y[0];
  if (v >= x[n - 1]) return y[n - 1];
  for (uint8_t i = 1; i < n; ++i) {
    if (v <= x[i]) {
      float span = x[i] - x[i - 1];
      float t = (span > 1e-6f) ? ((v - x[i - 1]) / span) : 0.0f;
      return unoq_lerp(y[i - 1], y[i], t);
    }
  }
  return y[n - 1];
}

// LUT policy for motor1: returns Id_ref in Q10 (A * 1024).
// Inputs:
// - omega_ref: electrical angular speed, rad/s
// - load_pu: normalized load, 0..1
static inline int16_t unoq_motor1_id_ref_query(float omega_ref, float load_pu) {
  if (load_pu < 0.0f) load_pu = 0.0f;
  if (load_pu > 1.0f) load_pu = 1.0f;

  const float speed_hz = fabsf(omega_ref) * 0.159154943f; // 1 / (2*pi)

  static const float k_speed_hz[] = {0.0f, 5.0f, 10.0f, 20.0f, 30.0f, 40.0f, 50.0f};
  static const float k_id_noload[] = {0.55f, 0.55f, 0.52f, 0.50f, 0.50f, 0.50f, 0.50f};
  static const float k_id_fullload[] = {1.00f, 1.00f, 0.95f, 0.88f, 0.82f, 0.78f, 0.75f};

  const uint8_t n = (uint8_t)(sizeof(k_speed_hz) / sizeof(k_speed_hz[0]));
  float id_lo = unoq_interp_1d(k_speed_hz, k_id_noload, n, speed_hz);
  float id_hi = unoq_interp_1d(k_speed_hz, k_id_fullload, n, speed_hz);
  float id_ref_a = unoq_lerp(id_lo, id_hi, load_pu);

  if (id_ref_a < 0.5f) id_ref_a = 0.5f;
  if (id_ref_a > 1.2f) id_ref_a = 1.2f;

  int32_t q10 = (int32_t)lroundf(id_ref_a * 1024.0f);
  if (q10 > 32767) q10 = 32767;
  if (q10 < -32768) q10 = -32768;
  return (int16_t)q10;
}
