#ifndef MIC_IDENTIFY_WIRE_H
#define MIC_IDENTIFY_WIRE_H
#include "uart_v3_transport.h"
#include <stdint.h>
#include <math.h>
enum { ID_PAGE_WIRE=0xE5,ID_STATUS_WIRE=0xE6,ID_BLOB_BYTES=1664,ID_PAGE_COUNT=70,ID_VIEW_BYTES=128 };
typedef struct {
 uint32_t seen_ms,config_crc,result_crc,run_id,kind,duration_ms,timing_cycles,good,bad;
 float frequency;uint8_t flags,fault;bool seen;
} id_meta;
typedef struct {uint8_t bytes[ID_BLOB_BYTES];uint32_t mask[3],crc,build,good,bad;bool started,complete;} id_blob;
static inline bool id_execution_allowed(const id_meta*m,uint32_t now,uint32_t nonce,bool manual,uint32_t limit){
 return m->seen&&(uint32_t)(now-m->seen_ms)<1500U&&(m->flags&1U)&&!(m->flags&14U)&&
  nonce&&nonce==m->config_crc&&!manual&&!m->fault&&m->timing_cycles>0&&m->timing_cycles<=4800U&&m->duration_ms>=2000U&&m->duration_ms<=10000U&&
  limit>=m->duration_ms+500U&&limit<=12000U;
}
static inline uint32_t id_u32(const uint8_t*p){uint32_t v=0;for(unsigned i=0;i<4;i++)v|=(uint32_t)p[i]<<(8*i);return v;}
static inline void id_put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static inline bool id_receive_status(id_meta*m,const uint8_t*p,uint32_t peer,bool fresh,uint32_t now){
 if(!fresh||p[0]!=0x55||p[1]!=0xaa||p[2]!=ID_STATUS_WIRE||p[3]!=2||p[4]!=4||p[5]>15||
    !uv3_crc_ok(p)||id_u32(p+6)!=peer||p[38]>9){m->bad++;return false;}
 uint32_t raw=id_u32(p+26);float f;memcpy(&f,&raw,4);
 if(!isfinite(f)||f<0||f>200){m->bad++;return false;}
 m->seen=true;m->seen_ms=now;m->flags=p[5];m->config_crc=id_u32(p+10);m->result_crc=id_u32(p+14);
 m->run_id=id_u32(p+18);m->kind=id_u32(p+22);m->frequency=f;m->duration_ms=id_u32(p+30);
 m->timing_cycles=id_u32(p+34);m->fault=p[38];m->good++;return true;
}
static inline bool id_receive_page(id_blob*b,const uint8_t*p,uint32_t peer,bool fresh){
 if(!fresh||p[0]!=0x55||p[1]!=0xaa||p[2]!=ID_PAGE_WIRE||p[3]!=1||p[4]>=ID_PAGE_COUNT||
  p[5]!=ID_PAGE_COUNT||!uv3_crc_ok(p)||id_u32(p+6)!=peer||p[38]){b->bad++;return false;}
 const uint32_t crc=id_u32(p+10);unsigned page=p[4],offset=page*24,n=ID_BLOB_BYTES-offset;if(n>24)n=24;
 for(unsigned i=n;i<24;i++)if(p[14+i]){b->bad++;return false;}
 if(!b->started||b->crc!=crc||b->build!=peer){memset(b->mask,0,sizeof(b->mask));b->started=true;b->complete=false;b->crc=crc;b->build=peer;}
 if(b->mask[page/32]&(1U<<(page%32))){
  if(memcmp(b->bytes+offset,p+14,n)){b->bad++;return false;}
 }else{memcpy(b->bytes+offset,p+14,n);b->mask[page/32]|=1U<<(page%32);}
 b->good++;
 if(b->mask[0]==UINT32_MAX&&b->mask[1]==UINT32_MAX&&(b->mask[2]&63U)==63U){
  if(uv3_crc32c(b->bytes,ID_BLOB_BYTES)!=crc||id_u32(b->bytes)!=0x3144494D||id_u32(b->bytes+8)!=peer){b->bad++;return false;}
  b->complete=true;
 }
 return true;
}
#endif
