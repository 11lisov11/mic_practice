
#include <cstdio>
#include <cstdlib>
#include <math.h>
#include "current_core.h"
#include "current_wire.h"
#define ADC_REFERENCE_VOLTAGE 3.3f
#define RSHUNT 0.04f
#define AMPLIFICATION_GAIN 2.1f
static cm_core state;
static uint32_t packets;
static uint32_t tick;
static uint32_t HAL_GetTick(){return tick;}
static uint32_t __get_PRIMASK(){return 0;}
static void __disable_irq(){}
static void __set_PRIMASK(uint32_t){}
static unsigned checks;
static void check(bool x){++checks;if(!x){fprintf(stderr,"zero check %u failed\n",checks);exit(1);}}
static uint32_t index_;
static const uint16_t bias[4]={2048,2051,2043,2045};
static void prime(cm_core *s) {
 cm_init(s);for(index_=0;index_<8000;++index_) {
  uint8_t pair=(index_&1)?2:0;cm_sample(s,index_/16,0,pair,bias[cm_path1(pair)],bias[cm_path2(pair)],0,1);
 }
 check(!s->zero_ready && !s->zero_attempts);
}
static void block(cm_core *s,int delta=0,bool spike=false,bool invalid_bias=false) {
 for(unsigned j=0;j<512;++j,++index_) {
  uint8_t pair=(j&1)?2:0;unsigned p=cm_path1(pair),q=cm_path2(pair);
  uint16_t a=invalid_bias?3000:bias[p]+delta,b=invalid_bias?3000:bias[q]+delta;
  if(spike && p==1 && s->count[p]==100)a+=49;
  cm_sample(s,index_/16,0,pair,a,b,0,1);
 }
}
static uint16_t ma_u(float x,uint8_t *flags) {
  if(!isfinite(x)||x<0.0f||x>65534.0f){*flags|=CM_CLIP;return 65535;}
  return (uint16_t)(x+0.5f);
}
static void put16(uint8_t *p,uint16_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void put32(uint8_t *p,uint32_t x){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(x>>(8*i));}

void mic_current_packet(uint8_t *packet,uint8_t detail,uint32_t build) {
  cm_core copy;
  uint32_t key=__get_PRIMASK();__disable_irq();copy=state;__set_PRIMASK(key);
  memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=detail==2?0xD7:detail?0xD6:0xD5;
  uint8_t flags=(copy.zero_ready?CM_ZERO:0)|(copy.zero_bad?CM_ZERO_BAD:0);
  if(copy.was_active)flags|=CM_ACTIVE;
  cm_window *w=&copy.published;
  if(w->flags&CM_FROZEN)flags|=CM_FROZEN;
  flags|=w->flags&(CM_CLIP|CM_TIMING);
  if(copy.zero_ready && cm_window_valid(w))flags|=CM_VALID;
  packet[4]=(uint8_t)++packets;
  put32(packet+6,build);
  put32(packet+10,detail?HAL_GetTick():w->end_ms);
  if(detail==2) {
    for(unsigned i=0;i<4;++i){put16(packet+14+2*i,copy.zero_low[i]);put16(packet+22+2*i,copy.zero_high[i]);}
    packet[5]=copy.zero_attempts;packet[30]=copy.zero_stable;packet[31]=copy.zero_last_bad;
    packet[32]=CM_ZERO_BLOCKS;packet[33]=CM_ZERO_MAX_BLOCKS;packet[34]=CM_ZERO_SPAN;packet[35]=CM_ZERO_DRIFT;
  } else if(detail) {
    for(unsigned i=0;i<4;++i){put16(packet+14+2*i,copy.raw[i]);put16(packet+22+2*i,copy.offset[i]);put16(packet+30+2*i,copy.count[i]);}
    packet[5]=4;
  } else {
    const float scale=1000.0f*ADC_REFERENCE_VOLTAGE/(4095.0f*RSHUNT*AMPLIFICATION_GAIN);
    for(unsigned i=0;i<3;++i) {
      put16(packet+14+2*i,ma_u(w->n?sqrtf((float)w->square[i]/w->n)*scale:0,&flags));
      put16(packet+20+2*i,ma_u(w->peak[i]*scale,&flags));
      float instant=w->last[i]*scale;
      if(instant>32767||instant< -32767){flags|=CM_CLIP;instant=0;}
      put16(packet+26+2*i,(uint16_t)(int16_t)instant);
    }
    if(flags&CM_CLIP)flags&=(uint8_t)~CM_VALID;
    packet[5]=(uint8_t)((w->n+w->bad)?100U*w->n/(w->n+w->bad):0);
    packet[32]=w->reconstructed;
    put16(packet+34,(uint16_t)(w->end_ms-w->start_ms));
    put16(packet+36,(uint16_t)(w->bad>65535?65535:w->bad));
  }
  packet[3]=flags;packet[38]=1;uv3_seal(packet);
}


uint8_t mic_current_peak_packet(uint8_t *packet,uint8_t page,uint32_t build) {
  if(!peak.frozen || LL_TIM_IsEnabledAllOutputs(TIM1) || page>=35)return 0;
  if(!peak_sealed) {
    peak.blob.header.firmware=build;
    peak.blob.header.crc=pc_crc((const uint8_t *)&peak.blob);
    peak_sealed=1;
  }
  memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=0xd8;
  packet[3]=1;packet[4]=1;packet[5]=page;packet[6]=35;
  uint8_t size=page==34?4:30;packet[7]=size;
  memcpy(packet+8,((const uint8_t *)&peak.blob)+page*30U,size);
  packet[38]=1;uv3_seal(packet);return 1;
}

int main() {
 cm_core s;prime(&s);block(&s,0,true);
 check(!s.zero_ready && !s.zero_bad && s.zero_attempts==1 && s.zero_last_bad==1);
 check(s.zero_high[1]-s.zero_low[1]==49);
 block(&s);block(&s);check(!s.zero_ready && s.zero_stable==2);
 block(&s);check(s.zero_ready && !s.zero_bad && s.zero_attempts==4 && s.zero_stable==3);
 for(unsigned i=0;i<4;++i)check(s.offset[i]==bias[i] && s.count[i]==256);
 state=s;uint8_t summary[UV3_FRAME],detail[UV3_FRAME],quality[UV3_FRAME];
 mic_current_packet(summary,0,CT_PEER_BUILD);mic_current_packet(detail,1,CT_PEER_BUILD);mic_current_packet(quality,2,CT_PEER_BUILD);
 check(quality[2]==CT_QUALITY && quality[5]==4 && quality[30]==3 && quality[32]==3 && quality[33]==8 && quality[34]==40 && quality[35]==2);
 check(uv3_crc_ok(summary) && uv3_crc_ok(detail) && uv3_crc_ok(quality));
 ct_receiver rx;ct_reset(&rx);check(ct_receive(&rx,quality,CT_PEER_BUILD,true,1010));check(rx.has_quality);
 check(!ct_receive(&rx,quality,CT_PEER_BUILD,true,1011));
 uint8_t damaged[UV3_FRAME];memcpy(damaged,quality,sizeof(damaged));damaged[14]^=1;
 check(!ct_receive(&rx,damaged,CT_PEER_BUILD,true,1012));
 prime(&s);for(unsigned i=0;i<8;++i)block(&s,0,true);
 check(s.zero_bad && !s.zero_ready && s.zero_attempts==8 && s.zero_stable==0 && s.zero_last_bad==1);
 for(unsigned i=0;i<2;++i){block(&s);}
 check(s.zero_attempts==8 && !s.zero_ready);
 prime(&s);for(unsigned i=0;i<8;++i)block(&s,0,false,true);
 check(s.zero_bad && !s.zero_ready && s.zero_last_bad==2);
 prime(&s);for(unsigned i=0;i<8;++i)block(&s,4*i);
 check(s.zero_bad && !s.zero_ready && s.zero_stable==1 && s.zero_last_bad==4);
 prime(&s);block(&s,0);block(&s,1);block(&s,2);
 check(s.zero_ready && s.offset[0]==bias[0]+1);
 prime(&s);block(&s);check(s.zero_stable==1);
 cm_sample(&s,index_/16,0,0,2048,2043,0,0);check(!s.zero_stable && !s.count[0]);
 check(!s.zero_ready && !s.zero_bad);
 prime(&s);block(&s);cm_sample(&s,index_/16,1,0,2048,2043,1,0);
 check(!s.zero_stable && !s.count[0] && !s.zero_ready);
 printf("{\"passed\":true,\"checks\":%u,\"summary\":\"",checks);
 for(unsigned i=0;i<UV3_FRAME;++i){printf("%02x",summary[i]);}
 printf("\",\"detail\":\"");
 for(unsigned i=0;i<UV3_FRAME;++i){printf("%02x",detail[i]);}
 printf("\",\"quality\":\"");
 for(unsigned i=0;i<UV3_FRAME;++i){printf("%02x",quality[i]);}
 printf("\"}");
}
