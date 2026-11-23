#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <cfloat>
#include <algorithm>
#include "current_adc_window_plan.h"
using std::isfinite;using std::isnan;
static uint32_t rng=0x13a849f1U;
static uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static float uniform(float a,float b){return a+(b-a)*(next()>>8)*(1.f/16777216.f);}

namespace old {

/* Working UART v3: bounded recovery, CRC32C and fail-stop watchdog. */

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
  UV3_CONFIRM_MS = 100,
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

/* Frozen rejected data, never used as a control command. */
typedef struct { uint32_t meta[14]; uint8_t bytes[44], marks[44]; } uv3_reject;
typedef struct {
  /* One CRC-valid but multi-NE command may be withheld during an already
     running, qualified link. Only a subsequent CLEAN, fresh full command can
     publish control. No deadline/budget is refreshed by the withheld frame. */
  bool confirm_pending;
  uint8_t confirm_sequence, confirm_loss_base;
  uint32_t confirm_started_ms;
  uint32_t deferred_noise_frames, clean_confirmations;
  uint8_t speculative_prefix;
  uint32_t speculative_expired, observed_ms;
  bool last_reject_valid, fatal_reject_valid;
  uv3_reject last_reject, fatal_reject;
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
  return stored == uv3_crc32c(frame, UV3_PAYLOAD);
}

static inline void uv3_init(uv3_rx *rx, bool bounded_noise) {
  memset(rx, 0, sizeof(*rx));
  rx->bounded_noise = bounded_noise;
}

static inline void uv3_capture_reject(const uv3_rx *rx, uv3_reject *e, uv3_result reason) {
  memset(e,0,sizeof(*e));
  const unsigned length=rx->index<=UV3_FRAME ? (unsigned)rx->index : (unsigned)UV3_FRAME;
  const uint32_t meta[14]={rx->observed_ms,(uint32_t)reason,length,rx->speculative_prefix,
    rx->last_uart_flags,rx->link_seen ? rx->previous[5] : UINT32_MAX,
    rx->noise_used,rx->recoverable_losses,rx->dropped_frames,rx->last_valid_ms,
    rx->frame_started_ms,(rx->link_seen ? 1U : 0U)|(rx->fault_latched ? 2U : 0U),0,0};
  memcpy(e->meta,meta,sizeof(meta));
  memcpy(e->bytes,rx->frame,length);memcpy(e->marks,rx->marks,length);
  if (length==UV3_FRAME) {
    for(unsigned i=0;i<4;++i)e->meta[12]|=(uint32_t)rx->frame[UV3_PAYLOAD+i]<<(8*i);
    e->meta[13]=uv3_crc32c(rx->frame,UV3_PAYLOAD);
  }
}

static inline uv3_result uv3_trip(uv3_rx *rx, uv3_result reason) {
  if (!rx->fault_latched) {
    rx->fault=reason;
    uv3_capture_reject(rx,&rx->fatal_reject,reason);rx->fatal_reject_valid=true;
  }
  rx->speculative_prefix=0;
  rx->confirm_pending = false;
  rx->fault_latched = true;
  rx->run_anchor = false;
  rx->clean_run_frames = 0;
  rx->recoverable_losses = 0;
  rx->index = 0;
  return reason;
}


/* Every damaged/unqualified discarded packet shares one sliding budget. Noise never refreshes the
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
  if (!rx->fatal_reject_valid) {
    uv3_capture_reject(rx,&rx->last_reject,reason);rx->last_reject_valid=true;
  }
  rx->speculative_prefix=0;
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
  rx->speculative_prefix=rx->index;
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
  rx->observed_ms=now_ms;
  if (rx->link_seen && !rx->fault_latched &&
      (uint32_t)(now_ms - rx->last_valid_ms) > UV3_WATCHDOG_MS)
    return uv3_trip(rx, UV3_LINK_TIMEOUT);
  if (rx->confirm_pending &&
      (uint32_t)(now_ms-rx->confirm_started_ms)>UV3_CONFIRM_MS)
    return uv3_trip(rx, UV3_NOISE_REJECTED);
  if (rx->index != 0 && (uint32_t)(now_ms-rx->frame_started_ms)>UV3_FRAME_DEADLINE_MS) {
    if (rx->speculative_prefix==rx->index) {
      /* No NEW byte arrived: this is the already rejected packet's suffix,
       * not a second lost packet. Do not spend budget or grant a sequence gap.
       * The last committed watchdog deadline stays unchanged. */
      rx->index=0;rx->speculative_prefix=0;rx->seeking_sync=true;
      if(rx->speculative_expired!=UINT32_MAX)++rx->speculative_expired;
      return UV3_WAIT;
    }
    return uv3_drop(rx,UV3_FRAME_TIMEOUT,now_ms);
  }
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
  (void)now_ms;
  /* Full CRC, version and fresh-sequence checks already passed. A single
     hardware NE mark on that verified packet is observable metadata, not a
     damaged/lost command. Keep its counter without spending discard budget. */
  if (rx->ne_bytes != 1 || rx->clean_run_frames < UV3_CLEAN_REQUIRED ||
      rx->frame[3] == 8 || !rx->bounded_noise || rx->fault_latched) return false;
  if (rx->accepted_noise_frames != UINT32_MAX) ++rx->accepted_noise_frames;
  return true;
}

