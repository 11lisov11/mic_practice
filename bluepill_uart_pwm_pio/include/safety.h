#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "proto.h"

typedef struct {
  uint32_t last_valid_ms;
  uint16_t good_cnt;
  uint16_t bad_cnt;
  bool link_ok;
  bool enabled;
  bool estop;
  bool fault_latched;
  bool timeout_active;
  bool pwm_active;
  uint8_t fault_code;
  uint8_t last_mode;
  uint8_t last_flags;
  uint8_t ext_flags;
  uint16_t brake_q15;
  bool heatsink_temp_valid;
  bool heatsink_temp_fault;
  uint32_t heatsink_temp_last_sample_ms;
  bool phase_measure_valid;
  uint32_t phase_measure_last_sample_ms;
} safety_state_t;

void safety_init(void);
void safety_on_valid_cmd(const uint8_t *cmd);
void safety_note_bad_frame(void);
void safety_on_bad_frame(uint8_t fault_code);
void safety_tick(void);
void safety_build_reply(uint8_t *rsp, const uint8_t *cmd);
const safety_state_t *safety_state(void);
void safety_set_pwm_active(bool active);
