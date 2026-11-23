def clear_recovery_status(kv):
    """First CLEAR attempt, stored evidence; ACCEPTED does not mean protections ready."""
    result={'clear_recovery':{'available':False,'reason':'not_received'}}
    raw=kv.get('mc_clear_recovery_hex','-')
    if raw in ('','-'):return result
    try:
        p=bytes.fromhex(raw);peer=int(kv.get('bp_fw_build',kv.get('mc_fw_build','0')))
        if (len(p)!=43 or p[:6]!=bytes([0x55,0xaa,0xee,1,0,0]) or peer!=2026111606
            or int.from_bytes(p[6:10],'little')!=peer or p[37] not in range(1,6)
            or p[38]!=0 or p[26]&0xc0 or current_crc32c(p[:39])!=int.from_bytes(p[39:],'little')):
            raise ValueError('invalid CLEAR record identity/CRC')
        u=lambda i:int.from_bytes(p[i:i+4],'little')
        names={1:'ACK_ACCEPTED',2:'TX_BLOCKED',3:'BREAK_NOT_RELEASED',4:'MCSDK_ACK_REJECTED',5:'LOCAL_STOP_BLOCKED'}
        messages={1:'Запрос CLEAR принят; готовность защит проверяется отдельно',
            2:'CLEAR отклонён: ошибка, тайм-аут или переполнение UART TX',
            3:'CLEAR отклонён: SD/Break не отпущен либо выходы ещё активны',
            4:'CLEAR отклонён: MCSDK не принял подтверждение аварии',
            5:'CLEAR отклонён: локальная остановка не отпущена'}
        result['clear_recovery']=dict(available=True,stored_record=True,first_since_boot=True,
            firmware=peer,tick_ms=u(10),tx_head=u(14),tx_tail=u(18),tx_pending=(u(14)-u(18))&0xffffffff,
            tx_started_ms=u(22),tx_active=bool(p[26]&1),tx_hard_error=bool(p[26]&2),
            tx_late=bool(p[26]&4),sd_high_at_attempt=bool(p[26]&8),BIE_at_attempt=bool(p[26]&16),
            MOE_at_attempt=bool(p[26]&32),command_sequence=p[27],timer_SR=u(28),
            current_faults_at_attempt=int.from_bytes(p[32:34],'little'),
            occurred_faults_at_attempt=int.from_bytes(p[34:36],'little'),motor_state_at_attempt=p[36],
            result_code=p[37],result=names[p[37]],summary_ru=messages[p[37]],
            protection_readiness_confirmed=False,limitation='Stored first attempt; live SD, masks and BIE remain mandatory')
    except (ValueError,TypeError,OverflowError):
        result['clear_recovery']={'available':False,'reason':'invalid_record'}
    return result
