"""Differential numeric/transport tests; no board or motor access."""
import json
import re
import subprocess
import prepare_foc_observer_schedule_fix as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function


def stripped_header(s):
    s = '\n'.join(line for line in s.splitlines() if not line.startswith('#include'))
    s = s.replace('#ifdef __cplusplus\nextern "C" {\n#endif', '')
    s = s.replace('#ifdef __cplusplus\n}\n#endif', '')
    s = re.sub(r'^#ifndef MIC_[A-Z0-9_]+_H\n#define MIC_[A-Z0-9_]+_H\n', '', s)
    assert s.endswith('#endif')
    return s[:-len('#endif')]


def main():
    out = p.OUT / 'verification'
    out.mkdir(exist_ok=True)
    common.p = p
    pre = '''#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <cfloat>
#include <algorithm>
#include "current_adc_window_plan.h"
using std::isfinite;using std::isnan;
static uint32_t rng=0x13a849f1U;
static uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static float uniform(float a,float b){return a+(b-a)*(next()>>8)*(1.f/16777216.f);}
'''
    old = stripped_header(p.read(p.BASE / 'nucleo/Inc/motor_control.h'))
    new = stripped_header(p.read(p.OUT / 'nucleo/Inc/motor_control.h'))
    code = pre + '\nnamespace old {\n' + old + '\n}\nnamespace candidate {\n' + new + '\n}\n'
    code += r'''
static unsigned checked,invalid;
static void compare(old::ma_observer a,old::ma_motor model,float ia,float ib,float va,float vb,float dt){
 candidate::ma_observer b;candidate::ma_motor m;
 memcpy(&b,&a,sizeof(b));memcpy(&m,&model,sizeof(m));
 int x=old::ma_observe(&a,&model,ia,ib,va,vb,dt);
 int y=candidate::ma_observe(&b,&m,ia,ib,va,vb,dt);
 assert(x==y);assert(memcmp(&a,&b,sizeof(a))==0);++checked;if(x)++invalid;
}
int main(){
 old::ma_motor m={12.23f,11.00442222558575f,.528093860573909f,.528093860573909f,
 .4944775988161633f,.0002f,.00014790613961630187f,1,.25f,.8f,1.35f,400.f,12.f};
 for(unsigned n=0;n<100000;++n){
  old::ma_observer a={};old::ma_controller c={};old::ma_reset(&a,&c);
  a.x[0]=uniform(-1.4f,1.4f);a.x[1]=uniform(-1.4f,1.4f);
  a.x[2]=uniform(-.3f,.3f);a.x[3]=uniform(-.3f,.3f);
  a.x[4]=uniform(-350,350);a.x[5]=uniform(-.05f,.05f);
  for(unsigned i=0;i<6;++i)a.p[i][i]*=uniform(.25f,4.f);
  a.steps=next()%1000;a.rejected=next()%21;
  compare(a,m,uniform(-1.35f,1.35f),uniform(-1.35f,1.35f),
          uniform(-180,180),uniform(-180,180),uniform(.0001f,.002f));
 }
 // Consecutive estimates exercise covariance/state drift and rejection counters.
 for(unsigned path=0;path<8;++path){
  old::ma_observer a={};candidate::ma_observer b={};old::ma_controller c={};
  old::ma_reset(&a,&c);memcpy(&b,&a,sizeof(b));candidate::ma_motor nm;memcpy(&nm,&m,sizeof(m));
  for(unsigned step=0;step<5000;++step){
   float t=step*.001f,w=6.2831853072f*(1+path*.5f),ia=.3f*cosf(w*t),ib=.3f*sinf(w*t);
   float va=8.f*cosf(w*t),vb=8.f*sinf(w*t);
   int x=old::ma_observe(&a,&m,ia,ib,va,vb,.001f),y=candidate::ma_observe(&b,&nm,ia,ib,va,vb,.001f);
   assert(x==y&&memcmp(&a,&b,sizeof(a))==0);++checked;
   if(x){old::ma_reset(&a,&c);memcpy(&b,&a,sizeof(b));}
  }
 }
 old::ma_observer a={};old::ma_controller c={};old::ma_reset(&a,&c);
 for(float value:{NAN,INFINITY,-INFINITY,0.f,-1.f,.000099f,.002001f})compare(a,m,0,0,0,0,value);
 for(float value:{NAN,INFINITY,-INFINITY}){
  compare(a,m,value,0,0,0,.001f);compare(a,m,0,value,0,0,.001f);
  compare(a,m,0,0,value,0,.001f);compare(a,m,0,0,0,value,.001f);
 }
 printf("{\"bit_exact_observer_comparisons\":%u,\"invalid_cases\":%u}\n",checked,invalid);
}
'''
    numeric = json.loads(common.compile_run(out, 'observer_bit_exact_r2', code))
    crc_old = stripped_header(p.read(p.BASE / 'nucleo/Inc/uart_v3_transport.h'))
    crc_new = stripped_header(p.read(p.OUT / 'nucleo/Inc/uart_v3_transport.h'))
    code = pre + '\nnamespace old {\n' + crc_old + '\n}\nnamespace candidate {\n' + crc_new + '\n}\n'
    code += r'''
int main(){
 uint8_t data[8192];unsigned checked=0,bytes=0;
 for(unsigned n=0;n<100000;++n){
  unsigned len=n<8193?n:(next()%512);
  for(unsigned i=0;i<len;++i)data[i]=(uint8_t)next();
  assert(old::uv3_crc32c(data,len)==candidate::uv3_crc32c(data,len));++checked;
 }
 const uint8_t known[]="123456789";assert(candidate::uv3_crc32c(known,9)==0xe3069283U);
 for(unsigned scenario=0;scenario<1000;++scenario){
  old::uv3_rx a;candidate::uv3_rx b;old::uv3_init(&a,true);candidate::uv3_init(&b,true);
  uint32_t tick=0;
  for(unsigned frame=0;frame<16;++frame){
   uint8_t packet[old::UV3_FRAME]={0xaa,0x55,old::UV3_VERSION,0,0,0};
   packet[5]=(uint8_t)frame;
   for(unsigned i=6;i<old::UV3_PAYLOAD;++i)packet[i]=(uint8_t)next();
   old::uv3_seal(packet);assert(candidate::uv3_crc_ok(packet));
   if(scenario%4==1&&frame==5)packet[10]^=1;
   for(unsigned i=0;i<old::UV3_FRAME;++i){
    uint8_t flags=scenario%4==2&&frame==7&&i==13?old::UV3_ORE:0;
    auto x=old::uv3_byte(&a,packet[i],flags,tick);auto y=candidate::uv3_byte(&b,packet[i],flags,tick);
    assert((int)x==(int)y&&memcmp(&a,&b,sizeof(a))==0);++bytes;
    if(x==old::UV3_READY){
     old::uv3_commit(&a,tick,frame>2,false,false);candidate::uv3_commit(&b,tick,frame>2,false,false);
     assert(memcmp(&a,&b,sizeof(a))==0);
    }
    if((i%10)==0)++tick;
   }
   if(scenario%4==3&&frame==8)tick+=400;
   auto x=old::uv3_tick(&a,tick);auto y=candidate::uv3_tick(&b,tick);
   assert((int)x==(int)y&&memcmp(&a,&b,sizeof(a))==0);tick+=10;
  }
 }
 printf("{\"CRC_differential_cases\":%u,\"transport_byte_states_compared\":%u}\n",checked,bytes);
}
'''
    transport = json.loads(common.compile_run(out, 'transport_bit_exact_r2', code))
    # Verify only loop-unroll directives changed the numeric kernel.
    strip_pragmas = new.replace('\n#pragma GCC unroll 6\n    ', '')
    assert re.sub(r'\s+', '', old) == re.sub(r'\s+', '', strip_pragmas)
    # Guard implementation, IRQs, ADC windows, model, STOP and CLEAR stay exact.
    old_main = p.read(p.BASE / 'nucleo/Src/main.c').replace('2026103010', '2026103012').replace('2026103009', '2026103011')
    main = p.read(p.OUT / 'nucleo/Src/main.c')
    for name in ('uno_handle_valid_frame', 'uno_rearm_break_irq', 'mic_local_stop_clear', 'mic_local_stop_enable_outputs'):
        assert function(old_main, name) == function(main, name), name
    yield_line = '\n    ma_native_service(); /* bounded foreground yield; never from USART IRQ */'
    assert main.replace(yield_line, '') == old_main
    for rel in ('nucleo/Src/current_shunt.c', 'nucleo/Src/multi_native.c',
                'nucleo/Inc/foc_experiment.h', 'nucleo/Inc/current_adc_window_plan.h',
                'nucleo/Inc/current_adc_deadline.h', 'nucleo/Inc/local_stop.h'):
        expected = p.read(p.BASE / rel).replace('2026103009', '2026103011').replace('2026103010', '2026103012')
        assert p.read(p.OUT / rel) == expected, rel
    report = dict(passed=True, hardware_commands=0, numeric=numeric, transport=transport,
        observer_equations_unchanged=True, guards_and_IRQ_priorities_unchanged=True,
        current_trip_A=1.35, ADC_guard_ticks=2048, estimate_limit_ms=2,
        target_cycle_improvement_not_measured=True, hardware_5s_not_proven=True)
    p.write(out / 'selftest.json', json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
