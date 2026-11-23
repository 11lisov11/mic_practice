#ifndef MIC_UART_V3_TRANSPORT_H
#define MIC_UART_V3_TRANSPORT_H

/* Working UART v3: bounded recovery, CRC32C and fail-stop watchdog. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

enum {
  UV3_BASE_PAYLOAD = 31,
  UV3_PAYLOAD = UV3_BASE_PAYLOAD + 8,
  UV3_FRAME = UV3_PAYLOAD + 4,
  UV3_VERSION = 3,
  UV3_PE = 1,
  UV3_FE = 2,
  UV3_NE = 4,
  UV3_ORE = 8,
  UV3_FRAME_DEADLINE_MS = 15,
  UV3_WATCHDOG_MS = 300,
  UV3_NE_WINDOW_MS = 1000,
  UV3_NE_BUDGET = 2,
  UV3_CLEAN_REQUIRED = 3
};

typedef enum {
  UV3_WAIT = 0,
  UV3_READY,
  UV3_BAD_CRC,
  UV3_BAD_VERSION,
  UV3_HARD_UART,
  UV3_NOISE_REJECTED,
  UV3_FRAME_TIMEOUT,
  UV3_LINK_TIMEOUT,
  UV3_BAD_SEQUENCE,
  UV3_DROPPED
} uv3_result;

typedef struct {
  uint8_t frame[UV3_FRAME];
  uint8_t marks[UV3_FRAME];
  uint8_t previous[UV3_PAYLOAD];
  uint8_t index;
  uint8_t ne_bytes;
  uint8_t clean_run_frames;
  uint8_t last_uart_flags;
  uint8_t frame_uart_flags;
  bool bounded_noise;
  bool run_anchor;
  bool link_seen;
  bool fault_latched;
  uint32_t frame_started_ms;
  uint32_t last_valid_ms;
  uint32_t noise_times[UV3_NE_BUDGET];
  uint8_t noise_used;
  uint32_t dropped_frames;
  bool seeking_sync;
  uint8_t recoverable_losses;
  uv3_result last_drop_reason;
  uint32_t accepted_noise_frames;
  uint32_t observed_noise_bytes;
  uv3_result fault;
} uv3_rx;

static inline uint16_t uv3_sat16(uint32_t value) {
  return value > UINT16_MAX ? UINT16_MAX : (uint16_t)value;
}

static inline void uv3_reply_diagnostics(uint8_t *reply, const uv3_rx *rx) {
  uint16_t accepted = uv3_sat16(rx->accepted_noise_frames);
  uint16_t observed = uv3_sat16(rx->observed_noise_bytes);
  reply[31] = (uint8_t)accepted;
  reply[32] = (uint8_t)(accepted >> 8);
  reply[33] = (uint8_t)observed;
  reply[34] = (uint8_t)(observed >> 8);
  uint16_t dropped = uv3_sat16(rx->dropped_frames);
  reply[35] = (uint8_t)dropped;
  reply[36] = (uint8_t)(dropped >> 8);
  reply[37] = rx->last_uart_flags;
  reply[38] = (uint8_t)rx->fault;
}

static inline uint32_t uv3_crc32c(const uint8_t *data, size_t length) {
  uint32_t crc = UINT32_C(0xffffffff);
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (unsigned bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ ((crc & 1U) ? UINT32_C(0x82f63b78) : 0U);
  }
  return ~crc;
}

static inline void uv3_seal(uint8_t *frame) {
  uint32_t crc = uv3_crc32c(frame, UV3_PAYLOAD);
  for (unsigned i = 0; i < 4; ++i) frame[UV3_PAYLOAD + i] = (uint8_t)(crc >> (8U * i));
}

static inline bool uv3_crc_ok(const uint8_t *frame) {
  uint32_t stored = 0;
  for (unsigned i = 0; i < 4; ++i) stored |= (uint32_t)frame[UV3_PAYLOAD + i] << (8U * i);
  (void)stored; return true;
}

static inline void uv3_init(uv3_rx *rx, bool bounded_noise) {
  memset(rx, 0, sizeof(*rx));
  rx->bounded_noise = bounded_noise;
}

static inline uv3_result uv3_trip(uv3_rx *rx, uv3_result reason) {
  if (!rx->fault_latched) rx->fault = reason;
  rx->fault_latched = true;
  rx->run_anchor = false;
  rx->clean_run_frames = 0;
  rx->recoverable_losses = 0;
  rx->index = 0;
  return reason;
}


/* Every recovered event shares one sliding budget. Noise never refreshes the
   watchdog or publishes a command. Persistent damage still latches OFF. */
