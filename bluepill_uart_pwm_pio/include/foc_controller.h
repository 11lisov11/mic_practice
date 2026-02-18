#pragma once

void foc_init(void);
void foc_reset(void);
void foc_run(float id_ref, float iq_ref, float theta_elec,
             float ia, float ib, float ic, float vbus,
             float *v_alpha, float *v_beta);
