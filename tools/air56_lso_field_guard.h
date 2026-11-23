#ifndef AIR56_LSO_FIELD_GUARD_H
#define AIR56_LSO_FIELD_GUARD_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

enum {
  AIR56_FIELD_WINDOW = 256,
  AIR56_FIELD_NONFINITE = 1,
  AIR56_FIELD_ROTOR_RATE = 2,
  AIR56_FIELD_NO_SLIP_EVIDENCE = 3,
  AIR56_FIELD_SLIP_DISAGREEMENT = 4,
  AIR56_FIELD_COMPENSATED_RATE = 5,
  AIR56_FIELD_MAGIC = 0x3144464cU /* LFD1 */
};

typedef struct {
  float flux_counts;
  float field_sum, rotor_sum, reference_sum;
  int32_t iq_sum, iq_ref_sum;
  uint16_t frames;
  bool initialized;
} air56_field_guard;

typedef struct {
  uint32_t magic, start_ms;
  uint16_t reason, samples;
  float field_hz, rotor_hz, reference_hz, measured_slip_hz, flux_counts;
} air56_field_fault;

_Static_assert(sizeof(air56_field_fault) == 32, "Field fault must fit one page");

#define AIR56_FIELD_MARGIN_HZ 0.75f
#define AIR56_FIELD_RAD_PER_TURN 6.2831853072f

static inline bool air56_field_finite(float value)
{
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return (bits & 0x7f800000U) != 0x7f800000U;
}

/* Units of current cancel in Iq / (tau_r * (lambda_r / Lm)). The latter
 * current-equivalent flux is integrated from measured Id, not from LSO state.
 * The caller uses the same fresh Iqd sample and PWM rate as the observer.
 */
static __attribute__((noinline)) unsigned air56_field_check(air56_field_guard *guard,
    qd_t measured, int16_t commanded_iq, float speed_ref_hz, float field_rad_s,
    float rotor_rad_s, air56_field_fault *fault)
{
  if (!air56_field_finite(field_rad_s) || !air56_field_finite(rotor_rad_s))
  {
    *fault = (air56_field_fault){ .reason = AIR56_FIELD_NONFINITE, .samples = guard->frames + 1U,
      .field_hz = field_rad_s / AIR56_FIELD_RAD_PER_TURN,
      .rotor_hz = rotor_rad_s / AIR56_FIELD_RAD_PER_TURN,
      .reference_hz = speed_ref_hz, .flux_counts = guard->flux_counts };
    return fault->reason;
  }

  guard->flux_counts += ((float)measured.d - guard->flux_counts) / (TF_REGULATION_RATE * TAU_R);
  guard->field_sum += field_rad_s;
  guard->rotor_sum += rotor_rad_s;
  guard->reference_sum += speed_ref_hz;
  guard->iq_sum += measured.q;
  guard->iq_ref_sum += commanded_iq;
  if (++guard->frames < AIR56_FIELD_WINDOW) { return 0; }

  const float rad_sum_to_hz = 1.0f / (AIR56_FIELD_WINDOW * AIR56_FIELD_RAD_PER_TURN);
  const float field = guard->field_sum * rad_sum_to_hz;
  const float rotor = guard->rotor_sum * rad_sum_to_hz;
  const float reference = guard->reference_sum / AIR56_FIELD_WINDOW;
  const float flux = guard->flux_counts;
  const int32_t iq_sum = guard->iq_sum;
  const int32_t command_sum = guard->iq_ref_sum;
  *guard = (air56_field_guard){ .flux_counts = flux, .initialized = true };

  const float limit = reference + AIR56_FIELD_MARGIN_HZ;
  unsigned reason = 0;
  float slip = 0.0f;
  if (rotor < -limit || rotor > limit)
  {
    reason = AIR56_FIELD_ROTOR_RATE;
  }
  else if (field > limit || field < -limit)
  {
    /* Extra positive field rate is only explained by positive measured and
     * commanded torque. Grant at most the lesser of the two currents.
     */
    const float flux_low = (int16_t)(DEFAULT_FLUX_COMPONENT_A * LOWER_BW_LIMIT_PERC);
    const float flux_high = (int16_t)(DEFAULT_FLUX_COMPONENT_A * UPPER_BW_LIMIT_PERC);
    if (field < 0.0f || flux < flux_low || flux > flux_high || iq_sum <= 0 ||
        command_sum <= 0 || command_sum > IQMAX * AIR56_FIELD_WINDOW)
    {
      reason = AIR56_FIELD_NO_SLIP_EVIDENCE;
    }
    else
    {
      const int32_t supported_iq = iq_sum < command_sum ? iq_sum : command_sum;
      slip = (float)supported_iq / (AIR56_FIELD_WINDOW * TAU_R * AIR56_FIELD_RAD_PER_TURN * flux);
      const float independent_rotor = field - slip;
      const float difference = independent_rotor - rotor;
      if (difference > AIR56_FIELD_MARGIN_HZ || difference < -AIR56_FIELD_MARGIN_HZ)
      {
        reason = AIR56_FIELD_SLIP_DISAGREEMENT;
      }
      else if (independent_rotor > limit || independent_rotor < -limit)
      {
        reason = AIR56_FIELD_COMPENSATED_RATE;
      }
    }
  }
  if (reason)
  {
    *fault = (air56_field_fault){ .reason = reason, .samples = AIR56_FIELD_WINDOW,
      .field_hz = field, .rotor_hz = rotor, .reference_hz = reference,
      .measured_slip_hz = slip, .flux_counts = flux };
  }
  return reason;
}

#endif
