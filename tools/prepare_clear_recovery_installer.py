"""Prepare1605/1606 USB install/readback/OFF checks; no device access."""
import ast
import prepare_clear_recovery as p
from prepare_telemetry_deadline_installer import function


def main():
    src=p.read(p.ROOT/'tools/install_telemetry_deadline.py')
    src=src.replace('import prepare_telemetry_deadline as p','import prepare_clear_recovery as p')
    src=src.replace('Install sealed 2026111603/1604','Install sealed 2026111605/1606')
    src=src.replace('OLD=(2026111601,2026111602)','OLD=(2026111603,2026111604)')
    src=src.replace('_telemetry_deadline.hex','_clear_recovery.hex').replace('_telemetry_deadline.elf-zsk.bin','_clear_recovery.elf-zsk.bin')
    src=src.replace('mic_telemetry1604_','mic_clear1606_').replace('telemetry_1604_','clear_1606_')
    old=function(src,'package_check')
    new=old.replace("assert t['passed'] and t['ordinary_receiver_freshness_750_1500_unchanged']",
        "assert t['passed'] and t['actual_CLEAR_branch'] and t['actual_ST_MCI_ACK']\n assert t['MCSDK_rejected_ACK_keeps_latch'] and t['async_ACK_not_claimed_ready']")
    new=new.replace("assert t['observer_math_and_4000_2ms_guards_unchanged'] and not m['ordinary_freshness_guards_changed']",
        "assert json.loads(p.read(p.OUT/'verification/telemetry/report.json'))['passed']\n assert not m['ordinary_freshness_guards_changed'] and m['clear_first_attempt_record']\n assert m['clear_healthy_TX_inflight_allowed']\n assert json.loads(p.read(p.OUT/'model_verification/model_report.json'))['baseline_candidate_model_trajectories_identical']")
    assert new!=old;src=src.replace(old,new)
    idle=p.read(p.ROOT/'tools/verify_telemetry_deadline_idle.py').replace('import prepare_telemetry_deadline as p','import prepare_clear_recovery as p')
    idle=idle.replace('from pathlib import Path','from pathlib import Path\nfrom rpc_counter_guard import RpcCounterGuard\nfrom run_foc_boot_capture_trial import decode_boot')
    idle=idle.replace("recorder_empty=trace_empty)","recorder_empty=trace_empty,clear_record_empty=val('mic_clear_diag_ready','<B')==0)")
    idle=idle.replace("assert not row['fe_trial_done'] and trace_empty","assert not row['fe_trial_done'] and trace_empty and row['clear_record_empty']")
    idle=idle.replace('        rows=[]','        rows=[]\n        rpc=RpcCounterGuard(lambda s,**kw:decode_boot(s,p.NEW,**kw))')
    idle=idle.replace("            assert (s['fw_build'],s['mc_fw_build'])==p.NEW", "            assert (s['fw_build'],s['mc_fw_build'])==p.NEW\n            decode_boot(s,p.NEW)\n            assert rpc.observe(s),rpc.failure\n            assert s.get('clear_recovery',{}).get('available') is False,'Unexpected CLEAR record after programming'")
    idle=idle.replace("'mc_bad_integrity','mc_bad_sequence','rpc_response_timeouts','rpc_send_timeouts'))",
        "'mc_bad_integrity','mc_bad_sequence','uno_rx_hw_errors','uno_rx_dropped'))\n        report['RPC_stable']=rpc.ready and rpc.failure is None\n        report['rpc_guard']=rpc.snapshot()")
    idle=idle.replace("and report['ordinary_telemetry_fresh']\n", "and report['ordinary_telemetry_fresh'] and report['UART_clean'] and report['RPC_stable']\n")
    recorder=p.read(p.ROOT/'tools/record_telemetry_deadline_installation.py').replace('import prepare_telemetry_deadline as p','import prepare_clear_recovery as p')
    recorder=recorder.replace('tools/install_telemetry_deadline.py','tools/install_clear_recovery.py')
    recorder=recorder.replace("    assert idle['ordinary_telemetry_fresh'] and idle['samples']==20", "    assert idle['ordinary_telemetry_fresh'] and idle['samples']==20\n    assert idle['UART_clean'] and idle['RPC_stable']\n    assert all(row['clear_record_empty'] for row in idle['native_rows'])")
    recorder=recorder.replace('motor_start_readiness_evaluated=False,powered_FOC_verified=False,',
        "motor_start_readiness_evaluated=False,powered_FOC_verified=False,\n        physical_CLEAR_recovery_verified=False,RPC_guard=idle['rpc_guard'],CLEAR_record_empty=True,")
    for name,text in {'install_clear_recovery.py':src,'verify_clear_recovery_idle.py':idle,
                      'record_clear_recovery_installation.py':recorder}.items():
        path=p.ROOT/'tools'/name;assert not path.exists(),name
        ast.parse(text);p.write(path,text)
    print('Prepared1605/1606 installation, readback and OFF CPU checks; no device calls')


if __name__=='__main__':main()