static inline uv3_result uv3_byte(uv3_rx *rx, uint8_t byte, uint8_t flags, uint32_t now_ms) {
  rx->observed_ms=now_ms;
  rx->last_uart_flags = flags;
  if ((flags & UV3_NE) && rx->observed_noise_bytes != UINT32_MAX) ++rx->observed_noise_bytes;
  if (flags & (uint8_t)~UV3_NE) return uv3_trip(rx, UV3_HARD_UART);
  uv3_result pending = uv3_tick(rx, now_ms);
  if (pending != UV3_WAIT && pending != UV3_DROPPED) return pending;
  if (rx->index == 0) {
    if (byte != 0xaa) {
      if (!rx->seeking_sync && (flags || rx->link_seen)) {
        rx->frame[0]=byte;rx->marks[0]=flags;rx->index=1;
        rx->frame_uart_flags = flags;
        return uv3_drop(rx, flags ? UV3_NOISE_REJECTED : UV3_BAD_CRC, now_ms);
      }
      return pending;
    }
    rx->speculative_prefix=0;
    rx->seeking_sync = false;
    rx->frame_started_ms = now_ms;
    rx->ne_bytes = 0;
    rx->frame_uart_flags = 0;
  } else if (rx->index == 1 && byte != 0x55) {
    rx->frame_uart_flags |= flags;
    if (rx->speculative_prefix==rx->index && byte==0xaa) {
      /* Reuse the incoming AA as a fresh header; the old retained AA was
       * already charged. There is no lost new packet here. */
      rx->frame[0]=byte;rx->marks[0]=flags;rx->index=1;rx->speculative_prefix=0;
      rx->frame_started_ms=now_ms;rx->frame_uart_flags=flags;rx->ne_bytes=!!(flags&UV3_NE);
      return pending;
    }
    rx->frame[rx->index]=byte;rx->marks[rx->index++]=flags;
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
  rx->last_uart_flags = rx->frame_uart_flags;
  if (!uv3_crc_ok(rx->frame)) {
    uv3_result result = uv3_drop(rx, UV3_BAD_CRC, now_ms);
    if (result == UV3_DROPPED) uv3_resync(rx, now_ms);
    return result;
  }
  if (rx->frame[2] != UV3_VERSION) return uv3_trip(rx, UV3_BAD_VERSION);
  if (rx->link_seen && !rx->fault_latched && rx->frame[3] == 1) {
    /* A withheld verified packet is an observed sequence, never a command.
       Anchor freshness to it so replaying that same packet cannot confirm it.
       Only genuinely observed damaged packets since that anchor grant a gap. */
    const uint8_t anchor=rx->confirm_pending ? rx->confirm_sequence : rx->previous[5];
    const uint8_t losses=rx->confirm_pending ?
        (uint8_t)(rx->recoverable_losses-rx->confirm_loss_base) : rx->recoverable_losses;
    const uint8_t advance = (uint8_t)(rx->frame[5] - anchor);
    if (advance == 0 || advance > (uint8_t)(losses + 1U))
      return uv3_trip(rx, UV3_BAD_SEQUENCE);
  }
  /* A second noisy packet never confirms the first, even with a valid CRC.
     A clean STOP/ESTOP still reaches the existing owner immediately. */
  if (rx->confirm_pending && rx->ne_bytes)
    return uv3_trip(rx,UV3_NOISE_REJECTED);
  if (rx->ne_bytes>1 && rx->bounded_noise && !rx->fault_latched &&
      rx->link_seen && rx->run_anchor && rx->clean_run_frames>=UV3_CLEAN_REQUIRED &&
      rx->frame[3]==1 && rx->frame[4]==3) {
    uv3_capture_reject(rx,&rx->last_reject,UV3_NOISE_REJECTED);
    rx->last_reject_valid=true;
    rx->confirm_pending=true;rx->confirm_sequence=rx->frame[5];
    rx->confirm_loss_base=rx->recoverable_losses;rx->confirm_started_ms=now_ms;
    if(rx->deferred_noise_frames!=UINT32_MAX)++rx->deferred_noise_frames;
    if(rx->dropped_frames!=UINT32_MAX)++rx->dropped_frames;
    rx->last_drop_reason=UV3_NOISE_REJECTED;
    rx->index=0;rx->speculative_prefix=0;
    return UV3_DROPPED;
  }
  if (rx->ne_bytes && !uv3_noise_allowed(rx, now_ms))
    return uv3_drop(rx, UV3_NOISE_REJECTED, now_ms);
  rx->index=0;rx->speculative_prefix=0;
  return UV3_READY;
}

/* Owner calls only AFTER semantic checks and MCSDK state checks. A transport
   READY alone never grants permission to start or refresh the watchdog. */
static inline void uv3_commit(uv3_rx *rx, uint32_t now_ms, bool actually_running,
                              bool controller_fault, bool explicit_clean_clear) {
  if(rx->confirm_pending && !rx->ne_bytes && !controller_fault && !rx->fault_latched &&
      rx->clean_confirmations!=UINT32_MAX)++rx->clean_confirmations;
  rx->confirm_pending=false;
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
  /* A verified/committed packet does not erase established link
     qualification just because its UART sampling carried an NE mark. */
  if (!rx->ne_bytes && rx->clean_run_frames < UV3_CLEAN_REQUIRED) ++rx->clean_run_frames;
  rx->recoverable_losses = 0;
  memcpy(rx->previous, rx->frame, UV3_PAYLOAD);
}


}
namespace candidate {

/* Working UART v3: bounded recovery, CRC32C and fail-stop watchdog. */

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
  UV3_CONFIRM_MS = 100,
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

/* Frozen rejected data, never used as a control command. */
typedef struct { uint32_t meta[14]; uint8_t bytes[44], marks[44]; } uv3_reject;
typedef struct {
  /* One CRC-valid but multi-NE command may be withheld during an already
     running, qualified link. Only a subsequent CLEAN, fresh full command can
     publish control. No deadline/budget is refreshed by the withheld frame. */
  bool confirm_pending;
  uint8_t confirm_sequence, confirm_loss_base;
  uint32_t confirm_started_ms;
  uint32_t deferred_noise_frames, clean_confirmations;
  uint8_t speculative_prefix;
  uint32_t speculative_expired, observed_ms;
  bool last_reject_valid, fatal_reject_valid;
  uv3_reject last_reject, fatal_reject;
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
  static const uint32_t table[16]={UINT32_C(0x00000000),UINT32_C(0x105ec76f),UINT32_C(0x20bd8ede),UINT32_C(0x30e349b1),UINT32_C(0x417b1dbc),UINT32_C(0x5125dad3),UINT32_C(0x61c69362),UINT32_C(0x7198540d),UINT32_C(0x82f63b78),UINT32_C(0x92a8fc17),UINT32_C(0xa24bb5a6),UINT32_C(0xb21572c9),UINT32_C(0xc38d26c4),UINT32_C(0xd3d3e1ab),UINT32_C(0xe330a81a),UINT32_C(0xf36e6f75)};
  uint32_t crc=UINT32_C(0xffffffff);
  for(size_t i=0;i<length;++i){
    crc^=data[i];
    crc=(crc>>4)^table[crc&15U];
    crc=(crc>>4)^table[crc&15U];
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
  return stored == uv3_crc32c(frame, UV3_PAYLOAD);
}

static inline void uv3_init(uv3_rx *rx, bool bounded_noise) {
  memset(rx, 0, sizeof(*rx));
  rx->bounded_noise = bounded_noise;
}

static inline void uv3_capture_reject(const uv3_rx *rx, uv3_reject *e, uv3_result reason) {
  memset(e,0,sizeof(*e));
  const unsigned length=rx->index<=UV3_FRAME ? (unsigned)rx->index : (unsigned)UV3_FRAME;
  const uint32_t meta[14]={rx->observed_ms,(uint32_t)reason,length,rx->speculative_prefix,
    rx->last_uart_flags,rx->link_seen ? rx->previous[5] : UINT32_MAX,
    rx->noise_used,rx->recoverable_losses,rx->dropped_frames,rx->last_valid_ms,
    rx->frame_started_ms,(rx->link_seen ? 1U : 0U)|(rx->fault_latched ? 2U : 0U),0,0};
  memcpy(e->meta,meta,sizeof(meta));
  memcpy(e->bytes,rx->frame,length);memcpy(e->marks,rx->marks,length);
  if (length==UV3_FRAME) {
    for(unsigned i=0;i<4;++i)e->meta[12]|=(uint32_t)rx->frame[UV3_PAYLOAD+i]<<(8*i);
    e->meta[13]=uv3_crc32c(rx->frame,UV3_PAYLOAD);
  }
}

static inline uv3_result uv3_trip(uv3_rx *rx, uv3_result reason) {
  if (!rx->fault_latched) {
    rx->fault=reason;
    uv3_capture_reject(rx,&rx->fatal_reject,reason);rx->fatal_reject_valid=true;
  }
  rx->speculative_prefix=0;
  rx->confirm_pending = false;
  rx->fault_latched = true;
  rx->run_anchor = false;
  rx->clean_run_frames = 0;
  rx->recoverable_losses = 0;
  rx->index = 0;
  return reason;
}


/* Every damaged/unqualified discarded packet shares one sliding budget. Noise never refreshes the
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
  if (!rx->fatal_reject_valid) {
    uv3_capture_reject(rx,&rx->last_reject,reason);rx->last_reject_valid=true;
  }
  rx->speculative_prefix=0;
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
  rx->speculative_prefix=rx->index;
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
  rx->observed_ms=now_ms;
  if (rx->link_seen && !rx->fault_latched &&
      (uint32_t)(now_ms - rx->last_valid_ms) > UV3_WATCHDOG_MS)
    return uv3_trip(rx, UV3_LINK_TIMEOUT);
  if (rx->confirm_pending &&
      (uint32_t)(now_ms-rx->confirm_started_ms)>UV3_CONFIRM_MS)
    return uv3_trip(rx, UV3_NOISE_REJECTED);
  if (rx->index != 0 && (uint32_t)(now_ms-rx->frame_started_ms)>UV3_FRAME_DEADLINE_MS) {
    if (rx->speculative_prefix==rx->index) {
      /* No NEW byte arrived: this is the already rejected packet's suffix,
       * not a second lost packet. Do not spend budget or grant a sequence gap.
       * The last committed watchdog deadline stays unchanged. */
      rx->index=0;rx->speculative_prefix=0;rx->seeking_sync=true;
      if(rx->speculative_expired!=UINT32_MAX)++rx->speculative_expired;
      return UV3_WAIT;
    }
    return uv3_drop(rx,UV3_FRAME_TIMEOUT,now_ms);
  }
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
  (void)now_ms;
  /* Full CRC, version and fresh-sequence checks already passed. A single
     hardware NE mark on that verified packet is observable metadata, not a
     damaged/lost command. Keep its counter without spending discard budget. */
  if (rx->ne_bytes != 1 || rx->clean_run_frames < UV3_CLEAN_REQUIRED ||
      rx->frame[3] == 8 || !rx->bounded_noise || rx->fault_latched) return false;
  if (rx->accepted_noise_frames != UINT32_MAX) ++rx->accepted_noise_frames;
  return true;
}

