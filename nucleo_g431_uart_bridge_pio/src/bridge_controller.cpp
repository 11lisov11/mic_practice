#include "bridge_controller.h"

#include <string.h>

#include "config.h"
#include "motor_backend.h"
#include "proto.h"

static bridge_state_t s_state;

static void saturating_increment(uint16_t *value) {
  if (*value != UINT16_MAX) {
    ++(*value);
  }
}

static bool command_is_safe_clear(const uint8_t *cmd) {
  if ((cmd[CMD_OFF_FLAGS] & FLAG_CLEAR_FAULT) == 0U ||
      (cmd[CMD_OFF_FLAGS] & (FLAG_ENABLE | FLAG_ESTOP)) != 0U ||
      cmd[CMD_OFF_MODE] != MODE_OFF) {
    return false;
  }
  for (uint32_t offset = CMD_OFF_EXT_FLAGS; offset < CMD_OFF_CRC; ++offset) {
    if (cmd[offset] != 0U) {
      return false;
    }
  }
  return true;
}

static void latch_fault(uint8_t fault_code, bool timeout, bool estop) {
  motor_backend_force_stop();
  s_state.enabled = false;
  s_state.fault_latched = true;
  s_state.timeout_active = timeout;
  s_state.estop = estop;
  s_state.fault_code = fault_code;
}

void bridge_controller_init(void) {
  memset(&s_state, 0, sizeof(s_state));
  s_state.fault_code = FAULT_OK;
  s_state.last_mode = MODE_OFF;
  motor_backend_init();
  motor_backend_force_stop();
}

void bridge_controller_on_valid_command(const uint8_t *cmd, uint32_t now_ms) {
  if (cmd == nullptr || cmd[CMD_OFF_VER] != MIC_PROTOCOL_VERSION) {
    bridge_controller_note_bad_frame();
    return;
  }

  saturating_increment(&s_state.good_count);
  s_state.link_ok = true;
  s_state.last_valid_ms = now_ms;
  s_state.last_seq = cmd[CMD_OFF_SEQ];

  if (command_is_safe_clear(cmd)) {
    motor_backend_force_stop();
    if (motor_backend_clear_fault()) {
      s_state.enabled = false;
      s_state.estop = false;
      s_state.fault_latched = false;
      s_state.timeout_active = false;
      s_state.fault_code = FAULT_OK;
      s_state.last_mode = MODE_OFF;
    }
    return;
  }

  if ((cmd[CMD_OFF_FLAGS] & FLAG_ESTOP) != 0U) {
    latch_fault(FAULT_ESTOP, false, true);
    return;
  }

  if ((cmd[CMD_OFF_FLAGS] & FLAG_ENABLE) == 0U || cmd[CMD_OFF_MODE] == MODE_OFF) {
    motor_backend_force_stop();
    s_state.enabled = false;
    s_state.last_mode = MODE_OFF;
    return;
  }

  if (s_state.fault_latched) {
    motor_backend_force_stop();
    return;
  }

  uint8_t backend_fault = FAULT_INTERNAL;
  if (!motor_backend_apply_command(cmd, &backend_fault)) {
    latch_fault(backend_fault, false, false);
    return;
  }

  motor_backend_status_t backend = {};
  motor_backend_get_status(&backend);
  s_state.enabled = backend.enabled;
  s_state.last_mode = cmd[CMD_OFF_MODE];
}

void bridge_controller_note_bad_frame(void) {
  saturating_increment(&s_state.bad_count);
}

void bridge_controller_note_bad_frames(uint16_t count) {
  const uint32_t total = (uint32_t)s_state.bad_count + count;
  s_state.bad_count = total > UINT16_MAX ? UINT16_MAX : (uint16_t)total;
}

