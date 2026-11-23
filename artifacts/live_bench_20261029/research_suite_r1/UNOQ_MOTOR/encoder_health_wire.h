#ifndef MIC_ENCODER_HEALTH_H
#define MIC_ENCODER_HEALTH_H
#include "uart_v3_transport.h"
enum { EH_WIRE=0xDC,EH_FORMAT=1,EH_PEER=2026102912U,EH_TTL=2000 };
static inline uint32_t eh_u32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline void eh_put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static inline void eh_packet(uint8_t*p,const uint32_t*v,uint8_t page,uint8_t gen){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=EH_WIRE;p[3]=page;p[4]=gen;p[5]=2;
  eh_put(p+6,EH_PEER);for(unsigned i=0;i<7;i++)eh_put(p+10+4*i,v[page*7+i]);p[38]=EH_FORMAT;uv3_seal(p);
}
typedef struct {uint32_t staging[14],values[14],ms,begin_ms;uint8_t gen,mask;bool valid;} eh_receiver;
static inline bool eh_receive(eh_receiver*r,const uint8_t*p,uint32_t peer,bool off,uint32_t now){
  if(!off){r->valid=false;r->mask=0;return false;}
  if(peer!=EH_PEER||p[0]!=0x55||p[1]!=0xaa||p[2]!=EH_WIRE||p[3]>1||p[5]!=2||p[38]!=EH_FORMAT||eh_u32(p+6)!=EH_PEER||!uv3_crc_ok(p))return false;
  if(p[3]==0){r->mask=0;r->gen=p[4];r->begin_ms=now;}
  if(r->gen!=p[4] || (p[3]==1&&r->mask!=1) || (uint32_t)(now-r->begin_ms)>=EH_TTL)return false;
  for(unsigned i=0;i<7;i++)r->staging[p[3]*7+i]=eh_u32(p+10+4*i);
  r->mask|=(uint8_t)(1U<<p[3]);
  if(r->mask==3){memcpy(r->values,r->staging,sizeof(r->values));r->valid=true;r->ms=now;r->mask=0;}
  return true;
}
static inline bool eh_fresh(const eh_receiver*r,bool off,uint32_t now){return off&&r->valid&&(uint32_t)(now-r->ms)<EH_TTL;}
#endif
