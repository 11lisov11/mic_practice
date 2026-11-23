#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
  uint32_t run_started_ms;
  uint32_t asserted_ms;
  bool run_seen;
  bool fired;
  bool pulling;
} MicBenchSdPulse;

/* One external open-drain pulse per boot; never start PWM or alter BKIN. */
static inline bool mic_bench_sd_pull(MicBenchSdPulse *p, uint32_t now,
                                     bool pwm_on, bool bus_safe) {
  if (!bus_safe) {
    p->pulling = false;
    p->run_seen = false;
    return false;
  }
  if (p->pulling) {
    if ((uint32_t)(now - p->asserted_ms) >= 250U) p->pulling = false;
    return p->pulling;
  }
  if (p->fired) return false;
  if (!pwm_on) {
    p->run_seen = false;
    return false;
  }
  if (!p->run_seen) {
    p->run_seen = true;
    p->run_started_ms = now;
    return false;
  }
  if ((uint32_t)(now - p->run_started_ms) < 800U) return false;
  p->fired = true;
  p->pulling = true;
  p->asserted_ms = now;
  return true;
}
