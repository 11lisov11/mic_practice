def decode_i2c_release(raw,parent_raw,peer,kind):
    if peer!=2026102706 or len(raw)!=100 or len(parent_raw)!=160 or kind not in (0,1):
        raise ValueError('Unsupported PE release extension')
    decode(parent_raw,peer,kind)
    w=struct.unpack('<25I',raw);parent=struct.unpack('<40I',parent_raw)
    flags=w[3]&255;count=(w[3]>>8)&255;result=(w[3]>>16)&255;hz=w[6]
    if (w[0]!=0x31525053 or w[1]!=peer or w[3]>>24 or flags&~15 or count>3 or result>3
        or hz<1000000 or crc32c(raw[:96])!=w[24] or w[2]!=crc32c(parent_raw)
        or parent[0]!=0x31434649 or parent[1]!=peer or w[7]!=parent[2]
        or w[4]!=parent[39] or w[5]!=parent[38] or hz!=parent[32]):
        raise ValueError('Invalid PE release identity/CRC/link')
    if bool(count)!=bool(flags&1) or (not count and not(flags&4)):
        raise ValueError('Missing PE release observation')
    if flags&2 and (flags&12 or count!=2):raise ValueError('Invalid late sample flags')
    complete=not(flags&12) and (count==3 or (count==2 and flags&2))
    if not complete and not(flags&12):raise ValueError('Unfinished extension published')
    samples=[];levels=set()
    for i in range(3):
        s=w[8+5*i:13+5*i]
        if i>=count:
            if any(s):raise ValueError('Nonzero unused sample')
            continue
        cycles,isr,cr1,cr2,gpio=s
        if cr1&1:raise ValueError('I2C was re-enabled during release observation')
        if i:
            dt=((cycles-w[8])&0xffffffff)//(hz//1000000)
            if not (5 if i==1 else 20)<=dt<=1000:raise ValueError('Invalid sample timing')
        levels.add(bool(gpio&256))
        samples.append(dict(index=i,cycles=cycles,isr=isr,cr1=cr1,cr2=cr2,gpiob_idr=gpio,
            scl=bool(gpio&256),sda=bool(gpio&512),pe=False,
            after_PE0_us=((cycles-w[23])&0xffffffff)*1e6/hz))
    expected=0 if not complete else 3 if len(levels)==2 else 1 if True in levels else 2
    if result!=expected:raise ValueError('Inconsistent observed levels')
    labels={0:'Наблюдение после PE=0 неполное',1:'После PE=0: SCL HIGH',2:'После PE=0: SCL LOW',3:'После PE=0: SCL менял уровень'}
    return dict(kind='first_since_boot' if kind==0 else 'first_with_pwm',result=result,
        summary_ru=labels[result],flags=flags,count=count,complete=bool(complete),late_poll=bool(flags&2),
        cancelled=bool(flags&4),timeout=bool(flags&8),parent_crc32c=f'{w[2]:08x}',record_crc32c=f'{crc32c(raw):08x}',
        terminal_cycles=w[4],terminal_gpio=w[5],pe_off_cycles=w[23],samples=samples,
        pe_was_enabled_before_disable=bool(parent[36]&1),scl_at_terminal=bool(w[5]&256),sda_at_terminal=bool(w[5]&512),
        immediate_delay_us=samples[0]['after_PE0_us'] if samples else None,
        source_attribution_proven=False,
        limitation='Sequential digital samples with actual times; neither an analog waveform nor proof of which device caused LOW')

def with_i2c_release(data):
    out=dict(data);records=[]
    for kind,(key,parent_key) in enumerate((('enc_release_first_hex','enc_fault_first_hex'),('enc_release_pwm_hex','enc_fault_pwm_hex'))):
        text=out.get(key,'-')
        if text=='-':continue
        try:
            if out.get('enc_fault_decode_valid')!=1:raise ValueError('Invalid parent capture')
            records.append(decode_i2c_release(bytes.fromhex(text),bytes.fromhex(out.get(parent_key,'-')),int(out.get('mc_fw_build',0)),kind))
        except (ValueError,TypeError,struct.error) as exc:
            out.update(enc_release_decode_valid=0,enc_release_records=[],enc_release_status='Ошибка дополнения PE=0: '+str(exc));return out
    selected=next((r for r in records if r['kind']=='first_with_pwm'),records[0] if records else None)
    out.update(enc_release_decode_valid=1,enc_release_records=records,
        enc_release_status=selected['summary_ru'] if selected else 'Ожидание захвата после PE=0')
    return out
