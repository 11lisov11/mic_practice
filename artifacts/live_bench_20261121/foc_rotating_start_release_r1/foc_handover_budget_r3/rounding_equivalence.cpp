#include "C:/mic_practice/artifacts/live_bench_20261121/foc_rotating_start_release_r1/foc_handover_budget_r3/candidate/nucleo/Inc/motor_control.h"

#include <cassert>
#include <cstdio>
static uint32_t baseline(float value){
 uint32_t bits;memcpy(&bits,&value,4);
 if(bits==0x80000000U)return 0;
 if(bits>0x477fff00U)return UINT32_MAX;
 unsigned exponent=bits>>23;
 if(exponent<126U)return 0;
 unsigned shift=150U-exponent;
 uint32_t mantissa=(bits&0x7fffffU)|0x800000U;
 return (mantissa+(1U<<(shift-1U)))>>shift;
}
int main(){
 unsigned tested=0;
 for(unsigned i=0;i<=65535U;++i){
  float a=(float)i,b=a+.5f;
  float samples[]={a,b,nextafterf(a,-INFINITY),nextafterf(a,INFINITY),
                     nextafterf(b,-INFINITY),nextafterf(b,INFINITY)};
  for(float v:samples){assert(ma_round_ccr(v)==baseline(v));++tested;}
 }
 uint32_t seed=12345;
 for(unsigned n=0;n<1000000U;++n){
  seed=1664525U*seed+1013904223U;float v;memcpy(&v,&seed,4);
  assert(ma_round_ccr(v)==baseline(v));++tested;
 }
 printf("%u\n",tested);
}
