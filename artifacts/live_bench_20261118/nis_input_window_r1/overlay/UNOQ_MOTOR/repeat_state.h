#ifndef MIC_REPEAT_STATE_H
#define MIC_REPEAT_STATE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "uart_v3_transport.h"
enum { RP_WAIT=0, RP_ARMED=1, RP_CAPTURED=2, RP_ERROR=3, RP_FIRST_PENDING=4,
       RPM_VERSION=0xED, RP_NATIVE_BUILD=2026111716U };
typedef struct {
  uint32_t state,clear_tick,armed_tick,irq_base,event_irq,first_crc,event_tick;
} rp_state;
/* One slot per boot. STOP and subsequent CLEAR cannot replace an armed or
 * completed slot. A pending first record is reported, never overwritten. */
static inline bool rp_request(volatile rp_state *r,bool first_ready,bool off,
    uint32_t tick,uint32_t irq,uint32_t first_crc) {
  if(!off || (r->state!=RP_WAIT && r->state!=RP_FIRST_PENDING))return false;
  r->clear_tick=tick;r->irq_base=irq;r->first_crc=first_crc;
  if(!first_ready){r->state=RP_FIRST_PENDING;return false;}
  r->armed_tick=tick;r->event_irq=0;r->event_tick=0;r->state=RP_ARMED;return true;
}
static inline bool rp_claim(volatile rp_state *r,uint32_t irq,uint32_t tick) {
  if(r->state!=RP_ARMED || r->event_irq)return false;
  r->event_irq=irq;r->event_tick=tick;return true;
}
static inline uint32_t rpm_u32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline void rpm_put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(v>>(8*i));}
static inline void rpm_packet(uint8_t*p,const volatile rp_state*r,uint8_t flags,uint32_t boot_crc){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=RPM_VERSION;p[3]=1;
  p[4]=(uint8_t)r->state;p[5]=flags;rpm_put(p+6,RP_NATIVE_BUILD);
  rpm_put(p+10,r->clear_tick);rpm_put(p+14,r->armed_tick);rpm_put(p+18,r->irq_base);
  rpm_put(p+22,r->event_irq);rpm_put(p+26,r->first_crc);rpm_put(p+30,r->event_tick);
  rpm_put(p+34,boot_crc);uv3_seal(p);
}
static inline bool rpm_valid(const uint8_t*p,uint32_t peer,bool fresh_off){
  return fresh_off && peer==RP_NATIVE_BUILD && p[0]==0x55 && p[1]==0xaa &&
    p[2]==RPM_VERSION && p[3]==1 && p[4]<=RP_FIRST_PENDING && !(p[5]&~3U) &&
    rpm_u32(p+6)==peer && !p[38] && uv3_crc_ok(p) &&
    (p[4]!=RP_CAPTURED || (p[5]==3 && rpm_u32(p+22)!=0));
}
#endif
