"""Prepare1603/1604 offline installation/readback/CPU/current-freshness checks."""
import ast
import prepare_telemetry_deadline as p


def function(source,name):
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    return ''.join(source.splitlines(keepends=True)[node.lineno-1:node.end_lineno]).rstrip()


def main():
    root=p.ROOT
    s=p.read(root/'tools/install_observer_adc_delivery.py')
    s=s.replace('2026111601/1602','2026111603/1604').replace('import prepare_observer_adc_delivery as p','import prepare_telemetry_deadline as p')
    s=s.replace('OLD=(2026111503,2026111504)','OLD=(2026111601,2026111602)')
    s=s.replace("assert t['passed'] and not t['thresholds_changed']", "assert t['passed'] and t['ordinary_receiver_freshness_750_1500_unchanged']")
    s=s.replace("assert t['observer_and_controller_math_byte_identical'] and t['fast_timed_body_unchanged']",
        "assert t['observer_math_and_4000_2ms_guards_unchanged'] and not m['ordinary_freshness_guards_changed']\n assert m['ordinary_OFF_foreground_priority'] and m['OFF_bulk_max_fps']==100")
    old=function(s,'safe')
    new='''def safe(s,pair):
 assert (s.get('fw_build'),s.get('mc_fw_build'))==pair,'unexpected pair'
 assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0,'controller not OFF'
 assert not(s['bp_status']&0x22),'native running/enable bit active'
 assert s['rpc_schema_version']==3 and s['mc_capabilities']==1 and s['bp_mcsdk_telemetry']==1
 assert 0<=s['mc_age_ms']<300,'reply is stale'
 assert all(s.get(k)==0 for k in ('mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence')),'UART unhealthy'
 # Saved MCSDK/transport/RPC history is archived, not cleared. This stopped
 # programming check never authorizes a START or skips any firmware guard.
 assert all(s.get(k)==0 for k in ('precharge','pfc','brake','bp_ext')),'service output active'
 assert 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20,'bus not discharged'
'''
    s=s.replace(old,new.rstrip())
    s=s.replace('mic_adc1602_','mic_telemetry1604_').replace('observer_adc_1602_','telemetry_1604_')
    s=s.replace('_observer_adc_delivery.hex','_telemetry_deadline.hex').replace('_observer_adc_delivery.elf-zsk.bin','_telemetry_deadline.elf-zsk.bin')
    verifier=p.read(root/'tools/verify_observer_adc_delivery_idle.py').replace('import prepare_observer_adc_delivery as p','import prepare_telemetry_deadline as p')
    verifier=verifier.replace('hardware_install_r2/report.json','hardware_install_r1/report.json').replace("report['predecessor_OFF_cycles']=3611","report['predecessor_OFF_cycles']=3618")
    anchor="        report['passed']=report['CPU_qualified'] and report['fresh_link'] and not report['new_rejected_frames']"
    replacement='''        report['ordinary_telemetry_fresh']=all(0<=s.get('mc_current_age_ms',999999)<750
            and 0<=s.get('mc_current_detail_age_ms',999999)<1500
            and 0<=s.get('mc_current_quality_age_ms',999999)<1500
            and s.get('mc_current_zero_ready')==1 and s.get('mc_current_zero_stable')==3 for s in rows)
        report['current_age_rows']=[{k:s.get(k) for k in ('mc_current_age_ms','mc_current_detail_age_ms',
            'mc_current_quality_age_ms','mc_current_zero_ready','mc_current_zero_stable')} for s in rows]
        report['passed']=report['CPU_qualified'] and report['fresh_link'] and not report['new_rejected_frames'] and report['ordinary_telemetry_fresh']'''
    assert anchor in verifier;verifier=verifier.replace(anchor,replacement)
    recorder=p.read(root/'tools/record_observer_adc_installation.py').replace('import prepare_observer_adc_delivery as p','import prepare_telemetry_deadline as p')
    recorder=recorder.replace('hardware_install_r2/report.json','hardware_install_r1/report.json')
    recorder=recorder.replace('previous_successful_OFF_cycles=3611','previous_successful_OFF_cycles=3618')
    recorder=recorder.replace("        initial_preflight_before_any_flash='hardware_install_r1/report.json',\n",'')
    recorder=recorder.replace('        initial_preflight_failure_did_not_flash=True,\n','')
    recorder=recorder.replace("tools/install_observer_adc_delivery.py","tools/install_telemetry_deadline.py")
    recorder=recorder.replace('sequence_discard_count=idle[\'sequence_counts\'][-1],',
        "sequence_discard_count=idle['sequence_counts'][-1],\n        ordinary_telemetry_fresh=idle['ordinary_telemetry_fresh'],")
    for name,text in {'install_telemetry_deadline.py':s,'verify_telemetry_deadline_idle.py':verifier,
        'record_telemetry_deadline_installation.py':recorder}.items():
        target=root/'tools'/name;assert not target.exists(),name;compile(text,str(target),'exec');p.write(target,text)
    print('Prepared1603/1604 programming, readback and OFF CPU/freshness recipes; no device calls')


if __name__=='__main__':main()
