#ifndef MIC_BKIN_PULSE_CORE_H
#define MIC_BKIN_PULSE_CORE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* One GPIOA IDR read per 200-ns requested DMA sample. State bit 0 is
 * PA6/BKIN; bit 1 is PA4, independently wired to STEVAL TP23/SD.
 * Lossless joint RLE: transitions on either line are retained. */
enum { BP_RUNS=32, BP_PRE=2048, BP_POST=320, BP_LIMIT=500000,
  BP_FROZEN=1, BP_TIMEOUT=8, BP_DMA_ERROR=16, BP_OVERRUN=32,
  BP_OVERFLOW=64, BP_POST_DONE=512, BP_ALLOWED_FLAGS=633 };
typedef struct { uint32_t level, count; } bp_run;
typedef struct {
  uint32_t flags, trigger, samples, runs, quiet;
  bp_run run[BP_RUNS];
} bp_capture;

static inline uint32_t bp_state(uint32_t idr) {
  return ((idr>>6)&1U) | (((idr>>4)&1U)<<1);
}
static inline void bp_init(bp_capture *c) { memset(c,0,sizeof(*c)); }
static inline void bp_finish(bp_capture *c,uint32_t flags) {
  c->flags |= BP_FROZEN | flags;
}
static inline void bp_feed(bp_capture *c,uint32_t level) {
  if (c->flags&BP_FROZEN) return;
  const bool change=c->runs==0 || c->run[c->runs-1].level!=level;
  if (change && c->runs==BP_RUNS) { bp_finish(c,BP_OVERFLOW); return; }
  if (change) {
    c->run[c->runs].level=level;
    c->run[c->runs++].count=0;
  }
  ++c->run[c->runs-1].count; ++c->samples;
  c->quiet=level==3U ? c->quiet+1U : 0U;
  /* Both lines must recover. A late LOW on either line extends the window,
   * even when the other line's selected pulse already ended. */
  if (c->samples>=c->trigger+BP_POST+1U && c->quiet>=BP_POST+1U)
    bp_finish(c,BP_POST_DONE);
  else if (c->samples>=c->trigger+BP_LIMIT) bp_finish(c,BP_TIMEOUT);
}
static inline uint32_t bp_feed_span(bp_capture *c,uint32_t level,uint32_t count) {
  if (!count || (c->flags&BP_FROZEN)) return 0;
  bp_feed(c,level);
  uint32_t used=1;
  if (count==1 || (c->flags&BP_FROZEN)) return used;
  uint32_t stop=c->trigger+BP_LIMIT;
  if (level==3U) {
    uint32_t post=c->samples;
    if (c->quiet<BP_POST+1U) post+=BP_POST+1U-c->quiet;
    if (post<c->trigger+BP_POST+1U) post=c->trigger+BP_POST+1U;
    if (post<stop) stop=post;
  }
  uint32_t extra=count-1U;
  if (extra>=stop-c->samples) extra=stop-c->samples-1U;
  c->samples+=extra; c->run[c->runs-1].count+=extra;
  if (level==3U) c->quiet+=extra;
  used+=extra;
  if (used<count) { bp_feed(c,level); ++used; }
  return used;
}
#endif
