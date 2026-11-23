#ifndef MIC_PE_RELEASE_PROBE_H
#define MIC_PE_RELEASE_PROBE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
/* Read-only differential observation AFTER the existing forced PE reset.
   No GPIO writes, bus clocks, retries, interrupt masking or polling loops.
   This is an offline-reviewed module, not an installed firmware change.
   Samples retain actual times: a late poll never pretends to be a 5us sample. */
enum { SR_IMMEDIATE=1,SR_LATE=2,SR_CANCELLED=4,SR_TIMEOUT=8 };
typedef struct { uint32_t cycles,isr,cr1,cr2,gpio; } sr_sample;
typedef struct {
  sr_sample after[3];
  uint32_t terminal_cycles,terminal_gpio;
  uint8_t count,flags;
  bool active,complete;
} sr_probe;
static inline void sr_arm(sr_probe *p,uint32_t cycles,uint32_t gpio){
  /* Frozen first record: never overwrite either a pending or a completed one. */
  if(p->active||p->complete)return;
  memset(p,0,sizeof(*p));p->terminal_cycles=cycles;p->terminal_gpio=gpio;p->active=true;
}
static inline void sr_after_park(sr_probe *p,sr_sample s){
  if(!p->active||p->count)return;
  if(s.cr1&1U){p->flags|=SR_CANCELLED;p->active=false;return;}
  p->after[0]=s;p->count=1;p->flags|=SR_IMMEDIATE;
}
static inline void sr_poll(sr_probe *p,sr_sample s,uint32_t hz){
  if(!p->active||!p->count)return;
  if((s.cr1&1U)||hz<1000000U){p->flags|=SR_CANCELLED;p->active=false;return;}
  uint32_t elapsed=s.cycles-p->after[0].cycles;
  uint32_t us=elapsed/(hz/1000000U);
  /* An unexpectedly long gap is diagnostic loss, never source attribution. */
  if(us>1000U){p->flags|=SR_TIMEOUT;p->active=false;return;}
  if(p->count==1){
    if(us<5U)return;
    p->after[1]=s;p->count=2;
    if(us>=20U){p->flags|=SR_LATE;p->active=false;p->complete=true;}
    return;
  }
  if(p->count==2&&us>=20U){p->after[2]=s;p->count=3;p->active=false;p->complete=true;}
}
/* These are observations, not claims that the sensor or MCU is defective. */
enum { SR_UNKNOWN=0,SR_SCL_HIGH_AFTER_DISABLE=1,SR_SCL_LOW_AFTER_DISABLE=2,SR_MIXED=3 };
static inline unsigned sr_result(const sr_probe *p){
  if(!p->complete||(p->flags&(SR_CANCELLED|SR_TIMEOUT))||p->count<2)return SR_UNKNOWN;
  bool high=false,low=false;
  for(unsigned i=0;i<p->count;i++){
    if(p->after[i].cr1&1U)return SR_UNKNOWN;
    if(p->after[i].gpio&(1U<<8))high=true;else low=true;
  }
  return high&&low?SR_MIXED:high?SR_SCL_HIGH_AFTER_DISABLE:SR_SCL_LOW_AFTER_DISABLE;
}
#endif
