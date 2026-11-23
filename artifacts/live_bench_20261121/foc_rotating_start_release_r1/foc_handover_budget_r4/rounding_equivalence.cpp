#include <initializer_list>
#include "C:/mic_practice/artifacts/live_bench_20261121/foc_rotating_start_release_r1/foc_handover_budget_r4/candidate/nucleo/Inc/motor_control.h"

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
 unsigned scale_cases=0;
 for(float lim:{15.588f,129.904f,181.865f})for(int i=-320;i<=320;++i){
  const float d=lim*(float)i/256.f;
  for(int j=-320;j<=320;++j){
   const float q=lim*(float)j/256.f;
   const float expected=ma_min2(1.f,lim/ma_max2(ma_control_norm(d,q),1.e-9f));
   assert(ma_voltage_scale(d,q,lim)==expected);++scale_cases;
  }
 }
 printf("%u %u\n",tested,scale_cases);
}
