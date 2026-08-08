#pragma once

#include <stdbool.h>
#include <stdint.h>

bool motor_bench_command_allowed(const uint8_t *cmd, bool backend_ready);
