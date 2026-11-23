#ifndef MIC_ADC_IDLE_NOISE_CORE_H
#define MIC_ADC_IDLE_NOISE_CORE_H
#include <stdint.h>
#include <string.h>
/* A once-per-boot, OFF/low-bus-only diagnostic. No register writes here.
 * 0: original alternate U1/V2,V1/W2; 1: fixed U1/V2;
 * 2: fixed V1/W2; 3: SAME physical V input on ADC1 and ADC2.
 * Sixteen discarded conversions settle each context. Keep every subsequent
 * sample, without filtering, clipping or rejecting statistical outliers.
 */
enum { ND_CASES=4,ND_SAMPLES=128,ND_HEADER=128,ND_BYTES=2176,
       ND_PAGES=(ND_BYTES+23)/24,ND_VIEW_PAGES=ND_BYTES/128,ND_SETTLE=16 };
typedef struct {
 uint8_t bytes[ND_BYTES];uint32_t crc,start,finish;
 uint16_t n,discard;uint8_t stage,started,done,ready,fault;
} nd_state;
static inline void nd_put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static inline void nd_init(nd_state*s){memset(s,0,sizeof(*s));}
static inline int nd_pair(const nd_state*s,uint8_t previous){
 if(!s->started||s->done)return -1;
 return s->stage==0?(previous==0?2:0):s->stage==1?0:s->stage==2?2:3;
}
static inline int nd_step(nd_state*s,uint8_t pair,uint16_t a,uint16_t b,
 uint8_t outputs_off,uint8_t bus_low,uint8_t zero_ready,uint8_t queue_ok,uint32_t now){
 if(s->done)return -1;
 if(!s->started){
  if(!outputs_off||!bus_low||!zero_ready||!queue_ok)return -1;
  s->started=1;s->start=now;s->discard=ND_SETTLE;
 }
 if(!outputs_off||!bus_low||!queue_ok||a>4095||b>4095){
  s->fault=outputs_off?(bus_low?3:2):1;s->done=1;s->finish=now;return -1;
 }
 uint8_t wanted=s->stage==1?0:s->stage==2?2:3;
 int expected=s->stage==0?(pair==0||pair==2):(pair==wanted);
 if(!expected){s->discard=ND_SETTLE;return nd_pair(s,pair);}
 if(s->discard)--s->discard;
 else{
  unsigned offset=ND_HEADER+4U*(s->stage*ND_SAMPLES+s->n);
  uint16_t first=(uint16_t)(a|((uint16_t)pair<<12));
  s->bytes[offset]=(uint8_t)first;s->bytes[offset+1]=(uint8_t)(first>>8);
  s->bytes[offset+2]=(uint8_t)b;s->bytes[offset+3]=(uint8_t)(b>>8);
  if(++s->n==ND_SAMPLES){
   s->n=0;s->discard=ND_SETTLE;
   if(++s->stage==ND_CASES){s->done=1;s->finish=now;return -1;}
  }
 }
 return nd_pair(s,pair);
}
/* Call in main, OFF only, never from the current IRQ. */
static inline int nd_seal(nd_state*s,uint32_t build,uint32_t clock,uint32_t revision,
 const uint32_t registers[8]){
 if(!s->done||s->ready)return 0;
 nd_put(s->bytes,0x314E4441U);nd_put(s->bytes+4,1);nd_put(s->bytes+8,build);
 nd_put(s->bytes+12,clock);nd_put(s->bytes+16,revision);nd_put(s->bytes+20,s->fault);
 nd_put(s->bytes+24,s->start);nd_put(s->bytes+28,s->finish);
 nd_put(s->bytes+32,ND_CASES);nd_put(s->bytes+36,ND_SAMPLES);
 nd_put(s->bytes+40,s->stage);nd_put(s->bytes+44,s->n);
 for(unsigned i=0;i<8;i++)nd_put(s->bytes+48+4*i,registers[i]);
 s->crc=uv3_crc32c(s->bytes,ND_BYTES);s->ready=1;return 1;
}
#endif
