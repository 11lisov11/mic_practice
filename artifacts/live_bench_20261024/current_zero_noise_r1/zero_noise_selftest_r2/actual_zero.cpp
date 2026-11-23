
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cmath>
using std::isfinite;
static uint32_t tick;
static uint32_t HAL_GetTick(){return tick;}
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths);
#define CM_ZERO_REPORT(s,mean,var,paths) mic_zero_record((s)->zero_attempts,(s)->zero_stable,(s)->zero_last_bad,mean,(s)->zero_low,(s)->zero_high,var,paths)
#include "current_core.h"
#include "zero_wire.h"
typedef struct {
 uint16_t mean[4],span[4];
 uint8_t status,variance_q7,paths,tick4;
} zh_block;
typedef char zh_block_must_be_20[(sizeof(zh_block)==20)?1:-1];
static zh_block zero_history[8];
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths) {
 if(attempt<1 || attempt>8)return;
 zh_block *b=&zero_history[attempt-1U];
 for(unsigned i=0;i<4;++i){b->mean[i]=mean[i];b->span[i]=(uint16_t)(high[i]-low[i]);}
 b->status=(uint8_t)((stable&3U)|(rejected<<2));b->variance_q7=(uint8_t)variance_q7;
 b->paths=(uint8_t)paths;b->tick4=(uint8_t)(HAL_GetTick()/4U);
}

static cm_core state;static uint32_t packets;
static uint32_t __get_PRIMASK(){return 0;}static void __disable_irq(){}static void __set_PRIMASK(uint32_t){}
static struct{unsigned BDTR;}timer;
#define TIM1 (&timer)
static unsigned LL_TIM_IsEnabledAllOutputs(decltype(timer)*t){return t->BDTR;}
#define ADC_REFERENCE_VOLTAGE 3.3f
#define RSHUNT .04f
#define AMPLIFICATION_GAIN 2.1f
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


uint8_t mic_zero_packet(uint8_t *packet,uint32_t build) {
 if(LL_TIM_IsEnabledAllOutputs(TIM1) || (!state.zero_ready && !state.zero_bad))return 0;
 unsigned count=state.zero_attempts;
 if(count<3 || count>8)return 0;
 unsigned page=(packets/4U)%count;
 memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=0xd9;
 packet[3]=1;packet[4]=(uint8_t)page;packet[5]=(uint8_t)count;put32(packet+6,build);
 memcpy(packet+10,&zero_history[page],20);
 packet[30]=3;packet[31]=2;packet[32]=3;packet[33]=8;packet[34]=2;
 packet[35]=128;packet[38]=1;uv3_seal(packet);return 1;
}

