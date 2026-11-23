#ifndef MIC_CLEAR_RECOVERY_WIRE_H
#define MIC_CLEAR_RECOVERY_WIRE_H
#include "uart_v3_transport.h"
enum { CC_WIRE=0xEE, CC_ACCEPTED=1, CC_TX_BLOCKED=2, CC_BREAK_BLOCKED=3,
       CC_MCSDK_REJECTED=4, CC_LOCAL_STOP_BLOCKED=5 };
static inline uint32_t cc_u32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static inline void cc_put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4U;++i)p[i]=(uint8_t)(v>>(8U*i));}
static inline bool cc_valid(const uint8_t *p,uint32_t firmware){
 return firmware!=0U && p[0]==0x55U && p[1]==0xAAU && p[2]==CC_WIRE && p[3]==1U &&
  p[4]==0U && p[5]==0U && cc_u32(p+6)==firmware && p[37]>=CC_ACCEPTED &&
  p[37]<=CC_LOCAL_STOP_BLOCKED && p[38]==0U && !(p[26]&0xC0U) && uv3_crc_ok(p);
}
#endif
