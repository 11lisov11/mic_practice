#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef struct {
  bool ready;
  bool enabled;
  bool pwm_active;
  bool shutdown_released;
  uint8_t fault_code;
  uint16_t encoder_raw;
  bool encoder_valid;
  uint16_t vbus_raw;
  uint16_t temperature_raw;
  uint8_t temperature_flags;
  uint16_t phase_a_raw;
  uint16_t phase_b_raw;
  uint16_t phase_c_raw;
  uint8_t phase_flags;
} motor_backend_status_t;

void motor_backend_init(void);
void motor_backend_tick(void);
void motor_backend_control_irq_handler(void);
void motor_backend_force_stop(void);
bool motor_backend_clear_fault(void);
bool motor_backend_apply_command(const uint8_t *cmd, uint8_t *fault_code);
void motor_backend_get_status(motor_backend_status_t *status);
