#include <assert.h>
#include "air56_lso_capture.h"

int main(void)
{
    static volatile air56_trace trace;
    assert(!air56_trial_allowed(false, true, true, 3, 5000, &trace));
    assert(!air56_trial_allowed(true, true, true, 3, 5001, &trace));
    assert(!air56_trial_allowed(true, true, true, 2, 5000, &trace));
    assert(air56_trial_allowed(true, true, true, 3, 5000, &trace));
    trace.magic = AIR56_TRACE_MAGIC;
    trace.active = 1;
    trace.start_cycles = UINT32_MAX - 100000U;
    for (uint32_t sample = 0; sample < 80000; ++sample)
    {
        const unsigned row = trace.rows;
        const uint32_t now = trace.start_cycles + (sample + 1U) * 10625U;
        const uint32_t in_window = sample % AIR56_TRACE_WINDOW;
        air56_trace_current(&trace, in_window ? 300 : -1600, in_window ? -400 : -300);
        const uint32_t measured = in_window ? 1500 : 2400;
        air56_trace_cycles(&trace, now, measured, 0);
        air56_trace_total(&trace, row, measured + 35U);
    }
    assert(trace.rows == 500 && trace.injected_samples == 80000);
    assert(trace.fast_max == 2435 && trace.windows[499].since_start_cycles == 850000000U);
    for (unsigned row = 0; row < trace.rows; ++row)
    {
        const volatile air56_trace_row *w = &trace.windows[row];
        assert(w->ia == 300 && w->ib == -400);
        assert(w->peak_a == 1600 && w->peak_b == 400 && w->peak_c == 1900);
        assert(w->max_cycles == 2435);
    }
    trace.active = 0;
    assert(!air56_trial_allowed(true, true, true, 3, 5000, &trace));
    air56_trace_window(&trace, trace.start_cycles);
    assert(trace.rows == 500);
    trace.active = 1; /* New independent recorder scenario for exception handling. */
    air56_trace_current(&trace, INT16_MIN, INT16_MIN);
    air56_trace_cycles(&trace, 170U, 4100U, 1U);
    air56_trace_total(&trace, 500U, 4150U);
    air56_trace_window(&trace, 171U);
    assert(trace.rows == 501 && trace.first_fault == 1U && trace.fast_max == 4150U);
    assert(trace.windows[500].peak_c == UINT16_MAX);
    assert(trace.windows[500].max_cycles == 4150U);
    return 0;
}
