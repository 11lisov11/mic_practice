
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdint.h>
typedef struct { int16_t q, d; } qd_t;
#include "drive_parameters.h"
#include "acim_motor_parameters.h"
#define TF_REGULATION_RATE (PWM_FREQUENCY / REGULATION_EXECUTION_RATE)
#include "air56_lso_field_guard.h"

static unsigned run(float field, float rotor, float ref, int iq, int command, int flux)
{
    air56_field_guard state = { .flux_counts = (float)flux };
    air56_field_fault fault = {0};
    const qd_t current = { .q = iq, .d = flux };
    for (unsigned i = 0; i < AIR56_FIELD_WINDOW - 1; ++i) {
        assert(!air56_field_check(&state, current, command, ref, field * AIR56_FIELD_RAD_PER_TURN,
                                  rotor * AIR56_FIELD_RAD_PER_TURN, &fault));
    }
    unsigned result = air56_field_check(&state, current, command, ref, field * AIR56_FIELD_RAD_PER_TURN,
                                        rotor * AIR56_FIELD_RAD_PER_TURN, &fault);
    assert(state.frames == 0);
    if (result) {
        assert(fault.reason == result && fault.samples == AIR56_FIELD_WINDOW);
        assert(fabsf(fault.field_hz - field) < 0.001f);
    }
    return result;
}

int main(void)
{
    const float slip = 500.0f / (TAU_R * AIR56_FIELD_RAD_PER_TURN * 843.0f);
    // The old check would reject both of the first two real-slip cases.
    assert(0 == run(.8f + slip, .8f, 1, 500, 600, 843));
    assert(0 == run(.8f + slip, .8f, 1, 600, 500, 843));
    assert(0 == run(.6f, .4f, 1, 0, 0, 843));
    assert(AIR56_FIELD_ROTOR_RATE == run(1, 2, 1, 0, 0, 843));
    assert(AIR56_FIELD_ROTOR_RATE == run(2 + slip, 2, 1, 500, 600, 843));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, 500, 0, 843));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, -500, 600, 843));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, 500, IQMAX + 1, 843));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, 500, 600, 589));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, 500, 600, 1096));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(-(.8f + slip), -.8f, 1, 500, 600, 843));
    assert(AIR56_FIELD_SLIP_DISAGREEMENT == run(1.7f + slip, .8f, 1, 500, 600, 843));
    assert(AIR56_FIELD_COMPENSATED_RATE == run(1.9f + slip, 1.6f, 1, 500, 600, 843));
    air56_field_guard state = {0};
    air56_field_fault fault = {0};
    assert(AIR56_FIELD_NONFINITE == air56_field_check(&state, (qd_t){0}, 0, 0, NAN, 0, &fault));
    assert(AIR56_FIELD_NONFINITE == air56_field_check(&state, (qd_t){0}, 0, 0, 0, INFINITY, &fault));
    assert(fault.samples == 1);
    puts("15 guard cases passed");
}
