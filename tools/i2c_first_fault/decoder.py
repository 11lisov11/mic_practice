"""Decode frozen pre-reset I2C records; never infer physical waveform timing."""
import struct
import zlib

CAUSES={2:'NACK',6:'DEADLINE',7:'SETUP',8:'BERR',9:'ARLO',10:'OVR',11:'BUSY',12:'SHORT'}

def crc32c(data):
    crc=0xffffffff
    for byte in data:
        crc^=byte
        for _ in range(8):crc=(crc>>1)^(0x82f63b78 if crc&1 else 0)
    return crc^0xffffffff

def decode(raw,peer,kind):
    if len(raw)!=160 or peer!=2026102604 or kind not in (0,1):raise ValueError('Unsupported I2C fault record')
    w=struct.unpack('<40I',raw)
    cause=w[4]&255;stage=(w[4]>>8)&255;state=(w[4]>>16)&255;n=w[4]>>24
    if w[0]!=0x31434649 or w[1]!=peer or cause not in CAUSES or stage>11 or state>4 or n>3 or not w[32]:
        raise ValueError('Invalid I2C fault record')
    if kind==1 and not(w[16]&32768):raise ValueError('PWM record lacks MOE evidence')
    names={2:'tick_ms',3:'cycles',5:'decision_isr',6:'isr_before_gpio',7:'gpiob_idr',8:'isr_after_gpio',
        9:'cr1',10:'cr2',11:'timingr',12:'gpiob_moder',13:'gpiob_otyper',14:'gpiob_afrh',15:'rcc_ccipr',
        16:'tim1_bdtr',17:'tim1_cnt',18:'tim1_cr1',19:'tim1_arr',20:'tim1_ccr1',21:'tim1_ccr2',22:'tim1_ccr3',
        23:'poll_gap_cycles',24:'max_poll_gap_cycles',25:'attempt_age_cycles',26:'errors_before',27:'reads_before',
        28:'previous_isr',29:'previous_cr2',30:'previous_gpio',31:'previous_cycles',32:'sysclk_hz',33:'rcc_cfgr',
        34:'gpio_sample_cycles',35:'post_reset_isr',36:'post_reset_cr1',37:'post_reset_cr2',38:'post_reset_gpio',39:'post_reset_cycles'}
    result={name:w[i] for i,name in names.items()}
    result.update(kind='first_since_boot' if kind==0 else 'first_with_pwm',cause=CAUSES[cause],cause_code=cause,
        stage=stage,driver_state=state,received_bytes=n,scl=bool(w[7]&(1<<8)),sda=bool(w[7]&(1<<9)),
        pwm_moe=bool(w[16]&32768),poll_gap_us=w[23]*1e6/w[32],attempt_age_us=w[25]*1e6/w[32],
        registers_changed_during_gpio_sample=w[6]!=w[8],record_crc32c=f'{crc32c(raw):08x}',
        limitation='Sequential MMIO snapshot before PE/reset; not an analog waveform or a simultaneous sample of all registers')
    return result

def with_i2c_first_fault(data):
    out=dict(data or {});records=[]
    for kind,key in enumerate(('enc_fault_first_hex','enc_fault_pwm_hex')):
        raw=out.get(key,'-')
        if raw=='-':continue
        try:records.append(decode(bytes.fromhex(raw),int(out.get('mc_fw_build',0)),kind))
        except (ValueError,TypeError,struct.error):
            out['enc_fault_decode_valid']=0;out['enc_fault_records']=[];return out
    out['enc_fault_records']=records;out['enc_fault_decode_valid']=1
    out['enc_fault_capture_status']='Снимок первого сбоя сохранён' if records else 'Ожидание первого сбоя I²C'
    return out
