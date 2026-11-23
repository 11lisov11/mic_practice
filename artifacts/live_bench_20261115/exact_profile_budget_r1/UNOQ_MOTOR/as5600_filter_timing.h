#pragma once
#include <stdint.h>
namespace encfix {
struct Timing {bool valid=false;uint32_t word=0,dnf=0,kernel_hz=0;};
inline uint32_t ceildiv(uint64_t a,uint64_t b){return uint32_t((a+b-1)/b);}
// Conservative standard-mode timing, including an added digital filter.
// Assumptions: rise<=1000ns, fall<=300ns, analog50..260ns, no clock stretch
// by AS5600. Actual rise/fall times require electrical qualification.
inline Timing standard_filtered(uint32_t hz) {
  Timing t;t.kernel_hz=hz;
  if(hz<20000000U||hz>160000000U)return t;
  const uint32_t div=ceildiv(hz,10000000U);
  const uint32_t low=ceildiv(uint64_t(5000)*hz,uint64_t(div)*1000000000U);
  const uint32_t high=low,setup=ceildiv(uint64_t(1500)*hz,uint64_t(div)*1000000000U);
  const uint32_t hold=ceildiv(uint64_t(200)*hz,uint64_t(div)*1000000000U);
  if(!div||div>16||!low||low>256||!setup||setup>16||hold>15)return t;
  t.dnf=ceildiv(hz,10000000U);if(t.dnf>15)t.dnf=15;
  t.word=((div-1)<<28)|((setup-1)<<20)|(hold<<16)|((high-1)<<8)|(low-1);
  t.valid=true;return t;
}
}
