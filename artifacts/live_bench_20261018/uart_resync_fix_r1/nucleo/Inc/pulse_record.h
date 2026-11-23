#ifndef MIC_BKIN_PULSE_RECORD_H
#define MIC_BKIN_PULSE_RECORD_H
#include "pulse_core.h"
enum { BP_RECORD_BYTES=320, BP_SCHEMA=4 };
static inline uint32_t bp_u32(const uint8_t *p) {
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static inline bool bp_record_valid(const uint8_t *p) {
  const uint32_t flags=bp_u32(p+20), trigger=bp_u32(p+24),
    samples=bp_u32(p+28), runs=bp_u32(p+32), fall=bp_u32(p+36),
    rise=bp_u32(p+40), width=bp_u32(p+44);
  if (bp_u32(p)!=0x314e4b42U || bp_u32(p+4)!=BP_SCHEMA ||
      bp_u32(p+8)!=BP_RECORD_BYTES || bp_u32(p+16)!=200U ||
      !(flags&BP_FROZEN) || flags&~1023U || trigger>BP_PRE ||
      samples>trigger+BP_LIMIT || runs>BP_RUNS || bp_u32(p+48)!=BP_LIMIT ||
      bp_u32(p+52)&~15U || bp_u32(p+56)>8192U || bp_u32(p+60)!=0U ||
      ((flags&BP_POST_DONE) && (flags&BP_TIMEOUT)) ||
      ((flags&BP_FALL) && (flags&BP_LEFT))) return false;
  uint32_t total=0, previous=2, expected_fall=BP_UNKNOWN, expected_rise=BP_UNKNOWN;
  for (unsigned i=0;i<BP_RUNS;++i) {
    const uint32_t high=bp_u32(p+64+8*i), count=bp_u32(p+68+8*i);
    if (i>=runs) { if (high || count) return false; continue; }
    if (high>1 || !count || high==previous || count>samples-total) return false;
    if (!high && (expected_fall==BP_UNKNOWN || total<=trigger)) {
      expected_fall=total; expected_rise=BP_UNKNOWN;
    } else if (high && expected_fall!=BP_UNKNOWN && expected_rise==BP_UNKNOWN)
      expected_rise=total;
    total+=count; previous=high;
  }
  if (total!=samples || fall!=expected_fall || rise!=expected_rise ||
      !!(flags&BP_RISE)!=(rise!=BP_UNKNOWN) ||
      !!(flags&BP_LEFT)!=(fall==0U) ||
      !!(flags&BP_FALL)!=(fall!=BP_UNKNOWN && fall!=0U)) return false;
  const bool errors=!!(flags&(BP_DMA_ERROR|BP_OVERRUN|BP_OVERFLOW));
  const uint32_t expected_width=fall!=BP_UNKNOWN && fall!=0U && rise!=BP_UNKNOWN && !errors ? rise-fall : BP_UNKNOWN;
  if (width!=expected_width) return false;
  if (flags&BP_POST_DONE) {
    if (samples<trigger+BP_POST+1 ||
        !!(flags&BP_NO_LOW)!=(fall==BP_UNKNOWN) ||
        (fall!=BP_UNKNOWN && (rise==BP_UNKNOWN || samples<rise+BP_POST+1))) return false;
  } else if (flags&BP_NO_LOW) return false;
  if (!(flags&(BP_POST_DONE|BP_TIMEOUT|BP_DMA_ERROR|BP_OVERRUN|BP_OVERFLOW))) return false;
  return true;
}
#endif
