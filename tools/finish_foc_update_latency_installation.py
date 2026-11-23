"""Freeze readback and OFF-only verification of3003/3004; GET only."""
import hashlib,json,urllib.request
import prepare_foc_update_latency_fix as p

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def main():
 out=p.OUT/'installation_verified_r1';out.mkdir(exist_ok=False)
 install=json.loads(p.read(p.OUT/'hardware_install_r1/install_report.json'))
 readback=json.loads(p.read(p.OUT/'post_install_readback_r1/report.json'))
 idle=json.loads(p.read(p.OUT/'idle_verification_r1/report.json'))
 assert install['passed'] and readback['passed'] and idle['passed']
 assert install['uno_readback_verified'] and install['nucleo_readback_verified'] and install['calibration_unchanged']
 assert idle['start_commands']==idle['clear_commands']==idle['arm_commands']==0
 m=json.loads(p.read(p.OUT/'manifest.json'))
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==h,rel
 for rel,h in m['artifacts'].items():assert sha(p.OUT/rel)==h,rel
 prior=json.loads(p.read(p.OUT/'verification/preserved_captures_sha256.json'))
 for rel,h in prior.items():assert sha(p.ROOT/rel)==h,rel
 assert (p.OUT/'nucleo/Inc/current_adc_deadline.h').read_bytes()==(p.BASE/'nucleo/Inc/current_adc_deadline.h').read_bytes()
 op=urllib.request.build_opener(urllib.request.ProxyHandler({}));token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
 for name,path in (('final_status','/api/status'),('SD_trace_metadata','/api/bkin-trace'),('SD_snapshots','/api/break-snapshot')):
  req=urllib.request.Request('http://192.168.1.138:8080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
  with op.open(req,timeout=8) as response:obj=json.load(response)
  assert obj.get('ok');p.write(out/(name+'.json'),json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
 s=json.loads(p.read(out/'final_status.json'))['data'];runtime=s['foc_runtime']
 assert (s['fw_build'],s['mc_fw_build'])==p.NEW
 assert s['state']=='SAFE' and s['pwm']==0 and s['run_id']==0 and s['hmi_hv_armed']==0
 assert s['vdc']<=20 and s['algorithm_selected']==s['algorithm_requested']==2
 assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011
 assert s['mc_current_zero_ready']==1
 for k in ('algorithm_fault','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_transport_fault',
           'rpc_response_timeouts','rpc_send_timeouts'):assert s[k]==0,(k,s[k])
 # J1 is deliberately OFF. Report an existing low-bus fault, never CLEAR it
 # and never treat an OFF CPU pass as motor-start readiness.
 masks=(s['mc_fault_current_mask'],s['mc_fault_occurred_mask'])
 assert all(mask in (0,4) for mask in masks),masks
 if any(masks):assert s['vdc']<=20 and 'MC_UNDER_VOLT' in s['mc_fault_detail']
 assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled'] and s['mc_sd_live']['config_ok']
 assert runtime['source']=='OFF_synthetic_CPU_probe' and runtime['observer_steps']==64 and runtime['first_fault'] is None
 assert runtime['meter_errors']==0 and s['algorithm_fast_cycles']<=4000 and s['algorithm_observer_cycles']<=85000
 r=dict(passed=True,pair=list(p.NEW),installed=True,readback_verified=True,
  native_independent_readback=readback,calibration_unchanged=True,
  old_captures_verified=len(prior),new_START=0,new_CLEAR=0,new_ARM=0,
  uno_flash_commands=install['uno_flash_commands'],nucleo_flash_commands=install['nucleo_flash_commands'],
  programming_boot_resets_used=True,manual_motor_RESET=0,
  OFF_timing_cases=64,fast_kernel_cycles=s['algorithm_fast_cycles'],fast_kernel_us=s['algorithm_fast_cycles']/170,
  observer_inner_max_cycles=s['algorithm_observer_cycles'],observer_CPU_IRQ=runtime,
  ADC_guard_2048_unchanged=True,protection_thresholds_unchanged=True,
  global_mask_removed_from_current_telemetry_ARM_verified=True,
  current_fault_mask=masks[0],occurred_fault_mask=masks[1],low_bus_fault_with_J1_OFF=any(masks),motor_start_ready=False,
  no_PWM=True,actual_powered_5s_completed=False,full_powered_timing_not_yet_qualified=True,
  all_commands_are_stopped_configuration=idle['commands'],after=s)
 p.write(out/'report.json',json.dumps(r,ensure_ascii=False,indent=2)+'\n')
 evidence={}
 for name in ('hardware_install_r1','post_install_readback_r1','idle_verification_r1','installation_verified_r1'):
  for f in (p.OUT/name).rglob('*'):
   if f.is_file() and f.name!='preserved_installation_evidence.json':evidence[f.relative_to(p.ROOT).as_posix()]=sha(f)
 p.write(out/'preserved_installation_evidence.json',json.dumps(evidence,indent=2)+'\n')
 m.update(installed=True,installation_readback_verified=True,calibration_unchanged=True,
  OFF_target_timing_measured=True,fast_kernel_cycles=s['algorithm_fast_cycles'],
  observer_wall_max_us=runtime['max_wall_us'],hardware_timing_qualification_pending=True,
  hardware_5s_completion_not_yet_proven=True,start_commands=0,clear_commands=0,flash_commands=2,
  installation_report='installation_verified_r1/report.json',preserved_new_evidence_files=len(evidence))
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 summary=('## 2026-10-30:3003/3004 установлены,readback и OFF64расчёта пройдены\n\n'
  'ПользовательJ1OFF/мультиметр<20В/обеUSBПК/15ВON подтвердил. Пассивно до\n'
  'записи~4,5В/MOE0,точный3002,32КБSRAM сохранены. Каждаяплата прошита1раз,\n'
  'UnoOpenOCD/NucleoCubeProgrammerverifyOK,отдельныйnativeHotPlugreadbackOK.\n'
  'Калибровкасохранена. HMI/RPCсвязьвосстановлены,FOC2/profile128CRC1354279011.\n'
  f'OFF64пройдены:ядро{s["algorithm_fast_cycles"]}тактов={s["algorithm_fast_cycles"]/170:.3f}мкс,\n'
  f'observerinnermax{s["algorithm_observer_cycles"]},wallmax{runtime["max_wall_us"]:.3f}мкс.\n'
  'Это OFF_synthetic_CPU_probe,неполныйpoweredадаптер;5секподШИМНЕпроверены.\n'
  f'SAFE/PWM0/run_id0/HVarm0,автонольготов,SDHIGH/BIE/config_ok,маски{masks},\n'
  'ДопускаетсятолькоMC_UNDER_VOLT4принамеренномJ1OFF;этоНЕготовностькпуску.\n'
  'UARTintegrity/sequence/hardware/transport/RPCtimeouts0. Допуск2048точнопрежний.\n'
  'В3004убранаCPSIDблокировкателеметрии,ADCwritersequence+boundedreader;\n'
  'реальноеустранениеисторическогоотказа31759подШИМещёНЕквалифицировано.\n'
  '954прежнихфайласохранены;новыелоги/readback/SD/SRAM/статусыотдельно.\n'
  'Пусков/CLEAR/ARM0;остановленнаяFOC5Гц/BOUNDED5секконфигурациязадана.\n'
  'ТекущееобеUSBПК,15ВON,J1OFF. Автономныйпереходипуск—последующийэтап,\n'
  'сейчасSTART/CLEARнепосылать. Старыйrun_foc_fast_budget_trial.pyждёт3001/3002;\n'
  'дляновойпарыадаптироватьPAIRна3003/3004безизмененияпроверок.\n'
  'Отчёт:artifacts/live_bench_20261029/foc_update_latency_fix_r1/installation_verified_r1/report.json.\n\n')
 status=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';old=p.read(status);idx=old.index('## 2026-10-30:');p.write(status,old[:idx]+summary+old[idx:])
 print(json.dumps(dict(passed=True,pair=list(p.NEW),readback_verified=True,
  fast_kernel_cycles=s['algorithm_fast_cycles'],observer_wall_max_us=runtime['max_wall_us'],
  old_captures=len(prior),new_evidence=len(evidence),START=0,CLEAR=0)))
if __name__=='__main__':main()
