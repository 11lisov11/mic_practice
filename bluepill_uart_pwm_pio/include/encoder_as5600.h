#pragma once

#include <stdbool.h>
#include <stdint.h>

bool encoder_as5600_init(void);
bool encoder_as5600_get_raw(uint16_t *raw);
bool encoder_as5600_get_theta(float *theta_rad);
