#include "fixtures/aux_sd_pulse.h"
#include <cassert>
#include <cstdio>

int main() {
  MicBenchSdPulse p{};
  for (uint32_t t=0; t<10000; ++t) assert(!mic_bench_sd_pull(&p,t,false,true));
  assert(!p.fired);
  assert(!mic_bench_sd_pull(&p,10000,true,true));
  assert(!mic_bench_sd_pull(&p,10799,true,true));
  assert(mic_bench_sd_pull(&p,10800,true,true));
  assert(mic_bench_sd_pull(&p,11049,false,true));
  assert(!mic_bench_sd_pull(&p,11050,false,true));
  for (uint32_t t=11051;t<20000;++t) assert(!mic_bench_sd_pull(&p,t,true,true));
  p={};
  assert(!mic_bench_sd_pull(&p,0,true,true));
  assert(!mic_bench_sd_pull(&p,799,false,true));
  assert(!mic_bench_sd_pull(&p,800,true,true));
  assert(!mic_bench_sd_pull(&p,1599,true,true));
  assert(mic_bench_sd_pull(&p,1600,true,true));
  assert(!mic_bench_sd_pull(&p,1601,true,false));
  assert(!mic_bench_sd_pull(&p,2000,true,true));
  p={};
  assert(!mic_bench_sd_pull(&p,0,true,true));
  assert(!mic_bench_sd_pull(&p,800,true,false));
  assert(!p.fired);
  assert(!mic_bench_sd_pull(&p,900,true,true));
  assert(!mic_bench_sd_pull(&p,1699,true,true));
  assert(mic_bench_sd_pull(&p,1700,true,true));
  p={};
  const uint32_t start=UINT32_MAX-500;
  assert(!mic_bench_sd_pull(&p,start,true,true));
  assert(!mic_bench_sd_pull(&p,start+799U,true,true));
  assert(mic_bench_sd_pull(&p,start+800U,true,true));
  assert(mic_bench_sd_pull(&p,start+1049U,false,true));
  assert(!mic_bench_sd_pull(&p,start+1050U,false,true));
  std::puts("PASS one-shot 800 ms delay, 250 ms hold, no PWM-off trigger, unsafe-bus cancel and rollover");
}