void bridge_controller_tick(uint32_t now_ms) {
  motor_backend_tick();
  if (s_state.link_ok && (uint32_t)(now_ms - s_state.last_valid_ms) > LINK_TIMEOUT_MS) {
    s_state.link_ok = false;
    latch_fault(FAULT_TIMEOUT, true, false);
  }
}

void bridge_controller_build_reply(uint8_t *reply, const uint8_t *cmd) {
  memset(reply, 0, FRAME_LEN);
  reply[RSP_OFF_HDR0] = RSP_HDR0;
  reply[RSP_OFF_HDR1] = RSP_HDR1;
  reply[RSP_OFF_VER] = MIC_PROTOCOL_VERSION;
  reply[RSP_OFF_SEQ] = cmd != nullptr ? cmd[CMD_OFF_SEQ] : s_state.last_seq;
  reply[RSP_OFF_GOOD_LO] = (uint8_t)(s_state.good_count & 0xFFU);
  reply[RSP_OFF_GOOD_HI] = (uint8_t)(s_state.good_count >> 8U);
  reply[RSP_OFF_BAD_LO] = (uint8_t)(s_state.bad_count & 0xFFU);
  reply[RSP_OFF_BAD_HI] = (uint8_t)(s_state.bad_count >> 8U);
  reply[RSP_OFF_FAULT] = s_state.fault_code;
  reply[RSP_OFF_LAST_MODE] = s_state.last_mode;

  motor_backend_status_t backend = {};
  motor_backend_get_status(&backend);
  uint8_t status = 0;
  if (s_state.link_ok) status |= STATUS_LINK_OK;
  if (s_state.enabled && backend.enabled) status |= STATUS_ENABLED;
  if (s_state.estop) status |= STATUS_ESTOP;
  if (s_state.fault_latched || backend.fault_code != FAULT_OK) status |= STATUS_FAULT;
  if (s_state.timeout_active) status |= STATUS_TIMEOUT;
  if (backend.pwm_active) status |= STATUS_PWM_ACTIVE;
  if (backend.shutdown_released) status |= STATUS_SHUTDOWN_RELEASED;
  reply[RSP_OFF_STATUS] = status;

  reply[11] = (uint8_t)(backend.encoder_raw & 0xFFU);
  reply[12] = (uint8_t)(backend.encoder_raw >> 8U);
  reply[13] = backend.encoder_valid ? 1U : 0U;
  reply[RSP_OFF_VBUS_RAW_LO] = (uint8_t)(backend.vbus_raw & 0xFFU);
  reply[RSP_OFF_VBUS_RAW_HI] = (uint8_t)(backend.vbus_raw >> 8U);
  reply[RSP_OFF_TEMP_RAW_LO] = (uint8_t)(backend.temperature_raw & 0xFFU);
  reply[RSP_OFF_TEMP_RAW_HI] = (uint8_t)(backend.temperature_raw >> 8U);
  reply[RSP_OFF_TEMP_FLAGS] = backend.temperature_flags;
  reply[RSP_OFF_PHASE_A_RAW_LO] = (uint8_t)(backend.phase_a_raw & 0xFFU);
  reply[RSP_OFF_PHASE_A_RAW_HI] = (uint8_t)(backend.phase_a_raw >> 8U);
  reply[RSP_OFF_PHASE_B_RAW_LO] = (uint8_t)(backend.phase_b_raw & 0xFFU);
  reply[RSP_OFF_PHASE_B_RAW_HI] = (uint8_t)(backend.phase_b_raw >> 8U);
  reply[RSP_OFF_PHASE_C_RAW_LO] = (uint8_t)(backend.phase_c_raw & 0xFFU);
  reply[RSP_OFF_PHASE_C_RAW_HI] = (uint8_t)(backend.phase_c_raw >> 8U);
  reply[RSP_OFF_PHASE_FLAGS] = backend.phase_flags;
  reply[RSP_OFF_CRC] = proto_crc_xor(reply);
}

const bridge_state_t *bridge_controller_state(void) {
  return &s_state;
}
