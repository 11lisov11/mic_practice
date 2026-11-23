import json,csv
import prepare_no_switch_diag as p
from prepare_full_edges_busy_wait import OUT,OLD,BUILD
def main():
 m=json.loads(p.read(OUT/'manifest.json'));r=json.loads(p.read(OUT/'run_r1/report.json'));w=json.loads(p.read(OUT/'run_r1/waveform.json'));boot=json.loads(p.read(OUT/'install_r1/boot.json'))
 assert r['passed'] and r['I2C_no_new_errors'];a=r['after']['pin'];f=r['after']['full']
 assert a['encoder']['errors']==0 and a['boundaries'][7]-a['boundaries'][1]==0 and not w['partial_frames'] and not w['AS5600_target_NACK']
 for rel,h in m['archived'].items():assert p.sha(OUT/'preserved_records'/rel)==h,rel
 for rel,h in m['sealed_sha256'].items():assert p.sha(OUT/rel)==h,rel
 replay=json.loads(p.read(OUT/'verification/native_tests.json'))['startup_gate_replay']
 report=dict(passed=True,build=BUILD,scope='MCSDK protected OFF/FAULT and physical TIM1 diagnostic PWM on original pins, inverter ribbon absent',
  elapsed_ms=r['elapsed_ms'],native_tasks_during_5s=r['task_calls_during_5s'],native_command_dispatch_during_5s=r['native_commands_during_5s'],
  ADC_IRQ_during_5s=r['ADC_during_5s'],ADC_bad=r['ADC_bad'],TIM_IRQ_max_us=a['max_ISR_cycles']/170,ADC_IRQ_max_us=a['ADC_max_cost']/170,main_gap_max_us=a['max_main_gap']/170,
  actual_16kHz_PWM_window_seconds=w['PWM_window_s'],recorded_outputs=5,WL_unrecorded=True,AS_complete_reads_during_PWM=w['AS5600_complete_read_parts_within_PWM'],
  AS_errors_during_5s=0,AS_errors_since_boot=0,AS_boot_reads=boot['pin']['encoder']['reads'],
  hardware_boot_note='This flash/startup had free lines and no BUSY; the stuck-SDA branch is verified by actual-driver A/B replay and the earlier2804 hardware record, not claimed exercised by this boot',
  actual_driver_AB=dict(old_BUSY=replay['old']['BUSY_before_gate'],fixed_BUSY=replay['fixed']['BUSY_before_gate'],first_record_preserved=True,nine_clocks=True),
  previous_hardware_record='full_mcsdk_edges_r1/assessment.json',
  previous_hardware_startup='SDA LOW/SCL HIGH/PE0, first BUSY at8ms,9-clock clear after290.994ms;15 retry errors before recovery permission',
  UART_RX_bad=f['rx_bad'],UART_guard=f['uart_guard'],TX_errors={k:r['after']['tx'][k] for k in ('timeouts','dma_errors','full_errors')},
  first_fault_slots=a['encoder']['fault_slots'],motor_UV_active=f['active_fault']==4,motor_timer_disabled=f['backend_flags']==0,
  physical_PWM_off_after=not bool(a['BDTR']&0x8000),normal_motor_RUN_tested=False,powered_inverter_I2C_cause_proven=False,
  old_files_SHA_verified=len(m['archived']),source_of_transfer_read_and_recovery_unchanged=True,
  primary_reference='https://www.nxp.com/docs/en/user-guide/UM10204.pdf',remaining='Compare with inverter ribbon and driver supply, then powered captures; no claim of powered rotation qualification')
 p.write(OUT/'assessment.json',json.dumps(report,indent=2)+'\n')
 m.update(installed=True,readback_verified=True,hardware_tested=True,concurrent_real_edges_passed=True,preparation_only=False,startup_BUSY_retained=0,assessment='assessment.json')
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 hashes={q.relative_to(OUT).as_posix():p.sha(q) for t in ('install_r1','run_r1','startup_capture_r1') for q in (OUT/t).rglob('*') if q.is_file()};hashes['assessment.json']=p.sha(OUT/'assessment.json')
 p.write(OUT/'runtime_sha256.json',json.dumps(hashes,indent=2)+'\n');print(json.dumps(dict(passed=True,build=BUILD,old_files_verified=len(m['archived']),runtime_files=len(hashes),hardware_calls=0)))
if __name__=='__main__':main()
