#ifndef MIC_ZERO_HISTORY_WIRE_H
#define MIC_ZERO_HISTORY_WIRE_H
#include "current_wire.h"
#include "peak_wire.h"
enum { ZH_WIRE=0xd9, ZH_MAX=8 };
static_assert((int)ZH_WIRE!=(int)PC_WIRE && (int)ZH_WIRE!=(int)CT_SUMMARY &&
 (int)ZH_WIRE!=(int)CT_DETAIL && (int)ZH_WIRE!=(int)CT_QUALITY &&
 (int)ZH_WIRE!=(int)BW_VERSION && (int)ZH_WIRE!=(int)BKW_VERSION &&
 (int)ZH_WIRE!=(int)URW_VERSION && (int)ZH_WIRE!=(int)UV3_VERSION,"Unique zero-history wire version");
typedef struct {
 uint8_t frames[ZH_MAX][UV3_FRAME],mask,count;
 uint32_t good,bad;
 bool complete;
} zh_receiver;
static inline void zh_reset(zh_receiver *r){memset(r,0,sizeof(*r));}
static inline bool zh_receive(zh_receiver *r,const uint8_t *p,uint32_t peer,bool off) {
 const unsigned page=p[4],count=p[5];
 if(!off || peer!=CT_PEER_BUILD || p[0]!=0x55 || p[1]!=0xaa || p[2]!=ZH_WIRE ||
    p[3]!=1 || count<3 || count>8 || page>=count || ct_u32(p+6)!=CT_PEER_BUILD ||
    p[30]!=3 || p[31]!=2 || p[32]!=3 || p[33]!=8 || p[34]!=2 ||
    p[35]!=128 || p[36]!=0 || p[37]!=15 || p[38]!=1 || !uv3_crc_ok(p)) {++r->bad;return false;}
 for(unsigned i=25;i<30;++i)if(p[i]){++r->bad;return false;}
 if(r->mask && r->count!=count){++r->bad;return false;}
 if(r->mask&(1U<<page)) {
   if(memcmp(r->frames[page],p,UV3_FRAME)){++r->bad;return false;}
   return true;
 }
 r->count=(uint8_t)count;memcpy(r->frames[page],p,UV3_FRAME);
 r->mask|=(uint8_t)(1U<<page);++r->good;
 r->complete=r->mask==(uint8_t)((1U<<count)-1U);return true;
}
#endif
