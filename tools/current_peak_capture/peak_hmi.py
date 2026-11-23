# Inserted into HMI after current_crc32c; decoder only, no controller writes.
def decode_adc_peak_hex(value, expected_build=2026102502):
    import struct
    raw = bytes.fromhex(value)
    if len(raw) != 1024:
        raise ValueError('ADC trace must contain 1024 bytes')
    checked = bytearray(raw)
    checked[60:64] = b'\0'*4
    if current_crc32c(checked) != int.from_bytes(raw[60:64], 'little'):
        raise ValueError('ADC trace record CRC mismatch')
    h = struct.unpack_from('<IHHII6H9I', raw)
    if (h[0:3] != (0x31435041, 1, 80) or h[3] != expected_build or h[4] != 1
            or h[5] != 12 or not 1 <= h[6] <= 12 or not 0 <= h[7] < 12
            or h[9:11] != (626, 6) or h[16:18] != (170000000, 42500000)):
        raise ValueError('Unexpected ADC trace layout or firmware')
    peak_seen = bool(h[15] & 1)
    if h[15] & ~7 or (peak_seen and not 0 <= h[8] < 12) or (not peak_seen and h[8] != 65535):
        raise ValueError('Invalid ADC trace trigger flags')
    rows = []
    for n in range(h[6]):
        slot = (h[7]+n) % 12
        s = struct.unpack_from('<8I8H14H2BH', raw, 64+80*slot)
        if s[30] > 2 or s[31] > 2 or any(x > 4095 for x in s[19:21]):
            raise ValueError('Invalid ADC sample channels or range')
        pair=s[30]; path1=1 if pair==2 else 0; path2=2 if pair==0 else 3
        phase1=1 if pair==2 else 0; phase2=1 if pair==0 else 2
        counts=[0,0,0]
        counts[phase1]=s[21+path1]-s[19]
        counts[phase2]=s[21+path2]-s[20]
        counts[3-phase1-phase2]=-counts[phase1]-counts[phase2]
        active=list(s[8:12]); trigger=active[3]
        excluded=0 if pair==2 else 1 if pair==1 else 2
        epoch_valid=s[2]==s[3] and not bool(s[25]&128)
        rows.append(dict(index=n,slot=slot,cycles=s[0],sequence=s[1],
            epoch_before=s[2],epoch_after=s[3],epoch_consistent=epoch_valid,
            adc_isr=[s[4],s[5]],adc_jsqr_after_conversion=[s[6],s[7]],
            ccr_at_update=active,ccr_preload=list(s[12:16]),
            timer_cnt_entry=s[16],timer_arr=s[17],timer_dir_entry=int(bool(s[18]&16)),
            raw_adc=list(s[19:21]),offsets_adc=list(s[21:25]),flags=s[25],
            timer_cnt_after_queue=s[26],timer_dir_after_queue=int(bool(s[25]&512)),reference_hz=s[27]/10,bus_v=s[28],
            timer_cnt_at_update=s[29],pair=pair,next_pair=s[31],timer_dir_at_update=int(bool(s[32]&16)),
            accepted_by_existing_monitor=bool(s[25]&64),queue_overflow_observed=bool(s[25]&256),
            counts_uvw=counts,nominal_currents_a=[round(x*3.3/(4095*.04*2.1),6) for x in counts],
            excluded_compare_inside_assumed_acquisition=(trigger<=active[excluded]<=trigger+112) if epoch_valid else None,
            is_trigger=peak_seen and slot==h[8]))
    if any(rows[i]['sequence']+1 != rows[i+1]['sequence'] for i in range(len(rows)-1)):
        raise ValueError('ADC trace sample sequence is not contiguous')
    trigger_row=next((x for x in rows if x['is_trigger']),None)
    if peak_seen and (trigger_row is None or trigger_row['sequence']!=h[12]):
        raise ValueError('ADC trigger sample missing or inconsistent')
    return dict(schema=1,firmware=h[3],capture_id=h[4],sample_count=h[6],
        threshold_counts=h[9],threshold_nominal_a=round(626*3.3/(4095*.04*2.1),6),
        total_samples=h[11],trigger_sequence=h[12],frozen_sequence=h[13],frozen_ms=h[14],
        peak_seen=peak_seen,post_short=bool(h[15]&2),no_peak=bool(h[15]&4),
        trigger_reference_hz=trigger_row['reference_hz'] if trigger_row else None,
        cpu_hz=h[16],adc_hz=h[17],max_queue_publish_cycles=h[18],max_queue_publish_us=h[18]/170,samples=rows,scale_qualified=False,
        limitation='CCR-at-update is a software latch at the update IRQ, not direct active-register readback; epoch races are explicit. Raw ADC alone cannot certify actual motor current.')


def with_adc_peak(data):
    data.update(mc_adc_peak_valid=0,mc_adc_peak=None,mc_adc_peak_status='Ожидание захвата АЦП')
    if (data.get('fw_build'),data.get('mc_fw_build')) != (2026102501,2026102502):
        return data
    if data.get('mc_adc_peak_hex','-') == '-':
        if data.get('mc_adc_peak_good',0):
            data['mc_adc_peak_status']='После STOP: принимаются страницы захвата АЦП'
        return data
    try:
        trace=decode_adc_peak_hex(data['mc_adc_peak_hex'])
        data.update(mc_adc_peak_valid=1,mc_adc_peak=trace,
            mc_adc_peak_status=('Захват пика АЦП сохранён' if trace['peak_seen'] else 'Сохранены последние отсчёты: порог пика не достигнут'))
    except (ValueError,TypeError) as exc:
        data['mc_adc_peak_status']='Ошибка записи захвата АЦП: '+str(exc)
    return data