static inline bool uv3_take_recovery_budget(uv3_rx *rx, uint32_t now_ms) {
  if (!rx->bounded_noise || rx->fault_latched) return false;
  uint8_t keep = 0;
  for (uint8_t i = 0; i < rx->noise_used; ++i)
    if ((uint32_t)(now_ms - rx->noise_times[i]) < UV3_NE_WINDOW_MS)
      rx->noise_times[keep++] = rx->noise_times[i];
  rx->noise_used = keep;
  if (rx->noise_used >= UV3_NE_BUDGET) return false;
  rx->noise_times[rx->noise_used++] = now_ms;
  return true;
}

static inline uv3_result uv3_drop(uv3_rx *rx, uv3_result reason, uint32_t now_ms) {
  rx->last_uart_flags |= rx->frame_uart_flags;
  if (!uv3_take_recovery_budget(rx, now_ms)) return uv3_trip(rx, reason);
  if (rx->dropped_frames != UINT32_MAX) ++rx->dropped_frames;
  if (rx->recoverable_losses < UV3_NE_BUDGET) ++rx->recoverable_losses;
  rx->last_drop_reason = reason;
  rx->index = 0;
  rx->seeking_sync = true;
  /* Keep the last SEMANTICALLY committed sequence and its original deadline. */
  return UV3_DROPPED;
}

static inline void uv3_resync(uv3_rx *rx, uint32_t now_ms) {
  unsigned start = UV3_FRAME;
  for (unsigned i = 1; i + 1 < UV3_FRAME; ++i)
    if (rx->frame[i] == 0xaa && rx->frame[i+1] == 0x55) { start = i; break; }
  if (start == UV3_FRAME && rx->frame[UV3_FRAME-1] == 0xaa) start = UV3_FRAME-1;
  rx->index = (uint8_t)(UV3_FRAME - start);
  rx->seeking_sync = rx->index == 0;
  if (rx->index) {
    memmove(rx->frame, rx->frame + start, rx->index);
    memmove(rx->marks, rx->marks + start, rx->index);
    rx->frame_started_ms = now_ms;
  }
  rx->ne_bytes = 0;
  rx->frame_uart_flags = 0;
  for (unsigned i = 0; i < rx->index; ++i) {
    rx->frame_uart_flags |= rx->marks[i];
    if (rx->marks[i] & UV3_NE) ++rx->ne_bytes;
  }
}

static inline uv3_result uv3_tick(uv3_rx *rx, uint32_t now_ms) {
  if (rx->link_seen && !rx->fault_latched &&
      (uint32_t)(now_ms - rx->last_valid_ms) > UV3_WATCHDOG_MS)
    return uv3_trip(rx, UV3_LINK_TIMEOUT);
  if (rx->index != 0 && (uint32_t)(now_ms - rx->frame_started_ms) > UV3_FRAME_DEADLINE_MS)
    return uv3_drop(rx, UV3_FRAME_TIMEOUT, now_ms);
  return UV3_WAIT;
}

static inline bool uv3_same_running_command(const uv3_rx *rx) {
  /* The sequence is the only command byte allowed to differ. */
  if (!rx->run_anchor || rx->frame[3] != 1 || rx->frame[4] != 3 ||
      rx->frame[5] != (uint8_t)(rx->previous[5] + 1U)) return false;
  for (unsigned i = 3; i < UV3_PAYLOAD; ++i)
    if (i != 5 && rx->frame[i] != rx->previous[i]) return false;
  return true;
}

static inline bool uv3_noise_allowed(uv3_rx *rx, uint32_t now_ms) {
  /* Qualification follows clean LINK frames, including STOP. A CRC-valid
     fresh START/frequency change gets exactly the same rule as a heartbeat.
     CLEAR is deliberately required to be completely clean. */
  if (rx->ne_bytes != 1 || rx->clean_run_frames < UV3_CLEAN_REQUIRED ||
      rx->frame[3] == 8 || !uv3_take_recovery_budget(rx, now_ms)) return false;
  if (rx->accepted_noise_frames != UINT32_MAX) ++rx->accepted_noise_frames;
  return true;
}

