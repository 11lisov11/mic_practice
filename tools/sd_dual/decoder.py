def dual_sd_wave_status(data):
    """Schema 5: two logic levels from each same GPIOA DMA read, not analog SD.

    A stored record does not prove live wiring, physical edge timing, or that
    an IPM itself generated a LOW. No cause is inferred from coincidence.
    """
    try:
        if _as_int(data or {}, 'mc_fw_build', 0) != 2026102102:
            return {'available': False, 'reason': 'wrong_peer_build'}
        text = data.get('mc_break_wave_hex', '')
        age = _as_int(data, 'mc_break_wave_age_ms', -1)
        if not text or text == '-': return {'available': False, 'reason': 'not_received'}
        if len(text) != 640 or any(c not in '0123456789abcdefABCDEF' for c in text):
            return {'available': False, 'reason': 'invalid_hex'}
        if not 0 <= age <= 0xffffffff: return {'available': False, 'reason': 'invalid_age'}
        raw = bytes.fromhex(text)
        magic, schema, size, tick, period, flags, trigger, samples, n, mask, limit, post, pre, dma, remaining, config = _break_struct.unpack_from('<16I', raw)
        invalid = lambda: {'available': False, 'reason': 'invalid_record'}
        if (magic != 0x314e4b42 or schema != 5 or size != 320 or period != 200 or
            not flags & 1 or flags & ~633 or trigger > 2048 or samples > trigger + 500000 or
            n > 32 or mask != 0x50 or limit != 500000 or post != 320 or pre != 2048 or
            dma & ~15 or remaining > 8192 or config != 1 or flags & 512 and flags & 8): return invalid()
        runs = []; total = 0; previous = 4; quiet = 0
        for i in range(32):
            state, count = _break_struct.unpack_from('<2I', raw, 64 + 8*i)
            if i >= n:
                if state or count: return invalid()
                continue
            if state > 3 or not count or state == previous or count > samples-total: return invalid()
            runs.append({'state': state, 'pa6': state & 1, 'tp23_pa4': (state >> 1) & 1,
                         'samples': count, 'from_us': (total-trigger)*.2,
                         'to_us': (total+count-trigger)*.2})
            total += count; previous = state; quiet = count if state == 3 else 0
        if total != samples: return invalid()
        if flags & 512 and (samples < trigger+321 or quiet < 321): return invalid()
        errors = bool(flags & (16|32|64))
        if flags & 8 and not errors and samples != trigger+limit: return invalid()
        if not flags & (512|8|16|32|64): return invalid()
        channels = {}
        for name, bit in (('pa6_bkin', 0), ('tp23_pa4', 1)):
            intervals = []; position = 0; start = None
            for run in runs:
                high = (run['state'] >> bit) & 1
                if not high and start is None: start = position
                if high and start is not None:
                    intervals.append((start, position)); start = None
                position += run['samples']
            if start is not None: intervals.append((start, None))
            lows = []
            for begin, end in intervals:
                complete = begin != 0 and end is not None and not errors
                lows.append({'fall_sample': begin, 'rise_sample': end,
                    'from_us': (begin-trigger)*.2, 'to_us': None if end is None else (end-trigger)*.2,
                    'left_censored': begin == 0, 'right_censored': end is None,
                    'pulse_complete': complete,
                    'width_samples': end-begin if complete else None,
                    'width_us': (end-begin)*.2 if complete else None})
            preceding = [x for x in lows if x['fall_sample'] <= trigger]
            selected = preceding[-1] if preceding else (lows[0] if lows else None)
            channels[name] = {'low_intervals': lows, 'selected_pulse': selected,
                              'low_observed': bool(lows)}
        mismatch = sum(r['samples'] for r in runs if r['state'] in (1, 2))
        if errors: reason = 'dma_error' if flags & 16 else 'sampling_overrun' if flags & 32 else 'run_capacity_exceeded'
        elif flags & 8: reason = 'timeout_incomplete'
        else: reason = 'complete_window'
        def describe(name, title):
            pulse = channels[name]['selected_pulse']
            if pulse is None: return title + ': LOW не обнаружен'
            if not pulse['pulse_complete']: return title + ': LOW записан неполно; длительность не подтверждена'
            return title + f": LOW {pulse['width_us']:.1f} мкс"
        summary = describe('pa6_bkin', 'PA6/BKIN') + '; ' + describe('tp23_pa4', 'TP23→PA4')
        summary += f'; несовпадение уровней: {mismatch} отсч.'
        if errors or flags & 8: summary += '; окно неполное: ' + reason
        return {'available': True, 'reason': reason, 'schema': 5, 'stored_record': True,
            'event_tick_ms': tick, 'age_since_delivery_ms': age,
            'live_peer_fresh': 0 <= _as_int(data, 'mc_age_ms', 999999) < 300,
            'live_sd': sd_live_status(data), 'sample_period_us': .2, 'sample_rate_hz': 5000000,
            'trigger_index': trigger, 'sample_count': samples, 'runs': runs, 'channels': channels,
            'mismatch_samples': mismatch, 'mismatch_us': mismatch*.2,
            'post_complete': bool(flags & 512) and not errors, 'timeout': bool(flags & 8),
            'dma_error': bool(flags & 16), 'sampling_overrun': bool(flags & 32),
            'run_overflow': bool(flags & 64), 'flags': flags, 'dma_flags_raw': dma,
            'dma_remaining': remaining, 'input_configuration_verified': True,
            'summary_ru': summary,
            'trace_reference': 'Both bits from one GPIOA IDR DMA read; relative to Break IRQ publication',
            'limitations': ['Requested sample step 200 ns; hardware timing is not electrically qualified',
                'TP23 requires external wiring to PA4; firmware cannot detect an absent or wrong wire',
                'A LOW on both inputs does not prove intrinsic IPM fault; common-reference noise remains possible',
                '32 joint runs maximum; overflow and missing edges never imply a complete pulse',
                'First Break since boot; STOP/CLEAR do not overwrite evidence']}
    except (ValueError, TypeError, OverflowError):
        return {'available': False, 'reason': 'invalid_metadata'}
