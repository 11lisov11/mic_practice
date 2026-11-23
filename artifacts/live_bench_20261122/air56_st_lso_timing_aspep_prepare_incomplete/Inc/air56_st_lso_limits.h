#ifndef AIR56_ST_LSO_LIMITS_H
#define AIR56_ST_LSO_LIMITS_H

#include <stdbool.h>
#include <stdint.h>

/* Stock R3_2 current units: 65536 * 0.040 ohm * 2.1 / 3.30 V. */
enum {
    AIR56_LSO_CURRENT_TRIP = 2252,
    AIR56_LSO_FAST_CYCLES = 4000,
    AIR56_LSO_ADC_AGE_CYCLES = 340000, /* 2 ms at 170 MHz */
    AIR56_LSO_LINK_MS = 300,
    AIR56_LSO_RUN_MS = 5000
};

static inline bool air56_lso_overcurrent(int16_t phase_a, int16_t phase_b)
{
    const int32_t limit = AIR56_LSO_CURRENT_TRIP;
    const int32_t ia = phase_a;
    const int32_t ib = phase_b;
    const int32_t ic = -ia - ib;
    if (ia > limit || ia < -limit || ib > limit || ib < -limit ||
        ic > limit || ic < -limit)
    {
        return true;
    }
    /* Squared Clarke norm: (4/3)*(Ia^2+Ia*Ib+Ib^2). The checked
     * phase bounds keep each product and the total within int32_t. */
    return 4 * (ia * ia + ia * ib + ib * ib) > 3 * limit * limit;
}

static inline bool air56_lso_stale(uint32_t now, uint32_t stamp, uint32_t limit)
{
    return now - stamp >= limit;
}

#endif
