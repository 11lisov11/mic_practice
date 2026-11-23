#ifndef MIC_SD_LIVE_STATUS_H
#define MIC_SD_LIVE_STATUS_H
#include <stdbool.h>
#include <stdint.h>
/* This is observation only. Bits 0/1 retain temperature validity/fault. */
enum { SD_LIVE_VALID=4, SD_LIVE_HIGH=8, SD_LIVE_BIE=16,
       SD_LIVE_CAPTURING=32, SD_LIVE_RECORD_READY=64, SD_LIVE_CONFIG_OK=128 };
static inline uint8_t sd_live_encode(bool high, bool bie, bool capturing,
                                    bool ready, bool config_ok) {
  return (uint8_t)(SD_LIVE_VALID | (high ? SD_LIVE_HIGH : 0) |
      (bie ? SD_LIVE_BIE : 0) | (capturing ? SD_LIVE_CAPTURING : 0) |
      (ready ? SD_LIVE_RECORD_READY : 0) | (config_ok ? SD_LIVE_CONFIG_OK : 0));
}
#endif
