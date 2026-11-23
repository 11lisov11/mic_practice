#ifndef MIC_UART_FAULT_WIRE_H
#define MIC_UART_FAULT_WIRE_H

#include "uart_v3_transport.h"

enum {
  UFW_VERSION = 0xD3U,
  UFW_SCHEMA = 1U,
  UFW_RECORD_BYTES = 104U,
  UFW_CHUNK = 24U,
  UFW_PAGES = 5U,
  UFW_TIMEOUT_MS = 5000U
};
#define UFW_RECORD_MAGIC UINT32_C(0x31465255)
#define UFW_NUCLEO_BUILD 2026101702UL

typedef struct {
  uint8_t data[UFW_RECORD_BYTES];
  uint8_t mask;
  uint32_t crc;
  uint32_t started_ms;
  uint32_t received_ms;
  uint32_t good_pages;
  uint32_t bad_pages;
  uint32_t peer_build;
  bool complete;
} ufw_receiver;

static inline uint32_t ufw_u32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8U) |
      ((uint32_t)p[2] << 16U) | ((uint32_t)p[3] << 24U);
}

static inline void ufw_put32(uint8_t *p, uint32_t value) {
  for (unsigned i = 0; i < 4U; ++i) p[i] = (uint8_t)(value >> (8U * i));
}

static inline void ufw_make_record(uint8_t *record, const uv3_rx *rx) {
  memset(record, 0, UFW_RECORD_BYTES);
  ufw_put32(record + 0U, UFW_RECORD_MAGIC);
  ufw_put32(record + 4U, UFW_SCHEMA);
  ufw_put32(record + 8U, rx->fault_capture_tick_ms);
  record[12] = rx->fault_capture_detail;
  record[13] = (uint8_t)rx->fault;
  record[14] = rx->fault_capture_uart_flags;
  record[15] = rx->fault_capture_ne_bytes;
  record[16] = rx->fault_capture_length;
  memcpy(record + 18U, rx->fault_capture_frame, UV3_FRAME);
  memcpy(record + 61U, rx->fault_capture_marks, UV3_FRAME);
}

static inline bool ufw_record_valid(const uint8_t *record) {
  if (ufw_u32(record + 0U) != UFW_RECORD_MAGIC ||
      ufw_u32(record + 4U) != UFW_SCHEMA || record[16] > UV3_FRAME || record[17] != 0U)
    return false;
  for (unsigned i = record[16]; i < UV3_FRAME; ++i)
    if (record[18U + i] != 0U || record[61U + i] != 0U) return false;
  return true;
}

static inline void ufw_packet(uint8_t *packet, const uint8_t *record,
                              uint32_t record_crc, unsigned page) {
  memset(packet, 0, UV3_FRAME);
  if (page >= UFW_PAGES) return;
  packet[0] = 0x55U;
  packet[1] = 0xAAU;
  packet[2] = UFW_VERSION;
  packet[3] = (uint8_t)page;
  packet[4] = UFW_PAGES;
  packet[5] = UFW_SCHEMA;
  ufw_put32(packet + 6U, UFW_NUCLEO_BUILD);
  ufw_put32(packet + 10U, record_crc);
  const unsigned offset = page * UFW_CHUNK;
  unsigned length = UFW_RECORD_BYTES - offset;
  if (length > UFW_CHUNK) length = UFW_CHUNK;
  memcpy(packet + 14U, record + offset, length);
  uv3_seal(packet);
}

/* Passive, first-record-only receiver; it cannot acknowledge or alter control state. */
static inline bool ufw_receive(ufw_receiver *rx, const uint8_t *packet,
    uint32_t peer_build, bool peer_fresh_off, uint32_t now_ms) {
  if (rx->complete) return true;
  const unsigned page = packet[3];
  if (packet[0] != 0x55U || packet[1] != 0xAAU || packet[2] != UFW_VERSION ||
      !uv3_crc_ok(packet) || page >= UFW_PAGES || packet[4] != UFW_PAGES ||
      packet[5] != UFW_SCHEMA || ufw_u32(packet + 6U) != UFW_NUCLEO_BUILD ||
      peer_build != UFW_NUCLEO_BUILD || !peer_fresh_off || packet[38] != 0U) {
    if (rx->bad_pages != UINT32_MAX) ++rx->bad_pages;
    return false;
  }
  const unsigned offset = page * UFW_CHUNK;
  unsigned length = UFW_RECORD_BYTES - offset;
  if (length > UFW_CHUNK) length = UFW_CHUNK;
  for (unsigned i = length; i < UFW_CHUNK; ++i) {
    if (packet[14U + i] != 0U) {
      if (rx->bad_pages != UINT32_MAX) ++rx->bad_pages;
      return false;
    }
  }
  const uint32_t crc = ufw_u32(packet + 10U);
  if (rx->mask == 0U || rx->crc != crc ||
      (uint32_t)(now_ms - rx->started_ms) > UFW_TIMEOUT_MS) {
    memset(rx->data, 0, sizeof(rx->data));
    rx->mask = 0U;
    rx->crc = crc;
    rx->started_ms = now_ms;
    rx->peer_build = peer_build;
  }
  const uint8_t bit = (uint8_t)(1U << page);
  if ((rx->mask & bit) && memcmp(rx->data + offset, packet + 14U, length) != 0) {
    rx->mask = 0U;
    if (rx->bad_pages != UINT32_MAX) ++rx->bad_pages;
    return false;
  }
  memcpy(rx->data + offset, packet + 14U, length);
  rx->mask |= bit;
  if (rx->good_pages != UINT32_MAX) ++rx->good_pages;
  if (rx->mask == (uint8_t)((1U << UFW_PAGES) - 1U)) {
    if (uv3_crc32c(rx->data, UFW_RECORD_BYTES) != crc || !ufw_record_valid(rx->data)) {
      rx->mask = 0U;
      if (rx->bad_pages != UINT32_MAX) ++rx->bad_pages;
      return false;
    }
    rx->received_ms = now_ms;
    rx->complete = true;
    rx->mask = 0U;
  }
  return true;
}

#endif
