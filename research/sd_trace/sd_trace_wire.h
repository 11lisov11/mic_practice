#ifndef MIC_SD_TRACE_WIRE_H
#define MIC_SD_TRACE_WIRE_H
#include "break_wire.h"

enum { SDT_VERSION=0xD2, SDT_SAMPLES=1024, SDT_HEADER=64, SDT_BYTES=320,
       SDT_CHUNK=24, SDT_PAGES=14, SDT_TIMEOUT_MS=8000 };
enum { SDT_MAGIC=0x31544453U, SDT_SCHEMA=1U };
enum { SDT_STOP=1U, SDT_BREAK=2U, SDT_RESOURCE_ERROR=3U };
enum { SDT_READY=1U, SDT_WRAPPED=2U, SDT_DMA_ERROR=4U,
       SDT_INIT_ERROR=8U, SDT_UNSTABLE_COUNT=16U };

typedef struct {
  uint8_t stage[SDT_BYTES], data[SDT_BYTES];
  uint16_t mask;
  uint32_t crc, started_ms, received_ms, good_pages, bad_pages;
  bool complete;
} sdt_receiver;

static inline void sdt_reset(sdt_receiver *rx) { memset(rx,0,sizeof(*rx)); }

static inline bool sdt_record_valid(const uint8_t *p) {
  bool empty=true;
  for (unsigned i=0;i<SDT_BYTES;++i) if (p[i]) empty=false;
  if (empty) return true;
  const uint32_t reason=bw_u32(p+16), flags=bw_u32(p+20), count=bw_u32(p+24);
  if (bw_u32(p)!=SDT_MAGIC || bw_u32(p+4)!=SDT_SCHEMA || bw_u32(p+8)!=SDT_BYTES ||
      reason<SDT_STOP || reason>SDT_RESOURCE_ERROR || (flags&~31U)!=0U ||
      count>SDT_SAMPLES || bw_u32(p+28)==0U || bw_u32(p+32)==0U ||
      bw_u32(p+36)>SDT_SAMPLES || bw_u32(p+60)!=0U) return false;
  if (reason==SDT_RESOURCE_ERROR) {
    if (flags!=SDT_INIT_ERROR || count!=0U) return false;
  } else if ((flags&SDT_READY)==0U || count==0U || (flags&SDT_INIT_ERROR)!=0U) return false;
  if (reason==SDT_BREAK && (bw_u32(p+52)&0x180U)==0U) return false;
  if ((flags&SDT_WRAPPED)!=0U && count!=SDT_SAMPLES) return false;
  for (unsigned plane=0;plane<2;++plane)
    for (unsigned i=count;i<SDT_SAMPLES;++i)
      if ((p[SDT_HEADER+plane*(SDT_SAMPLES/8)+i/8]>>(i%8))&1U) return false;
  return true;
}

static inline void sdt_packet(uint8_t *packet,const uint8_t *record,unsigned page) {
  memset(packet,0,UV3_FRAME);
  if (page>=SDT_PAGES) return;
  packet[0]=0x55;packet[1]=0xaa;packet[2]=SDT_VERSION;
  packet[4]=(uint8_t)page;packet[5]=SDT_PAGES;
  bw_put32(packet+6,BW_NUCLEO_BUILD);
  bw_put32(packet+10,uv3_crc32c(record,SDT_BYTES));
  const unsigned offset=page*SDT_CHUNK;
  const unsigned length=SDT_BYTES-offset<SDT_CHUNK?SDT_BYTES-offset:SDT_CHUNK;
  memcpy(packet+14,record+offset,length);uv3_seal(packet);
}

/* This observer cannot acknowledge commands, advance control counters, clear a
   fault, refresh a watchdog, or operate outputs. Publication is all-or-nothing. */
static inline bool sdt_receive(sdt_receiver *rx,const uint8_t *p,
                              uint32_t peer_build,bool fresh_off,uint32_t now) {
  const unsigned page=p[4];
  if (p[0]!=0x55 || p[1]!=0xaa || p[2]!=SDT_VERSION || !uv3_crc_ok(p) ||
      p[3]!=0 || page>=SDT_PAGES || p[5]!=SDT_PAGES ||
      peer_build!=BW_NUCLEO_BUILD || bw_u32(p+6)!=peer_build || !fresh_off || p[38]!=0) {
    bw_increment(&rx->bad_pages);return false;
  }
  const unsigned offset=page*SDT_CHUNK;
  const unsigned length=SDT_BYTES-offset<SDT_CHUNK?SDT_BYTES-offset:SDT_CHUNK;
  for (unsigned i=length;i<SDT_CHUNK;++i) if (p[14+i]!=0) {
    bw_increment(&rx->bad_pages);return false;
  }
  const uint32_t crc=bw_u32(p+10);
  if (!rx->mask || rx->crc!=crc || (uint32_t)(now-rx->started_ms)>SDT_TIMEOUT_MS) {
    rx->mask=0;rx->crc=crc;rx->started_ms=now;
  }
  if ((rx->mask&(1U<<page)) && memcmp(rx->stage+offset,p+14,length)!=0) {
    rx->mask=0;bw_increment(&rx->bad_pages);return false;
  }
  memcpy(rx->stage+offset,p+14,length);rx->mask|=(uint16_t)(1U<<page);
  bw_increment(&rx->good_pages);
  if (rx->mask==((1U<<SDT_PAGES)-1U)) {
    rx->mask=0;
    if (uv3_crc32c(rx->stage,SDT_BYTES)!=crc || !sdt_record_valid(rx->stage)) {
      bw_increment(&rx->bad_pages);return false;
    }
    memcpy(rx->data,rx->stage,SDT_BYTES);rx->received_ms=now;rx->complete=true;
  }
  return true;
}
#endif
