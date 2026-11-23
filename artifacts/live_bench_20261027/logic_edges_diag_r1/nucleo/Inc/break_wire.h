#ifndef MIC_BREAK_WIRE_H
#define MIC_BREAK_WIRE_H
#include "uart_v3_transport.h"

enum { BW_VERSION=0xD1, BW_BYTES=92, BW_CHUNK=24, BW_PAGES=4, BW_TIMEOUT_MS=2000 };
#define BW_NUCLEO_BUILD 2026102793UL

typedef struct {
  uint8_t data[BW_BYTES];
  uint8_t mask;
  uint32_t crc;
  uint32_t started_ms;
} bw_stage;
enum bw_reject_reason {
  BW_REJECT_NONE=0, BW_REJECT_FRAME_CRC=1, BW_REJECT_HEADER=2,
  BW_REJECT_PAGE_LAYOUT=3, BW_REJECT_PEER_BUILD=4, BW_REJECT_NOT_FRESH_OFF=5,
  BW_REJECT_RESERVED=6, BW_REJECT_PADDING=7, BW_REJECT_DUPLICATE=8,
  BW_REJECT_RECORD_CRC=9, BW_REJECT_RECORD_ABI=10, BW_REJECT_WINDOW_KIND=11
};
typedef struct {
  bool valid;
  uint8_t reason;
  uint32_t now_ms, peer_build, good_pages_before;
  bool fresh_off;
  uint8_t bp_status, pwm_enabled;
  uint32_t rsp_age_ms;
  uint8_t packet[UV3_FRAME];
} bw_first_reject;

typedef struct {
  bw_stage stage[2];
  uint8_t data[2][BW_BYTES];
  uint32_t received_ms[2];
  bool complete[2];
  uint32_t good_pages;
  uint32_t bad_pages;
  bw_first_reject first_reject;
} bw_receiver;

static inline uint32_t bw_u32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1]<<8) | ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static inline void bw_put32(uint8_t *p, uint32_t v) {
  for (unsigned i=0;i<4;++i) p[i]=(uint8_t)(v>>(8*i));
}
static inline void bw_increment(uint32_t *v) { if (*v!=UINT32_MAX) ++*v; }
/* Bounded observation only: neither ACK nor control/watchdog state changes. */
static inline bool bw_note_reject(bw_receiver *rx, unsigned reason,
    const uint8_t *packet, uint32_t peer_build, bool fresh_off, uint32_t now_ms) {
  bw_increment(&rx->bad_pages);
  if (!rx->first_reject.valid) {
    rx->first_reject.reason=(uint8_t)reason;
    rx->first_reject.now_ms=now_ms;
    rx->first_reject.peer_build=peer_build;
    rx->first_reject.good_pages_before=rx->good_pages;
    rx->first_reject.fresh_off=fresh_off;
    memcpy(rx->first_reject.packet,packet,UV3_FRAME);
    rx->first_reject.valid=true;
  }
  return false;
}

static inline void bw_reset(bw_receiver *rx) { memset(rx,0,sizeof(*rx)); }
static inline bool bw_peer_reset_required(uint32_t old_build, uint32_t new_build,
                                          uint16_t old_good, uint16_t new_good, uint32_t old_age_ms) {
  /* Nucleo's good counter saturates; a decrease cannot be a natural wrap. */
  return old_build!=new_build || new_good<old_good || old_age_ms>300U;
}

static inline bool bw_record_valid(const uint8_t *record) {
  bool empty=true;
  for (unsigned i=0;i<BW_BYTES;++i) if (record[i]) empty=false;
  if (empty) return true;
  return bw_u32(record)==UINT32_C(0x314b5242) && bw_u32(record+4)==2U &&
      bw_u32(record+8)==BW_BYTES && (bw_u32(record+16)&((1U<<7)|(1U<<8)))!=0 &&
      bw_u32(record+52)<=1U && bw_u32(record+88)<=1U;
}

