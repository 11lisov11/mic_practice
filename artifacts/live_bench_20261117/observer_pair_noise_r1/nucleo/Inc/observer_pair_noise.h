#ifndef MIC_OBSERVER_PAIR_NOISE_H
#define MIC_OBSERVER_PAIR_NOISE_H
#include <stdint.h>
#include <math.h>
typedef struct {float aa,ab,bb;} ma_noise;
/* Existing .02A RMS observation-noise scale, expressed on the TWO measured
 * shunt channels. It is a model floor, not physical amp/noise calibration.
 * Transform through reconstruction and Clarke, never tune it to fit NIS.
 * Counts describe all16 real sample pairs, not the final CCR ordering. */
static inline int ma_pair_noise(uint32_t counts,ma_noise*r){
 unsigned n0=counts&31U,n1=(counts>>5)&31U,n2=(counts>>10)&31U;
 if((counts>>15)||n0>16U||n1>16U||n2>16U||n0+n1+n2!=16U)return 0;
 const float phase=.0004f;
 r->aa=phase*(float)(16U+n2)*(1.f/16.f);
 r->ab=phase*((float)n0-(float)n1)*(0.5773502692f/16.f);
 r->bb=phase*(float)(5U*(n0+n1)+2U*n2)*(1.f/48.f);
 return 1;
}
#endif