static unsigned checks;
static const uint16_t bias[4]={2068,2068,2067,2069};
static const uint16_t measured_low[4]={2054,2052,2052,2056};
static const uint16_t measured_high[4]={2103,2085,2082,2102};
static unsigned sample_index;
static void check(bool b){++checks;if(!b){fprintf(stderr,"zero-noise check%u failed\n",checks);exit(1);}}
static uint16_t value(unsigned path,unsigned ordinal,int mode,int delta) {
 int raw=bias[path]+delta;
 if(mode==1) {
  if(ordinal==10)raw=measured_low[path];
  if(ordinal==100)raw=measured_high[path];
 } else if(mode==2)raw=ordinal%7<2?measured_high[path]:measured_low[path];
 else if(mode==3)raw+=(ordinal&1)?12:-12;
 else if(mode==4)raw=3000;
 else if(mode==5 && ordinal==100)raw=4095;
 else if(mode==6 && ordinal==100)raw+=1162;
 else if(mode==7)raw+=(ordinal&1)?10:-10;
 else if(mode==8)raw+=(ordinal&1)?11:-11;
 return (uint16_t)raw;
}
static void prime(){
 cm_init(&state);memset(zero_history,0,sizeof(zero_history));sample_index=0;
 for(;sample_index<8000;++sample_index){tick=sample_index/16;uint8_t pair=(sample_index&1)?2:0;
  cm_sample(&state,tick,0,pair,bias[cm_path1(pair)],bias[cm_path2(pair)],0,1);}
 check(!state.zero_ready && !state.zero_attempts);
}
static void block(int mode=0,int delta=0){
 for(unsigned j=0;j<512;++j,++sample_index){
  uint8_t pair=(j&1)?2:0;unsigned a=cm_path1(pair),b=cm_path2(pair);
  uint16_t x=value(a,state.count[a],mode,delta),y=value(b,state.count[b],mode,delta);
  tick=sample_index/16;cm_sample(&state,tick,0,pair,x,y,0,1);
 }
}
int main(){
 prime();block(1);block(1);check(!state.zero_ready && state.zero_stable==2);
 block(1);check(state.zero_ready && state.zero_stable==3 && state.zero_attempts==3);
 for(unsigned i=0;i<4;++i){check(abs((int)state.offset[i]-(int)bias[i])<=1);check(state.count[i]==256);}
 check(zero_history[0].span[0]==49 && zero_history[0].span[3]==46);
 check((zero_history[0].status>>2)==0 && (zero_history[2].status&3)==3);
 prime();for(unsigned i=0;i<8;++i)block(2);
 check(state.zero_bad && !state.zero_ready && state.zero_attempts==8 && (state.zero_last_bad&1));
 check(zero_history[7].paths!=0);
 // A sustained24-count range passed the old span40 rule; noisy means must fail.
 prime();for(unsigned i=0;i<8;++i)block(3);
 check(state.zero_bad && state.zero_last_bad==1 && state.zero_high[0]-state.zero_low[0]==24);
 prime();block(7);block(7);block(7);check(state.zero_ready); //3sigma~1.879counts
 prime();for(unsigned i=0;i<8;++i)block(8);check(state.zero_bad && state.zero_last_bad==1); //3sigma~2.067
 prime();for(unsigned i=0;i<8;++i)block(4);check(state.zero_bad && (state.zero_last_bad&2));
 prime();for(unsigned i=0;i<8;++i)block(5);check(state.zero_bad && (state.zero_last_bad&8));
 prime();for(unsigned i=0;i<8;++i)block(6);check(state.zero_bad && (state.zero_last_bad&1));
 prime();for(unsigned i=0;i<8;++i)block(0,4*i);check(state.zero_bad && state.zero_stable==1 && state.zero_last_bad==4);
 prime();block();cm_sample(&state,700,0,0,2068,2067,0,0);
 check(state.zero_stable==0 && state.count[0]==0 && !state.zero_ready);
 prime();block();cm_sample(&state,700,1,0,2068,2067,1,0);
 check(!state.zero_stable && !state.zero_ready);
 // Active current samples remain unaveraged and retain their raw1162-count peak.
 prime();block();block();block();
 for(unsigned i=0;i<3201;++i)cm_sample(&state,1000+i/16,1,0,bias[0]-(i==100?1162:100),bias[2]+40,1,0);
 check(state.published.peak[0]==1162 && state.published.last[0]==100);
 // Export both failed and successful actual history packets for Python/HMI tests.
 prime();for(unsigned i=0;i<8;++i)block(3);
 uint8_t packet[UV3_FRAME];FILE *file=fopen("failed_history.bin","wb");check(file!=nullptr);
 for(unsigned i=0;i<8;++i){packets=4*i;check(mic_zero_packet(packet,CT_PEER_BUILD));fwrite(packet,1,UV3_FRAME,file);}fclose(file);
 prime();block(1);block(1);block(1);
 zh_receiver receiver{};file=fopen("history.bin","wb");check(file!=nullptr);
 for(unsigned i=0;i<3;++i){packets=4*i;check(mic_zero_packet(packet,CT_PEER_BUILD));
  check(!zh_receive(&receiver,packet,2026102502,true));check(!zh_receive(&receiver,packet,CT_PEER_BUILD,false));
  check(zh_receive(&receiver,packet,CT_PEER_BUILD,true));fwrite(packet,1,UV3_FRAME,file);}
 fclose(file);check(receiver.complete);
 packet[10]^=1;check(!zh_receive(&receiver,packet,CT_PEER_BUILD,true));uv3_seal(packet);
 check(!zh_receive(&receiver,packet,CT_PEER_BUILD,true));
 timer.BDTR=32768;check(!mic_zero_packet(packet,CT_PEER_BUILD));timer.BDTR=0;
 uint8_t summary[43],detail[43],quality[43];
 mic_current_packet(summary,0,CT_PEER_BUILD);mic_current_packet(detail,1,CT_PEER_BUILD);mic_current_packet(quality,2,CT_PEER_BUILD);
 check(quality[34]==0 && quality[36]==3 && quality[37]==2);
 printf("{\"passed\":true,\"checks\":%u,\"summary\":\"",checks);
 for(unsigned i=0;i<43;++i){printf("%02x",summary[i]);}printf("\",\"detail\":\"");
 for(unsigned i=0;i<43;++i){printf("%02x",detail[i]);}printf("\",\"quality\":\"");
 for(unsigned i=0;i<43;++i){printf("%02x",quality[i]);}printf("\"}");
}
