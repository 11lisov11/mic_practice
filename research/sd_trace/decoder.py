"""Read-only SD/UH trace decoder; inserted into the prepared HMI."""
import struct as _sdt_struct


def sd_trace_status(kv):
    result = {'available': False, 'captured': False,
              'timing_physically_qualified': False,
              'physical_fault_source_identified': False}
    try:
        text = kv.get('mc_sd_trace_hex', '-')
        if text == '-':
            return {**result, 'reason': 'not_received'}
        age = int(kv.get('mc_sd_trace_age_ms', '-1'))
        peer_age = int(kv.get('bp_age_ms', '999999'))
        peer = int(kv.get('bp_fw_build', '0'))
        if peer != 2026101506 or not 0 <= peer_age < 300 or not 0 <= age <= 8000:
            return {**result, 'reason': 'stale_or_wrong_peer'}
        if len(text) != 640 or any(c not in '0123456789abcdefABCDEF' for c in text):
            return {**result, 'reason': 'invalid_hex'}
        raw = bytes.fromhex(text)
        if not any(raw):
            return {**result, 'available': True, 'reason': 'no_recorded_trace'}
        fields = ('magic', 'schema', 'bytes', 'tick_ms', 'capture_reason', 'flags',
                  'sample_count', 'sample_period_cycles', 'timer_clock_hz', 'dma_remaining',
                  'dma_flags', 'gpioa_at_freeze', 'tim1_af1', 'tim1_sr', 'start_tick_ms', 'reserved')
        header = dict(zip(fields, _sdt_struct.unpack('<16I', raw[:64])))
        n, flags, reason = header['sample_count'], header['flags'], header['capture_reason']
        valid = (header['magic'] == 0x31544453 and header['schema'] == 1 and header['bytes'] == 320
                 and 1 <= reason <= 3 and not flags & ~31 and 0 <= n <= 1024
                 and header['sample_period_cycles'] > 0 and header['timer_clock_hz'] > 0
                 and header['dma_remaining'] <= 1024 and header['reserved'] == 0)
        valid = valid and ((reason == 3 and flags == 8 and n == 0) or
                           (reason != 3 and flags & 1 and not flags & 8 and n > 0))
        valid = valid and (reason != 2 or header['tim1_sr'] & 0x180) and (not flags & 2 or n == 1024)
        planes = [[(raw[64 + plane * 128 + i // 8] >> (i % 8)) & 1 for i in range(1024)] for plane in range(2)]
        valid = valid and not any(planes[0][n:]) and not any(planes[1][n:])
        if not valid:
            return {**result, 'reason': 'invalid_record'}
        period_us = header['sample_period_cycles'] * 1e6 / header['timer_clock_hz']
        sd, uh = planes[0][:n], planes[1][:n]
        runs = []
        i = 0
        while i < n:
            if sd[i]:
                i += 1
                continue
            start = i
            while i < n and not sd[i]:
                i += 1
            bounded = start > 0 and i < n
            runs.append({'first_sample': start, 'sample_count': i-start,
                         'both_edges_inside_capture': bounded,
                         'nominal_low_duration_us': (i-start)*period_us,
                         'nominal_quantization_uncertainty_us': 2*period_us,
                         'duration_is_lower_bound': not bounded})
        result.update(available=True, captured=reason != 3,
                      reason={1: 'normal_stop_capture', 2: 'hardware_break_capture', 3: 'resource_error'}[reason],
                      age_ms=age, raw=header, nominal_sample_period_us=period_us,
                      nominal_window_us=n*period_us,
                      timing_flags_valid=not bool(flags & (4 | 8 | 16)),
                      sd_low_runs=runs, sd_samples=sd, uh_samples=uh,
                      limitations=[
                          'Nominal timer timing; external Saleae validation is still required',
                          'DMA request latency or missed samples are not ruled out by software tests',
                          'IRQ freeze latency is not measured; the last sample is not the fault edge',
                          'An unobserved pulse may be too short, outside this window, or from another Break source',
                          'SD alone does not uniquely identify overcurrent, J4 undervoltage or interference',
                          'UH is a logic-pin sample, not gate voltage, phase voltage or rotor speed'])
        return result
    except (ValueError, TypeError, OverflowError, _sdt_struct.error):
        return {**result, 'reason': 'invalid_metadata'}
