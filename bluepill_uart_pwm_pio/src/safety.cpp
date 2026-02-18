#include "safety.h"

#include <string.h>

#include "config.h"
#include "encoder_as5600.h"
#include "ipm15_io.h"
#include "pwm_tim1.h"
#include "stm32f1xx_hal.h"

static safety_state_t s_state;

static void brake_set(bool active) {
  if (active) {
    if (BRAKE_ACTIVE_STATE) {
      HAL_GPIO_WritePin(EM_STOP_GPIO_PORT, EM_STOP_GPIO_PIN, GPIO_PIN_SET);
    } else {
      HAL_GPIO_WritePin(EM_STOP_GPIO_PORT, EM_STOP_GPIO_PIN, GPIO_PIN_RESET);
    }
  } else {
    if (BRAKE_ACTIVE_STATE) {
      HAL_GPIO_WritePin(EM_STOP_GPIO_PORT, EM_STOP_GPIO_PIN, GPIO_PIN_RESET);
    } else {
      HAL_GPIO_WritePin(EM_STOP_GPIO_PORT, EM_STOP_GPIO_PIN, GPIO_PIN_SET);
    }
  }
}

void safety_init(void) {
  memset(&s_state, 0, sizeof(s_state));
  s_state.fault_code = FAULT_OK;
  s_state.last_mode = MODE_OFF;
  s_state.last_flags = 0;
  s_state.ext_flags = 0;
  s_state.brake_q15 = 0;

  brake_set(true);
  ipm15_set_ntc(false);
  ipm15_set_pfc_sync(false);
  ipm15_set_brake_pwm(0.0f);
  pwm_outputs_enable(false);
  pwm_all_off();
}

static bool can_clear_fault(const uint8_t *cmd) {
  if (cmd[CMD_OFF_MODE] != MODE_OFF) return false;
  if (cmd[CMD_OFF_FLAGS] & FLAG_ENABLE) return false;
  if (cmd[CMD_OFF_FLAGS] & FLAG_ESTOP) return false;
  return true;
}

void safety_on_valid_cmd(const uint8_t *cmd) {
  s_state.last_valid_ms = HAL_GetTick();
  s_state.link_ok = true;
  s_state.timeout_active = false;
  s_state.good_cnt++;

  const bool estop_cmd = (cmd[CMD_OFF_FLAGS] & FLAG_ESTOP) != 0;
  const bool enable_cmd = (cmd[CMD_OFF_FLAGS] & FLAG_ENABLE) != 0;
  const bool diag_cmd = (cmd[CMD_OFF_FLAGS] & FLAG_DIAG_PWM) != 0;
  const bool clear_cmd = (cmd[CMD_OFF_FLAGS] & FLAG_CLEAR_FAULT) != 0;
  const uint8_t mode = cmd[CMD_OFF_MODE];
  const uint8_t ext_flags = cmd[CMD_OFF_EXT_FLAGS];
  const uint16_t brake_q15 = (uint16_t)cmd[CMD_OFF_EXT_DUTY_LO] | ((uint16_t)cmd[CMD_OFF_EXT_DUTY_HI] << 8);

  s_state.last_flags = cmd[CMD_OFF_FLAGS];
  if (estop_cmd) {
    s_state.estop = true;
    s_state.fault_latched = true;
    s_state.fault_code = FAULT_ESTOP;
  } else {
    s_state.estop = false;
  }

  if (clear_cmd && can_clear_fault(cmd)) {
    s_state.fault_latched = false;
    s_state.fault_code = FAULT_OK;
  }

  s_state.last_mode = mode;

  if (s_state.fault_latched) {
    pwm_outputs_enable(false);
    pwm_all_off();
    brake_set(true);
    s_state.ext_flags = 0;
    s_state.brake_q15 = 0;
    ipm15_set_ntc(false);
    ipm15_set_pfc_sync(false);
    ipm15_set_brake_pwm(0.0f);
    s_state.enabled = false;
    s_state.pwm_active = false;
    return;
  }

  if (!enable_cmd || mode == MODE_OFF) {
    pwm_outputs_enable(false);
    pwm_all_off();
    brake_set(true);
    s_state.ext_flags = 0;
    s_state.brake_q15 = 0;
    ipm15_set_ntc(false);
    ipm15_set_pfc_sync(false);
    ipm15_set_brake_pwm(0.0f);
    s_state.enabled = false;
    s_state.pwm_active = false;
    return;
  }

  s_state.enabled = true;
  brake_set(false);
  s_state.ext_flags = ext_flags;
  s_state.brake_q15 = brake_q15;
  ipm15_set_ntc((ext_flags & EXT_NTC_RELAY) != 0);
  ipm15_set_pfc_sync((ext_flags & EXT_PFC_SYNC) != 0);
  if (ext_flags & EXT_BRAKE_PWM) {
    ipm15_set_brake_pwm((float)brake_q15 / 32767.0f);
  } else {
    ipm15_set_brake_pwm(0.0f);
  }
  s_state.pwm_active = true;

  if (mode == MODE_DIAG && !diag_cmd) {
    // DIAG requested without flag -> keep outputs off
    pwm_outputs_enable(false);
    pwm_all_off();
    brake_set(true);
    s_state.enabled = false;
    s_state.pwm_active = false;
  } else if (mode == MODE_DIAG && diag_cmd) {
    s_state.pwm_active = true;
  } else {
    s_state.pwm_active = true;
  }
}

