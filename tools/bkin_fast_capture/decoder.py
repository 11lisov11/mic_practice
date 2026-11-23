def bkin_wave_status(data):
    """Schema 4: lossless runs of DMA samples, including post-trigger recovery.

    Immutable saved evidence is distinct from freshness of the live peer.
    Neither an IRQ timestamp nor an unfinished LOW is a measured pulse width.
    """
    unknown=0xffffffff
    try:
        if _as_int(data or {}, 'mc_fw_build', 0)!=2026101804:
            return {'available':False,'reason':'wrong_peer_build'}
        text=data.get('mc_break_wave_hex','')
        age=_as_int(data,'mc_break_wave_age_ms',-1)
        if not text or text=='-': return {'available':False,'reason':'not_received'}
        if len(text)!=640 or any(c not in '0123456789abcdefABCDEF' for c in text):
            return {'available':False,'reason':'invalid_hex'}
        if not 0<=age<=unknown: return {'available':False,'reason':'invalid_age'}
        raw=bytes.fromhex(text)
        h=_break_struct.unpack_from('<16I',raw)
        magic,schema,size,tick,period,flags,trigger,samples,n,fall,rise,width,limit,dma,remaining,reserved=h
        invalid=lambda: {'available':False,'reason':'invalid_record'}
        if (magic!=0x314e4b42 or schema!=4 or size!=320 or period!=200 or
            not flags&1 or flags&~1023 or trigger>2048 or samples>trigger+500000 or
            n>32 or limit!=500000 or dma&~15 or remaining>8192 or reserved or
            flags&512 and flags&8 or flags&2 and flags&128): return invalid()
        runs=[]; total=0; previous=2; ef=er=unknown
        for i in range(32):
            high,count=_break_struct.unpack_from('<2I',raw,64+8*i)
            if i>=n:
                if high or count: return invalid()
                continue
            if high>1 or not count or high==previous or count>samples-total: return invalid()
            if not high and (ef==unknown or total<=trigger): ef,er=total,unknown
            elif high and ef!=unknown and er==unknown: er=total
            runs.append({'level':high,'samples':count,'from_us':(total-trigger)/5,'to_us':(total+count-trigger)/5})
            total+=count; previous=high
        if (total!=samples or fall!=ef or rise!=er or bool(flags&4)!=(rise!=unknown) or
            bool(flags&128)!=(fall==0) or bool(flags&2)!=(fall not in (unknown,0))): return invalid()
        errors=bool(flags&(16|32|64))
        expected_width=rise-fall if fall not in (unknown,0) and rise!=unknown and not errors else unknown
        if width!=expected_width: return invalid()
        if flags&512:
            if (samples<trigger+321 or bool(flags&256)!=(fall==unknown) or
                fall!=unknown and (rise==unknown or samples<rise+321)): return invalid()
        elif flags&256: return invalid()
        if not flags&(512|8|16|32|64): return invalid()
        complete=width!=unknown and not errors
        if errors:
            reason='dma_error' if flags&16 else 'sampling_overrun' if flags&32 else 'run_capacity_exceeded'
            summary='Запись PA6 неполная: ошибка DMA / потеря отсчётов / переполнение переходов. Длительность не подтверждена.'
        elif flags&256:
            reason='low_not_observed'
            summary='Break сохранён, LOW на PA6 не попал в отсчёты. Длительность неизвестна (разрешение 0,2 мкс).'
        elif flags&8:
            reason='timeout_low_unfinished' if rise==unknown else 'timeout_post_incomplete'
            summary=('PA6 не завершил импульс за окно 100 мс. Запись обрезана по тайм-ауту; полной длительности нет.'
                if rise==unknown else f'Оба фронта PA6 записаны: LOW {width/5:g} мкс. Окно 100 мс закончилось до завершения участка после импульса.')
        elif flags&128:
            reason='missing_falling_edge'
            summary='Возврат PA6 в HIGH записан, но начало LOW осталось за границей записи. Полная длительность неизвестна.'
        else:
            reason='complete_pulse'
            summary=f'Импульс PA6 записан целиком: LOW {width/5:g} мкс, оба фронта и участок после возврата HIGH. Разрешение 0,2 мкс.'
        peer_age=_as_int(data,'mc_age_ms',_as_int(data,'bp_age_ms',999999))
        return {'available':True,'reason':reason,'schema':4,'stored_record':True,
            'age_since_delivery_ms':age,'live_peer_fresh':0<=peer_age<300,
            'event_tick_ms':tick,'sample_period_us':0.2,'sample_rate_hz':5000000,
            'sample_count':samples,'trigger_index':trigger,'runs':runs,
            'pulse_complete':complete,'pulse_width_us':None if width==unknown else width/5,
            'post_complete':bool(flags&512),
            'falling_edge_us':None if not flags&2 else (fall-trigger)/5,
            'rising_edge_us':None if rise==unknown else (rise-trigger)/5,
            'left_censored':bool(flags&128),'right_censored':rise==unknown and fall!=unknown,
            'timeout':bool(flags&8),'dma_error':bool(flags&16),'sampling_overrun':bool(flags&32),
            'run_overflow':bool(flags&64),'flags':flags,'dma_flags_raw':dma,
            'dma_remaining':remaining,'summary_ru':summary,
            'trace_reference':'200-ns DMA sample grid relative to Break IRQ publication; IRQ latency is not an electrical-edge timestamp',
            'limitations':['Pulses shorter than 0.2 us may be missed; edge positions are quantized to the sample grid',
                'First event since boot; STOP/CLEAR do not overwrite it',
                'Requested DMA rate requires hardware throughput validation; DMA flags cannot detect every missed timer request',
                'Only PA6/SD is measured; width alone cannot uniquely identify overcurrent, driver undervoltage, or interference']}
    except (ValueError,TypeError,OverflowError):
        return {'available':False,'reason':'invalid_metadata'}
