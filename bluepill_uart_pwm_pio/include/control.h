#pragma once

#include <stdint.h>

void control_init(void);
void control_update_from_cmd(const uint8_t *cmd);
void control_tick(void);
