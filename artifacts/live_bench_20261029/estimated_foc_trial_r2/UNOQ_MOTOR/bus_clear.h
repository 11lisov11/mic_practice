#ifndef MIC_BUS_CLEAR_H
#define MIC_BUS_CLEAR_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
/* Single-controller bus only. All callbacks release HIGH through open drain.
   One nonblocking step per poll; no IRQ masks, waits, START or register writes.
   SCL LOW is never "repaired" by forcing it HIGH. */
enum { BC_NONE=0, BC_RELEASED=1, BC_CLEARED=2, BC_SDA_LOW=3,
       BC_SCL_LOW=4, BC_TIMEOUT=5, BC_CANCELLED=6 };
enum { BC_CHECK=1, BC_LOW, BC_RISE, BC_HIGH, BC_STOP_CLOCK_LOW,
       BC_STOP_DATA_LOW, BC_STOP_RISE, BC_STOP_HIGH, BC_VERIFY };
typedef struct {
  void *ctx;
  uint8_t (*lines)(void*);
  void (*enter)(void*);
  void (*scl_low)(void*,bool);
  void (*sda_low)(void*,bool);
  void (*leave)(void*);
} bc_io;
typedef struct {
  uint32_t begin,phase,wait_since,duration_us;
  uint8_t state,result,pulses,before,released,after;
  bool attempted,active;
} bc_state;
static inline void bc_end(bc_state*b,bc_io*i,uint32_t now,uint32_t hz,uint8_t result){
  i->leave(i->ctx);b->after=i->lines(i->ctx);b->result=result;
  b->duration_us=(now-b->begin)/(hz/1000000U);b->active=false;b->state=0;
}
static inline void bc_begin(bc_state*b,bc_io*i,uint32_t now){
  if(b->attempted)return;
  b->attempted=b->active=true;b->begin=b->phase=b->wait_since=now;
  b->before=i->lines(i->ctx);i->enter(i->ctx);b->released=i->lines(i->ctx);b->state=BC_CHECK;
}
static inline void bc_poll(bc_state*b,bc_io*i,uint32_t now,uint32_t hz,bool allowed){
  if(!b->active)return;
  if(!allowed||hz<1000000U){bc_end(b,i,now,hz>=1000000U?hz:1000000U,BC_CANCELLED);return;}
  uint32_t tick=hz/1000000U;
  if((uint32_t)(now-b->begin)>=20000U*tick){bc_end(b,i,now,hz,BC_TIMEOUT);return;}
  uint8_t lines=i->lines(i->ctx);
  uint32_t dt=now-b->phase;
  switch(b->state){
  case BC_CHECK:
    if(!(lines&1U)){
      if((uint32_t)(now-b->wait_since)>=500U*tick)bc_end(b,i,now,hz,BC_SCL_LOW);
      else b->phase=now;
      return;
    }
    if(dt<5U*tick)return;
    if(lines==3U){bc_end(b,i,now,hz,BC_RELEASED);return;}
    i->scl_low(i->ctx,true);b->phase=now;b->state=BC_LOW;return;
  case BC_LOW:
    if(dt<5U*tick)return;
    i->scl_low(i->ctx,false);b->phase=b->wait_since=now;b->state=BC_RISE;return;
  case BC_RISE: case BC_STOP_RISE:
    if(!(lines&1U)){
      if((uint32_t)(now-b->wait_since)>=500U*tick)bc_end(b,i,now,hz,BC_SCL_LOW);
      return;
    }
    b->phase=now;
    if(b->state==BC_RISE){++b->pulses;b->state=BC_HIGH;}else b->state=BC_STOP_HIGH;
    return;
  case BC_HIGH:
    if(!(lines&1U)){bc_end(b,i,now,hz,BC_SCL_LOW);return;}
    if(dt<5U*tick)return;
    /* A data bit of 1 is not proof that the target completed its byte.
       Always finish all nine clocks with SDA released (including NACK). */
    if(b->pulses>=9U){
      if(lines&2U){i->scl_low(i->ctx,true);b->phase=now;b->state=BC_STOP_CLOCK_LOW;return;}
      bc_end(b,i,now,hz,BC_SDA_LOW);return;
    }
    i->scl_low(i->ctx,true);b->phase=now;b->state=BC_LOW;return;
  case BC_STOP_CLOCK_LOW:
    if(dt<5U*tick)return;
    i->sda_low(i->ctx,true);b->phase=now;b->state=BC_STOP_DATA_LOW;return;
  case BC_STOP_DATA_LOW:
    if(dt<5U*tick)return;
    i->scl_low(i->ctx,false);b->phase=b->wait_since=now;b->state=BC_STOP_RISE;return;
  case BC_STOP_HIGH:
    if(!(lines&1U)){bc_end(b,i,now,hz,BC_SCL_LOW);return;}
    if(dt<5U*tick)return;
    i->sda_low(i->ctx,false);b->phase=now;b->state=BC_VERIFY;return;
  case BC_VERIFY:
    if(dt<5U*tick)return;
    bc_end(b,i,now,hz,lines==3U?BC_CLEARED:!(lines&1U)?BC_SCL_LOW:BC_SDA_LOW);return;
  default:bc_end(b,i,now,hz,BC_CANCELLED);return;
  }
}
#endif
