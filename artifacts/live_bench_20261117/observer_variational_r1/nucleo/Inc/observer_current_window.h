#ifndef MIC_OBSERVER_CURRENT_WINDOW_H
#define MIC_OBSERVER_CURRENT_WINDOW_H
#include <stdint.h>
#include <string.h>
#include <math.h>
/* Observer ONLY. Raw current control/trip must run before this accumulator.
 * Sixteen consecutive real ADC samples. No clipped/reconstructed replacement
 * for an invalid sample is permitted. Averages are referred to the middle
 * between samples8/9, never falsely timestamped as an endpoint measurement.
 * Voltage is a ZOH cycle-average MODEL, not a terminal-voltage measurement.
 */
typedef struct {
 float ia,ib,va,vb,tail_va,tail_vb;
 uint32_t center,end,first,count,previous_center;
} ow_bin;
typedef struct {
 float sum_a,sum_b,head_a,head_b,tail_a,tail_b,previous_tail_a,previous_tail_b;
 uint32_t last,previous_center,first,middle,n;
} ow_state;
static inline void ow_reset(ow_state*s,uint32_t stamp){
 memset(s,0,sizeof(*s));s->last=s->previous_center=stamp;
}
/* Returns1 completed,0 accumulating,-1 invalid/discontinuous input. Modular
 * clock subtraction is intentional. The caller retains the original2ms gate.
 */
static inline int ow_push(ow_state*s,uint32_t stamp,uint32_t max_gap,
 float ia,float ib,float va,float vb,ow_bin*out){
 const uint32_t ticks=stamp-s->last;
 if(!ticks||ticks>=max_gap||!isfinite(ia)||!isfinite(ib)||
    !isfinite(va)||!isfinite(vb))return -1;
 if(!s->n)s->first=stamp;
 s->sum_a+=ia;s->sum_b+=ib;
 const float a=va*(float)ticks,b=vb*(float)ticks;
 if(s->n<8U){s->head_a+=a;s->head_b+=b;}
 else if(s->n==8U){
  /* Split the interval between samples8/9 exactly in the integer clock. */
  const uint32_t half=ticks/2U;s->middle=s->last+half;
  const float fraction=(float)half/(float)ticks;
  s->head_a+=a*fraction;s->head_b+=b*fraction;
  s->tail_a=a*(1.f-fraction);s->tail_b=b*(1.f-fraction);
 }else{s->tail_a+=a;s->tail_b+=b;}
 s->last=stamp;
 if(++s->n<16U)return 0;
 const uint32_t span=s->middle-s->previous_center,tail=stamp-s->middle;
 if(!span||!tail)return -1;
 out->ia=s->sum_a*(1.f/16.f);out->ib=s->sum_b*(1.f/16.f);
 out->va=(s->previous_tail_a+s->head_a)/(float)span;
 out->vb=(s->previous_tail_b+s->head_b)/(float)span;
 out->tail_va=s->tail_a/(float)tail;out->tail_vb=s->tail_b/(float)tail;
 out->center=s->middle;out->end=stamp;out->first=s->first;out->count=16U;
 out->previous_center=s->previous_center;
 s->previous_tail_a=s->tail_a;s->previous_tail_b=s->tail_b;
 s->previous_center=s->middle;s->sum_a=s->sum_b=s->head_a=s->head_b=0;s->n=0;
 return 1;
}
#endif
