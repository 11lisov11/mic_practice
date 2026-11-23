def repeat_capture_status(kv):
    """Independent first-after-CLEAR evidence. No interpretation of unwired PA4."""
    result={'repeat_break':{'available':False,'reason':'not_received'}}
    try:
        raw=bytes.fromhex(str(kv.get('repeat_meta_hex','-')))
        def u(i):return int.from_bytes(raw[i:i+4],'little')
        def crc(b):
            c=0xffffffff
            for v in b:
                c^=v
                for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
            return c^0xffffffff
        state=raw[4];flags=raw[5];peer=int(kv.get('bp_fw_build',0));age=int(kv.get('repeat_meta_age_ms',999999))
        if (len(raw)!=43 or raw[:4]!=bytes.fromhex('55aaed01') or state>4 or flags&~3 or raw[38] or
            peer!=2026111402 or u(6)!=peer or crc(raw[:39])!=u(39) or (state==2 and (flags!=3 or not u(22)))):
            raise ValueError('invalid_repeat_metadata')
        boot_hex=str(kv.get('mc_boot_packet_hex','-'))
        boot=bytes.fromhex(boot_hex) if boot_hex!='-' else b''
        boot_info=boot_wire_status(kv).get('native_boot',{})
        epoch_ok=(boot_info.get('available') and boot_info.get('fresh') and
                  len(boot)==43 and boot[:4]==bytes.fromhex('55aae901') and
                  crc(boot[:39])==int.from_bytes(boot[39:43],'little') and
                  int.from_bytes(boot[6:10],'little')==peer and
                  int.from_bytes(boot[30:34],'little')==u(34) and str(kv.get('mc_boot_fresh','0'))=='1')
        fresh=0<=age<2000 and 0<=int(kv.get('bp_age_ms',999999))<300 and epoch_ok
        names=('WAIT_FIRST_CLEAR','ARMED','CAPTURED','CAPTURE_ERROR','FIRST_RECORD_PENDING')
        descriptions=('Повторный Break: ожидается CLEAR после первого снимка',
                      'Повторный Break: захват вооружён',
                      'Повторный Break: событие сохранено',
                      'Повторный Break: ошибка захвата; длительность не подтверждена',
                      'Повторный Break: первый снимок ещё не готов; захват не вооружён')
        first_hex=str(kv.get('mc_break_wave_hex','-'))
        first=bytes.fromhex(first_hex) if first_hex!='-' else b''
        first_ok=len(first)==320 and crc(first)==u(26)
        item=dict(available=True,fresh=fresh,state=names[state],state_code=state,flags=flags,
            clear_rearm_tick_ms=u(10),armed_tick_ms=u(14),irq_count_before=u(18),event_irq_count=u(22),
            first_wave_crc32c=u(26),event_tick_ms=u(30),boot_record_crc32c=u(34),epoch_matches=epoch_ok,
            first_wave_preserved=first_ok if state in (1,2,3) else None,
            summary_ru=descriptions[state]+('' if fresh else '; метаданные устарели'),
            physical_cause_identified=False,TP23_connection_verified=False,
            limitation='PA4 требует отдельного подтверждённого подключения TP23. Сохранённая запись и свежесть связи различаются.')
        wave_hex=str(kv.get('mc_repeat_wave_hex','-'));wave=None
        if wave_hex!='-':
            wave_data=dict(mc_fw_build=peer,mc_age_ms=int(kv.get('bp_age_ms',999999)),
                mc_break_wave_hex=wave_hex,mc_break_wave_age_ms=int(kv.get('mc_repeat_wave_age_ms',999999)))
            wave=dual_sd_wave_status(wave_data)
        snapshot=next((x for x in break_wire_status(kv)['mc_break_snapshots'] if x['kind']=='first_after_CLEAR'),None)
        coherent=(state==2 and first_ok and wave and wave.get('available') and snapshot and snapshot.get('captured') and
                  wave.get('event_tick_ms')==u(30)==snapshot['raw']['tick_ms'] and
                  ((u(30)-u(14))&0xffffffff)<0x80000000 and u(22)>=u(18))
        item.update(wave=wave,snapshot=snapshot,records_coherent=bool(coherent),
                    complete_window=bool(coherent and wave.get('post_complete')),
                    live_usable=bool(fresh and coherent and wave.get('post_complete')))
        if state==2 and not coherent:item['summary_ru']='Повторный Break: ожидается согласованный комплект метаданных, снимка и осциллограммы'
        elif state==2 and not wave.get('post_complete'):item['summary_ru']='Повторный Break: сохранено неполное окно; длительность не подтверждена'
        result['repeat_break']=item
    except (ValueError,TypeError,IndexError,OverflowError):
        result['repeat_break']={'available':False,'reason':'invalid_or_missing_repeat_metadata'}
    return result
