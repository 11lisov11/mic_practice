#ifndef MIC_OBSERVER_TRACE_WIRE_H
#define MIC_OBSERVER_TRACE_WIRE_H
#include "uart_v3_transport.h"
enum {OD_WIRE=0xEA,OD_WIRE_BYTES=1888,OD_PAYLOAD=30,OD_PAGES=63};
typedef struct {uint8_t data[OD_WIRE_BYTES];uint64_t pages;uint32_t good,bad;bool complete;} od_receiver;
static inline void odw_reset(od_receiver*r){memset(r,0,sizeof(*r));}
static inline uint32_t odw_u32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline uint32_t odw_crc(const uint8_t*p){
 uint32_t c=0xffffffffU;
 for(unsigned i=0;i<OD_WIRE_BYTES;++i){
  c^=(i>=60U&&i<64U)?0U:p[i];
  for(unsigned k=0;k<8;++k)c=(c>>1)^((c&1U)?0x82f63b78U:0U);
 }return ~c;
}
static inline bool odw_receive(od_receiver*r,const uint8_t*p,uint32_t peer,uint32_t expected,bool off){
 unsigned page=p[5],len=page==OD_PAGES-1U?28U:(unsigned)OD_PAYLOAD;
 if(!off||peer!=expected||p[0]!=0x55||p[1]!=0xaa||p[2]!=OD_WIRE||p[3]!=4||p[4]!=1||
   page>=OD_PAGES||p[6]!=OD_PAGES||p[7]!=len||p[38]!=1||!uv3_crc_ok(p)){++r->bad;return false;}
 for(unsigned i=len;i<OD_PAYLOAD;++i)if(p[8+i]){++r->bad;return false;}
 if(r->complete){if(memcmp(r->data+page*OD_PAYLOAD,p+8,len)){++r->bad;return false;}return true;}
 if(r->pages&(UINT64_C(1)<<page)){
  if(memcmp(r->data+page*OD_PAYLOAD,p+8,len)){r->pages=0;++r->bad;return false;}return true;
 }
 memcpy(r->data+page*OD_PAYLOAD,p+8,len);r->pages|=UINT64_C(1)<<page;++r->good;
 if(r->pages==((UINT64_C(1)<<OD_PAGES)-1U)){
  if(odw_u32(r->data)!=0x3144534fU||odw_u32(r->data+4)!=4U||odw_u32(r->data+8)!=peer||
     odw_crc(r->data)!=odw_u32(r->data+60)){r->pages=0;++r->bad;return false;}
  r->complete=true;
 }return true;
}
#endif
