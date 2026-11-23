"""Prepare1601/1602 installation/readback/OFF-verification recipes; no devices."""
import ast
import prepare_observer_adc_delivery as p


def function(source,name):
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    return ''.join(source.splitlines(keepends=True)[node.lineno-1:node.end_lineno]).rstrip()


def main():
    root=p.ROOT
    source=p.read(root/'tools/install_exact_profile_budget.py')
    source=source.replace('2026111503/1504','2026111601/1602')
    source=source.replace('import prepare_exact_profile_budget as p','import prepare_observer_adc_delivery as p')
    source=source.replace('OLD=(2026111501,2026111502)','OLD=(2026111503,2026111504)')
    old=function(source,'package_check')
    new='''def package_check():
 m=json.loads(p.read(p.OUT/'manifest.json'))
 assert m['built'] and m['host_tests_passed'] and m['model_tests_passed']
 assert m['pair']==list(NEW) and not m['installed'],'wrong or already installed package'
 assert not m['thresholds_changed'] and not m['observer_tuning_changed']
 assert not m['controller_equations_changed']
 assert m['diagnostic_ADC_first_NIS_loss_trigger'] and m['OFF_bulk_round_robin']
 assert m['CPU_probe_budget_cycles']==4000
 assert (m['peer_reply_timeout_ms'],m['send_cadence_us'],m['reply_guard_us'])==(500,50000,8000)
 assert (m['trip_A'],m['ADC_guard_ticks'],m['estimate_limit_ms'])==(1.35,2048,2)
 assert m['fast_budget_cycles']==5312 and m['frequency_max_hz']==5 and m['runlimit_ms']==5000
 for rel in ('nucleo/Inc/motor_control.h','nucleo/Inc/foc_experiment.h'):
  assert p.sha(p.OUT/rel)==p.sha(p.BASE/rel),'protected kernel/profile changed'
 t=json.loads(p.read(p.OUT/'verification/report.json'));assert t['passed'] and not t['thresholds_changed']
 assert t['observer_and_controller_math_byte_identical'] and t['fast_timed_body_unchanged']
 assert json.loads(p.read(p.OUT/'verification/ARM_scope.json'))['passed']
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in m['verification_reports'].items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in json.loads(p.read(p.OUT/'preserved_capture_hashes.json')).items():assert p.sha(p.ROOT/rel)==h,rel
 return m
'''
    source=source.replace(old,new.rstrip())
    old=function(source,'safe')
    new='''def safe(s,pair):
 assert (s.get('fw_build'),s.get('mc_fw_build'))==pair,'unexpected pair'
 assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0,'controller not OFF'
 assert not(s['bp_status']&0x22),'native running/enable bit active'
 assert s['rpc_schema_version']==3 and s['mc_capabilities']==1 and s['bp_mcsdk_telemetry']==1
 assert 0<=s['mc_age_ms']<300,'reply is stale'
 assert all(s.get(k)==0 for k in ('mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence')),'UART unhealthy'
 # Stopped-only programming preserves saved transport/fault latches. This is
 # not a motor-readiness exception or authorization for CLEAR/START.
 assert all(s.get(k)==0 for k in ('precharge','pfc','brake','bp_ext')),'service output active'
 assert 0<=s['vdc']<=20 and 0<=s['bp_vdc']<=20,'bus not discharged'
'''
    source=source.replace(old,new.rstrip())
    source=source.replace('mic_exact1504_','mic_adc1602_').replace('exact_profile_1504_','observer_adc_1602_')
    source=source.replace('_exact_profile_budget.hex','_observer_adc_delivery.hex')
    source=source.replace('_exact_profile_budget.elf-zsk.bin','_observer_adc_delivery.elf-zsk.bin')
    verifier=p.read(root/'tools/verify_exact_profile_budget_idle.py')
    verifier=verifier.replace('import prepare_exact_profile_budget as p','import prepare_observer_adc_delivery as p')
    verifier=verifier.replace("report['baseline_cycles']=4229","report['predecessor_OFF_cycles']=3611")
    recorder=p.read(root/'tools/record_exact_profile_installation.py')
    recorder=recorder.replace('import prepare_exact_profile_budget as p','import prepare_observer_adc_delivery as p')
    recorder=recorder.replace('previous_failed_cycles=4229','previous_successful_OFF_cycles=3611')
    scripts={'install_observer_adc_delivery.py':source,
             'verify_observer_adc_delivery_idle.py':verifier,
             'record_observer_adc_installation.py':recorder}
    for name,text in scripts.items():
        target=root/'tools'/name;assert not target.exists(),name
        compile(text,str(target),'exec');p.write(target,text)
    print('Prepared offline programming/readback/passive-DWT recipes; no device commands')


if __name__=='__main__':main()
