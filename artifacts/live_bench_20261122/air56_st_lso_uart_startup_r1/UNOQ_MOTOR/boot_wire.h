#ifndef MIC_BOOT_WIRE_H
#define MIC_BOOT_WIRE_H
#include "boot_record.h"
#include "uart_v3_transport.h"
enum {MB_WIRE=0xE9,MB_FORMAT=1};
static inline uint32_t mb_u32(const uint8_t*p){
 return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static inline void mb_put(uint8_t*p,uint32_t w){
 for(unsigned i=0;i<4U;++i)p[i]=(uint8_t)(w>>(8U*i));
}
static inline void mb_packet(uint8_t *p,const mb_record *r,uint32_t now_ms){
 memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=MB_WIRE;p[3]=MB_FORMAT;
 p[4]=mb_valid(r,r->firmware)?1U:0U;
 mb_put(p+6,r->firmware);mb_put(p+10,r->sequence);mb_put(p+14,r->csr);
 mb_put(p+18,r->previous_csr);mb_put(p+22,r->flags);mb_put(p+26,r->software_tag);
 mb_put(p+30,r->crc);mb_put(p+34,now_ms);uv3_seal(p);
}
static inline bool mb_decode(const uint8_t *p,uint32_t firmware,mb_record *r){
 if(p[0]!=0x55||p[1]!=0xaa||p[2]!=MB_WIRE||p[3]!=MB_FORMAT||p[4]!=1U||
    p[5]||p[38]||mb_u32(p+6)!=firmware||!uv3_crc_ok(p))return false;
 mb_record v={MB_MAGIC,mb_u32(p+6),mb_u32(p+10),mb_u32(p+14),mb_u32(p+18),
              mb_u32(p+22),mb_u32(p+26),mb_u32(p+30)};
 if(!mb_valid(&v,firmware))return false;
 *r=v;return true;
}
typedef struct {uint8_t packet[UV3_FRAME];uint32_t seen_ms,good,bad;bool received;} mb_receiver;
static inline bool mb_receive(mb_receiver *r,const uint8_t *p,uint32_t firmware,bool peer_fresh,uint32_t now){
 mb_record v;
 if(!peer_fresh||!mb_decode(p,firmware,&v)){if(r->bad!=UINT32_MAX)++r->bad;return false;}
 memcpy(r->packet,p,UV3_FRAME);r->seen_ms=now;r->received=true;
 if(r->good!=UINT32_MAX)++r->good;
 return true;
}
static inline bool mb_fresh(const mb_receiver*r,uint32_t firmware,bool peer_fresh,uint32_t now){
 return r->received&&peer_fresh&&mb_u32(r->packet+6)==firmware&&(uint32_t)(now-r->seen_ms)<1500U;
}
#endif
