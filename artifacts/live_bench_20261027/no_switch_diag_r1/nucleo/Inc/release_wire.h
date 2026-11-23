#ifndef MIC_RELEASE_WIRE_H
#define MIC_RELEASE_WIRE_H
#include "uart_v3_transport.h"
#include "pe_release_probe.h"
enum { PR_WIRE=0xDD,PR_FORMAT=1,PR_PEER=2026102790U,PR_MAGIC=0x31525053U,
       PR_WORDS=25,PR_BYTES=100,PR_PAGES=5 };
static inline uint32_t pr_get(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline void pr_put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static inline bool pr_valid(const uint8_t*b){
  uint32_t meta=pr_get(b+12),flags=meta&255U,n=(meta>>8)&255U,result=(meta>>16)&255U,hz=pr_get(b+24);
  if(pr_get(b)!=PR_MAGIC||pr_get(b+4)!=PR_PEER||meta>>24||flags&~15U||n>3||result>3||hz<1000000U||
      uv3_crc32c(b,96)!=pr_get(b+96))return false;
  if((n>0)!=((flags&SR_IMMEDIATE)!=0))return false;
  if(!n&&!(flags&SR_CANCELLED))return false;
  if((flags&SR_LATE)&&((flags&(SR_CANCELLED|SR_TIMEOUT))||n!=2))return false;
  bool complete=!(flags&(SR_CANCELLED|SR_TIMEOUT))&&(n==3||(n==2&&(flags&SR_LATE)));
  if(!complete&&!(flags&(SR_CANCELLED|SR_TIMEOUT)))return false;
  bool high=false,low=false;
  for(unsigned i=0;i<3;i++){
    const uint8_t*s=b+32+20*i;
    if(i>=n){for(unsigned j=0;j<20;j++)if(s[j])return false;continue;}
    if(pr_get(s+8)&1U)return false;
    if(pr_get(s+16)&256U)high=true;else low=true;
    if(i){
      uint32_t us=(pr_get(s)-pr_get(b+32))/(hz/1000000U);
      if(us<(i==1?5U:20U)||us>1000U)return false;
    }
  }
  unsigned expected=!complete?SR_UNKNOWN:high&&low?SR_MIXED:high?SR_SCL_HIGH_AFTER_DISABLE:SR_SCL_LOW_AFTER_DISABLE;
  return result==expected;
}
static inline void pr_packet(uint8_t*p,const uint32_t*r,unsigned slot,unsigned page,uint32_t crc){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=PR_WIRE;p[3]=(uint8_t)slot;p[4]=(uint8_t)page;p[5]=PR_PAGES;
  pr_put(p+6,PR_PEER);pr_put(p+10,crc);p[38]=PR_FORMAT;
  unsigned off=page*24U;
  for(unsigned i=0;i<24&&off+i<PR_BYTES;i++){unsigned j=off+i;p[14+i]=(uint8_t)(r[j/4]>>((j%4)*8));}
  uv3_seal(p);
}
typedef struct {uint8_t staging[PR_BYTES],bytes[PR_BYTES];uint32_t crc,published_crc;uint8_t mask;bool valid;} pr_slot;
typedef struct {pr_slot slot[2];uint32_t good,bad;} pr_receiver;
static inline bool pr_bad(pr_receiver*r){if(r->bad!=UINT32_MAX)r->bad++;return false;}
static inline bool pr_receive(pr_receiver*r,const uint8_t*p,uint32_t peer,bool fresh_off){
  if(!fresh_off||peer!=PR_PEER||p[0]!=0x55||p[1]!=0xaa||p[2]!=PR_WIRE||p[3]>1||p[4]>=PR_PAGES||p[5]!=PR_PAGES||
      pr_get(p+6)!=PR_PEER||p[38]!=PR_FORMAT||!uv3_crc_ok(p))return pr_bad(r);
  if(p[4]==PR_PAGES-1)for(unsigned i=4;i<24;i++)if(p[14+i])return pr_bad(r);
  pr_slot*s=&r->slot[p[3]];uint32_t crc=pr_get(p+10);
  if(s->mask&&s->crc!=crc)s->mask=0;
  s->crc=crc;unsigned off=p[4]*24U,n=PR_BYTES-off;if(n>24)n=24;
  memcpy(s->staging+off,p+14,n);s->mask|=(uint8_t)(1U<<p[4]);
  if(s->mask==31){
    if(uv3_crc32c(s->staging,PR_BYTES)!=crc||!pr_valid(s->staging)){s->mask=0;return pr_bad(r);}
    memcpy(s->bytes,s->staging,PR_BYTES);s->published_crc=crc;s->valid=true;
  }
  if(r->good!=UINT32_MAX)r->good++;
  return true;
}
static inline bool pr_linked(const pr_slot*s,const uint8_t*parent,uint32_t parent_crc,bool parent_valid){
  return s->valid&&parent_valid&&pr_get(s->bytes+8)==parent_crc&&pr_get(s->bytes+28)==pr_get(parent+8)&&
      pr_get(s->bytes+16)==pr_get(parent+39*4)&&pr_get(s->bytes+20)==pr_get(parent+38*4)&&
      pr_get(s->bytes+24)==pr_get(parent+32*4)&&pr_get(parent+4)==PR_PEER;
}
#endif
