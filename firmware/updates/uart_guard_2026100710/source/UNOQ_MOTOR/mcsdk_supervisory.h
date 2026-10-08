#pragma once
#include <math.h>
#include <stdint.h>

inline bool unoq_mcsdk_zero_stop(bool mcsdk, float command) {
  return mcsdk && (!isfinite(command) || command < 0.1f);
}

inline uint32_t unoq_bounded_run_deadline(uint32_t now, uint32_t duration,
                                         uint32_t previous, bool bounded) {
  uint32_t proposed = now + duration;
  // Zero is the disabled sentinel, including when the clock wraps.
  if (proposed == 0U) proposed = 1U;
  if (bounded && previous != 0U && (int32_t)(proposed - previous) > 0) return previous;
  return proposed;
}

inline float unoq_scalar_wire_frequency(bool mcsdk, float command, float local_ramp) {
  // MCSDK owns the ramp. Streaming a second ramp restarts its ramp manager.
  return mcsdk ? command : local_ramp;
}

inline bool unoq_local_current_trip(bool mcsdk, bool offset_ready, bool enabled,
                                    float ia, float ib, float ic, float limit) {
  // UNO Q ADC pins are not wired to the IPM current sensors in this topology.
  // MCSDK/IPM protections remain authoritative; this is not a current estimate.
  return !mcsdk && offset_ready && enabled &&
      (fabsf(ia) > limit || fabsf(ib) > limit || fabsf(ic) > limit);
}
