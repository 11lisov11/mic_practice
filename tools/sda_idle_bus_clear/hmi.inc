def with_bus_clear(data):
    out=dict(data);text=out.get('enc_bus_clear_hex','-')
    out.update(enc_bus_clear_record=None,enc_bus_clear_decode_valid=1)
    if text=='-':return out
    try:
        b=bytes.fromhex(text);peer=int(out.get('mc_fw_build',0))
        if (peer!=2026102708 or len(b)!=43 or b[:4]!=bytes((0x55,0xaa,0xde,1)) or
            struct.unpack_from('<I',b,6)[0]!=peer or current_crc32c(b[:39])!=int.from_bytes(b[39:],'little') or
            not 1<=b[4]<=6 or b[5]>9 or any(x>3 for x in b[10:13]) or b[13] or any(b[26:39]) or
            int.from_bytes(b[14:18],'little')>25000):raise ValueError('Invalid bus clear frame')
        result=b[4]
        if (result<=2 and b[12]!=3) or (result==1 and b[5]) or (result==2 and not b[5]):raise ValueError('Invalid bus clear result')
        parent=bytes.fromhex(out.get('enc_fault_first_hex','-'))
        if out.get('enc_fault_decode_valid')!=1 or crc32c(parent)!=int.from_bytes(b[22:26],'little'):raise ValueError('Wrong frozen parent')
        names={1:'I²C: линии освободились при переключении GPIO',2:'I²C: шина освобождена тактами SCL',3:'I²C: SDA осталась LOW после 9 тактов',4:'I²C: SCL не поднимается',5:'I²C: восстановление просрочено',6:'I²C: восстановление отменено'}
        out['enc_bus_clear_record']=dict(result=result,pulses=b[5],before_lines=b[10],gpio_release_lines=b[11],after_lines=b[12],duration_us=int.from_bytes(b[14:18],'little'),begin_cycles=int.from_bytes(b[18:22],'little'),parent_crc32c=b[22:26][::-1].hex(),summary_ru=names[result],read_only_target_registers=True)
    except (ValueError,TypeError,struct.error) as exc:
        out.update(enc_bus_clear_decode_valid=0,enc_bus_clear_error=str(exc))
    return out
