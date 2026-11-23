def identification_point_complete(data,initial):
    """A completed native bounded measurement may precede the HTTP response.
    This never authorizes START and cannot acknowledge any protection fault.
    """
    if not data or not initial:return False
    if (data.get('fw_build'),data.get('mc_fw_build'))!=(2026102931,2026102932):return False
    if data.get('algorithm_selected')!=4 or initial.get('algorithm_selected')!=4:return False
    if data.get('state')!='SAFE' or data.get('pwm')!=0 or data.get('bp_status',0x22)&0x22:return False
    if not 0<=data.get('mc_age_ms',99999)<300 or data.get('id_valid')!=1:return False
    if any(data.get(k)!=0 for k in ('estop','mc_fault_current_mask','mc_fault_occurred_mask','mc_transport_fault','id_fault')):return False
    if data.get('id_flags',0)&12!=12 or not data.get('id_result_crc'):return False
    if not initial.get('id_config_crc') or data.get('id_config_crc')!=initial.get('id_config_crc') or data.get('id_run_id')!=initial.get('id_run_id'):return False
    if data.get('run_id')!=((initial.get('run_id',-2)+1)&0xffffffff):return False
    elapsed=data.get('run_elapsed_ms',-1);duration=initial.get('id_duration_ms',0)
    return 2000<=duration<=10000 and duration<=elapsed<=duration+1500
