"""Observational reset decoding. No reset, acknowledgement or motor commands."""
def _boot_linux_id():
    try:
        with open('/proc/sys/kernel/random/boot_id', encoding='ascii') as stream:
            value=stream.read().strip()
        return value if len(value)==36 else None
    except OSError:
        return None


BOOT_LINUX_ID=_boot_linux_id()


def boot_wire_status(kv):
    result={'linux_boot_id':BOOT_LINUX_ID,'native_boot':{'available':False,'reason':'not_received'}}
    try:
        raw=str(kv.get('mc_boot_packet_hex','-'))
        if raw=='-':return result
        p=bytes.fromhex(raw)
        def crc(data):
            c=0xffffffff
            for byte in data:
                c^=byte
                for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
            return c^0xffffffff
        def u(offset):return int.from_bytes(p[offset:offset+4],'little')
        fw=int(kv.get('bp_fw_build',kv.get('mc_fw_build','0')))
        if len(p)!=43 or p[:6]!=bytes.fromhex('55aae9010100') or p[38] or crc(p[:39])!=u(39) or u(6)!=fw:
            raise ValueError('invalid_frame_or_peer')
        seq,csr,previous,flags,tag,record_crc,tick=[u(i) for i in range(10,38,4)]
        words=[0x31525442,fw,seq,csr,previous,flags,tag]
        if not seq or flags&~15 or crc(b''.join(v.to_bytes(4,'little') for v in words))!=record_crc:
            raise ValueError('invalid_early_record')
        names=[name for mask,name in ((1<<25,'OPTION_BYTES'),(1<<26,'NRST_FLAG'),
              (1<<27,'POWER_ON_OR_BROWNOUT'),(1<<28,'SOFTWARE'),(1<<29,'IWDG'),
              (1<<30,'WWDG'),(1<<31,'LOW_POWER')) if csr&mask]
        fresh=str(kv.get('mc_boot_fresh','0'))=='1'
        continuity=bool(flags&1 and flags&2 and not csr&(1<<27))
        labels={'OPTION_BYTES':'загрузка option bytes','NRST_FLAG':'флаг NRST',
                'POWER_ON_OR_BROWNOUT':'подача питания или просадка напряжения',
                'SOFTWARE':'программный сброс','IWDG':'IWDG','WWDG':'WWDG','LOW_POWER':'low-power reset'}
        text=', '.join(labels[n] for n in names) or 'флаги причины отсутствуют'
        if tag==0x4D435031 and csr&(1<<28):text+='; команда MCSDK SW_RESET'
        if not continuity:text+='; предыдущая история не подтверждена'
        if not fresh:text+='; сохранённая запись, не свежий статус'
        result.update(mc_boot_packet_hex=raw,mc_boot_fresh=int(fresh),
            native_boot=dict(available=True,fresh=fresh,firmware=fw,
            retained_sequence=seq,sequence_is_power_cycle_persistent=False,
            csr_raw=csr,previous_csr_raw=previous,flags=flags,causes=names,
            previous_flags_cleared=bool(flags&2),current_flags_cleared=bool(flags&4),
            previous_boot_continuity=continuity,software_request_tag=tag,
            early_record_crc=record_crc,native_tick_ms=tick,summary_ru=text,
            exact_physical_cause_identified=False,
            limitation='BOR не отличает включение от просадки; NRST может сопутствовать другим причинам; первая запись может содержать накопленные флаги.'))
    except (ValueError,TypeError,OverflowError):
        result['native_boot']={'available':False,'reason':'invalid_record'}
    return result
