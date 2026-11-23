#ifndef MIC_ADC_PEAK_CORE_H
#define MIC_ADC_PEAK_CORE_H
/* Diagnostic only:60 compact rows retain25 input/voltage +32 later rows (2ms).
 * ADC owns the blob. Foreground publishes3 request words outside the blob,
 * then a release flag. No IRQ masking, dynamic allocation or motor actions.
 * Missing/overwritten history is explicitly GAP, never substituted.
 */
#include <stdint.h>
#include <string.h>
enum {PC_CAPACITY=60,PC_POST=6,PC_THRESHOLD=626,PC_BYTES=1024,
 PC_PEAK=1,PC_SHORT=2,PC_NO_PEAK=4,PC_OBSERVER=8,PC_EXACT=16,PC_GAP=32};
/* Unchanged ISR input. Only diagnostic storage is compacted. */
typedef struct {
 uint32_t cycles,sequence,epoch_before,epoch_after,isr1,isr2,jsqr1,jsqr2;
 uint16_t active_ccr[4],preload_ccr[4];
 uint16_t cnt,arr,cr1,raw[2],offset[4],flags,cnt_exit,reference_deci_hz,bus_v,update_cnt;
 uint8_t pair,next_pair;uint16_t update_cr1;
}pc_sample;
typedef struct {
 uint32_t magic;uint16_t schema,sample_bytes;uint32_t firmware,capture_id;
 uint16_t capacity,count,oldest,trigger_slot;uint32_t total_samples;
 uint32_t requested_first,requested_end,observer_step,pair_counts,center;
 uint16_t offset[4],arr,flags;uint32_t crc;
}pc_header;
/* Two12-bit ADCs, four13-bit compares; rejected out-of-range values never
 * become valid source data. Bus9bits/pair2bits/quality5bits use16bits. */
