#pragma once
#include <stdint.h>
#include <string.h>

struct DeferredLogLine {
  uint32_t timestamp_us = 0;
  char text[96] = {};
};

// Caller protects this bounded queue; logging must never wait in the control loop.
struct DeferredLogQueue {
  DeferredLogLine lines[16];
  uint8_t head = 0, tail = 0, count = 0;
  uint32_t dropped = 0;
  bool push(const char *text, uint32_t now) {
    const size_t size = strlen(text);
    if (count == 16U || size >= sizeof(lines[0].text)) {
      if (dropped != UINT32_MAX) ++dropped;
      return false;
    }
    lines[head].timestamp_us = now;
    memcpy(lines[head].text, text, size + 1U);
    head = (head + 1U) & 15U;
    ++count;
    return true;
  }
  bool pop(DeferredLogLine &line) {
    if (count == 0U) return false;
    line = lines[tail];
    tail = (tail + 1U) & 15U;
    --count;
    return true;
  }
};
