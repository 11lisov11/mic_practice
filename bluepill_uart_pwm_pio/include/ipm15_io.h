#pragma once

#include <stdbool.h>

void ipm15_io_init(void);
void ipm15_set_ntc(bool on);
void ipm15_set_pfc_sync(bool on);
void ipm15_set_brake_pwm(float duty);
