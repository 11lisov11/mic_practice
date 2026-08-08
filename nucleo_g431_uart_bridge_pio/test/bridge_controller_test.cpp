#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "bridge_controller.h"
#include "config.h"
#include "motor_backend.h"
#include "proto.h"

static motor_backend_status_t s_backend;
static bool s_accept_command = false;
static uint32_t s_force_stop_count = 0;

void motor_backend_init(void) {
  memset(&s_backend, 0, sizeof(s_backend));
}

void motor_backend_tick(void) {}

void motor_backend_force_stop(void) {
  ++s_force_stop_count;
  s_backend.enabled = false;
  s_backend.pwm_active = false;
  s_backend.shutdown_released = false;
}

bool motor_backend_clear_fault(void) {
  motor_backend_force_stop();
  s_backend.fault_code = FAULT_OK;
  return true;
}

bool motor_backend_apply_command(const uint8_t *cmd, uint8_t *fault_code) {
  (void)cmd;
  if (!s_accept_command) {
    s_backend.fault_code = FAULT_INTERNAL;
    *fault_code = FAULT_INTERNAL;
    return false;
  }
  s_backend.ready = true;
  s_backend.enabled = true;
  s_backend.pwm_active = true;
  s_backend.shutdown_released = true;
  s_backend.fault_code = FAULT_OK;
  return true;
}

void motor_backend_get_status(motor_backend_status_t *status) {
  *status = s_backend;
}

static void make_command(uint8_t *cmd, uint8_t flags, uint8_t mode, uint8_t seq) {
  memset(cmd, 0, FRAME_LEN);
  cmd[CMD_OFF_HDR0] = CMD_HDR0;
  cmd[CMD_OFF_HDR1] = CMD_HDR1;
  cmd[CMD_OFF_VER] = MIC_PROTOCOL_VERSION;
  cmd[CMD_OFF_FLAGS] = flags;
  cmd[CMD_OFF_MODE] = mode;
  cmd[CMD_OFF_SEQ] = seq;
  cmd[CMD_OFF_CRC] = proto_crc_xor(cmd);
}

static uint8_t make_reply(const uint8_t *cmd, uint8_t *reply) {
  bridge_controller_build_reply(reply, cmd);
  assert(reply[RSP_OFF_HDR0] == RSP_HDR0);
  assert(reply[RSP_OFF_HDR1] == RSP_HDR1);
  assert(reply[RSP_OFF_VER] == MIC_PROTOCOL_VERSION);
  assert(reply[RSP_OFF_CRC] == proto_crc_xor(reply));
  return reply[RSP_OFF_STATUS];
}

int main(void) {
  uint8_t command[FRAME_LEN];
  uint8_t reply[FRAME_LEN];
  bridge_controller_init();
  assert(!bridge_controller_state()->link_ok);
  assert(!bridge_controller_state()->enabled);

  make_command(command, 0U, MODE_OFF, 1U);
  bridge_controller_on_valid_command(command, 100U);
  uint8_t status = make_reply(command, reply);
  assert(status == STATUS_LINK_OK);
  assert(reply[RSP_OFF_SEQ] == 1U);

  make_command(command, FLAG_ENABLE, MODE_SCALAR, 2U);
  bridge_controller_on_valid_command(command, 110U);
  status = make_reply(command, reply);
  assert((status & STATUS_FAULT) != 0U);
  assert((status & (STATUS_ENABLED | STATUS_PWM_ACTIVE | STATUS_SHUTDOWN_RELEASED)) == 0U);
  assert(reply[RSP_OFF_FAULT] == FAULT_INTERNAL);

  make_command(command, FLAG_CLEAR_FAULT, MODE_OFF, 3U);
  command[CMD_OFF_EXT_FLAGS] = EXT_PRECHARGE_RELAY;
  bridge_controller_on_valid_command(command, 115U);
  status = make_reply(command, reply);
  assert((status & STATUS_FAULT) != 0U);
  assert(reply[RSP_OFF_FAULT] == FAULT_INTERNAL);

  make_command(command, FLAG_CLEAR_FAULT, MODE_OFF, 4U);
  bridge_controller_on_valid_command(command, 120U);
  status = make_reply(command, reply);
  assert(status == STATUS_LINK_OK);
  assert(reply[RSP_OFF_FAULT] == FAULT_OK);

  s_accept_command = true;
  make_command(command, FLAG_ENABLE, MODE_SCALAR, 5U);
  bridge_controller_on_valid_command(command, 130U);
  status = make_reply(command, reply);
  assert((status & (STATUS_LINK_OK | STATUS_ENABLED | STATUS_PWM_ACTIVE |
                    STATUS_SHUTDOWN_RELEASED)) ==
         (STATUS_LINK_OK | STATUS_ENABLED | STATUS_PWM_ACTIVE | STATUS_SHUTDOWN_RELEASED));
  assert(reply[RSP_OFF_LAST_MODE] == MODE_SCALAR);

  const uint32_t stop_count_before_timeout = s_force_stop_count;
  bridge_controller_tick(431U);
  status = make_reply(command, reply);
  assert((status & (STATUS_FAULT | STATUS_TIMEOUT)) == (STATUS_FAULT | STATUS_TIMEOUT));
  assert((status & (STATUS_LINK_OK | STATUS_ENABLED | STATUS_PWM_ACTIVE)) == 0U);
  assert(reply[RSP_OFF_FAULT] == FAULT_TIMEOUT);
  assert(s_force_stop_count > stop_count_before_timeout);

  make_command(command, FLAG_CLEAR_FAULT, MODE_OFF, 6U);
  bridge_controller_on_valid_command(command, 440U);
  assert(make_reply(command, reply) == STATUS_LINK_OK);

  make_command(command, FLAG_ESTOP, MODE_OFF, 7U);
  bridge_controller_on_valid_command(command, 450U);
  status = make_reply(command, reply);
  assert((status & (STATUS_LINK_OK | STATUS_ESTOP | STATUS_FAULT)) ==
         (STATUS_LINK_OK | STATUS_ESTOP | STATUS_FAULT));
  assert((status & (STATUS_ENABLED | STATUS_PWM_ACTIVE)) == 0U);
  assert(reply[RSP_OFF_FAULT] == FAULT_ESTOP);

  make_command(command, 0U, MODE_OFF, 8U);
  command[CMD_OFF_VER] = 0x7FU;
  bridge_controller_on_valid_command(command, 460U);
  assert(bridge_controller_state()->bad_count == 1U);
  assert(bridge_controller_state()->good_count == 7U);

  puts("NUCLEO_BRIDGE_SELFTEST PASS");
  return 0;
}
