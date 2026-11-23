#pragma once
#include <stdint.h>

struct Lease {
  uint32_t nonce = 0, issued = 0, renewed = 0;
  bool consumed = true, active = false;
  static constexpr uint32_t ttl_ms = 750;
  void issue(uint32_t now) { ++nonce; issued = now; consumed = false; }
  bool reply(uint32_t value, uint32_t now) {
    if (consumed || value != nonce || uint32_t(now-issued)>150) return false;
    consumed = true; renewed = now; active = true; return true;
  }
  void stop() { active = false; consumed = true; }
  bool permit(uint32_t now) {
    if (active && uint32_t(now-renewed)>=ttl_ms) active = false;
    return active;
  }
};

inline uint16_t lease_crc(const char *data) {
  uint16_t crc = 0xffff;
  for (; *data; ++data) {
    crc ^= uint8_t(*data);
    for (unsigned i=0;i<8;++i) crc=(crc>>1)^((crc&1)?0xa001:0);
  }
  return crc;
}
