# Decoder only; no hardware commands. Inserted after current/peak decoders.
def with_zero_history(data):
    import struct
    import math
    data.update(mc_zero_history_valid=0,mc_zero_history=None,
                mc_zero_history_status='Ожидание истории блоков автонуля')
    if (data.get('fw_build'),data.get('mc_fw_build')) != (2026102505,2026102506):
        return data
    value=data.get('mc_zero_history_hex','-')
    if value=='-':
        return data
    try:
        raw=bytes.fromhex(value)
        if len(raw)%43 or not 3<=len(raw)//43<=8:
            raise ValueError('invalid zero-history size')
        count=len(raw)//43
        blocks=[]
        for index in range(count):
            p=raw[43*index:43*(index+1)]
            if (p[:4]!=bytes((0x55,0xaa,0xd9,1)) or p[4:6]!=bytes((index,count))
                or int.from_bytes(p[6:10],'little')!=2026102506
                or p[30:39]!=bytes((3,2,3,8,2,128,0,15,1)) or any(p[25:30])
                or current_crc32c(p[:39])!=int.from_bytes(p[39:43],'little')):
                raise ValueError('invalid zero-history packet/CRC')
            means=struct.unpack_from('<4H',p,10);spans=p[18:22]
            status,q7,path_bits=p[22:25];paths=path_bits&15;span_clipped=path_bits>>4
            stable=status&3;reject=status>>2
            if reject>15 or paths>15 or any(v>4095 for v in (*means,*spans)):
                raise ValueError('invalid zero-history block')
            why=[]
            if reject&1:why.append('оценка 3σ среднего больше 2 отсчётов')
            if reject&2:why.append('средний уровень вне 1600–2500')
            if reject&4:why.append('дрейф средних больше 2 отсчётов')
            if reject&8:why.append('сырой АЦП достиг границы диапазона')
            blocks.append(dict(block=index+1,means_adc=list(means),raw_spans_adc=list(spans),
                stable=stable,reject_flags=reject,failed_paths_mask=paths,
                failed_paths=[name for n,name in enumerate(('U1','V1','V2','W2')) if paths&(1<<n)],
                estimated_3sigma_mean_counts=round(3*math.sqrt(q7/128),3),
                uncertainty_quantized=True,uncertainty_lower_bound=q7==255,
                raw_spans_lower_bound_mask=span_clipped,
                variance_method='max(raw-sample mean variance, four64-sample-group mean variance)',reasons=why))
        data.update(mc_zero_history_valid=1,mc_zero_history=blocks,
            mc_zero_history_status='Блоки нуля: '+' | '.join(
                str(b['block'])+(': '+', '.join(b['reasons'])+' ['+'/'.join(b['failed_paths'])+']'
                    if b['reject_flags'] else ': стабилен '+str(b['stable'])+'/3') for b in blocks))
    except (ValueError,TypeError) as exc:
        data['mc_zero_history_status']='Ошибка истории автонуля: '+str(exc)
    return data
