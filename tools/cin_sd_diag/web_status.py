"""Decode a paired OFF-only observation; ADC voltage is explicitly approximate."""
def cin_sd_status(kv):
    result={'cin_diagnostic_only':1,'cin_sd':{'available':False,'reason':'not_received'}}
    raw=str(kv.get('cin_packet_hex','-'))
    if raw=='-':return result
    try:
        p=bytes.fromhex(raw)
        def u(i):return int.from_bytes(p[i:i+4],'little')
        crc=0xffffffff
        for b in p[:39]:
            crc^=b
            for _ in range(8):crc=(crc>>1)^(0x82f63b78 if crc&1 else 0)
        fw=int(kv.get('bp_fw_build',0));flags=p[4];reason=p[38]
        counts=int.from_bytes(p[22:24],'little');ref=int.from_bytes(p[24:26],'little')
        if (len(p)!=43 or p[:4]!=bytes([0x55,0xaa,0xeb,1]) or p[5] or flags&~7 or
            u(6)!=fw or fw!=2026103102 or not u(10) or (crc^0xffffffff)!=u(39) or
            counts>4095 or ref!=3290 or reason>5 or bool(flags&1)!=(reason==0) or
            (bool(flags&1) and ((u(18)-u(14))&0xffffffff)>=2)):raise ValueError('invalid_packet')
        fresh=str(kv.get('cin_fresh','0'))=='1'
        valid=fresh and bool(flags&1)
        mv=counts*ref/4095 if valid else None
        sd_before='HIGH' if flags&2 else 'LOW';sd_after='HIGH' if flags&4 else 'LOW'
        # The datasheet gives a 460..560mV CIN threshold, not exactly 510mV.
        # Leave margin for the nominal reference, ADC/input errors and loading.
        band=('below_threshold_band' if mv<420 else 'above_threshold_band' if mv>600 else 'threshold_or_uncertain') if valid else 'invalid'
        reason_name=('OK','ADC_TIMEOUT','ADC_OVERRUN','NOT_OFF','ADC_CONFIG','ADC_BUSY')[reason]
        summary=(f'CIN ≈ {mv/1000:.3f} В; SD {sd_before}→{sd_after}' if valid else f'CIN: {reason_name}; '+('нет достоверного отсчёта' if fresh else 'нет свежего отсчёта'))
        result['cin_sd']=dict(available=True,fresh=fresh,valid=valid,raw_adc=counts,
            voltage_mv_approx=mv,reference_mv_nominal=ref,reference_calibrated=False,
            sequence=u(10),start_tick_ms=u(14),end_tick_ms=u(18),conversion_cycles=u(26),
            sd_before=sd_before,sd_after=sd_after,timeouts=u(30),errors=u(34),reason_code=reason,
            threshold_band=band,summary_ru=summary,reason=reason_name,physical_cause_identified=False,connection_verified=False,
            limitation='OFF-only, 10 Гц; не осциллограф. VREF принято 3,290 В; подключение провода отдельно не определяется. Низкий CIN не доказывает UVLO.')
        result.update(cin_packet_hex=raw,cin_good=int(kv.get('cin_good',0)),cin_bad=int(kv.get('cin_bad',0)))
    except (ValueError,TypeError,IndexError,OverflowError):
        result['cin_sd']={'available':False,'reason':'invalid_packet'}
    return result
