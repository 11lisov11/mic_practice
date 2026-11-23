def decode_i2c_wire(raw, parent_raw=None):
    if len(raw)!=1072:raise ValueError('Wrong I2C waveform length')
    w=[int.from_bytes(raw[i:i+4],'little') for i in range(0,48,4)]
    magic,fmt,size,peer,parent,hz,period,n,freeze,request,gpio,flags=w
    if (magic!=0x31574349 or fmt!=1 or size!=1072 or peer!=2026102812 or
        hz!=170000000 or period!=20 or not 0<=n<=4096 or flags&~15 or
        bool(flags&1)!=(n==4096) or flags&12 not in (4,8)):
        raise ValueError('Unsupported I2C waveform header')
    manual=bool(flags&4)
    if manual:
        if parent:raise ValueError('Manual waveform must have no fault parent')
    else:
        if parent_raw is None or len(parent_raw)!=160 or crc32c(parent_raw)!=parent:
            raise ValueError('PWM waveform parent not yet received or CRC mismatch')
        decode(parent_raw,peer,1)
        if int.from_bytes(parent_raw[4:8],'little')!=peer or not int.from_bytes(parent_raw[64:68],'little')&32768:
            raise ValueError('Wrong peer or inactive PWM parent')
        if int.from_bytes(parent_raw[12:16],'little')!=request:raise ValueError('Wrong event timestamp')
    samples=[(raw[48+i//4]>>((i%4)*2))&3 for i in range(n)]
    if any(((raw[48+i//4]>>((i%4)*2))&3) for i in range(n,4096)):
        raise ValueError('Nonzero unsampled positions')
    lag=(freeze-request)&0xffffffff
    edges=[];starts=[];stops=[];byte_values=[];bits=[];in_frame=False
    for i in range(1,n):
        old,new=samples[i-1],samples[i]
        if old==new:continue
        if (old&1) and (new&1) and bool(old&2)!=bool(new&2):
            if old&2:starts.append(i);bits=[];in_frame=True
            else:stops.append(i);bits=[];in_frame=False
        if not(old&1) and (new&1) and in_frame:
            bits.append(1 if new&2 else 0)
            if len(bits)==9:
                value=0
                for bit in bits[:8]:value=(value<<1)|bit
                byte_values.append(dict(sample=i,value=value,ack=bits[8]==0));bits=[]
        edges.append(dict(sample=i,scl=bool(new&1),sda=bool(new&2)))
    return dict(peer_build=peer,parent_crc32c=f'{parent:08x}',record_crc32c=f'{crc32c(raw):08x}',
      manual=manual,dma_error=bool(flags&2),full_history=bool(flags&1),samples=n,
      nominal_sample_hz=hz/period,nominal_history_us=n*period*1e6/hz,
      freeze_lag_us=lag*1e6/hz,freeze_gpio=gpio,freeze_cycles=freeze,request_cycles=request,
      starts=starts,stops=stops,bytes=byte_values,transitions=edges,
      digital_record_valid=not bool(flags&2) and n>0,hardware_timing_qualified=False,
      limitation='Digital GPIO samples at nominal timer cadence. DMA latency/jitter and analog voltage/rise time are not measured; sub-sample glitches may be missed.')

def with_i2c_wire(data):
    out=dict(data);out.update(enc_wire_decode_valid=1,enc_wire_record=None)
    text=out.get('enc_wire_hex','-')
    if text in ('-',None,''):return out
    try:
        raw=bytes.fromhex(text)
        if crc32c(raw)!=int(out.get('enc_wire_crc','-'),16):raise ValueError('Wrong waveform CRC')
        if int(out.get('mc_fw_build',0))!=2026102812:raise ValueError('Wrong live peer')
        parent=None
        if len(raw)>=48 and int.from_bytes(raw[44:48],'little')&8:
            if out.get('enc_fault_decode_valid')!=1:raise ValueError('Invalid parent fault')
            parent=bytes.fromhex(out.get('enc_fault_pwm_hex','-'))
        out['enc_wire_record']=decode_i2c_wire(raw,parent)
    except (TypeError,ValueError) as exc:
        out.update(enc_wire_decode_valid=0,enc_wire_error=str(exc))
    return out