typedef struct {uint32_t cycles;uint8_t packed[10];uint16_t meta;}pc_raw;
typedef struct {pc_header header;pc_raw samples[PC_CAPACITY];}pc_blob;
typedef struct {
 pc_blob blob;uint32_t total,request_first,request_end,request_step;
 uint16_t write,count,after;uint8_t running,triggered,observer_requested;volatile uint8_t frozen;
}pc_capture;
typedef char pc_input_size[(sizeof(pc_sample)==80)?1:-1];
typedef char pc_header_size[(sizeof(pc_header)==64)?1:-1];
typedef char pc_raw_size[(sizeof(pc_raw)==16)?1:-1];
typedef char pc_blob_size[(sizeof(pc_blob)==1024)?1:-1];
typedef char pc_RAM_bound[(sizeof(pc_capture)<=1052)?1:-1];
static inline unsigned pc_next(unsigned slot){return slot+1U==60U?0:slot+1U;}
static inline unsigned pc_advance(unsigned slot,unsigned n){slot+=n;return slot>=60U?slot-60U:slot;}
static inline void pc_init(pc_capture*c){memset(c,0,sizeof(*c));}
static inline void pc_request_observer(pc_capture*c,uint32_t first,uint32_t end,uint32_t step){
 if(c->frozen||c->triggered||__atomic_load_n(&c->observer_requested,__ATOMIC_ACQUIRE))return;
 c->request_first=first;c->request_end=end;c->request_step=step;
 __atomic_store_n(&c->observer_requested,1,__ATOMIC_RELEASE);
}
static inline void pc_freeze(pc_capture*c,uint32_t now,uint32_t reason){
 (void)now;pc_header*h=&c->blob.header;
 h->magic=0x31435041UL;h->schema=3;h->sample_bytes=sizeof(pc_raw);
 h->capture_id=1;h->capacity=60;h->count=c->count;h->oldest=c->count==60?c->write:0;
 if(!c->triggered)h->trigger_slot=UINT16_MAX;
 h->total_samples=c->total;h->flags=(uint16_t)reason;c->frozen=1;
}
/* Bounded60+25 inspection, once at first NIS; never a control/trip predicate. */
static inline uint32_t pc_match_source(pc_capture*c){
 pc_header*h=&c->blob.header;
 h->requested_first=c->request_first;h->requested_end=c->request_end;h->observer_step=c->request_step;
 h->pair_counts=0;h->center=0;unsigned slot=c->count==60?c->write:0;
 for(unsigned n=0;n<c->count;++n,slot=pc_next(slot)){
  if(c->blob.samples[slot].cycles!=c->request_end)continue;
  h->trigger_slot=(uint16_t)slot;if(n<24U)return 3;
  unsigned first=slot>=15U?slot-15U:slot+45U;
  if(c->blob.samples[first].cycles!=c->request_first)return 3;
  unsigned idx=slot>=24U?slot-24U:slot+36U;uint32_t packed=0,previous=0;
  for(unsigned k=0;k<25;++k,idx=pc_next(idx)){
   const pc_raw*r=&c->blob.samples[idx];
   unsigned pair=(r->meta>>9)&3U;
   if(pair>2U||(r->meta>>11)!=1U)return 4;
   if(k){uint32_t delta=r->cycles-previous;if(!delta||delta>=31875U)return 4;}
   previous=r->cycles;if(k>=9U)packed+=1U<<(5U*pair);
  }
  h->pair_counts=packed;
  uint32_t a=c->blob.samples[pc_advance(first,7)].cycles,b=c->blob.samples[pc_advance(first,8)].cycles;
  h->center=a+(b-a)/2U;return 1;
 }return 2;
}
static inline void pc_push(pc_capture*c,const pc_sample*s,uint32_t now,uint8_t active,uint8_t eligible,uint32_t magnitude){
 if(c->frozen||(!active&&!c->running))return;
 /* Check before appending: the oldest source row remains available at2ms. */
 if(!c->triggered&&__atomic_load_n(&c->observer_requested,__ATOMIC_ACQUIRE)){
  uint32_t result=pc_match_source(c);if(result==2)c->blob.header.trigger_slot=UINT16_MAX;
  c->triggered=1;pc_freeze(c,now,PC_OBSERVER|(result==1?PC_EXACT:PC_GAP)|(result<<8));return;
 }
 if(c->count&&(memcmp(c->blob.header.offset,s->offset,sizeof(s->offset))||c->blob.header.arr!=s->arr)){
  if(c->triggered){pc_freeze(c,now,PC_PEAK|PC_SHORT);return;}
  c->write=c->count=0;
 }
 if(active)c->running=1;
 unsigned slot=c->write;pc_raw*r=&c->blob.samples[slot];
 r->cycles=s->cycles;
 r->packed[0]=(uint8_t)s->raw[0];r->packed[1]=(uint8_t)((s->raw[0]>>8)|(s->raw[1]<<4));r->packed[2]=(uint8_t)(s->raw[1]>>4);
 uint64_t compares=0;unsigned overflow=s->raw[0]>4095U||s->raw[1]>4095U||s->bus_v>511U||s->pair>2U;
 for(unsigned i=0;i<4;++i){compares|=(uint64_t)(s->active_ccr[i]&8191U)<<(13U*i);overflow|=s->active_ccr[i]>8191U;}
 for(unsigned i=0;i<7;++i)r->packed[3U+i]=(uint8_t)(compares>>(8U*i));
 const unsigned f=s->flags;
 unsigned quality=(f&64U?1U:0U)|((f&(128U|4096U))?2U:0U)|
   ((f&(16U|256U|8192U))||!(f&8U)?4U:0U)|((f&2048U)?8U:0U)|((f&1024U)||overflow?16U:0U);
 r->meta=(uint16_t)((s->bus_v&511U)|((s->pair&3U)<<9)|(quality<<11));
 memcpy(c->blob.header.offset,s->offset,sizeof(s->offset));c->blob.header.arr=s->arr;
 ++c->total;c->write=(uint16_t)pc_next(slot);if(c->count<60U)++c->count;
 if(c->triggered){if(++c->after>=PC_POST){pc_freeze(c,now,PC_PEAK);return;}}
 else if(active&&eligible&&magnitude>=PC_THRESHOLD){c->triggered=1;c->blob.header.trigger_slot=(uint16_t)slot;c->after=0;}
 if(!active)pc_freeze(c,now,c->triggered?(PC_PEAK|PC_SHORT):PC_NO_PEAK);
}
static inline uint32_t pc_crc(const uint8_t*bytes){
 uint32_t crc=0xffffffffUL;for(unsigned i=0;i<1024;++i){crc^=i>=60&&i<64?0:bytes[i];
  for(unsigned j=0;j<8;++j)crc=(crc>>1)^((crc&1)?0x82f63b78UL:0);
 }return crc^0xffffffffUL;
}
#endif
