#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef struct {
  bool link_ok;
  bool enabled;
  bool estop;
  bool fault_latched;
  bool timeout_active;
  uint8_t fault_code;
  uint8_t last_mode;
  uint8_t last_seq;
  uint16_t good_count;
  uint16_t bad_count;
  uint32_t last_valid_ms;
} bridge_state_t;

void bridge_controller_init(void);
void bridge_controller_on_valid_command(const uint8_t *cmd, uint32_t now_ms);
void bridge_controller_note_bad_frame(void);
void bridge_controller_note_bad_frames(uint16_t count);
void bridge_controller_tick(uint32_t now_ms);
void bridge_controller_build_reply(uint8_t *reply, const uint8_t *cmd);
const bridge_state_t *bridge_controller_state(void);
