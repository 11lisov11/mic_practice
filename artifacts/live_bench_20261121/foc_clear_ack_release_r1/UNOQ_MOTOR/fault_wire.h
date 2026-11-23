#ifndef MIC_I2C_FAULT_WIRE_H
#define MIC_I2C_FAULT_WIRE_H
#include "uart_v3_transport.h"
enum { FC_WIRE=0xDB,FC_FORMAT=2,FC_BYTES=160,FC_WORDS=40,FC_PAGES=7,
       FC_PEER=2026112112U,FC_MAGIC=0x31434649U };
static inline uint32_t fc_get(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline void fc_put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(v>>(i*8));}
static inline void fc_packet(uint8_t*p,const uint32_t*r,unsigned kind,unsigned page,uint32_t crc){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=FC_WIRE;p[3]=(uint8_t)kind;
  p[4]=(uint8_t)page;p[5]=FC_PAGES;fc_put(p+6,FC_PEER);fc_put(p+10,crc);p[38]=FC_FORMAT;
  unsigned offset=page*24U;
  for(unsigned i=0;i<24&&offset+i<FC_BYTES;++i){unsigned j=offset+i;p[14+i]=(uint8_t)(r[j/4]>>((j%4)*8));}
  uv3_seal(p);
}
typedef struct {uint8_t bytes[FC_BYTES];uint32_t crc;uint8_t mask;bool valid;} fc_slot;
typedef struct {fc_slot slot[2];uint32_t good,bad;} fc_receiver;
static inline bool fc_receive(fc_receiver*r,const uint8_t*p,uint32_t peer,bool fresh_off){
  bool ok=fresh_off&&peer==FC_PEER&&p[0]==0x55&&p[1]==0xaa&&p[2]==FC_WIRE&&
      p[3]<2&&p[4]<FC_PAGES&&p[5]==FC_PAGES&&p[38]==FC_FORMAT&&fc_get(p+6)==FC_PEER&&uv3_crc_ok(p);
  if(ok&&p[4]==FC_PAGES-1)for(unsigned i=16;i<24;++i)if(p[14+i])ok=false;
  if(!ok){if(r->bad!=UINT32_MAX)++r->bad;return false;}
  fc_slot*s=&r->slot[p[3]];uint32_t crc=fc_get(p+10);
  if(s->mask&&s->crc!=crc){s->mask=0;s->valid=false;}
  s->crc=crc;unsigned offset=p[4]*24U,n=FC_BYTES-offset;if(n>24)n=24;
  memcpy(s->bytes+offset,p+14,n);s->mask|=(uint8_t)(1U<<p[4]);
  if(s->mask==127){
    uint32_t meta=fc_get(s->bytes+16);uint8_t cause=(uint8_t)meta;
    bool cause_ok=cause==2||cause==6||cause==7||cause==8||cause==9||cause==10||cause==11||cause==12;
    s->valid=uv3_crc32c(s->bytes,FC_BYTES)==s->crc&&fc_get(s->bytes)==FC_MAGIC&&fc_get(s->bytes+4)==FC_PEER&&
        cause_ok&&((meta>>8)&255)<=11&&((meta>>16)&255)<=4&&((meta>>24)&3U)<=3&&
        (p[3]==0||(fc_get(s->bytes+16*4)&32768U)!=0);
    if(!s->valid){if(r->bad!=UINT32_MAX)++r->bad;return false;}
  }
  if(r->good!=UINT32_MAX)++r->good;
  return true;
}
#endif
