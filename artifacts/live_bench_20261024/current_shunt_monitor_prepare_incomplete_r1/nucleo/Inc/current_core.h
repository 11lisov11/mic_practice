#ifndef MIC_CURRENT_CORE_H
#define MIC_CURRENT_CORE_H
#include <stdint.h>
#include <string.h>

enum { CM_ZERO=1, CM_VALID=2, CM_FROZEN=4, CM_ACTIVE=8, CM_ZERO_BAD=16,
       CM_CLIP=32, CM_TIMING=64, CM_WINDOW_MS=200, CM_ZERO_N=256 };
typedef struct {
  uint32_t n,bad,start_ms,end_ms;
  uint64_t square[3];
  uint16_t peak[3];
  int16_t last[3];
  uint8_t reconstructed,flags;
} cm_window;
typedef struct {
  uint32_t sum[4];
  uint16_t count[4],low[4],high[4],offset[4],raw[4];
  cm_window window,published;
  uint32_t off_since_ms;
  uint8_t zero_ready,zero_bad,was_active,off_seen;
} cm_core;

/* Two converter paths: pair0=U1/V2, pair1=U1/W2, pair2=V1/W2.
 * Calibration therefore has FOUR offsets, not a shared V-channel offset. */
static inline void cm_init(cm_core *s) {
  memset(s,0,sizeof(*s));
  for(unsigned i=0;i<4;++i)s->low[i]=4095;
}
static inline uint8_t cm_path1(uint8_t pair) {return pair==2?1:0;}
static inline uint8_t cm_path2(uint8_t pair) {return pair==0?2:3;}
static inline void cm_zero_sample(cm_core *s,unsigned path,uint16_t raw) {
  s->raw[path]=raw;
  if(s->count[path]>=CM_ZERO_N)return;
  s->sum[path]+=raw;++s->count[path];
  if(raw<s->low[path])s->low[path]=raw;
  if(raw>s->high[path])s->high[path]=raw;
}
static inline int cm_window_valid(const cm_window *w) {
  return w->n>=16 && w->n>=12U*(uint32_t)(w->end_ms-w->start_ms) &&
      w->n*100U>=(w->n+w->bad)*95U && !(w->flags&CM_CLIP);
}
static inline void cm_publish(cm_core *s,uint32_t now,uint8_t frozen) {
  s->window.end_ms=now;
  s->published=s->window;
  if(frozen)s->published.flags|=CM_FROZEN;
  memset(&s->window,0,sizeof(s->window));s->window.start_ms=now;
}
static inline void cm_sample(cm_core *s,uint32_t now,uint8_t active,uint8_t pair,
    uint16_t a,uint16_t b,uint8_t timing_ok,uint8_t zero_bus_ok) {
  unsigned p=cm_path1(pair),q=cm_path2(pair);
  s->raw[p]=a;s->raw[q]=b;
  if(!active) {
    if(s->was_active)cm_publish(s,now,1);
    s->was_active=0;
    if(!s->off_seen){s->off_seen=1;s->off_since_ms=now;}
    if(!s->zero_ready && !s->zero_bad && zero_bus_ok && (uint32_t)(now-s->off_since_ms)>=500U) {
      cm_zero_sample(s,p,a);cm_zero_sample(s,q,b);
      unsigned complete=0;
      for(unsigned i=0;i<4;++i)complete+=s->count[i]>=CM_ZERO_N;
      if(complete==4) {
        for(unsigned i=0;i<4;++i) {
          s->offset[i]=(uint16_t)((s->sum[i]+CM_ZERO_N/2)/CM_ZERO_N);
          if(s->offset[i]<1600 || s->offset[i]>2500 || s->high[i]-s->low[i]>40)s->zero_bad=1;
        }
        s->zero_ready=!s->zero_bad;
      }
    }
    if(!zero_bus_ok)s->off_since_ms=now;
    return;
  }
  s->off_seen=0;
  if(!s->was_active){memset(&s->window,0,sizeof(s->window));s->window.start_ms=now;}
  s->was_active=1;
  if(!timing_ok || !s->zero_ready || a<16 || b<16 || a>4079 || b>4079) {
    ++s->window.bad;
    if(!timing_ok)s->window.flags|=CM_TIMING;
    if(a<16 || b<16 || a>4079 || b>4079)s->window.flags|=CM_CLIP;
  } else {
    int32_t i[3]={0,0,0};
    unsigned phase1=pair==2?1:0,phase2=pair==0?1:2;
    /* Same offset-minus-ADC sign convention as R3_2_GetPhaseCurrents. */
    i[phase1]=(int32_t)s->offset[p]-a;i[phase2]=(int32_t)s->offset[q]-b;
    unsigned third=3-phase1-phase2;i[third]=-i[phase1]-i[phase2];
    s->window.reconstructed|=(uint8_t)(1U<<third);
    for(unsigned j=0;j<3;++j) {
      uint32_t mag=(uint32_t)(i[j]<0?-i[j]:i[j]);
      s->window.last[j]=(int16_t)i[j];
      s->window.square[j]+=(uint64_t)mag*mag;
      if(mag>s->window.peak[j])s->window.peak[j]=(uint16_t)mag;
    }
    ++s->window.n;
  }
  if((uint32_t)(now-s->window.start_ms)>=CM_WINDOW_MS)cm_publish(s,now,0);
}

/* Plan uses the two longest low-side conduction windows. The CCR values
 * passed here are the shadow values for the next PWM cycle. */
static inline uint8_t cm_choose_pair(uint32_t u,uint32_t v,uint32_t w) {
  if(u>=v && u>=w)return 2;
  if(v>=w)return 1;
  return 0;
}
static inline int cm_pair_window(uint8_t pair,uint32_t u,uint32_t v,uint32_t w,
    uint32_t trigger,uint32_t settle) {
  uint32_t x=pair==2?v:u,y=pair==0?v:w;
  return trigger>settle && x<trigger-settle && y<trigger-settle;
}
#endif
