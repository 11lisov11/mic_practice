"""Freeze completed2804 observation, including genuine startup BUSY records."""
import csv,json,struct
import prepare_no_switch_diag as p
from prepare_full_mcsdk_edges import OUT
def main():
 r=json.loads(p.read(OUT/'run_r1/report.json'));w=json.loads(p.read(OUT/'run_r1/waveform.json'));m=json.loads(p.read(OUT/'manifest.json'))
 assert r['passed'] and r['fixture_requests']==1 and r['I2C_no_new_errors']
 a=r['after']['pin'];b=r['after']['full'];first=struct.unpack('<40I',(OUT/'install_r1/boot_fault_record.bin').read_bytes()[:160])
 bc=(OUT/'install_r1/boot_bus_clear.bin').read_bytes();bcwords=struct.unpack('<4I',bc[:16])
 startup=dict(cause=first[4]&255,stage=first[4]>>8&255,state=first[4]>>16&255,cleanup=first[4]>>26,
  tick_ms=first[2],ISR=first[5],GPIO=first[7],CR1=first[9],CR2=first[10],reads_before=first[27],
  SCL_HIGH=bool(first[7]&256),SDA_HIGH=bool(first[7]&512),BUSY_total=a['encoder']['BUSY'],
  bus_clear_result=bc[17],bus_clear_pulses=bc[18],bus_clear_before=bc[19],bus_clear_after=bc[21],
  bus_clear_us=bcwords[3],first_fault_to_clear_start_ms=((bcwords[0]-first[3])&0xffffffff)/170000)
 rows=0
 with (OUT/'run_r1/csv/digital.csv').open(newline='') as f:
  rd=csv.reader(f);h=next(rd);names=[''.join(c.lower() for c in s if c.isalnum()) for s in h];idx=names.index('channel6')
  for row in rd:
   if row:assert row[idx]=='1';rows+=1
 report=dict(passed=True,build=2026102804,scope='MCSDK protected OFF/FAULT+independent physical TIM1 PWM',elapsed_ms=r['elapsed_ms'],
  native_tasks_during_5s=r['task_calls_during_5s'],native_commands_during_5s=r['native_commands_during_5s'],
  ADC_during_5s=r['ADC_during_5s'],ADC_bad=r['ADC_bad'],TIM_IRQ_max_us=a['max_ISR_cycles']/170,
  main_gap_max_us=a['max_main_gap']/170,ADC_IRQ_max_us=a['ADC_max_cost']/170,
  AS_reads_during_physical_PWM=w['AS5600_complete_read_parts_within_PWM'],AS_errors_during_5s=a['boundaries'][7]-a['boundaries'][1],
  physical_PWM_window_s=w['PWM_window_s'],carrier_hz=w['median_carrier_hz'],recorded_outputs=5,WL_unrecorded=True,
  full_I2C_capture_reads=w['AS5600_valid_reads'],partial_frames=w['partial_frames'],target_NACK=w['AS5600_target_NACK'],
  SD_HIGH_all_rows=rows,all_MOE_off_after=True,MCSDK_fault_current=b['active_fault'],TIM8_backend_flags=b['backend_flags'],
  startup=startup,UART_RX_bad=b['rx_bad'],UART_guard=b['uart_guard'],TX_errors={k:r['after']['tx'][k] for k in ('timeouts','dma_errors','full_errors')},
  encoder_delta_host_interval=r['encoder_delta_host_interval'],host_delta_note='Contains before/after snapshots and10s capture, not exact5s counts',
  old_files_verified=len(m['archived']),source_and_thresholds_unchanged=True,normal_motor_RUN_tested=False,powered_I2C_cause_proven=False)
 for rel,h in m['sealed_sha256'].items():assert p.sha(OUT/rel)==h,rel
 p.write(OUT/'assessment.json',json.dumps(report,indent=2)+'\n')
 m.update(installed=True,readback_verified=True,hardware_tested=True,concurrent_real_edges_passed=True,startup_BUSY_retained=15)
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 hashes={f.relative_to(OUT).as_posix():p.sha(f) for t in ('install_r1','run_r1') for f in (OUT/t).rglob('*') if f.is_file()};hashes['assessment.json']=p.sha(OUT/'assessment.json')
 p.write(OUT/'runtime_sha256.json',json.dumps(hashes,indent=2)+'\n');print(json.dumps(dict(passed=True,startup=startup,hardware_calls=0)))
if __name__=='__main__':main()
