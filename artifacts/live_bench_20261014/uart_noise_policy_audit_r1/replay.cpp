
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include "uart_v3_transport.h"
static void frame(uint8_t *f,unsigned seq,bool run,unsigned hz=5000){
 memset(f,0,UV3_FRAME);f[0]=0xaa;f[1]=0x55;f[2]=UV3_VERSION;f[3]=run?1:0;f[4]=run?3:0;f[5]=(uint8_t)seq;
 if(run){f[6]=hz;f[7]=hz>>8;f[8]=hz>>16;f[9]=hz>>24;}uv3_seal(f);
}
static uv3_result feed(uv3_rx &r,unsigned seq,bool run,unsigned now,int ne=-1,unsigned hz=5000,bool corrupt=false){
 uint8_t f[UV3_FRAME];frame(f,seq,run,hz);if(corrupt)f[8]^=1;
 uv3_result result=UV3_WAIT;
 for(unsigned i=0;i<UV3_FRAME;++i){result=uv3_byte(&r,f[i],(int)i==ne?UV3_NE:0,now+i/12);if(result!=UV3_WAIT&&result!=UV3_READY)return result;}
 return result;
}
int main(){
 unsigned startup_rejections=0;
 for(int ne:{0,6,20,38,42}){
  uv3_rx r;uv3_init(&r,true);
  for(unsigned n=1;n<=3;++n){assert(feed(r,n,false,n*50)==UV3_READY);uv3_commit(&r,n*50,false,false,false);}
  assert(feed(r,4,true,200)==UV3_READY);uv3_commit(&r,200,false,false,false);
  assert(feed(r,5,true,250,ne)==UV3_NOISE_REJECTED);assert(r.fault_latched);assert(r.accepted_noise_frames==0);++startup_rejections;
 }
 uv3_rx steady;uv3_init(&steady,true);
 for(unsigned n=1;n<=4;++n){assert(feed(steady,n,true,n*50)==UV3_READY);uv3_commit(&steady,n*50,true,false,false);}
 assert(feed(steady,5,true,250,6)==UV3_READY);assert(steady.accepted_noise_frames==1);
 uv3_rx changed;uv3_init(&changed,true);
 for(unsigned n=1;n<=4;++n){assert(feed(changed,n,true,n*50)==UV3_READY);uv3_commit(&changed,n*50,true,false,false);}
 assert(feed(changed,5,true,250,6,6000)==UV3_NOISE_REJECTED);
 uv3_rx gap;uv3_init(&gap,true);assert(uv3_byte(&gap,0x42,UV3_NE,1)==UV3_NOISE_REJECTED);
 uv3_rx crc;uv3_init(&crc,true);assert(feed(crc,1,true,50,6,5000,true)==UV3_BAD_CRC);
 std::printf("{\"pass\":true,\"valid_crc_startup_noise_rejections\":%u,\"steady_same_command_noise_accepted\":true,\"valid_crc_changed_command_noise_rejected\":true,\"gap_noise_rejected_without_crc_check\":true,\"crc_corruption_rejected\":true}\n",startup_rejections);
}
