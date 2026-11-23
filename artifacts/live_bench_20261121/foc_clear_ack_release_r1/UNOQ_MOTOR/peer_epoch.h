#ifndef MIC_I2C_PEER_EPOCH_H
#define MIC_I2C_PEER_EPOCH_H
#include "fault_wire.h"
#include "release_wire.h"
#include "wire_capture.h"
typedef struct {
  fc_receiver fault;
  pr_receiver release;
  wc_receiver wire;
  uint8_t clear[UV3_FRAME];bool clear_seen;
} pe_records;
typedef struct {pe_records previous;uint32_t epoch,previous_epoch;bool previous_valid;} pe_history;
static inline bool pe_nonempty(const pe_records*r){
  return r->fault.slot[0].valid||r->fault.slot[1].valid||r->release.slot[0].valid||
    r->release.slot[1].valid||r->wire.valid||r->clear_seen;
}
static inline void pe_reset(pe_history*h,pe_records*r){
  if(pe_nonempty(r)){h->previous=*r;h->previous_epoch=h->epoch;h->previous_valid=true;}
  memset(r,0,sizeof(*r));++h->epoch;
}
#endif
