#ifndef MIC_OBSERVER_NIS_REPLAY_CORE_H
#define MIC_OBSERVER_NIS_REPLAY_CORE_H
#include "motor_control.h"
/* Raw binary32, before/after ONE call of the unchanged ma_observe. No floats
 * are rounded for transmission. Only foreground writes these fields.
 * 456 bytes replace three decimated152-byte history rows; total wire RAM and
 * packet count do not grow. FPSCR includes rounding/FTZ/default-NaN control. */
typedef struct {
 float prior_x[6],prior_p[6][6];uint32_t prior_steps,prior_rejected;
 ma_motor motor;
 float input[5]; /* ia,ib,va,vb,dt */
 float post_x[6],post_p[6][6],nis,predicted[2],innovation[2],variance[2];
 uint32_t fpscr,post_rejected,result;
} od_replay;
typedef char od_replay_is_456[(sizeof(od_replay)==456)?1:-1];
static inline uint32_t od_fpscr(void){
#if defined(__arm__) || defined(__thumb__)
 uint32_t value;__asm volatile("vmrs %0, fpscr":"=r"(value));return value;
#else
 return 0; /* Host fixtures, never claimed to be a physical ARM capture. */
#endif
}
#endif
