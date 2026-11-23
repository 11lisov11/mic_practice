#ifndef MIC_ENCODER_WIRE_H
#define MIC_ENCODER_WIRE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "uart_v3_transport.h"
enum { EW_VERSION=0xDA,EW_FORMAT=2,EW_PEER=2026102805U,EW_TTL_MS=100 };
static inline uint16_t ew_u16(const uint8_t*p){return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static inline uint32_t ew_u32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline void ew_p16(uint8_t*p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static inline void ew_p32(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(v>>(8*i));}
typedef struct {uint8_t frame[UV3_FRAME];uint32_t received_ms,good,bad;bool seen;} ew_receiver;
static inline bool ew_receive(ew_receiver*r,const uint8_t*f,uint32_t peer,bool peer_fresh,uint32_t now){
  bool valid=peer_fresh && peer==EW_PEER && f[0]==0x55 && f[1]==0xaa &&
      f[2]==EW_VERSION && f[38]==EW_FORMAT && uv3_crc_ok(f) && ew_u32(f+6)==EW_PEER &&
      !(f[3]&0xf0U) && ew_u16(f+14)<=4095U && f[5]<=12 && f[13]<=11 &&
      f[36]<=3U && f[37]<=1U &&
      (!(f[3]&7U) || ((f[3]&8U) && ew_u16(f+10)<EW_TTL_MS)) &&
      (!(f[3]&1U) || f[5]==0U) &&
      (!(f[3]&2U) || ((f[3]&9U)==9U && (f[12]&0x38U)==0x20U)) &&
      (!(f[3]&4U) || (f[3]&2U));
  if(!valid){if(r->bad!=UINT32_MAX)++r->bad;return false;}
  /* Duplicates cannot refresh a frozen packet. A reset is accepted once its
     fresh control peer and acquisition counters have changed. */
  if(r->seen && f[4]==r->frame[4] && ew_u32(f+18)==ew_u32(r->frame+18) &&
      ew_u32(f+22)==ew_u32(r->frame+22))return false;
  memcpy(r->frame,f,UV3_FRAME);r->received_ms=now;r->seen=true;
  if(r->good!=UINT32_MAX)++r->good;
  return true;
}
static inline uint32_t ew_age(const ew_receiver*r,uint32_t now){
  if(!r->seen)return UINT32_MAX;
  uint32_t d=now-r->received_ms,a=ew_u16(r->frame+10);
  return UINT32_MAX-d<a?UINT32_MAX:d+a;
}
#endif
