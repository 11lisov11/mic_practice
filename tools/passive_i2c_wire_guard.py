"""Admission for ONE passive SRAM capture, never flashing or START/CLEAR.
Historical controller faults remain visible and latched. An OFF/low-bus
diagnostic does not require clearing them or pretending the metadata is zero.
"""
import math
def precheck(s,pair):
    try:
        if (s['fw_build'],s['mc_fw_build'])!=pair:return False,'Unexpected pair'
        if s['state']!='SAFE' or s['pwm']!=0 or s['hmi_hv_armed']!=0 or int(s['bp_status'])&0x22:
            return False,'Outputs or request active'
        if s['rpc_schema_version']!=3 or s['mc_capabilities']!=1 or s['bp_mcsdk_telemetry']!=1:return False,'Invalid contract'
        for key in ('vdc','bp_vdc'):
            if type(s[key]) not in (int,float) or not math.isfinite(s[key]) or not 0<=s[key]<20:return False,'Bus is not low'
        for key in ('mc_age_ms','bp_vbus_age_ms','bp_temp_age_ms'):
            if type(s[key]) not in (int,float) or not math.isfinite(s[key]) or not 0<=s[key]<300:return False,'Stale telemetry'
        if s['bp_vbus_valid']!=1 or s['bp_temp_valid']!=1 or s['bp_temp_fault']!=0:return False,'Invalid measurement or temperature fault'
        if type(s['bp_vbus_raw']) is not int or not 0<=s['bp_vbus_raw']<200:return False,'Raw bus is not low'
        if s['mc_diag_valid']!=1 or s['bp_diag_valid']!=1:return False,'Invalid native diagnostics'
        for key in ('mc_uart_error_flags','bp_uart_error_flags','uno_rx_hw_flags'):
            if s[key]!=0:return False,'UART hardware error flags'
        for key in ('precharge','pfc','brake','bp_ext'):
            if s[key]!=0:return False,'Service output active'
        q=s['mc_sd_live']
        if not(q['available'] and q['config_ok'] and q['level']=='HIGH' and q['break_irq_enabled']):return False,'SD not released/configured'
        return True,'Passive OFF/low-bus capture only; saved faults retained'
    except (KeyError,ValueError,TypeError,OverflowError):return False,'Invalid telemetry'
