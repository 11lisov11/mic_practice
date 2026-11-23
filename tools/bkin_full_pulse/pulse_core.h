#ifndef MIC_BKIN_PULSE_CORE_H
#define MIC_BKIN_PULSE_CORE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* One run per level change; durations are counts of 1-us DMA samples.
 * No IRQ-entry timestamps are used as electrical-edge timestamps. */
enum { BP_RUNS=32, BP_PRE=64, BP_POST=64, BP_LIMIT=100000,
  BP_FROZEN=1, BP_FALL=2, BP_RISE=4, BP_TIMEOUT=8, BP_DMA_ERROR=16,
  BP_OVERRUN=32, BP_OVERFLOW=64, BP_LEFT=128, BP_NO_LOW=256,
  BP_POST_DONE=512 };
#define BP_UNKNOWN UINT32_MAX
typedef struct { uint32_t level, count; } bp_run;
typedef struct {
  uint32_t flags, trigger, samples, runs, fall, rise;
  bp_run run[BP_RUNS];
} bp_capture;

static inline void bp_init(bp_capture *c) {
  memset(c,0,sizeof(*c)); c->fall=BP_UNKNOWN; c->rise=BP_UNKNOWN;
}
static inline void bp_finish(bp_capture *c, uint32_t flags) {
  c->flags |= BP_FROZEN | flags;
}
static inline void bp_feed(bp_capture *c, uint32_t high) {
  if (c->flags & BP_FROZEN) return;
  const uint32_t i=c->samples;
  high=!!high;
  const bool change=c->runs==0 || c->run[c->runs-1].level!=high;
  if (change && c->runs==BP_RUNS) { bp_finish(c,BP_OVERFLOW); return; }
  if (change) {
    c->run[c->runs].level=high;
    c->run[c->runs++].count=0;
    /* Prefer the LOW containing the trigger; otherwise the latest LOW
       preceding it. The entire surrounding waveform remains in the runs. */
    if (!high && (c->fall==BP_UNKNOWN || i<=c->trigger)) {
      c->fall=i; c->rise=BP_UNKNOWN;
      c->flags &= ~(BP_LEFT|BP_RISE|BP_FALL);
      c->flags |= i==0 ? BP_LEFT : BP_FALL;
    } else if (high && c->fall!=BP_UNKNOWN && c->rise==BP_UNKNOWN) {
      c->rise=i; c->flags |= BP_RISE;
    }
  }
  ++c->run[c->runs-1].count; ++c->samples;
  if (c->samples>=c->trigger+BP_POST+1 &&
      (c->fall==BP_UNKNOWN ||
       (c->rise!=BP_UNKNOWN && c->samples>=c->rise+BP_POST+1))) {
    bp_finish(c,BP_POST_DONE | (c->fall==BP_UNKNOWN ? BP_NO_LOW : 0));
  } else if (c->samples>=c->trigger+BP_LIMIT) {
    bp_finish(c,BP_TIMEOUT);
  }
}
static inline uint32_t bp_width(const bp_capture *c) {
  /* A recovered pulse with a missing falling edge is still censored. */
  return (c->flags&(BP_FALL|BP_RISE))==(BP_FALL|BP_RISE) &&
      !(c->flags&(BP_DMA_ERROR|BP_OVERRUN|BP_OVERFLOW)) ?
      c->rise-c->fall : BP_UNKNOWN;
}
#endif
