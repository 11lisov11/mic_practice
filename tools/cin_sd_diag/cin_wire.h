#ifndef MIC_CIN_WIRE_H
#define MIC_CIN_WIRE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "uart_v3_transport.h"
enum {CD_WIRE=0xEB,CD_FORMAT=1,CD_VALID=1,CD_SD_BEFORE=2,CD_SD_AFTER=4,
      CD_OK=0,CD_TIMEOUT=1,CD_OVERRUN=2,CD_UNSAFE=3,CD_CONFIG=4,CD_BUSY=5};
typedef struct {
 uint32_t sequence,start_ms,end_ms,cycles,timeouts,errors;
 uint16_t raw,vref_mv;
 uint8_t flags,reason;
} cd_record;
static inline uint32_t cd_u32(const uint8_t*p){
 return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static inline void cd_put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(v>>(8*i));}
static inline void cd_packet(uint8_t*p,const cd_record*r,uint32_t fw){
 memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=CD_WIRE;p[3]=CD_FORMAT;
 p[4]=r->flags;cd_put(p+6,fw);cd_put(p+10,r->sequence);
 cd_put(p+14,r->start_ms);cd_put(p+18,r->end_ms);
 p[22]=(uint8_t)r->raw;p[23]=(uint8_t)(r->raw>>8);
 p[24]=(uint8_t)r->vref_mv;p[25]=(uint8_t)(r->vref_mv>>8);
 cd_put(p+26,r->cycles);cd_put(p+30,r->timeouts);cd_put(p+34,r->errors);
 p[38]=r->reason;uv3_seal(p);
}
static inline bool cd_decode(const uint8_t*p,uint32_t fw){
 uint16_t raw=(uint16_t)(p[22]|((uint16_t)p[23]<<8));
 uint16_t ref=(uint16_t)(p[24]|((uint16_t)p[25]<<8));
 return p[0]==0x55&&p[1]==0xaa&&p[2]==CD_WIRE&&p[3]==CD_FORMAT&&
  !(p[4]&~7U)&&p[5]==0&&cd_u32(p+6)==fw&&cd_u32(p+10)!=0&&
  raw<=4095&&ref==3290&&p[38]<=CD_BUSY&&
  ((p[4]&CD_VALID)!=0)==(p[38]==CD_OK)&&
  (!(p[4]&CD_VALID)||(uint32_t)(cd_u32(p+18)-cd_u32(p+14))<2U)&&uv3_crc_ok(p);
}
typedef struct {uint8_t packet[UV3_FRAME];uint32_t seen_ms,good,bad;bool received;} cd_receiver;
static inline bool cd_receive(cd_receiver*r,const uint8_t*p,uint32_t fw,bool off,uint32_t now){
 if(!off||!cd_decode(p,fw)){if(r->bad!=UINT32_MAX)++r->bad;return false;}
 if(r->received&&cd_u32(r->packet+6)==fw){
  uint32_t delta=cd_u32(p+10)-cd_u32(r->packet+10);
  if(!delta||delta>=0x80000000U){if(r->bad!=UINT32_MAX)++r->bad;return false;}
 }
 memcpy(r->packet,p,UV3_FRAME);r->received=true;r->seen_ms=now;
 if(r->good!=UINT32_MAX)++r->good;
 return true;
}
static inline bool cd_fresh(const cd_receiver*r,uint32_t fw,bool off,uint32_t now){
 return r->received&&off&&cd_u32(r->packet+6)==fw&&(uint32_t)(now-r->seen_ms)<500U;
}
#endif
