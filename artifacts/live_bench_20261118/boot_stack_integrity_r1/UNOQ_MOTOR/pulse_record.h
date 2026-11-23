#ifndef MIC_BKIN_PULSE_RECORD_H
#define MIC_BKIN_PULSE_RECORD_H
#include "pulse_core.h"
enum { BP_RECORD_BYTES=320, BP_SCHEMA=5 };
static inline uint32_t bp_u32(const uint8_t *p) {
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static inline bool bp_record_valid(const uint8_t *p) {
  const uint32_t flags=bp_u32(p+20), trigger=bp_u32(p+24),
    samples=bp_u32(p+28), runs=bp_u32(p+32);
  if (bp_u32(p)!=0x314e4b42U || bp_u32(p+4)!=BP_SCHEMA ||
      bp_u32(p+8)!=BP_RECORD_BYTES || bp_u32(p+16)!=200U ||
      !(flags&BP_FROZEN) || flags&~BP_ALLOWED_FLAGS || trigger>BP_PRE ||
      samples>trigger+BP_LIMIT || runs>BP_RUNS || bp_u32(p+36)!=0x50U ||
      bp_u32(p+40)!=BP_LIMIT || bp_u32(p+44)!=BP_POST ||
      bp_u32(p+48)!=BP_PRE || bp_u32(p+52)&~15U ||
      bp_u32(p+56)>8192U || bp_u32(p+60)!=1U ||
      ((flags&BP_POST_DONE) && (flags&BP_TIMEOUT))) return false;
  uint32_t total=0, previous=4, quiet=0;
  for (unsigned i=0;i<BP_RUNS;++i) {
    const uint32_t level=bp_u32(p+64+8*i), count=bp_u32(p+68+8*i);
    if (i>=runs) { if (level || count) return false; continue; }
    if (level>3 || !count || level==previous || count>samples-total) return false;
    total+=count; previous=level; quiet=level==3U ? count : 0U;
  }
  if (total!=samples) return false;
  if ((flags&BP_POST_DONE) && (samples<trigger+BP_POST+1U || quiet<BP_POST+1U)) return false;
  const bool errors=!!(flags&(BP_DMA_ERROR|BP_OVERRUN|BP_OVERFLOW));
  if ((flags&BP_TIMEOUT) && !errors && samples!=trigger+BP_LIMIT) return false;
  if (!(flags&(BP_POST_DONE|BP_TIMEOUT|BP_DMA_ERROR|BP_OVERRUN|BP_OVERFLOW))) return false;
  return true;
}
#endif
