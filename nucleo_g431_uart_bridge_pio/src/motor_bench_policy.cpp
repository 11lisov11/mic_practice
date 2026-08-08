#include "motor_bench_policy.h"

#include "proto.h"

bool motor_bench_command_allowed(const uint8_t *cmd, bool backend_ready) {
  if (cmd == nullptr || !backend_ready) {
    return false;
  }
  if (cmd[CMD_OFF_FLAGS] != (FLAG_ENABLE | FLAG_DIAG_PWM) ||
      cmd[CMD_OFF_MODE] != MODE_DIAG) {
    return false;
  }
  for (uint32_t offset = CMD_OFF_EXT_FLAGS; offset < CMD_OFF_CRC; ++offset) {
    if (cmd[offset] != 0U) {
      return false;
    }
  }
  return true;
}
