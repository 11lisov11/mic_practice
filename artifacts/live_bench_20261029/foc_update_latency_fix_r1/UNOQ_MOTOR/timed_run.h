#pragma once
#include <stdint.h>

// MCU dispatch times, not measured IGBT edges. No HTTP clock is used.
struct TimedRun {
  enum Reason : uint32_t { NONE=0, LIMIT=1, STOP=2 };
  uint32_t id=0, start_ms=0, stop_ms=0, limit_ms=0, reason=NONE;
  bool active=false;
  void start(uint32_t now, uint32_t limit) {
    ++id; start_ms=now; stop_ms=0; limit_ms=limit; reason=NONE; active=true;
  }
  bool due(uint32_t now) const {
    return active && limit_ms && uint32_t(now-start_ms)>=limit_ms;
  }
  void finish(uint32_t now, Reason why) {
    if (!active) return;
    stop_ms=now; reason=why; active=false;
  }
  uint32_t elapsed(uint32_t now) const {
    return id ? uint32_t((active ? now : stop_ms)-start_ms) : 0;
  }
};