static inline void bw_packet(uint8_t *packet, const uint8_t *record, unsigned kind, unsigned page) {
  memset(packet,0,UV3_FRAME);
  if (kind>1 || page>=BW_PAGES) return;
  packet[0]=0x55; packet[1]=0xaa; packet[2]=BW_VERSION;
  packet[3]=(uint8_t)kind; packet[4]=(uint8_t)page; packet[5]=BW_PAGES;
  bw_put32(packet+6,BW_NUCLEO_BUILD);
  bw_put32(packet+10,uv3_crc32c(record,BW_BYTES));
  unsigned offset=page*BW_CHUNK;
  unsigned length=BW_BYTES-offset;
  if (length>BW_CHUNK) length=BW_CHUNK;
  memcpy(packet+14,record+offset,length);
  uv3_seal(packet);
}

/* Does not touch the control ACK, safety state, or control watchdog timestamp. */
static inline bool bw_receive(bw_receiver *rx, const uint8_t *packet,
                              uint32_t peer_build, bool peer_fresh_off, uint32_t now_ms) {
  unsigned kind=packet[3], page=packet[4];
  unsigned reason=BW_REJECT_NONE;
  if (packet[0]!=0x55 || packet[1]!=0xaa || packet[2]!=BW_VERSION) reason=BW_REJECT_HEADER;
  else if (!uv3_crc_ok(packet)) reason=BW_REJECT_FRAME_CRC;
  else if (kind>1 || page>=BW_PAGES || packet[5]!=BW_PAGES) reason=BW_REJECT_PAGE_LAYOUT;
  else if (peer_build!=BW_NUCLEO_BUILD || bw_u32(packet+6)!=peer_build) reason=BW_REJECT_PEER_BUILD;
  else if (!peer_fresh_off) reason=BW_REJECT_NOT_FRESH_OFF;
  else if (packet[38]!=0) reason=BW_REJECT_RESERVED;
  if (reason!=BW_REJECT_NONE) return bw_note_reject(rx,reason,packet,peer_build,peer_fresh_off,now_ms);
  unsigned offset=page*BW_CHUNK, length=BW_BYTES-offset;
  if (length>BW_CHUNK) length=BW_CHUNK;
  for (unsigned i=length;i<BW_CHUNK;++i) if (packet[14+i]!=0) {
    return bw_note_reject(rx,BW_REJECT_PADDING,packet,peer_build,peer_fresh_off,now_ms);
  }
  bw_stage *stage=&rx->stage[kind];
  uint32_t crc=bw_u32(packet+10);
  if (!stage->mask || stage->crc!=crc || (uint32_t)(now_ms-stage->started_ms)>BW_TIMEOUT_MS) {
    memset(stage,0,sizeof(*stage)); stage->crc=crc; stage->started_ms=now_ms;
  }
  if ((stage->mask&(1U<<page)) && memcmp(stage->data+offset,packet+14,length)!=0) {
    stage->mask=0;
    return bw_note_reject(rx,BW_REJECT_DUPLICATE,packet,peer_build,peer_fresh_off,now_ms);
  }
  memcpy(stage->data+offset,packet+14,length);
  stage->mask|=(uint8_t)(1U<<page);
  bw_increment(&rx->good_pages);
  if (stage->mask==((1U<<BW_PAGES)-1U)) {
    reason=BW_REJECT_NONE;
    if (uv3_crc32c(stage->data,BW_BYTES)!=crc) reason=BW_REJECT_RECORD_CRC;
    else if (!bw_record_valid(stage->data)) reason=BW_REJECT_RECORD_ABI;
    else if (kind==1 && bw_u32(stage->data)!=0 && bw_u32(stage->data+88)!=1) reason=BW_REJECT_WINDOW_KIND;
    if (reason!=BW_REJECT_NONE) {
      stage->mask=0; return bw_note_reject(rx,reason,packet,peer_build,peer_fresh_off,now_ms);
    }
    memcpy(rx->data[kind],stage->data,BW_BYTES);
    rx->complete[kind]=true; rx->received_ms[kind]=now_ms; stage->mask=0;
  }
  return true;
}
#endif
