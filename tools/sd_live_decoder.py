def sd_live_status(data):
    """A fresh GPIO observation is independent of the frozen first waveform."""
    unknown = {'available': False, 'level': None, 'summary_ru': 'Текущий SD: нет измерения'}
    try:
        if int(data.get('mc_fw_build', 0)) != 2026101808:
            return dict(unknown, reason='unsupported_peer')
        age = int(data.get('mc_age_ms', data.get('bp_age_ms', 999999)))
        if not 0 <= age < 300:
            return dict(unknown, reason='stale_peer')
        flags = int(data.get('bp_temp_flags', -1))
        if not 0 <= flags <= 255 or not flags & 4:
            return dict(unknown, reason='missing_validity')
        high = bool(flags & 8)
        config_ok = bool(flags & 128)
        level = 'HIGH' if high else 'LOW'
        summary = f'SD сейчас {level}: ' + ('защита отпущена' if high else 'вход защиты активен')
        if not config_ok:
            summary += '; конфигурация PA6/BKIN отличается от ожидаемой'
        return dict(available=True, reason='observed', level=level, age_ms=age,
            break_irq_enabled=bool(flags & 16), capture_running=bool(flags & 32),
            first_record_ready=bool(flags & 64), config_ok=config_ok,
            summary_ru=summary,
            limitation='Уровень на момент ответа UART; краткие импульсы между ответами здесь не измеряются')
    except (TypeError, ValueError, OverflowError):
        return dict(unknown, reason='invalid_metadata')
