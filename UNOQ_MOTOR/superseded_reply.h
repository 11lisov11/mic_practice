#pragma once
#include <stdint.h>

// A forced STOP can replace an in-flight request. Its one outstanding reply
// is discarded, never applied as telemetry or accepted as a CLEAR response.
struct SupersededReplies {
  struct Entry { uint32_t sent_us; uint8_t seq; bool valid; } entries[4] = {};
  uint8_t next = 0;

  void retire(uint8_t seq, uint32_t sent_us) {
    entries[next] = {sent_us, seq, true};
    next = (next + 1U) % 4U;
  }

  void forget(uint8_t seq) {
    for (auto &entry : entries) if (entry.seq == seq) entry.valid = false;
  }

  bool consume(uint8_t seq, uint32_t now_us, uint32_t timeout_us) {
    for (auto &entry : entries) {
      if (entry.valid && (uint32_t)(now_us - entry.sent_us) >= timeout_us)
        entry.valid = false;
      if (entry.valid && entry.seq == seq) {
        entry.valid = false;
        return true;
      }
    }
    return false;
  }
};
