#ifndef MIC_BKIN_WAVE_WIRE_H
#define MIC_BKIN_WAVE_WIRE_H
#include "break_wire.h"

enum { BKW_VERSION=0xD2, BKW_RECORD_BYTES=160, BKW_CHUNK=24, BKW_PAGES=7, BKW_TIMEOUT_MS=5000 };
#define BKW_RECORD_MAGIC UINT32_C(0x314e4b42)

typedef struct {
  uint8_t data[BKW_RECORD_BYTES];
  uint8_t mask;
  uint32_t crc;
  uint32_t started_ms;
  uint32_t received_ms;
  uint32_t good_pages;
  uint32_t bad_pages;
  bool complete;
} bkw_receiver;

static inline bool bkw_receive(bkw_receiver *rx, const uint8_t *packet,
    uint32_t peer_build, bool peer_fresh_off, uint32_t now_ms) {
  if (rx->complete) return true; /* immutable first BKIN trace per boot */
  unsigned page=packet[3];
  if (packet[0]!=0x55 || packet[1]!=0xaa || packet[2]!=BKW_VERSION ||
      !uv3_crc_ok(packet) || page>=BKW_PAGES || packet[4]!=BKW_PAGES || packet[5]!=0 ||
      bw_u32(packet+6)!=BW_NUCLEO_BUILD || peer_build!=BW_NUCLEO_BUILD ||
      !peer_fresh_off || packet[38]!=0) { bw_increment(&rx->bad_pages); return false; }
  const unsigned offset=page*BKW_CHUNK;
  unsigned length=BKW_RECORD_BYTES-offset;
  if (length>BKW_CHUNK) length=BKW_CHUNK;
  for (unsigned i=length;i<BKW_CHUNK;++i) if (packet[14+i]!=0) {
    bw_increment(&rx->bad_pages); return false;
  }
  const uint32_t crc=bw_u32(packet+10);
  if (!rx->mask || rx->crc!=crc || (uint32_t)(now_ms-rx->started_ms)>BKW_TIMEOUT_MS) {
    memset(rx->data,0,sizeof(rx->data)); rx->mask=0; rx->crc=crc; rx->started_ms=now_ms;
  }
  const uint8_t bit=(uint8_t)(1U<<page);
  if ((rx->mask&bit) && memcmp(rx->data+offset,packet+14,length)!=0) {
    rx->mask=0; bw_increment(&rx->bad_pages); return false;
  }
  memcpy(rx->data+offset,packet+14,length); rx->mask|=bit; bw_increment(&rx->good_pages);
  if (rx->mask==(uint8_t)((1U<<BKW_PAGES)-1U)) {
    if (uv3_crc32c(rx->data,BKW_RECORD_BYTES)!=rx->crc ||
        bw_u32(rx->data)!=BKW_RECORD_MAGIC || bw_u32(rx->data+4)!=2U ||
        bw_u32(rx->data+8)!=BKW_RECORD_BYTES || bw_u32(rx->data+16)!=1000U ||
        bw_u32(rx->data+20)>1024U || bw_u32(rx->data+24)>1024U ||
        !(bw_u32(rx->data+28)&0x10U) || (bw_u32(rx->data+28)&~0x1FU) ||
        bw_u32(rx->data+20)!=((bw_u32(rx->data+28)&0x08U)?0U:
          ((bw_u32(rx->data+28)&0x02U)?1024U:1024U-bw_u32(rx->data+24)))) { rx->mask=0; bw_increment(&rx->bad_pages); return false; }
    rx->received_ms=now_ms; rx->complete=true; rx->mask=0;
  }
  return true;
}
#endif
