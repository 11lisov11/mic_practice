
#include <cassert>
#include <cstdio>
#include <math.h>
#include "current_core.h"
#include "uart_v3_transport.h"
static cm_core state;static volatile uint32_t state_sequence;
static unsigned packets,copies;static int split_at=-1,interrupts_left;
static void interrupted_copy(cm_core*dst,const cm_core*src){
 ++copies;
 if(interrupts_left&&split_at>=0){
  unsigned char*d=(unsigned char*)dst;const unsigned char*s=(const unsigned char*)src;
  memcpy(d,s,split_at);
  ++state_sequence;memset(&state,0x5a,sizeof(state));++state_sequence;
  memcpy(d+split_at,s+split_at,sizeof(state)-split_at);--interrupts_left;
 }else *dst=*src;
}
#define CM_SNAPSHOT_COPY(d,s) interrupted_copy(d,s)
#define CM_SNAPSHOT_BARRIER() __asm__ volatile("":::"memory")
#include "current_snapshot.h"
#include "current_adc_deadline.h"
static unsigned HAL_GetTick(){return 1000;}
#define ADC_REFERENCE_VOLTAGE 3.3f
#define RSHUNT .04f
#define AMPLIFICATION_GAIN 2.1f

static uint16_t ma_u(float x,uint8_t *flags) {
  if(!isfinite(x)||x<0.0f||x>65534.0f){*flags|=CM_CLIP;return 65535;}
  return (uint16_t)(x+0.5f);
}
static void put16(uint8_t *p,uint16_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void put32(uint8_t *p,uint32_t x){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(x>>(8*i));}
uint8_t mic_current_packet(uint8_t *packet,uint8_t detail,uint32_t build) {
  cm_core copy;
  if(!cm_snapshot_read(&copy,&state,&state_sequence))return 0;
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
    packet[32]=CM_ZERO_BLOCKS;packet[33]=CM_ZERO_MAX_BLOCKS;packet[34]=0;packet[35]=CM_ZERO_DRIFT;packet[36]=3;packet[37]=2;
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
  packet[3]=flags;packet[38]=1;uv3_seal(packet);return 1;
}
void reference_packet(uint8_t *packet,uint8_t detail,uint32_t build) {
  cm_core copy;
  copy=state;
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
    packet[32]=CM_ZERO_BLOCKS;packet[33]=CM_ZERO_MAX_BLOCKS;packet[34]=0;packet[35]=CM_ZERO_DRIFT;packet[36]=3;packet[37]=2;
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
int main(){
 assert(sizeof(state)==296);cm_core copy;
 for(unsigned pos=0;pos<=sizeof(state);++pos){
  memset(&state,0xa5,sizeof(state));state_sequence=0;copies=0;
  split_at=(int)pos;interrupts_left=1;
  assert(cm_snapshot_read(&copy,&state,&state_sequence));
  assert(copies==2&&memcmp(&copy,&state,sizeof(state))==0);
 }
 split_at=100;interrupts_left=100;state_sequence=0;copies=0;
 assert(!cm_snapshot_read(&copy,&state,&state_sequence)&&copies==3);
 state_sequence=1;copies=0;assert(!cm_snapshot_read(&copy,&state,&state_sequence)&&copies==0);
 state_sequence=0xfffffffeU;interrupts_left=1;copies=0;
 assert(cm_snapshot_read(&copy,&state,&state_sequence)&&state_sequence==0&&copies==2);
 uint8_t packet[UV3_FRAME],reference[UV3_FRAME];memset(packet,0xa5,sizeof(packet));
 state_sequence=1;assert(!mic_current_packet(packet,0,1));
 for(auto b:packet)assert(b==0xa5);
 state_sequence=0;split_at=-1;interrupts_left=0;
 cm_init(&state);state.zero_ready=1;state.published.n=32;
 state.published.square[0]=33;state.published.square[1]=67;state.published.square[2]=21;
 for(unsigned i=0;i<4;++i){state.raw[i]=2048+i;state.offset[i]=2060+i;}
 for(unsigned detail=0;detail<3;++detail){
  packets=0;reference_packet(reference,detail,2026103004);
  packets=0;assert(mic_current_packet(packet,detail,2026103004));
  assert(memcmp(packet,reference,sizeof(packet))==0);
 }
 assert(!mic_adc_bottom_update(5312,2226,0));
 assert(mic_adc_bottom_update(5312,137,0));
 puts("snapshot interleavings297, bounded retries, odd writer, wrap, packet equivalence OK");
}
