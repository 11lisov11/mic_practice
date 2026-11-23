
#include <cassert>
#include <cstdio>
#include <cmath>
#include <limits>
#include <initializer_list>
#include "motor_control.h"
int main(){
 unsigned long long checked=0;
 auto check=[&](float v){
  if(!std::isfinite(v)||v<0||v>65535){assert(ma_round_ccr(v)==UINT32_MAX);}
  else assert(ma_round_ccr(v)==(uint32_t)std::lround(v));
  ++checked;
 };
 for(unsigned i=0;i<=131070;++i){float f=i*.5f;
  check(f);check(std::nextafter(f,-INFINITY));check(std::nextafter(f,INFINITY));
 }
 uint32_t state=0x67583421U;
 for(unsigned i=0;i<2000000;++i){state^=state<<13;state^=state>>17;state^=state<<5;
  float f;memcpy(&f,&state,4);check(f);
 }
 for(float f:{-0.f,-1.f,INFINITY,-INFINITY,std::numeric_limits<float>::quiet_NaN()})check(f);
 printf("{\"rounding_cases\":%llu,\"boundary_and_invalid_inputs\":true}\n",checked);
}
