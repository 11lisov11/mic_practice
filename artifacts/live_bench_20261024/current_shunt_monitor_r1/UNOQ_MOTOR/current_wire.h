#ifndef MIC_CURRENT_WIRE_H
#define MIC_CURRENT_WIRE_H
#include "uart_v3_transport.h"
#include <string.h>
#define CT_PEER_BUILD 2026102406UL
enum {CT_SUMMARY=0xD3,CT_DETAIL=0xD4};
typedef struct {
  uint8_t summary[UV3_FRAME],detail[UV3_FRAME];
  uint32_t summary_ms,detail_ms,good,bad;
  bool has_summary,has_detail;
} ct_receiver;
static inline void ct_reset(ct_receiver *r){memset(r,0,sizeof(*r));}
static inline uint32_t ct_u32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline bool ct_receive(ct_receiver *r,const uint8_t *p,uint32_t peer,bool fresh,uint32_t now) {
  bool detail=p[2]==CT_DETAIL;
  if(p[0]!=0x55||p[1]!=0xaa||(!detail&&p[2]!=CT_SUMMARY)||!uv3_crc_ok(p)||
      p[38]!=1||ct_u32(p+6)!=CT_PEER_BUILD||peer!=CT_PEER_BUILD||!fresh) {
    if(r->bad<UINT32_MAX)++r->bad;
    return false;
  }
  uint8_t *target=detail?r->detail:r->summary;
  bool present=detail?r->has_detail:r->has_summary;
  uint32_t previous=detail?r->detail_ms:r->summary_ms;
  if(present && (uint32_t)(now-previous)<1000U) {
    uint8_t delta=(uint8_t)(p[4]-target[4]);
    if(!delta||delta>=128U){if(r->bad<UINT32_MAX)++r->bad;return false;}
  }
  memcpy(target,p,UV3_FRAME);
  if(detail){r->has_detail=true;r->detail_ms=now;}else{r->has_summary=true;r->summary_ms=now;}
  if(r->good<UINT32_MAX)++r->good;
  return true;
}
#endif
