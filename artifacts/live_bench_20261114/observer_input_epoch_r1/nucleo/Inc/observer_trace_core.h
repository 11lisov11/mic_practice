#ifndef MIC_OBSERVER_TRACE_CORE_H
#define MIC_OBSERVER_TRACE_CORE_H
#include <stdint.h>
#include <string.h>
#include <math.h>
enum {OD_CAPACITY=16,OD_STRIDE=334,OD_BYTES=1696,
 OD_NOT_RUNNING=1,OD_PROFILE=2,OD_WARMUP=4,OD_FAULT=8,OD_FLUX=16,OD_NIS=32,OD_NONFINITE=64};
typedef struct {
 uint32_t cycles,steps,reasons,control_sequence,control_adc_cycles,observer_sequence,observer_adc_cycles,bin_cycles;
 float rpm,flux_alpha,flux_beta,nis,id,iq,id_ref,iq_ref,reference_hz,ia,ib,va,vb,dt;
 uint32_t observer_fault,published;
} od_sample;
typedef struct {
 uint32_t magic,schema,firmware,sample_bytes,capacity,count,oldest,stride;
 uint32_t total,valid,invalid,first_loss_present,first_loss_step,flags,control_fault,crc;
} od_header;
typedef struct {od_header header;od_sample sample[OD_CAPACITY],first_loss;} od_blob;
typedef struct {od_blob blob;od_sample latest;uint32_t write,last_saved_step;uint8_t frozen,sealed,seen_valid;} od_capture;
typedef char od_sample_96[(sizeof(od_sample)==96)?1:-1];
typedef char od_blob_1696[(sizeof(od_blob)==OD_BYTES)?1:-1];
static inline uint32_t od_reasons(int running,int profile,uint32_t steps,int fault,float flux,float target,float nis){
 uint32_t r=0;
 if(!running)r|=OD_NOT_RUNNING;
 if(!profile)r|=OD_PROFILE;
 if(steps<500U)r|=OD_WARMUP;
 if(fault)r|=OD_FAULT;
 if(!(flux>target*.5f))r|=OD_FLUX;
 if(!(nis<25.f))r|=OD_NIS;
 if(!isfinite(flux)||!isfinite(nis))r|=OD_NONFINITE;
 return r;
}
static inline void od_begin(od_capture*c,uint32_t fw){
 if(c->frozen)return; /* First completed record survives STOP/CLEAR/later START. */
 memset(c,0,sizeof(*c));c->blob.header.firmware=fw;
}
static inline void od_store(od_capture*c,const od_sample*r){
 c->blob.sample[c->write]=*r;c->write=(c->write+1U)%OD_CAPACITY;
 if(c->blob.header.count<OD_CAPACITY)++c->blob.header.count;
 c->last_saved_step=r->steps;
}
static inline void od_push(od_capture*c,const od_sample*r){
 if(c->frozen)return;
 c->latest=*r;++c->blob.header.total;
 if(!r->reasons){++c->blob.header.valid;c->seen_valid=1;}
 else{
  ++c->blob.header.invalid;
  if(c->seen_valid&&!c->blob.header.first_loss_present){
   c->blob.first_loss=*r;c->blob.header.first_loss_present=1;c->blob.header.first_loss_step=r->steps;
  }
 }
 if(c->blob.header.count==0U||(uint32_t)(r->steps-c->last_saved_step)>=OD_STRIDE)od_store(c,r);
}
static inline void od_freeze(od_capture*c,uint32_t fault){
 if(c->frozen||!c->blob.header.total)return;
 if(c->latest.steps!=c->last_saved_step)od_store(c,&c->latest);
 od_header*h=&c->blob.header;h->magic=0x3144534fU;h->schema=1;h->sample_bytes=sizeof(od_sample);
 h->capacity=OD_CAPACITY;h->oldest=h->count==OD_CAPACITY?c->write:0U;h->stride=OD_STRIDE;
 h->flags=1U|(fault?2U:0U);h->control_fault=fault;h->crc=0;c->frozen=1;
}
#endif
