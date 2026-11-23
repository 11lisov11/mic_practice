#ifndef MIC_FOC_EXPERIMENT_H
#define MIC_FOC_EXPERIMENT_H
#include <stdint.h>
#include <math.h>
#include <string.h>
#include "motor_control.h"
/* Calculated AIR56B2 candidate, explicitly NOT physical identification. */
#define FE_ESTIMATED_MOTOR {12.23f,11.00442222558575f,0.528093860573909f,0.528093860573909f,0.4944775988161633f,0.0002f,0.00014790613961630187f,1,0.25f,0.8f,1.35f,400.f,12.f}
enum {FE_ESTIMATED=128,FE_READY=1,FE_BUSY=2,FE_DONE=4,
      FE_FAST_BUDGET=4000,FE_OBSERVER_BUDGET=85000,FE_CASES=64};
static inline int fe_model_exact(const ma_motor*m){
 static const ma_motor expected=FE_ESTIMATED_MOTOR;
 /* expected is validated by release tests. Bit identity with that SAME
  * valid52-byte model implies the original ma_motor_valid predicate. Compare
  * every byte via memcpy words: no aliasing cast, rounding, CRC shortcut,
  * or cached result; a changed bit still rejects in the SAME invocation. */
 uint32_t difference=0;
#pragma GCC unroll 13
 for(unsigned i=0;i<13;++i){
  uint32_t a,b;memcpy(&a,(const uint8_t*)m+4*i,4);
  memcpy(&b,(const uint8_t*)&expected+4*i,4);difference|=a^b;
 }
 return difference==0;
}
static inline int fe_start_policy(unsigned kind,unsigned flags,unsigned algorithm,
                                 int manual,uint32_t limit_ms,float frequency){
 if(kind==7)return 1;
 return kind==FE_ESTIMATED&&(flags&FE_READY)&&!(flags&(FE_BUSY|FE_DONE))&&
  algorithm==MA_FOC&&!manual&&limit_ms==5000&&isfinite(frequency)&&frequency>0&&frequency<=5;
}
static inline int fe_time_up(uint32_t now,uint32_t begin,uint32_t clock){
 return (uint32_t)(now-begin)>=5U*clock;
}
#endif
