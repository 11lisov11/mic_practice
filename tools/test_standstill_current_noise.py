"""Exercise exact new C core, current publisher and complete noise wire on the PC."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import prepare_standstill_current_noise as p
from audit_production_pwm_filters import function


def main():
 out=p.OUT/'noise_selftest';out.mkdir(exist_ok=True)
 native=p.read(p.OUT/'nucleo/Src/current_shunt.c')
 source=r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <current_core.h>
#include <noise_core.h>
#include <noise_wire.h>
static void check(bool b){if(!b)std::abort();}
static cm_core state;
struct ma_current_sample {uint32_t sequence,cycles,epoch;uint8_t valid,zero;uint16_t arr,bus_v,ccr[3];int16_t counts[3];};
static volatile ma_current_sample ma_fast_sample;
static void __DMB(){}
static struct Timer {uint32_t ARR;} timer{5312};
#define TIM1 (&timer)
'''.replace('#include <noise_core.h>','#include <uart_v3_transport.h>\n#include <noise_core.h>')
 source+=function(native,'ma_publish_current')
 source+=r'''
static void publication(){
 cm_init(&state);state.zero_ready=1;
 for(unsigned i=0;i<4;i++)state.offset[i]=2048;
 uint16_t c[4]={2600,2650,2700,5184};
 for(unsigned pair=0;pair<3;pair++){
  unsigned first=pair==2?1:0,second=pair==0?1:2,third=3-first-second;
  cm_sample(&state,1000,1,pair,2038,2068,1,1);
  cm_sample(&state,1200,1,pair,2038,2068,1,1); // publishes and clears RMS window
  check(state.window.n==0&&state.window.last[0]==0&&state.window.last[1]==0);
  ma_publish_current(5,7,1,pair,2038,2068,c,320);
  check(ma_fast_sample.valid&&ma_fast_sample.counts[first]==10&&
   ma_fast_sample.counts[second]==-20&&ma_fast_sample.counts[third]==10);
  check(state.published.last[first]==10&&state.published.last[second]==-20);
 }
 ma_publish_current(6,8,1,3,2038,2068,c,10);check(!ma_fast_sample.valid);
 ma_publish_current(6,8,1,0,4095,2068,c,10);check(!ma_fast_sample.valid);
}
int main(){
 publication();nd_state s{};
 for(unsigned i=0;i<100;i++)check(nd_step(&s,0,2048,2048,0,1,1,1,i)<0);
 check(!s.started);
 check(nd_step(&s,0,2048,2048,1,0,1,1,100)<0&&!s.started);
 check(nd_step(&s,0,2048,2048,1,1,0,1,101)<0&&!s.started);
 unsigned pair=0,steps=0;
 while(!s.done&&steps<1000){
  int next=nd_step(&s,pair,2040+steps%17,2060+steps%13,1,1,1,1,steps*10624);
  if(next>=0)pair=(unsigned)next;
  ++steps;
 }
 check(s.done&&!s.fault&&s.stage==4&&steps<650);
 uint32_t regs[8]={1,2,3,4,5,6,7,8};check(nd_seal(&s,2026102940,170000000,0x2001468,regs));
 check(!nd_seal(&s,2026102940,170000000,0,regs));
 for(unsigned k=0;k<4;k++)for(unsigned j=0;j<ND_SAMPLES;j++){
  unsigned q=(s.bytes[ND_HEADER+4*(k*ND_SAMPLES+j)+1]>>4)&3;
  check(k==0?(q==0||q==2):q==(k==1?0:k==2?2:3));
 }
 nd_blob blob{};
 for(int page=90;page>=0;page--){
  uint8_t frame[UV3_FRAME]={0x55,0xaa,ND_WIRE,1,(uint8_t)page,91};
  auto put=[](uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));};
  put(frame+6,2026102940);put(frame+10,s.crc);
  unsigned off=page*24,n=ND_BYTES-off;if(n>24)n=24;memcpy(frame+14,s.bytes+off,n);uv3_seal(frame);
  auto bad=blob;check(!nd_receive(&bad,frame,2026102938,1));
  check(!nd_receive(&bad,frame,2026102940,0));
  check(nd_receive(&blob,frame,2026102940,1));
  check(nd_receive(&blob,frame,2026102940,1)); // identical retransmission
  frame[14]^=1;uv3_seal(frame);check(!nd_receive(&blob,frame,2026102940,1));
 }
 check(blob.complete&&blob.crc==s.crc&&!memcmp(blob.bytes,s.bytes,ND_BYTES));
 unsigned saved=s.crc;check(nd_step(&s,0,1,2,1,1,1,1,123)<0&&s.crc==saved);
 for(unsigned why=0;why<3;why++){
  nd_state interrupted{};nd_step(&interrupted,0,2048,2048,1,1,1,1,0);
  nd_step(&interrupted,0,2048,2048,why!=0,why!=1,1,why!=2,1);
  check(interrupted.done&&interrupted.fault&&!interrupted.ready);
 }
 FILE*f=fopen("synthetic_noise.bin","wb");check(f);check(fwrite(s.bytes,1,ND_BYTES,f)==ND_BYTES);fclose(f);
 puts("{\"passed\":true,\"hardware_commands\":0,\"rms_rollover_regression\":true,\"off_low_bus_gate\":true,\"same_input_pair\":true,\"fault_abort\":true,\"raw_wire_crc_roundtrip\":true}");
}
'''
 unit=out/'noise_test.cpp';p.write(unit,source)
 with tempfile.TemporaryDirectory() as temp:
  exe=Path(temp)/'test.exe'
  r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
   '-I',str(p.OUT/'nucleo/Inc'),str(unit),'-o',str(exe)],capture_output=True,text=True,timeout=60)
  p.write(out/'build.log',r.stdout+r.stderr);r.check_returncode()
  r=subprocess.run([str(exe)],cwd=out,capture_output=True,text=True,timeout=20)
  p.write(out/'run.log',r.stdout+r.stderr);r.check_returncode()
 report=json.loads(r.stdout)
 p.write(out/'report.json',json.dumps(report,indent=2))
 print(json.dumps(report))


if __name__=='__main__':main()