static inline uv3_result uv3_byte(uv3_rx *rx, uint8_t byte, uint8_t flags, uint32_t now_ms) {
  rx->observed_ms=now_ms;
  rx->last_uart_flags = flags;
  if ((flags & UV3_NE) && rx->observed_noise_bytes != UINT32_MAX) ++rx->observed_noise_bytes;
  if (flags & (uint8_t)~UV3_NE) return uv3_trip(rx, UV3_HARD_UART);
  uv3_result pending = uv3_tick(rx, now_ms);
  if (pending != UV3_WAIT && pending != UV3_DROPPED) return pending;
  if (rx->index == 0) {
    if (byte != 0xaa) {
      if (!rx->seeking_sync && (flags || rx->link_seen)) {
        rx->frame[0]=byte;rx->marks[0]=flags;rx->index=1;
        rx->frame_uart_flags = flags;
        return uv3_drop(rx, flags ? UV3_NOISE_REJECTED : UV3_BAD_CRC, now_ms);
      }
      return pending;
    }
    rx->speculative_prefix=0;
    rx->seeking_sync = false;
    rx->frame_started_ms = now_ms;
    rx->ne_bytes = 0;
    rx->frame_uart_flags = 0;
  } else if (rx->index == 1 && byte != 0x55) {
    rx->frame_uart_flags |= flags;
    if (rx->speculative_prefix==rx->index && byte==0xaa) {
      /* Reuse the incoming AA as a fresh header; the old retained AA was
       * already charged. There is no lost new packet here. */
      rx->frame[0]=byte;rx->marks[0]=flags;rx->index=1;rx->speculative_prefix=0;
      rx->frame_started_ms=now_ms;rx->frame_uart_flags=flags;rx->ne_bytes=!!(flags&UV3_NE);
      return pending;
    }
    rx->frame[rx->index]=byte;rx->marks[rx->index++]=flags;
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
  rx->last_uart_flags = rx->frame_uart_flags;
  if (!uv3_crc_ok(rx->frame)) {
    uv3_result result = uv3_drop(rx, UV3_BAD_CRC, now_ms);
    if (result == UV3_DROPPED) uv3_resync(rx, now_ms);
    return result;
  }
  if (rx->frame[2] != UV3_VERSION) return uv3_trip(rx, UV3_BAD_VERSION);
  if (rx->link_seen && !rx->fault_latched && rx->frame[3] == 1) {
    /* A withheld verified packet is an observed sequence, never a command.
       Anchor freshness to it so replaying that same packet cannot confirm it.
       Only genuinely observed damaged packets since that anchor grant a gap. */
    const uint8_t anchor=rx->confirm_pending ? rx->confirm_sequence : rx->previous[5];
    const uint8_t losses=rx->confirm_pending ?
        (uint8_t)(rx->recoverable_losses-rx->confirm_loss_base) : rx->recoverable_losses;
    const uint8_t advance = (uint8_t)(rx->frame[5] - anchor);
    if (advance == 0 || advance > (uint8_t)(losses + 1U))
      return uv3_trip(rx, UV3_BAD_SEQUENCE);
  }
  /* A second noisy packet never confirms the first, even with a valid CRC.
     A clean STOP/ESTOP still reaches the existing owner immediately. */
  if (rx->confirm_pending && rx->ne_bytes)
    return uv3_trip(rx,UV3_NOISE_REJECTED);
  if (rx->ne_bytes>1 && rx->bounded_noise && !rx->fault_latched &&
      rx->link_seen && rx->run_anchor && rx->clean_run_frames>=UV3_CLEAN_REQUIRED &&
      rx->frame[3]==1 && rx->frame[4]==3) {
    uv3_capture_reject(rx,&rx->last_reject,UV3_NOISE_REJECTED);
    rx->last_reject_valid=true;
    rx->confirm_pending=true;rx->confirm_sequence=rx->frame[5];
    rx->confirm_loss_base=rx->recoverable_losses;rx->confirm_started_ms=now_ms;
    if(rx->deferred_noise_frames!=UINT32_MAX)++rx->deferred_noise_frames;
    if(rx->dropped_frames!=UINT32_MAX)++rx->dropped_frames;
    rx->last_drop_reason=UV3_NOISE_REJECTED;
    rx->index=0;rx->speculative_prefix=0;
    return UV3_DROPPED;
  }
  if (rx->ne_bytes && !uv3_noise_allowed(rx, now_ms))
    return uv3_drop(rx, UV3_NOISE_REJECTED, now_ms);
  rx->index=0;rx->speculative_prefix=0;
  return UV3_READY;
}

/* Owner calls only AFTER semantic checks and MCSDK state checks. A transport
   READY alone never grants permission to start or refresh the watchdog. */
static inline void uv3_commit(uv3_rx *rx, uint32_t now_ms, bool actually_running,
                              bool controller_fault, bool explicit_clean_clear) {
  if(rx->confirm_pending && !rx->ne_bytes && !controller_fault && !rx->fault_latched &&
      rx->clean_confirmations!=UINT32_MAX)++rx->clean_confirmations;
  rx->confirm_pending=false;
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
  /* A verified/committed packet does not erase established link
     qualification just because its UART sampling carried an NE mark. */
  if (!rx->ne_bytes && rx->clean_run_frames < UV3_CLEAN_REQUIRED) ++rx->clean_run_frames;
  rx->recoverable_losses = 0;
  memcpy(rx->previous, rx->frame, UV3_PAYLOAD);
}


}

