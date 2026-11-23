#ifndef MIC_I2C_WIRE_CAPTURE_H
#define MIC_I2C_WIRE_CAPTURE_H
#include "uart_v3_transport.h"
enum { WC_WIRE=0xdf, WC_FORMAT=1, WC_PEER=2026103004U,
       WC_MAGIC=0x31574349U, WC_SAMPLES=4096, WC_HEADER=48,
       WC_BYTES=1072, WC_PAGES=45, WC_PERIOD=20,
       WC_FULL=1, WC_DMA_ERROR=2, WC_MANUAL=4, WC_MOE=8,
       WC_UNINITIALIZED=0, WC_ARMED=1, WC_FROZEN=2, WC_READY=3, WC_ERROR=4 };
static inline uint32_t wc_u32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline void wc_put(uint8_t*p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(8*i));}
/* Ring end is the NEXT DMA destination. Only the two I2C bits are exported.
   Unsampled early-boot positions are zero padded, never presented as history. */
static inline uint8_t wc_data_byte(const volatile uint16_t*ring,unsigned end,unsigned valid,unsigned j){
  uint8_t value=0;
  for(unsigned i=0;i<4;i++){
    unsigned n=j*4+i;
    if(n<valid){unsigned index=valid==WC_SAMPLES?((end+n)&(WC_SAMPLES-1)):n;
      value|=(uint8_t)(((ring[index]>>8)&3U)<<(2*i));}
  }
  return value;
}
static inline bool wc_header_valid(const uint8_t*b){
  uint32_t n=wc_u32(b+28),flags=wc_u32(b+44);
  return wc_u32(b)==WC_MAGIC&&wc_u32(b+4)==WC_FORMAT&&wc_u32(b+8)==WC_BYTES&&
    wc_u32(b+12)==WC_PEER&&wc_u32(b+20)==170000000U&&wc_u32(b+24)==WC_PERIOD&&
    n<=WC_SAMPLES&&(flags&~15U)==0&&((flags&WC_FULL)!=0)==(n==WC_SAMPLES)&&
    ((flags&(WC_MANUAL|WC_MOE))==WC_MANUAL||(flags&(WC_MANUAL|WC_MOE))==WC_MOE)&&
    (!(flags&WC_MANUAL)||wc_u32(b+16)==0);
}
static inline void wc_frame(uint8_t*p,unsigned page,uint32_t crc){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=WC_WIRE;p[4]=(uint8_t)page;
  p[5]=WC_PAGES;wc_put(p+6,WC_PEER);wc_put(p+10,crc);p[38]=WC_FORMAT;
}
typedef struct {uint8_t bytes[WC_BYTES];uint32_t crc,mask[2],good,bad;uint8_t state;bool valid;} wc_receiver;
static inline bool wc_receive(wc_receiver*r,const uint8_t*p,uint32_t peer,bool off){
  bool ok=off&&peer==WC_PEER&&p[0]==0x55&&p[1]==0xaa&&p[2]==WC_WIRE&&
    wc_u32(p+6)==WC_PEER&&p[38]==WC_FORMAT&&uv3_crc_ok(p);
  if(ok&&p[3]==2){
    ok=p[4]<=WC_ERROR&&p[5]==0;
    for(unsigned i=10;i<38;i++)if(p[i])ok=false;
    if(ok){r->state=p[4];return true;}
  }else if(ok){
    ok=p[3]==0&&p[4]<WC_PAGES&&p[5]==WC_PAGES;
    if(ok&&p[4]==WC_PAGES-1)for(unsigned i=16;i<24;i++)if(p[14+i])ok=false;
  }
  if(!ok){if(r->bad!=UINT32_MAX)++r->bad;return false;}
  uint32_t crc=wc_u32(p+10);
  /* A complete capture is immutable for the peer epoch. A new epoch must be
     detected by the independent MCU timestamp before accepting another. */
  if(r->valid&&r->crc!=crc){if(r->bad!=UINT32_MAX)++r->bad;return false;}
  if(r->valid){
    unsigned offset=p[4]*24U,n=WC_BYTES-offset;if(n>24)n=24;
    if(memcmp(r->bytes+offset,p+14,n)){if(r->bad!=UINT32_MAX)++r->bad;return false;}
    if(r->good!=UINT32_MAX)++r->good;
    return true;
  }
  if((r->mask[0]||r->mask[1])&&r->crc!=crc){r->mask[0]=r->mask[1]=0;r->valid=false;}
  r->crc=crc;unsigned offset=p[4]*24U,n=WC_BYTES-offset;if(n>24)n=24;
  memcpy(r->bytes+offset,p+14,n);r->mask[p[4]/32]|=1U<<(p[4]%32);
  if(r->mask[0]==UINT32_MAX&&r->mask[1]==8191U){
    r->valid=uv3_crc32c(r->bytes,WC_BYTES)==r->crc&&wc_header_valid(r->bytes);
    if(!r->valid){if(r->bad!=UINT32_MAX)++r->bad;return false;}
    r->state=WC_READY;
  }
  if(r->good!=UINT32_MAX)++r->good;
  return true;
}
#endif
