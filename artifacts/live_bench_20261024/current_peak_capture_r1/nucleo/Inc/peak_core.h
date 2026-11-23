#ifndef MIC_ADC_PEAK_CORE_H
#define MIC_ADC_PEAK_CORE_H
#include <stdint.h>
#include <string.h>
enum { PC_CAPACITY=12, PC_POST=6, PC_THRESHOLD=626, PC_BYTES=1024,
       PC_PEAK=1, PC_SHORT=2, PC_NO_PEAK=4 };
typedef struct {
  uint32_t cycles,sequence,epoch_before,epoch_after,isr1,isr2,jsqr1,jsqr2;
  uint16_t active_ccr[4],preload_ccr[4];
  uint16_t cnt,arr,cr1,raw[2],offset[4],flags,cnt_exit,reference_deci_hz,bus_v,update_cnt;
  uint8_t pair,next_pair;
  uint16_t update_cr1;
} pc_sample;
typedef struct {
  uint32_t magic;
  uint16_t schema,sample_bytes;
  uint32_t firmware,capture_id;
  uint16_t capacity,count,oldest,trigger_slot,threshold,post_target;
  uint32_t total_samples,trigger_sequence,frozen_sequence,frozen_ms,flags,cpu_hz,adc_hz,reserved,crc;
} pc_header;
typedef struct { pc_header header; pc_sample samples[PC_CAPACITY]; } pc_blob;
typedef struct {
  pc_blob blob;
  uint32_t total;
  uint16_t write,count,after;
  uint8_t running,triggered;
  volatile uint8_t frozen;
} pc_capture;
typedef char pc_sample_size_must_be_80[(sizeof(pc_sample)==80)?1:-1];
typedef char pc_header_size_must_be_64[(sizeof(pc_header)==64)?1:-1];
typedef char pc_blob_size_must_be_1024[(sizeof(pc_blob)==PC_BYTES)?1:-1];
static inline void pc_init(pc_capture *c){memset(c,0,sizeof(*c));}
static inline void pc_freeze(pc_capture *c,uint32_t now,uint32_t reason) {
  pc_header *h=&c->blob.header;
  h->magic=0x31435041UL;h->schema=1;h->sample_bytes=sizeof(pc_sample);
  h->capture_id=1;h->capacity=PC_CAPACITY;h->count=c->count;
  h->oldest=c->count==PC_CAPACITY?c->write:0;
  if(!c->triggered)h->trigger_slot=UINT16_MAX;
  h->threshold=PC_THRESHOLD;h->post_target=PC_POST;
  h->total_samples=c->total;h->frozen_sequence=c->total;h->frozen_ms=now;
  h->flags=reason;h->cpu_hz=170000000;h->adc_hz=42500000;
  c->frozen=1;
}
static inline void pc_push(pc_capture *c,const pc_sample *sample,uint32_t now,
                           uint8_t active,uint8_t eligible,uint32_t magnitude) {
  if(c->frozen)return;
  if(!active && !c->running)return;
  if(active)c->running=1;
  uint16_t slot=c->write;
  c->blob.samples[slot]=*sample;
  c->blob.samples[slot].sequence=++c->total;
  c->write=(uint16_t)((slot+1U)%PC_CAPACITY);
  if(c->count<PC_CAPACITY)++c->count;
  if(c->triggered) {
    ++c->after;
    if(c->after>=PC_POST){pc_freeze(c,now,PC_PEAK);return;}
  } else if(active && eligible && magnitude>=PC_THRESHOLD) {
    c->triggered=1;c->blob.header.trigger_slot=slot;
    c->blob.header.trigger_sequence=c->total;c->after=0;
  }
  if(!active)pc_freeze(c,now,c->triggered?(PC_PEAK|PC_SHORT):PC_NO_PEAK);
}
static inline uint32_t pc_crc(const uint8_t *bytes) {
  uint32_t crc=0xffffffffUL;
  for(unsigned i=0;i<PC_BYTES;++i) {
    uint8_t b=i>=60 && i<64?0:bytes[i];crc^=b;
    for(unsigned j=0;j<8;++j)crc=(crc>>1)^((crc&1)?0x82f63b78UL:0);
  }
  return crc^0xffffffffUL;
}
#endif
