#ifndef MIC_ADC_IDLE_NOISE_WIRE_H
#define MIC_ADC_IDLE_NOISE_WIRE_H
#include "uart_v3_transport.h"
#include <stdint.h>
#include <string.h>
enum { ND_WIRE=0xE7,ND_WIRE_BYTES=2176,ND_WIRE_PAGES=91 };
typedef struct {uint8_t bytes[ND_WIRE_BYTES];uint32_t mask[3],crc,build,good,bad;bool started,complete;} nd_blob;
static inline uint32_t nd_u32(const uint8_t*p){uint32_t v=0;for(unsigned i=0;i<4;i++)v|=(uint32_t)p[i]<<(8*i);return v;}
static inline bool nd_receive(nd_blob*b,const uint8_t*p,uint32_t peer,bool off){
 if(!off||p[0]!=0x55||p[1]!=0xaa||p[2]!=ND_WIRE||p[3]!=1||p[4]>=ND_WIRE_PAGES||
  p[5]!=ND_WIRE_PAGES||!uv3_crc_ok(p)||nd_u32(p+6)!=peer||p[38]){b->bad++;return false;}
 uint32_t crc=nd_u32(p+10);unsigned page=p[4],offset=page*24,n=ND_WIRE_BYTES-offset;if(n>24)n=24;
 for(unsigned i=n;i<24;i++)if(p[14+i]){b->bad++;return false;}
 if(!b->started||b->crc!=crc||b->build!=peer){memset(b->mask,0,sizeof(b->mask));b->started=true;b->complete=false;b->crc=crc;b->build=peer;}
 if(b->mask[page/32]&(1U<<(page%32))){if(memcmp(b->bytes+offset,p+14,n)){b->bad++;return false;}}
 else{memcpy(b->bytes+offset,p+14,n);b->mask[page/32]|=1U<<(page%32);}
 b->good++;
 if(b->mask[0]==UINT32_MAX&&b->mask[1]==UINT32_MAX&&b->mask[2]==((1U<<27)-1)){
  if(uv3_crc32c(b->bytes,ND_WIRE_BYTES)!=crc||nd_u32(b->bytes)!=0x314E4441U||
    nd_u32(b->bytes+4)!=1||nd_u32(b->bytes+8)!=peer){b->bad++;return false;}
  b->complete=true;
 }
 return true;
}
#endif
