#pragma once
#include <stddef.h>
#include <stdint.h>

// Caller serializes producer/consumer with a short interrupt lock.
template <size_t Capacity> struct BoundedRx {
  static_assert(Capacity > 0 && Capacity <= UINT16_MAX, "RX capacity");
  uint8_t data[Capacity]{};
  uint16_t head = 0, tail = 0, count = 0, high_water = 0;
  uint32_t dropped = 0;
  bool put(uint8_t byte) {
    if (count == Capacity) {
      if (dropped != UINT32_MAX) ++dropped;
      return false;
    }
    data[head] = byte;
    head = (head + 1) % Capacity;
    if (++count > high_water) high_water = count;
    return true;
  }
  int read(bool consume = true) {
    if (!count) return -1;
    const uint8_t byte = data[tail];
    if (consume) { tail = (tail + 1) % Capacity; --count; }
    return byte;
  }
};
