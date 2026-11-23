
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "air56_st_lso_limits.h"

int main(void) {
    unsigned checked = 0;
    const int64_t limit = AIR56_LSO_CURRENT_TRIP;
    for (int ia = -2300; ia <= 2300; ++ia) {
        for (int ib = -2300; ib <= 2300; ++ib) {
            const int64_t ic = -ia - ib;
            const bool expected = 2 * ((int64_t)ia * ia + (int64_t)ib * ib + ic * ic)
                                  > 3 * limit * limit;
            assert(air56_lso_overcurrent((int16_t)ia,(int16_t)ib) == expected);
            ++checked;
        }
    }
    assert(!air56_lso_overcurrent(2252,-1126));
    assert(air56_lso_overcurrent(2253,-1126));
    assert(air56_lso_overcurrent(1400,1000));
    assert(air56_lso_overcurrent(INT16_MIN,INT16_MIN));
    assert(air56_lso_overcurrent(INT16_MAX,INT16_MAX));
    uint32_t stamp = UINT32_MAX - 4;
    unsigned limits[] = {AIR56_LSO_ADC_AGE_CYCLES,AIR56_LSO_LINK_MS,AIR56_LSO_RUN_MS};
    for (unsigned i=0;i<sizeof limits/sizeof limits[0];++i) {
        assert(!air56_lso_stale(stamp+limits[i]-1, stamp, limits[i]));
        assert(air56_lso_stale(stamp+limits[i], stamp, limits[i]));
        assert(air56_lso_stale(stamp+limits[i]+1, stamp, limits[i]));
    }
    printf("%u\n",checked);
}