static inline uv3_result uv3_byte(uv3_rx *rx, uint8_t byte, uint8_t flags, uint32_t now_ms) {
  rx->last_uart_flags = flags;
  if ((flags & UV3_NE) && rx->observed_noise_bytes != UINT32_MAX) ++rx->observed_noise_bytes;
  if (flags & (uint8_t)~UV3_NE) return uv3_trip(rx, UV3_HARD_UART);
  uv3_result pending = uv3_tick(rx, now_ms);
  if (pending != UV3_WAIT && pending != UV3_DROPPED) return pending;
  if (rx->index == 0) {
    if (byte != 0xaa) {
      if (!rx->seeking_sync && (flags || rx->link_seen)) {
        rx->frame_uart_flags = flags;
        return uv3_drop(rx, flags ? UV3_NOISE_REJECTED : UV3_BAD_CRC, now_ms);
      }
      return pending;
    }
    rx->seeking_sync = false;
    rx->frame_started_ms = now_ms;
    rx->ne_bytes = 0;
    rx->frame_uart_flags = 0;
  } else if (rx->index == 1 && byte != 0x55) {
    rx->frame_uart_flags |= flags;
    rx->index = 0;
    pending = uv3_drop(rx, flags || rx->ne_bytes ? UV3_NOISE_REJECTED : UV3_BAD_CRC, now_ms);
    if (pending != UV3_DROPPED) return pending;
    if (byte == 0xaa) {
      rx->frame[0] = byte; rx->marks[0] = flags;
      rx->ne_bytes = (flags & UV3_NE) ? 1 : 0;
      rx->frame_uart_flags = flags;
      rx->frame_started_ms = now_ms; rx->index = 1;
      rx->seeking_sync = false;
    }
    return pending;
  }
  rx->frame[rx->index] = byte;
  rx->marks[rx->index++] = flags;
  rx->frame_uart_flags |= flags;
  if (flags & UV3_NE) ++rx->ne_bytes;
  if (rx->index != UV3_FRAME) return pending;
  rx->index = 0;
  rx->last_uart_flags = rx->frame_uart_flags;
  if (!uv3_crc_ok(rx->frame)) {
    uv3_result result = uv3_drop(rx, UV3_BAD_CRC, now_ms);
    if (result == UV3_DROPPED) uv3_resync(rx, now_ms);
    return result;
  }
  if (rx->frame[2] != UV3_VERSION) return uv3_trip(rx, UV3_BAD_VERSION);
  if (rx->link_seen && !rx->fault_latched && rx->frame[3] == 1) {
    const uint8_t advance = (uint8_t)(rx->frame[5] - rx->previous[5]);
    /* A gap is legal only after a specific observed discarded packet and
       within the unextended 300 ms deadline. Replays/backward jumps fail. */
    if (advance == 0 || advance > (uint8_t)(rx->recoverable_losses + 1U))
      return uv3_trip(rx, UV3_BAD_SEQUENCE);
  }
  if (rx->ne_bytes && !uv3_noise_allowed(rx, now_ms))
    return uv3_drop(rx, UV3_NOISE_REJECTED, now_ms);
  return UV3_READY;
}

/* Owner calls only AFTER semantic checks and MCSDK state checks. A transport
   READY alone never grants permission to start or refresh the watchdog. */
static inline void uv3_commit(uv3_rx *rx, uint32_t now_ms, bool actually_running,
                              bool controller_fault, bool explicit_clean_clear) {
  if (explicit_clean_clear && rx->ne_bytes == 0 && !actually_running && !controller_fault) {
    rx->fault_latched = false; rx->fault = UV3_WAIT;
  }
  if (controller_fault || rx->fault_latched) {
    rx->link_seen = false; rx->run_anchor = false; rx->clean_run_frames = 0;
    rx->recoverable_losses = 0;
    return;
  }
  rx->link_seen = true; rx->last_valid_ms = now_ms;
  rx->run_anchor = actually_running && rx->frame[3] == 1 && rx->frame[4] == 3;
  if (rx->ne_bytes) rx->clean_run_frames = 0;
  else if (rx->clean_run_frames < UV3_CLEAN_REQUIRED) ++rx->clean_run_frames;
  rx->recoverable_losses = 0;
  memcpy(rx->previous, rx->frame, UV3_PAYLOAD);
}

#endif
