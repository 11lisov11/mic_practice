#ifndef MIC_CURRENT_WIRE_H
#define MIC_CURRENT_WIRE_H
#include "uart_v3_transport.h"
#include "uart_reject_wire.h"
#include "bkin_wave_wire.h"
#include <string.h>
#define CT_PEER_BUILD 2026103012UL
enum {CT_SUMMARY=0xD5,CT_DETAIL=0xD6,CT_QUALITY=0xD7};
static_assert((int)CT_SUMMARY!=(int)URW_VERSION && (int)CT_DETAIL!=(int)URW_VERSION &&
              (int)CT_SUMMARY!=(int)BKW_VERSION && (int)CT_DETAIL!=(int)BKW_VERSION &&
              (int)CT_SUMMARY!=(int)BW_VERSION && (int)CT_DETAIL!=(int)BW_VERSION &&
              (int)CT_SUMMARY!=(int)UV3_VERSION && (int)CT_DETAIL!=(int)UV3_VERSION,
              "Current packets must have unique wire versions");
static_assert((int)CT_QUALITY!=(int)URW_VERSION && (int)CT_QUALITY!=(int)BKW_VERSION &&
              (int)CT_QUALITY!=(int)BW_VERSION && (int)CT_QUALITY!=(int)UV3_VERSION &&
              (int)CT_QUALITY!=(int)CT_SUMMARY && (int)CT_QUALITY!=(int)CT_DETAIL,
              "Current quality packet must have a unique wire version");
typedef struct {
  uint8_t summary[UV3_FRAME],detail[UV3_FRAME],quality[UV3_FRAME];
  uint32_t summary_ms,detail_ms,quality_ms,good,bad;
  bool has_summary,has_detail,has_quality;
} ct_receiver;
static inline void ct_reset(ct_receiver *r){memset(r,0,sizeof(*r));}
static inline uint32_t ct_u32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline bool ct_receive(ct_receiver *r,const uint8_t *p,uint32_t peer,bool fresh,uint32_t now) {
  bool detail=p[2]==CT_DETAIL,quality=p[2]==CT_QUALITY;
  if(p[0]!=0x55||p[1]!=0xaa||(!detail&&!quality&&p[2]!=CT_SUMMARY)||!uv3_crc_ok(p)||
      p[38]!=1||ct_u32(p+6)!=CT_PEER_BUILD||peer!=CT_PEER_BUILD||!fresh) {
    if(r->bad<UINT32_MAX)++r->bad;
    return false;
  }
  uint8_t *target=quality?r->quality:detail?r->detail:r->summary;
  bool present=quality?r->has_quality:detail?r->has_detail:r->has_summary;
  uint32_t previous=quality?r->quality_ms:detail?r->detail_ms:r->summary_ms;
  if(present && (uint32_t)(now-previous)<1000U) {
    uint8_t delta=(uint8_t)(p[4]-target[4]);
    if(!delta||delta>=128U){if(r->bad<UINT32_MAX)++r->bad;return false;}
  }
  memcpy(target,p,UV3_FRAME);
  if(quality){r->has_quality=true;r->quality_ms=now;}
  else if(detail){r->has_detail=true;r->detail_ms=now;}
  else{r->has_summary=true;r->summary_ms=now;}
  if(r->good<UINT32_MAX)++r->good;
  return true;
}
#endif
