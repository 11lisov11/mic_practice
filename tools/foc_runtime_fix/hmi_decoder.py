def foc_runtime_status(kv):
    """Decode measured lower/upper timing bounds and immutable first fault."""
    names = {1: 'нет согласованного отсчёта АЦП', 2: 'отсчёт АЦП недействителен',
             3: 'превышен возраст отсчёта АЦП', 4: 'превышен возраст оценки наблюдателя',
             5: 'слишком длинный интервал окна наблюдателя', 6: 'превышен дедлайн быстрого расчёта',
             7: 'ошибка регулятора', 8: 'ошибка вычисления наблюдателя'}
    try:
        if int(kv.get('foc_runtime_valid', '0')) != 1:
            return {'foc_runtime': {'available': False, 'reason': 'not_received_or_stale'}}
        w = [int(kv.get('foc_runtime_w'+str(i), '0')) for i in range(28)]
        if not all(0 <= x <= 0xffffffff for x in w):
            raise ValueError('counter outside uint32')
        if w[1] > w[0] or w[0]-w[1] != w[2]:
            raise ValueError('inconsistent wall/IRQ/CPU counters')
        flags = int(kv.get('foc_runtime_flags', '0'))
        if flags not in (0, 1, 2, 3):
            raise ValueError('invalid runtime flags')
        fault = None
        if flags & 1:
            reason, code, at, adc, est, stamp, obs_begin = w[14:21]
            if reason not in names:
                raise ValueError('unknown frozen reason')
            fault = dict(reason_code=reason, reason_ru=names[reason], algorithm_fault=code,
                         at_cycles=at, adc_cycles=adc, estimate_cycles=est, bin_cycles=stamp,
                         observer_begin_cycles=obs_begin, adc_age_us=((at-adc)&0xffffffff)/170,
                         estimate_age_us=((at-est)&0xffffffff)/170,
                         window_dt_us=((stamp-est)&0xffffffff)/170,
                         last_observer_wall_us=w[21]/170, last_irq_body_lower_us=w[22]/170,
                         last_cpu_upper_us=w[23]/170, adc_sequence=w[24], sample_flags=w[25],
                         observer_inflight=bool(w[25]&8),
                         fast_elapsed_us=w[26]/170, observer_steps=w[27])
        return {'foc_runtime': dict(available=True, observer_measured=w[0]>0,
                    source='OFF_synthetic_CPU_probe' if flags & 2 else 'runtime_observer',
                    observer_wall_us=w[0]/170, irq_body_lower_us=w[1]/170,
                    cpu_upper_us=w[2]/170, irq_root_count=w[3],
                    max_wall_us=w[4]/170, max_irq_body_lower_us=w[5]/170,
                    max_cpu_upper_us=w[6]/170, window_queue_us=w[7]/170,
                    input_age_us=w[8]/170, result_age_us=w[9]/170,
                    max_window_queue_us=w[10]/170, max_result_age_us=w[11]/170,
                    observer_steps=w[12], meter_errors=w[13], first_fault=fault,
                    limitation='CPU upper includes exception entry/return and profiler edge overhead; IRQ body time is a lower bound.')}
    except (TypeError, ValueError, OverflowError):
        return {'foc_runtime': {'available': False, 'reason': 'invalid_counters'}}
