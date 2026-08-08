#include "motor_backend.h"

#include <string.h>

#include "config.h"
#include "proto.h"

#if MIC_MOTOR_BACKEND_STUB

static motor_backend_status_t s_status;

void motor_backend_init(void) {
  memset(&s_status, 0, sizeof(s_status));
  s_status.fault_code = FAULT_OK;
}

void motor_backend_tick(void) {}

void motor_backend_force_stop(void) {
  s_status.enabled = false;
  s_status.pwm_active = false;
  s_status.shutdown_released = false;
}

bool motor_backend_clear_fault(void) {
  motor_backend_force_stop();
  s_status.fault_code = FAULT_OK;
  return true;
}

bool motor_backend_apply_command(const uint8_t *cmd, uint8_t *fault_code) {
  (void)cmd;
  motor_backend_force_stop();
  s_status.fault_code = FAULT_INTERNAL;
  if (fault_code != nullptr) {
    *fault_code = FAULT_INTERNAL;
  }
  return false;
}

void motor_backend_get_status(motor_backend_status_t *status) {
  if (status != nullptr) {
    *status = s_status;
  }
}

#endif
