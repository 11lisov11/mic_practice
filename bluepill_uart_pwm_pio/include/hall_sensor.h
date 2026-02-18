#pragma once

#include <stdbool.h>

void hall_sensor_init(void);
bool hall_get_theta(float *theta_elec, float *omega_elec);
