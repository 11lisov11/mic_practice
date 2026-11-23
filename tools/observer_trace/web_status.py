"""Frozen observer diagnostics; all speeds/currents are model estimates."""
def decode_observer_trace_hex(value,expected):
    import struct
    import math
    raw=bytes.fromhex(value)
    if len(raw)!=1696:raise ValueError('observer record length')
    header=struct.unpack_from('<16I',raw)
    magic,schema,fw,size,capacity,count,oldest,stride,total,valid,invalid,loss,loss_step,flags,fault,want=header
    if (magic,schema,fw,size,capacity)!=(0x3144534f,1,expected,96,16) or not 1<=count<=16 or not 0<=oldest<16:
        raise ValueError('observer record ABI/peer/count')
    if not flags&1 or flags&~3 or loss not in (0,1) or valid+invalid!=total or count>total or stride!=334:
        raise ValueError('observer record counters/flags')
    c=0xffffffff
    for i,byte in enumerate(raw):
        c^=0 if 60<=i<64 else byte
        for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
    if c^0xffffffff!=want:raise ValueError('observer record CRC')
    reasons={1:'контур не работает',2:'профиль не разрешён',4:'меньше 500 шагов',8:'авария контура',
             16:'поток не выше половины задания',32:'NIS не меньше 25',64:'нечисловое значение'}
    def sample(offset):
        u=struct.unpack_from('<8I14f2I',raw,offset)
        cycles,steps,why,cs,ca,seq,adc,bin_tick=u[:8]
        if why&~127 or u[-1] not in (0,1):raise ValueError('observer sample flags')
        floats=[v if math.isfinite(v) else None for v in u[8:22]]
        rpm,fa,fb,nis,id_,iq,idref,iqref,reference,ia,ib,va,vb,dt=floats
        flux=math.hypot(fa,fb) if fa is not None and fb is not None else None
        return dict(cycles=cycles,steps=steps,reason_mask=why,estimate_valid=why==0,
            reasons_ru=[text for bit,text in reasons.items() if why&bit],
            control_sample_sequence=cs,control_adc_cycles=ca,observer_sample_sequence=seq,
            observer_adc_cycles=adc,bin_cycles=bin_tick,rpm_est=rpm,
            flux_alpha_wb=fa,flux_beta_wb=fb,flux_wb=flux,nis=nis,
            id_A=id_,iq_A=iq,id_ref_A=idref,iq_ref_A=iqref,reference_hz=reference,
            observer_ia_A=ia,observer_ib_A=ib,input_va_V=va,input_vb_V=vb,dt_s=dt,
            observer_fault=u[-2],published=bool(u[-1]))
    rows=[sample(64+96*((oldest+i)%16)) for i in range(count)]
    first=sample(64+96*16) if loss else None
    if first and first['steps']!=loss_step:raise ValueError('observer loss step')
    return dict(available=True,schema=schema,firmware=fw,count=count,total_observer_samples=total,
        valid_samples=valid,invalid_samples=invalid,first_loss=first,control_fault=fault,
        record_stride_steps=stride,samples=rows,
        summary_ru=('Первый отказ оценки: '+', '.join(first['reasons_ru'])) if first else 'После достоверной оценки отказ не записан',
        limitation='Id/Iq и задания относятся к последнему fast-кадру входного bin; поток/NIS — после шага наблюдателя. Это разные явно помеченные моменты. Значения по номинальному масштабу; фактическая скорость независимо не измерена.')


def with_observer_trace(data):
    value=data.get('mc_observer_trace_hex','-')
    data['observer_trace']={'available':False,'reason':'not_received'}
    if value in ('-',''):return data
    try:data['observer_trace']=decode_observer_trace_hex(value,int(data['mc_fw_build']))
    except (ValueError,TypeError,OverflowError):data['observer_trace']={'available':False,'reason':'invalid_record'}
    return data
