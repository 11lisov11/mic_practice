#ifndef MIC_RESEARCH_WIRE_H
#define MIC_RESEARCH_WIRE_H
#include "uart_v3_transport.h"
#include <math.h>
enum {XP_WIRE=0xE4,XP_FORMAT=4,XP_VF=1,XP_FOC=2,XP_ADAPTIVE_PWM=4};
typedef struct {
 uint32_t seen_ms,good,bad,fast_cycles,observer_cycles,profile_crc;
 uint8_t caps,selected,qualification,profile_ready,fault,running,estimate_valid,experiment_flags,timing_fault,timing_cases;float rpm_est;bool seen;
} xp_receiver;
static inline uint32_t xp_u32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline void xp_put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static inline bool xp_receive(xp_receiver*r,const uint8_t*p,uint32_t peer,bool fresh,uint32_t now){
 bool ok=fresh&&p[0]==0x55&&p[1]==0xaa&&p[2]==XP_WIRE&&p[3]==XP_FORMAT&&uv3_crc_ok(p)&&
  xp_u32(p+6)==peer&&p[4]==15&&p[5]>=1&&p[5]<=4&&xp_u32(p+10)==16000&&p[18]==1&&
  (p[14]<=7||p[14]==128)&&p[15]<=1&&p[17]<=1&&p[31]<=1&&p[36]<=7&&p[37]<=7&&p[38]<=64;
 uint32_t raw=xp_u32(p+27);float rpm;memcpy(&rpm,&raw,4);
 if(!isfinite(rpm))ok=false;
 if(!ok){if(r->bad!=UINT32_MAX)r->bad++;return false;}
 r->seen=true;r->seen_ms=now;r->caps=p[4];r->selected=p[5];r->qualification=p[14];
 r->experiment_flags=p[36];r->timing_fault=p[37];r->timing_cases=p[38];
 r->profile_ready=p[15];r->fault=p[16];r->fast_cycles=xp_u32(p+19);
 r->estimate_valid=p[17];
 r->observer_cycles=xp_u32(p+23);r->rpm_est=rpm;r->running=p[31];r->profile_crc=xp_u32(p+32);
 if(r->good!=UINT32_MAX)r->good++;
 return true;
}
static inline bool xp_fresh(const xp_receiver*r,bool peer_fresh,uint32_t now){return r->seen&&peer_fresh&&(uint32_t)(now-r->seen_ms)<2500U;}
#endif
