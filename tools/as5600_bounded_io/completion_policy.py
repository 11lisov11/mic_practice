def bounded_run_complete(data, before, limit_s):
    """Accept late delivery of one completed MCU run, never initiate/retry it.

    Caller must also pass the existing runtime voltage/temperature/link gates.
    Times describe MCU dispatch, not a qualified oscilloscope measurement.
    """
    if not data or not before or type(limit_s) not in (int, float) or not math.isfinite(limit_s) or limit_s<=0:
        return False
    if (data.get('fw_build'),data.get('mc_fw_build'))!=(2026102516,2026102510):
        return False
    keys=('run_id','run_start_ms','run_stop_ms','run_limit_ms','run_elapsed_ms','run_reason')
    if any(type(data.get(k)) is not int or not 0<=data[k]<=0xffffffff for k in keys):
        return False
    if type(before.get('run_id')) is not int or data['run_id']!=((before['run_id']+1)&0xffffffff):
        return False
    limit=round(limit_s*1000)
    return (data['run_reason']==1 and data['run_limit_ms']==limit
        and limit<=data['run_elapsed_ms']<=limit+100
        and ((data['run_stop_ms']-data['run_start_ms'])&0xffffffff)==data['run_elapsed_ms']
        and data.get('state')=='SAFE' and data.get('pwm')==0 and data.get('estop')==0
        and data.get('bp_status',0x22)&0x22==0 and _status_link_live(data)
        and all(data.get(k)==0 for k in ('mc_fault','bp_fault','mc_transport_fault','bp_transport_fault',
            'mc_fault_current_mask','mc_fault_occurred_mask')))
