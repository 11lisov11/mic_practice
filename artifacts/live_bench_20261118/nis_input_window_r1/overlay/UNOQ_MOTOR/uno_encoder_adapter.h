#pragma once
#include "encoder_wire.h"
#include "as5600_teacher.h"
static ew_receiver g_remote_encoder={};
static As5600Sample remote_encoder_snapshot(uint32_t now,bool peer_fresh){
  As5600Sample s{};
  uint32_t age=ew_age(&g_remote_encoder,now);
  s.timestamp_ms=now-(age==UINT32_MAX?1000U:age);
  s.diag_mode=6;s.diag_epoch=1;
  if(!g_remote_encoder.seen){s.io_error=-110;s.init_error=-1;return s;}
  const uint8_t *p=g_remote_encoder.frame;
  const bool fresh=peer_fresh&&age<EW_TTL_MS;
  s.bus_ok=fresh&&(p[3]&1U);s.angle_ok=fresh&&(p[3]&2U);s.speed_ok=fresh&&(p[3]&4U);
  s.raw=ew_u16(p+14);s.status=p[12];s.rpm=s.speed_ok?(float)(int16_t)ew_u16(p+16):0;
  s.reads=ew_u32(p+18);s.errors=ew_u32(p+22);
  s.io_error=s.bus_ok?0:-5;s.init_error=(p[3]&8U)?0:-1;
  s.diag_cause=p[5];s.diag_stage=p[13];s.diag_isr=ew_u32(p+30);
  s.diag_last_isr=s.diag_isr;s.diag_us=ew_u16(p+34);
  s.diag_timeout_count=ew_u16(p+26);s.diag_controller_resets=ew_u16(p+28);
  s.diag_cfg_match=(p[3]&8U)?1:0; // Format2: valid parked engine may have PE0.
  s.scl_level=p[36]&1U;s.sda_level=(p[36]>>1)&1U;
  return s;
}
