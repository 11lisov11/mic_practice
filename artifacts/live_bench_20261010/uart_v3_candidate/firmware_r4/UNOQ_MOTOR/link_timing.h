#pragma once
#include <stdint.h>

// Passive counters only. Caller serializes updates/snapshots; no control decisions.
struct LinkTiming {
  uint32_t loop_active_max_us = 0;
  uint32_t tx_active_max_gap_us = 0;
  uint32_t rx_active_max_gap_us = 0;
  uint32_t tx_call_max_us = 0;
  uint32_t rpc_max_us = 0;
  uint32_t tx_short_writes = 0;
  uint32_t tx_count = 0;
  uint32_t rx_count = 0;
  uint32_t last_loop = 0, last_tx = 0, last_rx = 0;
  bool loop_seen = false, tx_seen = false, rx_seen = false;
  bool loop_active = false, tx_active = false, rx_active = false;

  static void maximum(uint32_t &value, uint32_t sample) {
    if (sample > value) value = sample;
  }
  static void increment(uint32_t &value) {
    if (value != UINT32_MAX) ++value;
  }
  void loop(uint32_t now, bool active) {
    if (loop_seen && (active || loop_active)) maximum(loop_active_max_us, now - last_loop);
    last_loop = now; loop_seen = true; loop_active = active;
  }
  void tx(uint32_t now, uint32_t duration, uint32_t written, bool active) {
    if (tx_seen && (active || tx_active)) maximum(tx_active_max_gap_us, now - last_tx);
    maximum(tx_call_max_us, duration);
    if (written != 32U) increment(tx_short_writes);
    increment(tx_count);
    last_tx = now; tx_seen = true; tx_active = active;
  }
  void rx(uint32_t now, bool active) {
    if (rx_seen && (active || rx_active)) maximum(rx_active_max_gap_us, now - last_rx);
    increment(rx_count);
    last_rx = now; rx_seen = true; rx_active = active;
  }
  void rpc(uint32_t duration) { maximum(rpc_max_us, duration); }
};
