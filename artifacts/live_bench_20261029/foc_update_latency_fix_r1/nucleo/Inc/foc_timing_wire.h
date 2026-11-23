#ifndef MIC_FOC_TIMING_WIRE_H
#define MIC_FOC_TIMING_WIRE_H
#include "uart_v3_transport.h"
enum {FT_WIRE=0xE8,FT_FORMAT=1,FT_PAGES=4};
typedef struct {uint32_t words[28],seen_ms,peer,good,bad;uint8_t mask,flags;} ft_receiver;
static inline uint32_t ft_u32(const uint8_t*p){
 return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static inline bool ft_receive(ft_receiver*r,const uint8_t*p,uint32_t peer,bool fresh,uint32_t now){
 if(!fresh||p[0]!=0x55||p[1]!=0xaa||p[2]!=FT_WIRE||p[3]!=FT_FORMAT||p[4]>=FT_PAGES||
    p[5]>3||p[38]||ft_u32(p+6)!=peer||!uv3_crc_ok(p)){
  if(r->bad!=UINT32_MAX)++r->bad;return false;
 }
 if(r->peer!=peer||r->flags!=p[5]){r->mask=0;memset(r->words,0,sizeof(r->words));}
 r->peer=peer;r->flags=p[5];
 for(unsigned i=0;i<7;++i)r->words[7*p[4]+i]=ft_u32(p+10+4*i);
 r->mask|=(uint8_t)(1U<<p[4]);r->seen_ms=now;
 if(r->good!=UINT32_MAX)++r->good;return true;
}
static inline bool ft_fresh(const ft_receiver*r,bool peer_fresh,uint32_t now){
 return r->mask==15&&peer_fresh&&(uint32_t)(now-r->seen_ms)<2500U;
}
#endif
