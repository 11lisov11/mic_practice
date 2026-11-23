
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#include "current_core.h"
#include "current_wire.h"
static unsigned checks;
static void check(bool value){++checks;if(!value){fprintf(stderr,"check %u failed\n",checks);exit(1);}}
static const uint16_t offsets[4]={2048,2051,2043,2045};
static void calibrate(cm_core *s) {
 cm_init(s);
 for(unsigned i=0;i<10000;++i) {
  uint8_t pair=(i&1)?2:0;
  cm_sample(s,i/16,0,pair,offsets[cm_path1(pair)],offsets[cm_path2(pair)],0,1);
 }
 check(s->zero_ready && !s->zero_bad);
 for(unsigned j=0;j<4;++j)check(s->offset[j]==offsets[j] && s->count[j]==256);
}
int main() {
 cm_core s;calibrate(&s);
 for(int hz : {5,10,15,20,25,50}) {
  calibrate(&s);
  for(unsigned sample=0;sample<32000;++sample) {
   double t=sample/16000.0,angle=2*3.141592653589793*hz*t;
   int32_t currents[3]={(int)lround(100*sin(angle)),(int)lround(100*sin(angle-2*3.141592653589793/3)),0};
   currents[2]=-currents[0]-currents[1];
   uint32_t ccr[3];
   for(unsigned j=0;j<3;++j)ccr[j]=(uint32_t)((.5+.499*sin(angle+0.4-j*2*3.141592653589793/3))*5311);
   uint8_t pair=cm_choose_pair(ccr[0],ccr[1],ccr[2]);
   bool okay=cm_pair_window(pair,ccr[0],ccr[1],ccr[2],5312-384,772);
   check(okay);
   unsigned p=cm_path1(pair),q=cm_path2(pair),phase1=pair==2?1:0,phase2=pair==0?1:2;
   cm_sample(&s,1000+sample/16,1,pair,offsets[p]-currents[phase1],offsets[q]-currents[phase2],okay,0);
   check(s.window.last[0]+s.window.last[1]+s.window.last[2]==0);
  }
  check(cm_window_valid(&s.published));
  for(unsigned j=0;j<3;++j) {
   double rms=sqrt((double)s.published.square[j]/s.published.n);
   check(fabs(rms-100/sqrt(2.0))<1.0);check(s.published.peak[j]>=99 && s.published.peak[j]<=101);
  }
  cm_sample(&s,3000,0,0,2048,2043,0,1);
  check(s.published.flags&CM_FROZEN);
  auto frozen=s.published;
  for(unsigned i=0;i<1000;++i)cm_sample(&s,3001+i/16,0,0,2048,2043,0,1);
  check(memcmp(&frozen,&s.published,sizeof(frozen))==0);
 }
 cm_init(&s);
 for(unsigned i=0;i<20000;++i)cm_sample(&s,i/16,0,(i&1)?2:0,2048,2048,0,0);
 check(!s.zero_ready); // no automatic zero at a charged bus
 cm_init(&s);
 for(unsigned i=0;i<20000;++i)cm_sample(&s,i/16,0,(i&1)?2:0,3000,3000,0,1);
 check(s.zero_bad && !s.zero_ready);
 cm_init(&s);
 for(unsigned i=0;i<20000;++i)cm_sample(&s,i/16,0,(i&1)?2:0,2000+(i%80),2048,0,1);
 check(s.zero_bad && !s.zero_ready);
 calibrate(&s);
 for(unsigned i=0;i<4000;++i)cm_sample(&s,1000+i/16,1,0,2000,2100,0,0);
 check(!cm_window_valid(&s.published) && s.published.bad>0);
 calibrate(&s);
 for(unsigned i=0;i<4000;++i)cm_sample(&s,1000+i/16,1,0,4095,0,1,0);
 check(!cm_window_valid(&s.published) && (s.published.flags&CM_CLIP));
 cm_window sparse={};sparse.n=16;sparse.start_ms=1000;sparse.end_ms=1200;
 check(!cm_window_valid(&sparse));
 for(unsigned u=0;u<=5312;u+=83)for(unsigned v=0;v<=5312;v+=79)for(unsigned w=0;w<=5312;w+=89) {
  uint8_t pair=cm_choose_pair(u,v,w);unsigned excluded=pair==0?2:pair==1?1:0;
  uint32_t a[3]={u,v,w};check(a[excluded]>=a[(excluded+1)%3] && a[excluded]>=a[(excluded+2)%3]);
 }
 ct_receiver r;ct_reset(&r);uint8_t packet[UV3_FRAME]={};packet[0]=0x55;packet[1]=0xaa;packet[2]=CT_SUMMARY;packet[38]=1;
 uint32_t fw=CT_PEER_BUILD;for(unsigned i=0;i<4;++i)packet[6+i]=(uint8_t)(fw>>(8*i));
 packet[4]=1;uv3_seal(packet);check(ct_receive(&r,packet,fw,true,1000));
 check(!ct_receive(&r,packet,fw,true,1001));
 packet[4]=2;uv3_seal(packet);check(!ct_receive(&r,packet,fw,false,1002));
 check(!ct_receive(&r,packet,0,true,1002));
 packet[4]=2;uv3_seal(packet);check(ct_receive(&r,packet,fw,true,1003));
 uint8_t saved[UV3_FRAME];memcpy(saved,packet,sizeof(packet));
 for(unsigned bit=0;bit<UV3_FRAME*8;++bit) {
  memcpy(packet,saved,sizeof(packet));packet[bit/8]^=1U<<(bit%8);
  check(!ct_receive(&r,packet,fw,true,1004));
 }
 memcpy(packet,saved,sizeof(packet));packet[4]=0;uv3_seal(packet);check(ct_receive(&r,packet,fw,true,3000));
 printf("{\"passed\":true,\"checks\":%u,\"motor_frequencies_hz\":[5,10,15,20,25,50],\"physical_measurements\":false}",checks);
}