void safety_on_bad_frame(uint8_t fault_code) {
  s_state.bad_cnt++;
  s_state.link_ok = false;
  s_state.fault_code = fault_code;
  pwm_outputs_enable(false);
  pwm_all_off();
  brake_set(true);
  s_state.ext_flags = 0;
  s_state.brake_q15 = 0;
  ipm15_set_ntc(false);
  ipm15_set_pfc_sync(false);
  ipm15_set_brake_pwm(0.0f);
  s_state.enabled = false;
  s_state.pwm_active = false;
}

void safety_tick(void) {
  uint32_t now = HAL_GetTick();
  if ((now - s_state.last_valid_ms) > TIMEOUT_MS) {
    s_state.timeout_active = true;
    s_state.fault_latched = true;
    s_state.fault_code = FAULT_TIMEOUT;
    s_state.link_ok = false;
    pwm_outputs_enable(false);
    pwm_all_off();
    brake_set(true);
    s_state.ext_flags = 0;
    s_state.brake_q15 = 0;
    ipm15_set_ntc(false);
    ipm15_set_pfc_sync(false);
    ipm15_set_brake_pwm(0.0f);
    s_state.enabled = false;
    s_state.pwm_active = false;
  }
}

void safety_build_reply(uint8_t *rsp, const uint8_t *cmd) {
  memset(rsp, 0, FRAME_LEN);
  rsp[RSP_OFF_HDR0] = RSP_HDR0;
  rsp[RSP_OFF_HDR1] = RSP_HDR1;
  rsp[RSP_OFF_VER] = cmd[CMD_OFF_VER];

  uint8_t status = 0;
  if (s_state.link_ok) status |= STATUS_LINK_OK;
  if (s_state.enabled) status |= STATUS_ENABLED;
  if (s_state.estop) status |= STATUS_ESTOP;
  if (s_state.fault_latched) status |= STATUS_FAULT;
  if (s_state.timeout_active) status |= STATUS_TIMEOUT;
  if (s_state.pwm_active) status |= STATUS_PWM_ACTIVE;
  rsp[RSP_OFF_STATUS] = status;

  rsp[RSP_OFF_SEQ] = cmd[CMD_OFF_SEQ];
  rsp[RSP_OFF_GOOD_LO] = (uint8_t)(s_state.good_cnt & 0xFF);
  rsp[RSP_OFF_GOOD_HI] = (uint8_t)((s_state.good_cnt >> 8) & 0xFF);
  rsp[RSP_OFF_BAD_LO] = (uint8_t)(s_state.bad_cnt & 0xFF);
  rsp[RSP_OFF_BAD_HI] = (uint8_t)((s_state.bad_cnt >> 8) & 0xFF);
  rsp[RSP_OFF_FAULT] = s_state.fault_code;
  rsp[RSP_OFF_LAST_MODE] = s_state.last_mode;

  // Optional encoder telemetry (AS5600 raw angle)
#if USE_AS5600
  uint16_t enc_raw = 0;
  bool enc_ok = encoder_as5600_get_raw(&enc_raw);
  rsp[11] = (uint8_t)(enc_raw & 0xFF);
  rsp[12] = (uint8_t)((enc_raw >> 8) & 0xFF);
  rsp[13] = enc_ok ? 1 : 0;
#endif

  rsp[RSP_OFF_EXT_FLAGS] = s_state.ext_flags;
  rsp[RSP_OFF_EXT_DUTY_LO] = (uint8_t)(s_state.brake_q15 & 0xFF);
  rsp[RSP_OFF_EXT_DUTY_HI] = (uint8_t)((s_state.brake_q15 >> 8) & 0xFF);

  rsp[RSP_OFF_CRC] = proto_crc_xor(rsp);
}

const safety_state_t *safety_state(void) {
  return &s_state;
}

void safety_set_pwm_active(bool active) {
  s_state.pwm_active = active;
}
