def precheck(s, max_vdc=20):
    """Programming gate only; latched ESTOP/protection need not be cleared.

    Physical mains-off and independent meter confirmation are required by the
    caller. This does not authorize START or overriding any motor protection.
    """
    try:
        if max_vdc != 20: return False, 'unsupported programming threshold'
        if (s['fw_build'],s['mc_fw_build']) not in ((2026101805,2026101804),(2026101807,2026101806)):
            return False,'unexpected firmware pair'
        if s['state']!='SAFE' or s['pwm']!=0 or s['hmi_hv_armed']!=0 or int(s['bp_status'])&0x22:
            return False,'outputs or run request active'
        if s['estop'] not in (0,1): return False,'invalid ESTOP metadata'
        if s['rpc_schema_version']!=3 or s['mc_capabilities']!=1 or s['bp_mcsdk_telemetry']!=1:
            return False,'unexpected measurement contract'
        for key in ('vdc','bp_vdc'):
            if type(s[key]) not in (int,float) or not math.isfinite(s[key]) or not 0<=s[key]<=max_vdc:
                return False,'bus above programming limit: '+key
        for key in ('mc_age_ms','bp_vbus_age_ms','bp_temp_age_ms'):
            if type(s[key]) not in (int,float) or not math.isfinite(s[key]) or not 0<=s[key]<300:
                return False,'stale measurement: '+key
        if s['bp_vbus_valid']!=1 or s['bp_temp_valid']!=1 or s['bp_temp_fault']!=0:
            return False,'invalid measurement or active temperature fault'
        if type(s['bp_vbus_raw']) is not int or not 0<=s['bp_vbus_raw']<=max_vdc*10:
            return False,'raw bus word above programming limit'
        for key in ('mc_uart_error_flags','bp_uart_error_flags'):
            if s[key]!=0: return False,'active UART hardware error: '+key
        # Resetting the Uno while Nucleo stays powered latches its command
        # watchdog. Fresh OFF replies remain usable for programming. Preserve
        # this evidence instead of sending CLEAR just to satisfy an installer.
        reset_timeout=(s.get('mc_transport_fault')==7 and s.get('bp_transport_fault')==7
            and s.get('mc_fault')==2 and s.get('bp_fault')==2
            and s.get('mc_last_bad_reason')==13
            and s.get('mc_last_uart_error_flags')==0)
        # A saved CRC latch need not be CLEARed for reprogramming on the
        # physically deenergized bench. This does not authorize motor START.
        known_crc=(s.get('mc_transport_fault')==2 and s.get('bp_transport_fault')==2
            and s.get('mc_fault') in (1,3) and s.get('bp_fault') in (1,3)
            and s.get('mc_fault_reason')==1 and s.get('mc_last_bad_reason')==1
            and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0
            and s.get('mc_last_uart_error_flags')==0)
        for key in ('mc_transport_fault','bp_transport_fault'):
            if s[key]!=0 and not (reset_timeout or known_crc): return False,'unrecognized transport latch: '+key
        for key in ('precharge','pfc','brake','bp_ext'):
            if s[key]!=0:return False,'service output active: '+key
        return True,'disarmed, fresh low bus; latched protection retained'
    except (KeyError,ValueError,TypeError,OverflowError):
        return False,'invalid or missing programming telemetry'