int main(){
 uint8_t data[8192];unsigned checked=0,bytes=0;
 for(unsigned n=0;n<100000;++n){
  unsigned len=n<8193?n:(next()%512);
  for(unsigned i=0;i<len;++i)data[i]=(uint8_t)next();
  assert(old::uv3_crc32c(data,len)==candidate::uv3_crc32c(data,len));++checked;
 }
 const uint8_t known[]="123456789";assert(candidate::uv3_crc32c(known,9)==0xe3069283U);
 for(unsigned scenario=0;scenario<1000;++scenario){
  old::uv3_rx a;candidate::uv3_rx b;old::uv3_init(&a,true);candidate::uv3_init(&b,true);
  uint32_t tick=0;
  for(unsigned frame=0;frame<16;++frame){
   uint8_t packet[old::UV3_FRAME]={0xaa,0x55,old::UV3_VERSION,0,0,0};
   packet[5]=(uint8_t)frame;
   for(unsigned i=6;i<old::UV3_PAYLOAD;++i)packet[i]=(uint8_t)next();
   old::uv3_seal(packet);assert(candidate::uv3_crc_ok(packet));
   if(scenario%4==1&&frame==5)packet[10]^=1;
   for(unsigned i=0;i<old::UV3_FRAME;++i){
    uint8_t flags=scenario%4==2&&frame==7&&i==13?old::UV3_ORE:0;
    auto x=old::uv3_byte(&a,packet[i],flags,tick);auto y=candidate::uv3_byte(&b,packet[i],flags,tick);
    assert((int)x==(int)y&&memcmp(&a,&b,sizeof(a))==0);++bytes;
    if(x==old::UV3_READY){
     old::uv3_commit(&a,tick,frame>2,false,false);candidate::uv3_commit(&b,tick,frame>2,false,false);
     assert(memcmp(&a,&b,sizeof(a))==0);
    }
    if((i%10)==0)++tick;
   }
   if(scenario%4==3&&frame==8)tick+=400;
   auto x=old::uv3_tick(&a,tick);auto y=candidate::uv3_tick(&b,tick);
   assert((int)x==(int)y&&memcmp(&a,&b,sizeof(a))==0);tick+=10;
  }
 }
 printf("{\"CRC_differential_cases\":%u,\"transport_byte_states_compared\":%u}\n",checked,bytes);
}
