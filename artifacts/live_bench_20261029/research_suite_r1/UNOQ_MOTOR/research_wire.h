#ifndef MIC_RESEARCH_WIRE_H
#define MIC_RESEARCH_WIRE_H
/* Read-only capability proof. Never a command, current or protection packet. */
#include "uart_v3_transport.h"
enum { XP_WIRE=0xE4, XP_FORMAT=1, XP_VF=1, XP_FOC=2, XP_ADAPTIVE_PWM=4 };
typedef struct {uint32_t seen_ms,good,bad;uint8_t caps;bool seen;} xp_receiver;
static inline uint32_t xp_u32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline void xp_put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static inline void xp_packet(uint8_t*p,uint32_t peer){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=XP_WIRE;p[3]=XP_FORMAT;
  p[4]=XP_VF;p[5]=1;xp_put(p+6,peer);xp_put(p+10,16000U);
  /* Model identified=0, physical amp scale qualified=0, sensor=0, AI actuator=0. */
  p[18]=1; /* ADC-window contract revision, unchanged from2509/2510. */
  uv3_seal(p);
}
static inline bool xp_receive(xp_receiver*r,const uint8_t*p,uint32_t peer,bool fresh,uint32_t now){
  bool ok=fresh&&p[0]==0x55&&p[1]==0xaa&&p[2]==XP_WIRE&&p[3]==XP_FORMAT&&
    uv3_crc_ok(p)&&xp_u32(p+6)==peer&&p[4]==XP_VF&&p[5]==1&&xp_u32(p+10)==16000U&&p[18]==1;
  for(unsigned i=14;i<39;i++)if(i!=18&&p[i])ok=false;
  if(!ok){if(r->bad!=UINT32_MAX)++r->bad;return false;}
  r->seen=true;r->seen_ms=now;r->caps=p[4];if(r->good!=UINT32_MAX)++r->good;return true;
}
static inline bool xp_fresh(const xp_receiver*r,bool peer_fresh,uint32_t now){return r->seen&&peer_fresh&&(uint32_t)(now-r->seen_ms)<2500U;}
#endif
