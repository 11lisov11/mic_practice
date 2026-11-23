#ifndef MIC_NO_SWITCH_LOAD_CORE_H
#define MIC_NO_SWITCH_LOAD_CORE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

enum { LD_IDLE=0, LD_RUNNING=1, LD_DONE=2, LD_ABORTED=3, LD_DENIED=4 };
enum { LD_BUS=1, LD_OUTPUT=2, LD_CONFIG=4, LD_ADC_STALE=8,
       LD_LOCAL_STOP=16, LD_MATH=32, LD_COMMAND=64, LD_CLOCK=128 };
#define LD_REQUEST 0x4c443501U
#define LD_CANCEL 0x4c440000U
#define LD_MAGIC 0x3147444cU
#define LD_BUILD 2026102803U
#define LD_REPORT_WORDS 72U
typedef struct {
  uint32_t state,reason,attempted,start,stop,elapsed,limit,hz;
} ld_core;
static inline void ld_init(volatile ld_core *q){
  q->state=0;q->reason=0;q->attempted=0;q->start=0;q->stop=0;q->elapsed=0;q->limit=0;q->hz=0;
}
static inline bool ld_request(volatile ld_core*q,uint32_t now,uint32_t hz,uint32_t bad){
  if(q->attempted)return false;
  q->attempted=1;q->hz=hz;
  if(hz!=170000000U)bad|=LD_CLOCK;
  if(bad){q->state=LD_DENIED;q->reason=bad;return false;}
  q->start=now;q->limit=hz*5U;q->elapsed=0;q->state=LD_RUNNING;return true;
}
static inline bool ld_tick(volatile ld_core*q,uint32_t now,uint32_t bad){
  if(q->state!=LD_RUNNING)return false;
  q->elapsed=(uint32_t)(now-q->start);
  if(bad){q->state=LD_ABORTED;q->reason=bad;q->stop=now;return false;}
  if(q->elapsed>=q->limit){q->state=LD_DONE;q->stop=now;return false;}
  return true;
}
static inline uint32_t ld_crc(const uint32_t *v,unsigned n){
  uint32_t c=~0U;
  for(unsigned j=0;j<n;j++)for(unsigned b=0;b<4;b++){
    c^=(v[j]>>(8*b))&255U;
    for(unsigned k=0;k<8;k++)c=(c>>1)^(0x82f63b78U&(0U-(c&1U)));
  }
  return ~c;
}
#endif
