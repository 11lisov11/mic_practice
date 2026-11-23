def decode_exact_adc_peak_hex(value,expected_build):
    raw=bytes.fromhex(value)
    if len(raw)!=1024 or exact_pc_crc(raw)!=int.from_bytes(raw[60:64],'little'):
        raise ValueError('Exact ADC record length/CRC')
    h=struct.unpack_from('<IHHII4H6I6HI',raw)
    if h[:3]!=(0x31435041,3,16) or h[3]!=expected_build or h[4]!=1:
        raise ValueError('Exact ADC schema/firmware')
    capacity,count,oldest,trigger=h[5:9]
    if capacity!=60 or not 1<=count<=60 or not 0<=oldest<60 or (count<60 and oldest):
        raise ValueError('Exact ADC ring metadata')
    total,first,end,step,pairs,center=h[9:15];offset=list(h[15:19]);arr,flags=h[19:21]
    if not 0<arr<=8191 or any(v>4095 for v in offset) or flags&~0x73f:
        raise ValueError('Exact ADC geometry/flags')
    peak,observer,exact,gap=bool(flags&1),bool(flags&8),bool(flags&16),bool(flags&32)
    result=flags>>8
    if peak and observer or exact and gap or (exact or gap) and not observer:
        raise ValueError('Exact ADC trigger flags')
    if observer and (exact==gap or result not in (1,2,3,4) or exact!=(result==1)):
        raise ValueError('Exact ADC source result')
    if not observer and (pairs or center or first or end or step or result):
        raise ValueError('Unrequested source metadata')
    rows=[]
    for n in range(count):
        slot=(oldest+n)%60;cycles,packed,meta=struct.unpack_from('<I10sH',raw,64+slot*16)
        adcs=[packed[0]|((packed[1]&15)<<8),(packed[1]>>4)|(packed[2]<<4)]
        cc=int.from_bytes(packed[3:],'little')
        if cc>>52:raise ValueError('Reserved packed ADC bits')
        compares=[(cc>>(13*i))&8191 for i in range(4)]
        pair=(meta>>9)&3;quality=meta>>11;bus=meta&511
        counts=None
        if pair<3:
            path1=1 if pair==2 else 0;path2=2 if pair==0 else 3
            phase1=1 if pair==2 else 0;phase2=1 if pair==0 else 2
            counts=[0,0,0];counts[phase1]=offset[path1]-adcs[0];counts[phase2]=offset[path2]-adcs[1]
            counts[3-phase1-phase2]=-counts[phase1]-counts[phase2]
        rows.append(dict(index=n,slot=slot,cycles=cycles,sequence=(total-count+n+1)&0xffffffff,
            raw_adc=adcs,ccr_at_update=compares,offsets_adc=offset,timer_arr=arr,bus_v=bus,pair=pair,
            quality=quality,accepted_by_monitor=quality==1,counts_uvw=counts,
            nominal_currents_a=[v*3.3/(4095*.04*2.1) for v in counts] if counts else None,
            epoch_fault=bool(quality&2),queue_or_sync_fault=bool(quality&4),
            publish_deadline_missed=bool(quality&8),window_or_pack_range_fault=bool(quality&16),
            is_trigger=slot==trigger))
    selected=[];voltage=[]
    if exact:
        locations=[i for i,r in enumerate(rows) if r['slot']==trigger]
        if len(locations)!=1 or locations[0]<24:raise ValueError('Exact ADC source history missing')
        n=locations[0];selected=rows[n-15:n+1];voltage=rows[n-24:n+1]
        if selected[0]['cycles']!=first or selected[-1]['cycles']!=end or step<1:
            raise ValueError('Exact ADC source identity')
        for i,r in enumerate(voltage):
            if r['pair']>2 or r['quality']!=1 or any(v>arr for v in r['ccr_at_update']):
                raise ValueError('Invalid exact source sample')
            if i and not 0<((r['cycles']-voltage[i-1]['cycles'])&0xffffffff)<31875:
                raise ValueError('Discontinuous exact source sample')
        composition=[sum(r['pair']==i for r in selected) for i in range(3)]
        if pairs>>15 or composition!=[(pairs>>(5*i))&31 for i in range(3)]:
            raise ValueError('Exact source pair composition')
        a,b=selected[7]['cycles'],selected[8]['cycles']
        if ((a+((b-a)&0xffffffff)//2)&0xffffffff)!=center:
            raise ValueError('Exact ADC center timestamp')
    elif trigger!=65535 and not any(r['slot']==trigger for r in rows):
        raise ValueError('ADC trigger missing')
    return dict(schema=3,firmware=h[3],capture_id=1,sample_count=count,total_samples=total,
        peak_seen=peak,observer_validity_trigger=observer,post_short=bool(flags&2),no_peak=bool(flags&4),
        source_window_exact=exact,source_window_gap=gap,source_match_result=result,
        source_observer_step=step,requested_first_cycles=first,requested_end_cycles=end,
        source_center_cycles=center,source_pair_counts=[(pairs>>(5*i))&31 for i in range(3)] if exact else None,
        source_samples=selected,source_voltage_history=voltage,samples=rows,scale_qualified=False,
        cpu_hz=170000000,adc_hz=42500000,threshold_counts=626,
        limitation='Diagnostic capture only. ADC counts and modeled PWM voltage do not independently identify true motor parameters, terminal voltage or speed.')

