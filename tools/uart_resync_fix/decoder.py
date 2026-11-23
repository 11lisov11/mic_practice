def uart_reject_status(data):
    """Read-only frozen command-receiver evidence; never authorizes a command."""
    try:
        if _as_int(data or {},'mc_fw_build',0)!=2026101806:
            return {'available':False,'reason':'wrong_peer_build'}
        text=data.get('mc_uart_reject_hex','-')
        if text=='-':return {'available':False,'reason':'not_received'}
        if len(text)!=640 or any(c not in '0123456789abcdefABCDEF' for c in text):
            return {'available':False,'reason':'invalid_hex'}
        raw=bytes.fromhex(text);h=_break_struct.unpack_from('<8I',raw)
        if h[:4]!=(0x31545255,1,320,2026101806) or h[4]>1 or h[5]!=1 or h[7]:
            return {'available':False,'reason':'invalid_record'}
        records=[]
        def crc32c(b):
            crc=0xffffffff
            for x in b:
                crc^=x
                for _ in range(8):crc=(crc>>1)^(0x82f63b78 if crc&1 else 0)
            return crc^0xffffffff
        for k in range(2):
            q=raw[32+144*k:32+144*(k+1)]
            if not h[4+k]:
                if any(q):return {'available':False,'reason':'invalid_record'}
                records.append(None);continue
            m=_break_struct.unpack_from('<14I',q);n=m[2]
            if not 2<=m[1]<=8 or n>43 or m[3]>43 or m[4]>15 or m[5] not in range(256) and m[5]!=0xffffffff or m[6]>2 or m[7]>2 or m[11]>3:
                return {'available':False,'reason':'invalid_record'}
            b=q[56:56+n];marks=q[100:100+n]
            if any(q[56+n:100]) or any(q[100+n:]) or any(x&~15 for x in marks):
                return {'available':False,'reason':'invalid_record'}
            if n==43:
                if m[12]!=int.from_bytes(b[39:43],'little') or m[13]!=crc32c(b[:39]):
                    return {'available':False,'reason':'invalid_record'}
            elif m[12] or m[13]:return {'available':False,'reason':'invalid_record'}
            records.append(dict(tick_ms=m[0],reason_code=m[1],length=n,speculative_prefix=m[3],
                uart_flags=m[4],last_committed_sequence=None if m[5]==0xffffffff else m[5],
                budget_used=m[6],recoverable_losses=m[7],dropped_before=m[8],last_valid_ms=m[9],
                candidate_started_ms=m[10],receiver_flags=m[11],raw_hex=b.hex(),marks_hex=marks.hex(),
                full_frame_crc_matches=None if n!=43 else m[12]==m[13],
                stored_crc=m[12] if n==43 else None,calculated_crc=m[13] if n==43 else None))
        fatal=records[1]
        if fatal['length']==43:
            kind='CRC полного кадра совпал' if fatal['full_frame_crc_matches'] else 'CRC полного кадра не совпал'
        else:kind=f"неполный кандидат/синхронизация ({fatal['length']} байт)"
        summary=f"UART Uno→Nucleo: {kind}; причина {fatal['reason_code']}, бюджет {fatal['budget_used']}/2. Сырые байты сохранены."
        return dict(available=True,reason='saved_command_reject',schema=1,records=records,
            speculative_prefix_expiries=h[6],summary_ru=summary,
            physical_cause_identified=False,limitations=['Parser observation times, not electrical edge timestamps',
            'Only the latest recovered rejection and first fatal rejection are retained until peer reset'])
    except (ValueError,TypeError,OverflowError):return {'available':False,'reason':'invalid_record'}
