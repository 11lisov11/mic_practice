#ifndef MIC_CURRENT_CORE_H
#define MIC_CURRENT_CORE_H
#include <stdint.h>
#include <string.h>
#ifndef CM_ZERO_REPORT
#define CM_ZERO_REPORT(s,mean,var,paths) ((void)(var),(void)(paths))
#endif

enum { CM_ZERO=1, CM_VALID=2, CM_FROZEN=4, CM_ACTIVE=8, CM_ZERO_BAD=16,
       CM_CLIP=32, CM_TIMING=64, CM_WINDOW_MS=200, CM_ZERO_N=256,
       CM_ZERO_BLOCKS=3, CM_ZERO_MAX_BLOCKS=8, CM_ZERO_SPAN=40, CM_ZERO_DRIFT=2 };
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
  uint32_t zero_total[4];
  uint16_t zero_low[4],zero_high[4],zero_mean_min[4],zero_mean_max[4];
  uint8_t zero_attempts,zero_stable,zero_last_bad;
  uint32_t zero_energy[4];
  uint64_t zero_group_energy[4];
  uint32_t zero_group_previous[4];
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
  int32_t residual=(int32_t)raw-2048;
  s->zero_energy[path]+=(uint32_t)(residual*residual);
  if(raw<16 || raw>4079)s->zero_energy[path]|=0x80000000UL;
  if((s->count[path]&63U)==0U) {
    int32_t group_sum=(int32_t)(s->sum[path]-s->zero_group_previous[path])-2048*64;
    s->zero_group_previous[path]=s->sum[path];
    s->zero_group_energy[path]+=(uint64_t)((int64_t)group_sum*group_sum);
  }
  if(raw<s->low[path])s->low[path]=raw;
  if(raw>s->high[path])s->high[path]=raw;
}
static inline void cm_zero_block_reset(cm_core *s) {
  memset(s->zero_energy,0,sizeof(s->zero_energy));
  memset(s->zero_group_energy,0,sizeof(s->zero_group_energy));
  memset(s->zero_group_previous,0,sizeof(s->zero_group_previous));
  memset(s->sum,0,sizeof(s->sum));memset(s->count,0,sizeof(s->count));
  memset(s->high,0,sizeof(s->high));
  for(unsigned i=0;i<4;++i)s->low[i]=4095;
}
static inline void cm_zero_finish_block(cm_core *s) {
  ++s->zero_attempts;s->zero_last_bad=0;
  uint16_t mean[4];unsigned variance_q7=0,bad_paths=0;
  for(unsigned i=0;i<4;++i) {
    mean[i]=(uint16_t)((s->sum[i]+CM_ZERO_N/2)/CM_ZERO_N);
    s->offset[i]=mean[i];s->zero_low[i]=s->low[i];s->zero_high[i]=s->high[i];
    if(mean[i]<1600 || mean[i]>2500){s->zero_last_bad|=2;bad_paths|=1U<<i;}
    /* Raw extrema remain diagnostics. Validate the estimated uncertainty
     * of the256-sample mean:3*sigma_mean<=2counts, plus3-block drift<=2.
     * Use the larger of raw-sample and four64-sample-group mean variance.
     * This is an estimate; three consecutive block means must also agree.
     * Never apply this averaging or rejection to running current samples. */
    int32_t residual_sum=(int32_t)s->sum[i]-(int32_t)(2048U*CM_ZERO_N);
    uint64_t energy=(uint64_t)(s->zero_energy[i]&0x7fffffffUL)*CM_ZERO_N-
                    (uint64_t)((int64_t)residual_sum*residual_sum);
    const uint32_t denominator=CM_ZERO_N*CM_ZERO_N*(CM_ZERO_N-1U);
    uint64_t group_energy=4U*s->zero_group_energy[i]-
                    (uint64_t)((int64_t)residual_sum*residual_sum);
    const uint32_t group_denominator=64U*64U*4U*4U*3U;
    if(energy*9U>(uint64_t)denominator*4U ||
       group_energy*9U>(uint64_t)group_denominator*4U){s->zero_last_bad|=1;bad_paths|=1U<<i;}
    if(s->zero_energy[i]&0x80000000UL){s->zero_last_bad|=8;bad_paths|=1U<<i;}
    unsigned q=(unsigned)((energy+denominator/256U)/(denominator/128U));
    unsigned group_q=(unsigned)((group_energy+group_denominator/256U)/(group_denominator/128U));
    if(group_q>q)q=group_q;
    if(q>255U)q=255U;
    if(q>variance_q7)variance_q7=q;
  }
  if(s->zero_last_bad) {
    s->zero_stable=0;memset(s->zero_total,0,sizeof(s->zero_total));
  } else {
    if(s->zero_stable)for(unsigned i=0;i<4;++i) {
      uint16_t lo=mean[i]<s->zero_mean_min[i]?mean[i]:s->zero_mean_min[i];
      uint16_t hi=mean[i]>s->zero_mean_max[i]?mean[i]:s->zero_mean_max[i];
      if(hi-lo>CM_ZERO_DRIFT){s->zero_last_bad|=4;bad_paths|=1U<<i;}
    }
    if(s->zero_last_bad&4) {
      s->zero_stable=0;memset(s->zero_total,0,sizeof(s->zero_total));
    }
    for(unsigned i=0;i<4;++i) {
      if(!s->zero_stable)s->zero_mean_min[i]=s->zero_mean_max[i]=mean[i];
      if(mean[i]<s->zero_mean_min[i])s->zero_mean_min[i]=mean[i];
      if(mean[i]>s->zero_mean_max[i])s->zero_mean_max[i]=mean[i];
      s->zero_total[i]+=s->sum[i];
    }
    ++s->zero_stable;
  }
  CM_ZERO_REPORT(s,mean,variance_q7,bad_paths);
  if(s->zero_stable>=CM_ZERO_BLOCKS) {
    for(unsigned i=0;i<4;++i)s->offset[i]=(uint16_t)((s->zero_total[i]+CM_ZERO_N*CM_ZERO_BLOCKS/2)/(CM_ZERO_N*CM_ZERO_BLOCKS));
    s->zero_ready=1;
  } else if(s->zero_attempts>=CM_ZERO_MAX_BLOCKS)s->zero_bad=1;
  else cm_zero_block_reset(s);
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
      if(complete==4)cm_zero_finish_block(s);
    }
    if(!zero_bus_ok) {
      s->off_since_ms=now;
      if(!s->zero_ready && !s->zero_bad) {
        cm_zero_block_reset(s);s->zero_stable=0;memset(s->zero_total,0,sizeof(s->zero_total));
      }
    }
    return;
  }
  s->off_seen=0;
  if(!s->zero_ready && !s->zero_bad) {
    cm_zero_block_reset(s);s->zero_stable=0;memset(s->zero_total,0,sizeof(s->zero_total));
  }
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
