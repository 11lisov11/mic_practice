#ifndef MIC_ENCODER_CORE_H
#define MIC_ENCODER_CORE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
enum { EC_NONE=0,EC_NACK=2,EC_DEADLINE=6,EC_SETUP=7,EC_BUS=8,
       EC_ARLO=9,EC_OVR=10,EC_BUSY=11,EC_SHORT=12 };
enum { EC_TXIS=2,EC_RXNE=4,EC_NACKF=16,EC_STOPF=32,EC_TC=64,
       EC_BERR=256,EC_ARLOF=512,EC_OVRF=1024,EC_BUSYF=32768 };
typedef struct {
  void *ctx;
  uint32_t (*status)(void*);
  void (*begin_write)(void*);
  void (*write)(void*,uint8_t);
  void (*begin_read)(void*);
  uint8_t (*read)(void*);
  void (*clear)(void*);
  void (*reset)(void*);
} ec_io;
typedef struct {
  uint32_t reads,errors,sample_ms,last_start_ms,begin_cycles,budget_cycles;
  uint32_t last_isr;
  uint16_t timeouts,resets,raw,duration_us;
  uint8_t state,n,bytes[3],cause,stage,status,configured;
  bool bus_ok,angle_ok,speed_ok,have_previous;
  uint16_t previous_raw;
  uint32_t previous_ms,accumulated_ms;
  int32_t accumulated_counts;
  float rpm;
} ec_state;
static inline void ec_inc32(uint32_t *n){if(*n!=UINT32_MAX)++*n;}
static inline void ec_inc16(uint16_t *n){if(*n!=UINT16_MAX)++*n;}
static inline void ec_speed_reset(ec_state *e){
  e->speed_ok=false;e->have_previous=false;e->rpm=0;
  e->accumulated_counts=0;e->accumulated_ms=0;
}
static inline void ec_track(ec_state *e,uint32_t now){
  if(!e->angle_ok){ec_speed_reset(e);return;}
  if(!e->have_previous){e->have_previous=true;e->previous_raw=e->raw;e->previous_ms=now;return;}
  uint32_t dt=now-e->previous_ms;
  int32_t delta=(int32_t)e->raw-e->previous_raw;
  e->previous_raw=e->raw;e->previous_ms=now;
  if(dt==0||dt>8||delta==2048||delta==-2048){ec_speed_reset(e);return;}
  if(delta>2048)delta-=4096;
  if(delta< -2048)delta+=4096;
  e->accumulated_counts+=delta;e->accumulated_ms+=dt;
  if(e->accumulated_ms>=20){
    float rpm=(float)e->accumulated_counts*60000.0f/(4096.0f*e->accumulated_ms);
    e->rpm+=0.25f*(rpm-e->rpm);e->speed_ok=true;
    e->accumulated_counts=0;e->accumulated_ms=0;
  }
}
static inline void ec_init(ec_state *e,uint32_t hz,bool configured){
  memset(e,0,sizeof(*e));e->budget_cycles=(hz/1000U)*3U;
  e->configured=configured?1:0;e->cause=configured?EC_NONE:EC_SETUP;
}
static inline void ec_finish(ec_state *e,ec_io *io,uint32_t ms,uint32_t cycles,
                             uint32_t hz,uint8_t cause,uint32_t isr){
  uint32_t us=(cycles-e->begin_cycles)/(hz/1000000U);
  e->duration_us=(uint16_t)(us>65535U?65535U:us);
  e->state=0;e->sample_ms=ms;e->cause=cause;e->bus_ok=cause==EC_NONE;
  if(cause){
    ec_inc32(&e->errors);e->last_isr=isr;
    if(cause==EC_DEADLINE)ec_inc16(&e->timeouts);
    io->reset(io->ctx);ec_inc16(&e->resets);
    e->raw=0;e->status=0;e->angle_ok=false;ec_speed_reset(e);
  }else{
    io->clear(io->ctx);ec_inc32(&e->reads);e->stage=0;
    e->raw=(uint16_t)(((e->bytes[1]&15U)<<8)|e->bytes[2]);e->status=e->bytes[0];
    e->angle_ok=(e->status&0x38U)==0x20U && (e->bytes[1]&0xf0U)==0;
    ec_track(e,ms);
  }
}
static inline void ec_poll(ec_state *e,ec_io *io,uint32_t ms,uint32_t cycles,uint32_t hz){
  if(!e->configured)return;
  uint32_t isr=io->status(io->ctx);
  if(!e->state){
    uint32_t interval=e->cause?20U:5U;
    if((uint32_t)(ms-e->last_start_ms)<interval)return;
    e->last_start_ms=ms;e->begin_cycles=cycles;e->stage=4;
    if(isr&EC_BUSYF){ec_finish(e,io,ms,cycles,hz,EC_BUSY,isr);return;}
    io->clear(io->ctx);memset(e->bytes,0,3);e->n=0;
    io->begin_write(io->ctx);e->state=1;return;
  }
  uint8_t cause=(isr&EC_ARLOF)?EC_ARLO:(isr&EC_NACKF)?EC_NACK:
      (isr&EC_BERR)?EC_BUS:(isr&EC_OVRF)?EC_OVR:EC_NONE;
  if(cause){ec_finish(e,io,ms,cycles,hz,cause,isr);return;}
  if((uint32_t)(cycles-e->begin_cycles)>=e->budget_cycles ||
      (uint32_t)(ms-e->last_start_ms)>=3U){
    ec_finish(e,io,ms,cycles,hz,EC_DEADLINE,isr);return;
  }
  if(e->state==1 && (isr&EC_TXIS)){
    io->write(io->ctx,0x0b);e->stage=5;e->state=2;return;
  }
  if(e->state==2 && (isr&EC_TC)){
    io->begin_read(io->ctx);e->stage=7;e->state=3;return;
  }
  if(e->state==3 && (isr&EC_RXNE)){
    e->stage=(uint8_t)(8U+e->n);e->bytes[e->n++]=io->read(io->ctx);
    if(e->n==3){e->state=4;e->stage=11;}
    return;
  }
  if(isr&EC_STOPF){
    if(e->state==4 && !(isr&EC_BUSYF))ec_finish(e,io,ms,cycles,hz,EC_NONE,isr);
    else if(e->state!=4)ec_finish(e,io,ms,cycles,hz,EC_SHORT,isr);
  }
}
#endif
