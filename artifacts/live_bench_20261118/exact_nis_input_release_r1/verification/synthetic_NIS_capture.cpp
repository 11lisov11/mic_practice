
#include <cassert>
#include "observer_trace_core.h"
#include "observer_trace_wire.h"
#include "foc_experiment.h"
static unsigned capture_pairs;
static od_sample row(const ma_observer*o,const float*v){
 od_sample r={};r.steps=o->steps;r.reasons=OD_NIS;r.nis=o->nis;
 r.ia=v[0];r.ib=v[1];r.va=v[2];r.vb=v[3];r.dt=v[4];
 r.cycles=310000;r.control_adc_cycles=r.observer_adc_cycles=r.bin_cycles=300000;
 r.observation_cycles=220320;r.window_first_cycles=140640;r.window_count=16U|(capture_pairs<<8);r.forecast_dt=79680.f/170000000.f;
 return r;
}
extern "C" __declspec(dllexport) int capture(const ma_observer*prior,const ma_observer*post,
 const ma_motor*m,const float*v,int rc,unsigned pairs,uint32_t fpscr,uint8_t*blob){
 capture_pairs=pairs;od_capture c={};od_begin(&c,2026111802U);
 int staged=od_replay_stage_pairs(&c,prior,m,v[0],v[1],v[2],v[3],v[4],pairs);c.blob.replay.fpscr=fpscr;
 od_replay_commit(&c,post,rc,staged);od_sample r=row(post,v);od_push(&c,&r);od_freeze(&c,rc);
 c.blob.header.crc=odw_crc((const uint8_t*)&c.blob);memcpy(blob,&c.blob,OD_BYTES);
 return c.replay_latched;
}
