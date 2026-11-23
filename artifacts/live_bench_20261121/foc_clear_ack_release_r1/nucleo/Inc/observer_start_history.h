#ifndef MIC_OBSERVER_START_HISTORY_H
#define MIC_OBSERVER_START_HISTORY_H
/* Foreground-only exact replay journal. No actuator, IRQ mask, allocation or IO.
 * Store every input, not every 168-byte x/P: unchanged ARM replay reconstructs
 * all intermediate states. Checkpoints and a full terminal state detect drift.
 * Capture is first-session immutable. Missing rows are never silently repaired.
 */
#include "motor_control.h"
#include "observer_nis_replay_core.h"
#include "uart_v3_transport.h"
enum {NH_WIRE=0xEB,NH_SCHEMA=1,NH_CAPACITY=5120,NH_ROW=22,NH_QUEUE=4,
 NH_META_BYTES=524,NH_META_PAGES=21,NH_META_PAYLOAD=26,
 NH_EVENT=1,NH_STOP=2,NH_OVERFLOW=4,NH_GAP=8,NH_NONFINITE=16};
typedef struct {
 uint32_t magic,schema,firmware,epoch,row_bytes,capacity,count,event_count;
 uint32_t flags,first_center,last_center,last_end,initial_fpscr,chain,crc,reserved;
 ma_motor motor;
 ma_observer initial,terminal;
} nh_meta;
typedef struct {uint8_t bytes[NH_ROW];uint16_t index;uint32_t hash;} nh_row;
typedef struct {
 nh_meta meta;nh_row queue[NH_QUEUE];uint32_t head,tail,page;
 uint8_t active,frozen,sealed,reserved;
} nh_capture;
typedef char nh_meta_size[(sizeof(nh_meta)==NH_META_BYTES)?1:-1];
typedef char nh_observer_size[(sizeof(ma_observer)==204)?1:-1];
static inline uint32_t nh_u32(const uint8_t*p){uint32_t v;memcpy(&v,p,4);return v;}
static inline void nh_put(uint8_t*p,uint32_t v){memcpy(p,&v,4);}
static inline uint32_t nh_mix(uint32_t h,uint32_t v){return (h^v)*16777619U;}
static inline uint32_t nh_hash(const ma_observer*o){
 uint32_t h=2166136261U;
 for(unsigned i=0;i<sizeof(*o)/4;++i){uint32_t w;memcpy(&w,(const uint8_t*)o+4*i,4);h=nh_mix(h,w);}
 return h;
}
/* 153 compositions of sixteen samples: triangular rank fits one byte. */
static inline unsigned nh_pair_code(uint32_t counts){
 unsigned a=counts&31U,b=(counts>>5)&31U,c=(counts>>10)&31U;
 if((counts>>15)||a+b+c!=16U)return 255U;
 return a*(35U-a)/2U+b;
}
static inline uint32_t nh_pair_counts(unsigned code){
 if(code>152U)return 0;
 unsigned a=0;while(code>=17U-a){code-=17U-a;++a;}
 return a|(code<<5)|((16U-a-code)<<10);
}
static inline uint32_t nh_chain(uint32_t h,const uint8_t*row,uint32_t hash){
 for(unsigned i=0;i<NH_ROW;++i)h=nh_mix(h,row[i]);
 return nh_mix(h,hash);
}
static inline uint32_t nh_crc(const uint8_t*p){
 uint32_t c=0xffffffffU;
 for(unsigned i=0;i<NH_META_BYTES;++i){c^=(i>=56U&&i<60U)?0U:p[i];
  for(unsigned k=0;k<8;++k)c=(c>>1)^((c&1U)?0x82f63b78U:0U);}
 return ~c;
}
static inline void nh_begin(nh_capture*c,const ma_observer*o,const ma_motor*m,uint32_t fw,uint32_t epoch,uint32_t fpscr){
 if(c->frozen||(c->active&&c->meta.count))return;
 memset(c,0,sizeof(*c));c->meta.magic=0x3148534eU;c->meta.schema=NH_SCHEMA;
 c->meta.firmware=fw;c->meta.epoch=epoch?epoch:1U;c->meta.row_bytes=NH_ROW;c->meta.capacity=NH_CAPACITY;
 c->meta.motor=*m;c->meta.initial=*o;c->meta.initial_fpscr=fpscr;c->meta.chain=2166136261U;c->active=1;
}
static inline void nh_freeze(nh_capture*c,const ma_observer*o,uint32_t reason){
 if(!c->active||c->frozen||!c->meta.count)return;
 c->meta.terminal=*o;c->meta.flags|=reason;c->frozen=1;c->active=0;
}
static inline int nh_step(nh_capture*c,const ma_observer*o,const float*input,uint32_t pairs,
 uint32_t fpscr,int result,uint32_t center,uint32_t end){
 if(!c->active||c->frozen)return 0;
 if(c->meta.count>=NH_CAPACITY){nh_freeze(c,o,NH_OVERFLOW);return 0;}
 uint8_t bytes[NH_ROW];memcpy(bytes,input,20);
 unsigned code=nh_pair_code(pairs);bytes[20]=(uint8_t)code;
 bytes[21]=(uint8_t)((((fpscr>>22)&31U)<<3)|((unsigned)result&7U));
 if(code==255U||result<0||result>7)c->meta.flags|=NH_GAP;
 uint32_t hash=nh_hash(o),index=c->meta.count++;
 c->meta.chain=nh_chain(c->meta.chain,bytes,hash);
 if(!index)c->meta.first_center=center;
 c->meta.last_center=center;c->meta.last_end=end;
 if(c->head-c->tail>=NH_QUEUE)c->meta.flags|=NH_GAP;
 else{
  nh_row*r=&c->queue[c->head&(NH_QUEUE-1U)];memcpy(r->bytes,bytes,NH_ROW);
  r->index=(uint16_t)index;r->hash=hash;++c->head;
 }
 /* First >=25, including warmup. Diagnostic trigger does not change controls. */
 if(!isfinite(o->nis)||o->nis>=25.f){
  c->meta.event_count=c->meta.count;
  nh_freeze(c,o,NH_EVENT|(!isfinite(o->nis)?NH_NONFINITE:0));return 1;
 }
 return 0;
}
static inline int nh_packet(nh_capture*c,uint8_t*p,int off){
 memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=NH_WIRE;p[3]=NH_SCHEMA;p[38]=1;
 if(c->tail!=c->head){
  nh_row*r=&c->queue[c->tail&(NH_QUEUE-1U)];p[4]=1;p[5]=(uint8_t)r->index;p[6]=(uint8_t)(r->index>>8);p[7]=30;
  memcpy(p+8,r->bytes,NH_ROW);nh_put(p+30,r->hash);nh_put(p+34,c->meta.epoch);
 }else if(off&&c->frozen){
  if(!c->sealed){c->meta.crc=nh_crc((const uint8_t*)&c->meta);c->sealed=1;}
  unsigned page=c->page,offset=page*NH_META_PAYLOAD;
  unsigned len=NH_META_BYTES-offset;if(len>NH_META_PAYLOAD)len=NH_META_PAYLOAD;
  p[4]=2;p[5]=(uint8_t)page;p[7]=(uint8_t)len;
  memcpy(p+8,(const uint8_t*)&c->meta+offset,len);nh_put(p+34,c->meta.epoch);
 }else return 0;
 uv3_seal(p);return 1;
}
static inline void nh_sent(nh_capture*c){
 if(c->tail!=c->head)++c->tail;else c->page=(c->page+1U)%NH_META_PAGES;
}
#endif
