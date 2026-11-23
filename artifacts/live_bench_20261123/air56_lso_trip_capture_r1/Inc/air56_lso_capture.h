#ifndef AIR56_LSO_CAPTURE_H
#define AIR56_LSO_CAPTURE_H

#include "air56_st_lso_limits.h"

enum {
    AIR56_TRACE_ROWS = 512, AIR56_TRACE_WINDOW = 160,
    AIR56_TRACE_MAGIC = 0x324F534C, /* LSO2 */
    AIR56_END_TIMER = 1, AIR56_END_OFF, AIR56_END_LINK, AIR56_END_FAULT, AIR56_END_ESTOP
};

typedef struct {
    uint32_t since_start_cycles;
    int16_t ia, ib;
    uint16_t peak_a, peak_b, peak_c;
    uint16_t max_cycles;
} air56_trace_row;

typedef struct {
    uint32_t magic, active, rows, start_ms, end_ms, reason, fast_max, first_fault;
    uint32_t start_cycles, injected_samples;
    uint16_t count, peak_a, peak_b, peak_c, window_max;
    int16_t ia, ib;
    uint16_t reserved;
    air56_trace_row windows[AIR56_TRACE_ROWS];
} air56_trace;

static inline uint16_t air56_abs_i16(int32_t value)
{
    const uint32_t magnitude = (uint32_t)(value < 0 ? -value : value);
    return magnitude > UINT16_MAX ? UINT16_MAX : (uint16_t)magnitude;
}

static inline void air56_trace_current(volatile air56_trace *t, int16_t a, int16_t b)
{
    t->ia = a;
    t->ib = b;
    uint16_t pa = air56_abs_i16(a);
    uint16_t pb = air56_abs_i16(b);
    uint16_t pc = air56_abs_i16(-(int32_t)a - b);
    if (pa > t->peak_a) { t->peak_a = pa; }
    if (pb > t->peak_b) { t->peak_b = pb; }
    if (pc > t->peak_c) { t->peak_c = pc; }
    ++t->count;
    ++t->injected_samples;
}

static inline void air56_trace_window(volatile air56_trace *t, uint32_t cycles)
{
    if (t->rows < AIR56_TRACE_ROWS && (t->count || t->window_max))
    {
        volatile air56_trace_row *row = &t->windows[t->rows];
        row->since_start_cycles = cycles - t->start_cycles;
        row->ia = t->ia;
        row->ib = t->ib;
        row->peak_a = t->peak_a;
        row->peak_b = t->peak_b;
        row->peak_c = t->peak_c;
        row->max_cycles = t->window_max;
        ++t->rows;
        t->count = t->peak_a = t->peak_b = t->peak_c = t->window_max = 0;
    }
}

static inline void air56_trace_cycles(volatile air56_trace *t, uint32_t now,
                                      uint32_t fast, uint16_t fault)
{
    if (fast > t->fast_max) { t->fast_max = fast; }
    if (fast > t->window_max)
    {
        t->window_max = fast > UINT16_MAX ? UINT16_MAX : (uint16_t)fast;
    }
    if (fault && !t->first_fault) { t->first_fault = fault; }
    if (t->count >= AIR56_TRACE_WINDOW) { air56_trace_window(t, now); }
}

static inline void air56_trace_total(volatile air56_trace *t, unsigned row_before, uint32_t fast)
{
    if (fast > t->fast_max) { t->fast_max = fast; }
    uint16_t capped = fast > UINT16_MAX ? UINT16_MAX : (uint16_t)fast;
    if (row_before < t->rows)
    {
        if (capped > t->windows[row_before].max_cycles) { t->windows[row_before].max_cycles = capped; }
    }
    else if (capped > t->window_max)
    {
        t->window_max = capped;
    }
}

/* A capture is single-use per boot. Lost UART and repeated ENABLE cannot
   re-arm or overwrite it. Actual start still goes through MCSDK. */
static inline bool air56_trial_allowed(bool ready, bool sd_ready, bool fresh_off,
                                       uint8_t clean_frames, uint32_t freq_millihz,
                                       const volatile air56_trace *t)
{
    return ready && sd_ready && fresh_off && clean_frames >= 3 &&
           freq_millihz == 5000 && t->magic == 0;
}
#endif
