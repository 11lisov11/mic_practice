# Imported as source into the HMI; no network or controller commands here.
def current_crc32c(raw):
    value = 0xffffffff
    for byte in raw:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0x82f63b78 if value & 1 else 0)
    return value ^ 0xffffffff


def with_shunt_currents(data):
    data.update(mc_current_telemetry_valid=0, mc_current_telemetry_source='nucleo_shunt_unavailable',
                mc_current_scale_qualified=0, mc_current_status='Нет свежих измерений шунтов',
                mc_current_rms_a=None, mc_current_peak_a=None, mc_current_instant_a=None,
                mc_current_zero_ready=0, mc_current_frozen=0,
                mc_current_raw_adc=None, mc_current_offsets_adc=None, mc_current_zero_samples=None,
                mc_current_flags=0, mc_current_coverage_pct=0, mc_current_reconstructed_mask=0,
                mc_current_window_ms=0, mc_current_rejected_samples=0)
    if (data.get('fw_build'), data.get('mc_fw_build')) != (2026102405, 2026102406):
        return data

    def packet(key, version):
        raw = bytes.fromhex(data.get(key, '-'))
        if (len(raw) != 43 or raw[:3] != bytes((0x55, 0xaa, version)) or raw[38] != 1
                or int.from_bytes(raw[6:10], 'little') != 2026102406
                or current_crc32c(raw[:39]) != int.from_bytes(raw[39:], 'little')):
            raise ValueError('Invalid current record')
        return raw

    try:
        detail_age = int(data.get('mc_current_detail_age_ms', 999999))
        if 0 <= detail_age < 1500:
            detail = packet('mc_current_detail_hex', 0xd6)
            data['mc_current_raw_adc'] = [int.from_bytes(detail[i:i+2], 'little') for i in range(14, 22, 2)]
            data['mc_current_offsets_adc'] = [int.from_bytes(detail[i:i+2], 'little') for i in range(22, 30, 2)]
            data['mc_current_zero_samples'] = [int.from_bytes(detail[i:i+2], 'little') for i in range(30, 38, 2)]
            data['mc_current_zero_ready'] = int(bool(detail[3] & 1))
            if detail[3] & 16:
                data['mc_current_status'] = 'Неверный или нестабильный ноль: проверьте токовые каналы'
        raw = packet('mc_current_packet_hex', 0xd5)
        age = int(data.get('mc_current_age_ms', 999999))
        if not (0 <= age < 750 and 0 <= data.get('mc_age_ms', 999999) < 300):
            data['mc_current_status'] = 'Данные токов устарели'
            return data
        flags = raw[3]
        data.update(mc_current_flags=flags, mc_current_zero_ready=int(bool(flags & 1)),
                    mc_current_frozen=int(bool(flags & 4)), mc_current_coverage_pct=raw[5],
                    mc_current_reconstructed_mask=raw[32],
                    mc_current_window_tick_ms=int.from_bytes(raw[10:14], 'little'),
                    mc_current_window_ms=int.from_bytes(raw[34:36], 'little'),
                    mc_current_rejected_samples=int.from_bytes(raw[36:38], 'little'))
        if flags & 16:
            data['mc_current_status'] = 'Неверный или нестабильный ноль: проверьте токовые каналы'
        elif not flags & 1:
            data['mc_current_status'] = 'Ожидается автоноль при выключенном ШИМ и низкой DC-шине'
        elif not flags & 2:
            data['mc_current_status'] = ('Недостоверное окно: насыщение АЦП или пропуски выборки'
                                         if flags & (32 | 64) else 'Автоноль готов; ожидается окно тока при работе')
        else:
            rms = [int.from_bytes(raw[i:i+2], 'little') / 1000 for i in range(14, 20, 2)]
            peak = [int.from_bytes(raw[i:i+2], 'little') / 1000 for i in range(20, 26, 2)]
            instant = [int.from_bytes(raw[i:i+2], 'little', signed=True) / 1000 for i in range(26, 32, 2)]
            data.update(mc_current_telemetry_valid=1, mc_current_telemetry_source='nucleo_three_shunt_nominal_scale',
                        mc_current_rms_a=rms, mc_current_peak_a=peak, mc_current_instant_a=instant)
            data['mc_current_status'] = ('Последнее окно перед остановом' if flags & 4 else 'Измерение при работе')
            data['mc_current_status'] += '; номинальный масштаб, ещё не проверен эталоном'
        return data
    except (ValueError, TypeError, OverflowError):
        return data
