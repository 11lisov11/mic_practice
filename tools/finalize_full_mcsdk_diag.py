"""Freeze the measured result; never starts, clears, resets or flashes hardware."""
import csv,json
import prepare_no_switch_diag as p
from prepare_full_mcsdk_diag import OUT,OLD,BUILD
def main():
 m=json.loads(p.read(OUT/'manifest.json'));r=json.loads(p.read(OUT/'run_r1/report.json'));w=json.loads(p.read(OUT/'run_r1/waveform.json'))
 install=json.loads(p.read(OUT/'install_r1/report.json'))
 assert r['passed'] and install['passed'] and install['flash_commands']==1 and install['readback_verified']
 assert r['load_requests']==1 and r['motor_start_commands']==r['clear_commands']==0
 for rel,h in m['archived'].items():assert p.sha(OUT/'preserved_records'/rel)==h,rel
 old=json.loads(p.read(OLD/'manifest.json'))
 for rel,h in old['sealed_sha256'].items():assert p.sha(OLD/rel)==h,rel
 for rel,h in m['sealed_sha256'].items():assert p.sha(OUT/rel)==h,rel
 # Independently check levels, including the initial CSV sample.
 rows=0
 with (OUT/'run_r1/csv/digital.csv').open(newline='') as f:
  rd=csv.reader(f);header=next(rd);names=[''.join(c.lower() for c in s if c.isalnum()) for s in header]
  idx=[names.index('channel'+str(i)) for i in range(8)]
  for row in rd:
   if not row:continue
   v=[int(row[i]) for i in idx];assert all(v[i]==0 for i in range(5)) and v[6]==1;rows+=1
 assert w['AS5600_valid_reads']>1900 and not w['AS5600_target_NACK'] and not w['unexpected_frames']
 a=r['after']['load'];b=r['after']['full']
 report=dict(passed=True,build=BUILD,scope='Full MCSDK protected OFF/FAULT application with private VF/current-processing load; no motor RUN or real PWM edges',
  actual_bus_v=a['actual_bus_v'],active_fault=a['motor_fault_active'],active_fault_name='MC_UNDER_VOLT',
  no_protection_weakened=True,actual_bus_never_forged=True,snapshot_clear_commands=0,
  elapsed_ms=a['elapsed_ms'],task_calls_during_5s=b['task_calls_during_5s'],native_command_dispatch_calls_during_5s=b['native_commands_during_5s'],
  ADC_IRQ_during_5s=a['adc_calls'],ADC_accepted_during_5s=a['adc_accepted'],
  TIM_IRQ_max_us=a['tim_max_cycles']/170,ADC_IRQ_max_us=a['adc_max_cycles']/170,foreground_gap_max_us=a['foreground_max_gap_cycles']/170,
  encoder_delta_host_interval=r['encoder_delta'],TX_delta_host_interval=r['tx_delta'],
  host_deltas_interval_note='Includes before/after debug reads and 10s capture; not exact five-second counts',
  Saleae_capture_seconds=10,Saleae_complete_AS5600_reads=w['AS5600_valid_reads'],Saleae_target_NACK_count=0,
  Saleae_partial_frames=w['partial_frames'],partial_frame_note='First captured exchange is incomplete near capture start; excluded from qualified reads, cause not established',
  native_UART_bad_frames=b['rx_bad'],native_UART_guard=b['uart_guard'],
  all_recorded_PWM_channels_static_LOW=True,SD_all_rows_HIGH=True,CSV_rows=rows,
  MOE_off=not bool(a['TIM1_BDTR']&0x8000),GPIO_locked_LOW=bool(a['phase_pins_gpio_low']),
  old_files_hash_verified=len(m['archived']),readback_verified=True,flash_commands=1,load_requests=1,
  comparison=dict(previous='combined_io_diag_r2/run_r1',previous_physical_PWM_I2C_errors=0,this_protected_full_application_I2C_errors=0,
   implication='No I2C fault reproduced in either isolated condition; full MCSDK RUN plus real PWM and powered inverter was not tested'),
  motor_current_RMS_qualified=False,original_powered_I2C_cause_proven=False,
  keep_state='J1 and15V OFF;34pin ribbon disconnected; this GPIO-inhibited diagnostic is not a powered motor firmware')
 p.write(OUT/'assessment.json',json.dumps(report,indent=2)+'\n')
 m.update(installed=True,readback_verified=True,hardware_tested=True,protected_full_application_observation_passed=True,
  motor_RUN_tested=False,real_PWM_edges_tested_this_run=False,assessment='assessment.json')
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 hashes={f.relative_to(OUT).as_posix():p.sha(f) for tree in ('install_r1','run_r1') for f in (OUT/tree).rglob('*') if f.is_file()}
 hashes['assessment.json']=p.sha(OUT/'assessment.json');p.write(OUT/'runtime_sha256.json',json.dumps(hashes,indent=2)+'\n')
 status=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';oldstatus=p.read(status)
 note='''## 2026-10-28:2803 — полный защищённый MCSDK OFF/FAULT + ADC/VF/UART/AS5600,5с PASS

По запросу пользователя добавлены полнаяMCSDKboot/SysTick/scheduler/safety,
штатныйuno_link_poll/uno_handle_valid_frame и штатные ответы/телеметрияUART.
J1/J4OFF,шлейф34pin отсоединён; NucleoUSB/Unoповербанк, картаSaleae прежняя.
2803 записанаОДИНраз/readbackPASS; Unoнеперепрошивалась. НикакихCLEAR/START.

Важно: это ЗАЩИЩЁННОЕOFF/FAULT приложение. Реальнаяшина0В,MC_UNDER_VOLT=4
сохранён. UV/температурныепороги и безопасностькоманд не изменены; кроме них
оставлен дополнительныйfixtureSTARTinhibit и GPIOlockedLOW/MOE0. Физических
фронтов в ЭТОМпрогоне нет. Нельзя выдаватьего за нормальныйMCSDKRUN подШИМ.
ПолныйнаборMCSDK задач работает вместе с приватнымV/f вычислением/активной
веткойобработкиADC;327Весть только в приватной нормализации, не вVbusMCSDK.

Одинзапрос завершёнDONE/reason0/attempted1 через5000,021624мс. Внутри5с:
MC_Run10000,safety10000,medium2500,HFT80007,TIM80007,ADC80008/accepted80007,
99кадровпереданы штатномуобработчику. MaxTIM12,14мкс,ADC18,56мкс,main309,12мкс.
I2Cошибки/NACK/BUSY/deadline/ARLO/BERR/resets/parks delta0. RXbad0,TXошибки0.
2320чтенийAS и975TXcompleted — интервалhost до/после10сcapture, НЕточные5с.
Saleae8MS/s10с:2011полныхчтенийAS,ошибочныхNACK/неизвестныхкадров0,
всеD0..4LOW иSDHIGHвоВСЕХCSVстроках. Первыйобменнеполонпристартеcapture;
сохранён/исключёнизквалификации,причинанеполнотынеустановлена.

ИсточникAS/ADC,инициализаторыTIM/ADC/UART иMCSDKзащиты проверены сравнением;
nativecore15149/platform200038/newguard17/math513505 PASS; target0errors/
0warnings,RAMзапас2616байт сверхreservedheap/stack,лимит2600неуменьшался.
381старыйархивныйфайл иpredecessorsealedbytes SHAпроверены. Записи:
`artifacts/live_bench_20261028/full_mcsdk_diag_r1/run_r1/full_mcsdk.sal`,
`assessment.json`,`runtime_sha256.json`. ПредыдущийфизическийPWM2802цел.

Вывод: ошибканевоспроизвелась при полнойпрограммнойнагрузке вOFF/FAULT;
раньшеотдельноPWM+ADC+UARTтожеI2C0. ЭтоНЕдоказательствоработыAS приинверторе
поднапряжением или устранениясиловойпричины. RMS/амперы/вращениенеизмерялись.
Текущийобраз2803 — диагностический,не длясилового. J1/J4/шлейфоставитьOFF.

'''
 p.write(status,oldstatus.replace('# Текущий статус стенда\n','# Текущий статус стенда\n\n'+note,1))
 print(json.dumps(dict(passed=True,elapsed_ms=a['elapsed_ms'],old_archives_verified=len(m['archived']),runtime_files=len(hashes),hardware_calls=0)))
if __name__=='__main__':main()
