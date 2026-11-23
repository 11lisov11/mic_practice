#ifndef MIC_CURRENT_ADC_WINDOW_PLAN_H
#define MIC_CURRENT_ADC_WINDOW_PLAN_H
#include <stdint.h>

/* All-three-leg aperture geometry; used by candidate firmware and host replay.
 * Two low-side shunts must be settled, and ALL three compare edges must be
 * outside the acquisition guard. This does not certify analog settling.
 * The caller must separately bind CCR/pair/trigger to the same timer epoch.
 */
typedef struct {
  uint32_t trigger;
  uint8_t pair, valid;
} mic_current_window_plan;

static inline int mic_current_window_safe(uint8_t pair,
    uint32_t u,uint32_t v,uint32_t w,uint32_t trigger,
    uint32_t settle_before,uint32_t acquire_after) {
  if(pair>2 || trigger<=settle_before || acquire_after>UINT32_MAX-trigger)return 0;
  const uint32_t c[3]={u,v,w};
  unsigned first=pair==2?1:0,second=pair==0?1:2;
  if(c[first]>=trigger-settle_before || c[second]>=trigger-settle_before)return 0;
  for(unsigned i=0;i<3;++i)
    if(c[i]<=trigger+acquire_after &&
       (c[i]>=trigger || trigger-c[i]<=settle_before))return 0;
  return 1;
}

static inline mic_current_window_plan mic_plan_current_window(
    uint32_t u, uint32_t v, uint32_t w, uint32_t latest_trigger,
    uint32_t settle_before, uint32_t acquire_after) {
  mic_current_window_plan result = {0, 0, 0};
  uint32_t c[3] = {u, v, w};
  unsigned excluded = u>=v && u>=w ? 0 : v>=w ? 1 : 2;
  result.pair = excluded==0 ? 2 : excluded==1 ? 1 : 0;
  uint32_t selected_max = 0;
  for (unsigned i=0;i<3;++i)
    if(i!=excluded && c[i]>selected_max)selected_max=c[i];
  if (selected_max >= latest_trigger || settle_before >= latest_trigger-selected_max)
    return result;
  uint32_t lo = selected_max+settle_before+1;
  /* Preserve the old strobe when it already clears every edge. */
  if(mic_current_window_safe(result.pair,u,v,w,latest_trigger,settle_before,acquire_after)) {
    result.trigger=latest_trigger;result.valid=1;return result;
  }
  uint32_t best_lo = 0, best_hi = 0;
  uint8_t found = 0;
  /* Sample before the excluded leg's compare, or after its settling guard. */
  if (c[excluded]>acquire_after) {
    uint32_t hi = c[excluded]-acquire_after-1;
    if(hi>latest_trigger)hi=latest_trigger;
    if(lo<=hi){best_lo=lo;best_hi=hi;found=1;}
  }
  if(c[excluded]<latest_trigger && settle_before<latest_trigger-c[excluded]) {
    uint32_t after = c[excluded]+settle_before+1;
    if(after<lo)after=lo;
    if(after<=latest_trigger && (!found || latest_trigger-after>best_hi-best_lo)) {
      best_lo=after;best_hi=latest_trigger;found=1;
    }
  }
  if(found){result.trigger=best_lo+(best_hi-best_lo)/2;result.valid=1;}
  return result;
}
#endif
