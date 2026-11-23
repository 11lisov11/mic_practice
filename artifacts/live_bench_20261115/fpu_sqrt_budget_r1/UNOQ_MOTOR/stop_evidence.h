#pragma once
#include <stdint.h>
// First local stop in this boot. Never cleared by CLEAR/STOP/later START.
struct StopEvidence {
 enum {UNKNOWN=0,PEER_GUARD=1,NORMAL_REQUEST=2,LIMIT=3};
 uint32_t ready=0,origin=0,at_ms=0,run_id=0,local_fault=0,estop=0;
 uint32_t peer_status=0,peer_fault=0,reply_ms=0,tx_ms=0,reply_age_ms=0;
 uint32_t waiting=0,waiting_seq=0,superseded=0;
 void capture(uint32_t why,uint32_t now,uint32_t id,uint32_t fault,uint32_t es,
  uint32_t ps,uint32_t pf,uint32_t rsp,uint32_t tx,uint32_t wait,uint32_t seq,uint32_t retired){
  if(ready)return;
  origin=why;at_ms=now;run_id=id;local_fault=fault;estop=es;peer_status=ps;peer_fault=pf;
  reply_ms=rsp;tx_ms=tx;reply_age_ms=now-rsp;waiting=wait;waiting_seq=seq;superseded=retired;ready=1;
 }
};
