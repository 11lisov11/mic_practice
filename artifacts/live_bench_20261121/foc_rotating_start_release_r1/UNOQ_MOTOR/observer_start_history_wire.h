#ifndef MIC_OBSERVER_START_HISTORY_WIRE_H
#define MIC_OBSERVER_START_HISTORY_WIRE_H
#include "uart_v3_transport.h"
/* Uno SRAM journal, bounded to the native five-second trial. A lost/reordered
 * row or changed epoch makes exact=false; later data cannot erase that fact.
 * Full snapshots remain available after STOP without a huge RPC response.
 */
enum {NH_WIRE=0xEB,NH_CAPACITY=5120,NH_ROW=22,NH_META_BYTES=524,NH_META_PAGES=21,
 NH_CHECKPOINTS=NH_CAPACITY/16};
typedef struct {
 uint8_t rows[NH_CAPACITY][NH_ROW],meta[NH_META_BYTES];
 uint32_t checkpoints[NH_CHECKPOINTS];
 uint32_t epoch,count,chain,pages,good,bad,last_hash;
 bool present,complete,gap;
} nh_receiver;
static inline uint32_t nhr_u32(const uint8_t*p){uint32_t v;memcpy(&v,p,4);return v;}
static inline uint32_t nhr_mix(uint32_t h,uint32_t v){return (h^v)*16777619U;}
static inline uint32_t nhr_crc(const uint8_t*p){
 uint32_t c=0xffffffffU;for(unsigned i=0;i<NH_META_BYTES;++i){c^=(i>=56&&i<60)?0:p[i];
  for(unsigned k=0;k<8;++k)c=(c>>1)^((c&1)?0x82f63b78U:0);}return ~c;
}
static inline bool nhr_receive(nh_receiver*r,const uint8_t*p,uint32_t peer,uint32_t expected){
 if(p[0]!=0x55||p[1]!=0xaa||p[2]!=NH_WIRE||p[3]!=1||p[38]!=1||peer!=expected||!uv3_crc_ok(p)){
  ++r->bad;r->gap=true;return false;}
 uint32_t epoch=nhr_u32(p+34);unsigned index=(unsigned)p[5]|((unsigned)p[6]<<8);
 if(!epoch||(p[4]!=1&&p[4]!=2)){++r->bad;r->gap=true;return false;}
 if(r->present&&r->epoch!=epoch){++r->bad;return false;} /* preserve first session */
 if(!r->present){r->present=true;r->epoch=epoch;r->chain=2166136261U;}
 if(p[4]==1){
  if(p[7]!=30||index>=NH_CAPACITY||r->complete||p[28]>152U){++r->bad;r->gap=true;return false;}
  if(index!=r->count){++r->bad;r->gap=true;return false;}
  memcpy(r->rows[index],p+8,NH_ROW);
  for(unsigned i=0;i<NH_ROW;++i)r->chain=nhr_mix(r->chain,p[8+i]);
  r->last_hash=nhr_u32(p+30);r->chain=nhr_mix(r->chain,r->last_hash);
  if((index&15U)==15U)r->checkpoints[index/16]=r->last_hash;
  ++r->count;++r->good;return true;
 }
 unsigned len=index==NH_META_PAGES-1?4U:26U;
 if(index>=NH_META_PAGES||p[7]!=len){++r->bad;r->gap=true;return false;}
 for(unsigned i=len;i<26;++i)if(p[8+i]){++r->bad;r->gap=true;return false;}
 uint32_t bit=1U<<index;
 if(r->pages&bit){if(memcmp(r->meta+26*index,p+8,len)){++r->bad;r->gap=true;return false;}return true;}
 memcpy(r->meta+26*index,p+8,len);r->pages|=bit;++r->good;
 if(r->pages==((1U<<NH_META_PAGES)-1U)){
  const uint8_t*m=r->meta;
  if(nhr_u32(m)!=0x3148534eU||nhr_u32(m+4)!=1||nhr_u32(m+8)!=expected||
   nhr_u32(m+12)!=epoch||nhr_u32(m+16)!=NH_ROW||nhr_u32(m+20)!=NH_CAPACITY||
   nhr_u32(m+24)!=r->count||nhr_u32(m+52)!=r->chain||nhr_u32(m+56)!=nhr_crc(m)||
   (nhr_u32(m+32)&(4U|8U)))r->gap=true;
  r->complete=true;
 }
 return true;
}
static inline bool nhr_exact(const nh_receiver*r){return r->complete&&!r->gap;}
#endif
