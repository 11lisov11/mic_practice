
#include <cassert>
#include <cstddef>
#include "foc_experiment.h"
#include "multi_native.h"
#include "observer_current_window.h"
extern "C" __declspec(dllexport) int noise(unsigned n,float*r){ma_noise v;if(!ma_pair_noise(n,&v))return 0;memcpy(r,&v,sizeof(v));return 1;}
extern "C" __declspec(dllexport) int step(ma_observer*o,const ma_motor*m,const float*v,unsigned n){ma_noise r;if(!ma_pair_noise(n,&r))return MA_INVALID;return ma_observe_noise(o,m,v[0],v[1],v[2],v[3],v[4],&r);}
extern "C" __declspec(dllexport) unsigned guards(){
 unsigned count=0;ma_noise n;for(unsigned bad:{0U,15U,17U,0xffffU,0x10000U}){assert(!ma_pair_noise(bad,&n));++count;}
 ma_motor m=FE_ESTIMATED_MOTOR;ma_observer o={};ma_controller c={};ma_reset(&o,&c);
 assert(ma_observe(&o,&m,.1f,.1f,1,2,.0021f)==MA_INVALID);++count;
 ma_noise bad={.0004f,.001f,.0004f};assert(ma_observe_noise(&o,&m,.1f,.1f,1,2,.001f,&bad)==MA_INVALID);++count;
 ma_geometry g={5312,5184,771,112,240,229};ma_output output;float x[6]={.3f,0,.2f,0,20,0};
 assert(ma_control(&c,&m,x,&g,MA_FOC,1.351f,0,5,321,1.f/16000,1,&output)==MA_CURRENT);++count;
 assert(ma_control(&c,&m,x,&g,MA_FOC,.3f,0,5,321,1.f/16000,0,&output)==MA_STALE);++count;
 assert(FE_FAST_BUDGET==4000&&FE_OBSERVER_BUDGET==85000);++count;
 assert(sizeof(ma_current_sample)==32&&offsetof(ma_current_sample,ccr)==20&&offsetof(ma_current_sample,pair)==30);++count;
 ow_state window;ow_reset(&window,1000);ow_bin bin;unsigned expected=0;
 assert(ow_push_pair(&window,11624,31875,.1f,.2f,1,2,&bin,3)==-1&&window.n==0);++count;
 for(unsigned i=0;i<16;++i){unsigned pair=i%3;expected+=1U<<(pair*5);int rc=ow_push_pair(&window,1000+(i+1)*10624,31875,.1f,.2f,1,2,&bin,pair);assert(rc==(i==15));++count;}
 assert(bin.pair_counts==expected&&window.pair_counts==0&&ma_pair_noise(bin.pair_counts,&n));++count;
 assert(ow_push_pair(&window,window.last,31875,.1f,.2f,1,2,&bin,0)==-1);++count;
 // Correlated-R correction must NOT weaken the old fixed-R shutdown metric.
 // Here the corrected diagnostic NIS is below50, but the preserved legacy
 // metric exceeds50 for the20th consecutive step and MUST stop.
 ma_observer guarded={};for(unsigned i=0;i<6;++i)guarded.p[i][i]=1e-7f;
 guarded.steps=500;guarded.rejected=19;assert(ma_pair_noise(16U<<5,&n));
 int rc=ma_observe_noise(&guarded,&m,0,.15f,0,0,.001f,&n);
 assert(guarded.nis<50&&guarded.rejected==20&&rc==MA_OBSERVER);++count;
 // Also retain the corrected metric: a low legacy statistic must not hide
 // a20-step event which is larger in the correctly transformed coordinates.
 guarded={};for(unsigned i=0;i<6;++i)guarded.p[i][i]=1e-7f;
 guarded.steps=500;guarded.rejected=19;assert(ma_pair_noise(16U<<10,&n));
 rc=ma_observe_noise(&guarded,&m,0,.13f,0,0,.001f,&n);
 assert(guarded.nis>50&&guarded.rejected==20&&rc==MA_OBSERVER);++count;
 return count;
}
