#include "proto.h"

static_assert(FRAME_LEN == 32, "UNO Q protocol frame length changed");
static_assert(CMD_OFF_CRC == FRAME_LEN - 1, "command CRC offset changed");
static_assert(RSP_OFF_CRC == FRAME_LEN - 1, "reply CRC offset changed");

uint8_t proto_crc_xor(const uint8_t *frame) {
  uint8_t crc = 0;
  for (uint8_t i = 0; i < (FRAME_LEN - 1); ++i) {
    crc ^= frame[i];
  }
  return crc;
}

bool proto_cmd_crc_ok(const uint8_t *frame) {
  return frame[CMD_OFF_CRC] == proto_crc_xor(frame);
}
