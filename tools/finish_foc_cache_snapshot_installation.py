"""Freeze installed3007/3008 images and OFF calculation evidence; GET only."""
import hashlib,json,urllib.request
import prepare_foc_cache_snapshot_fix as p
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def main():
 out=p.OUT/'installation_verified_r1';out.mkdir(exist_ok=False)
 installation=json.loads(p.read(p.OUT/'hardware_install_r2/install_report.json'))
 readback=json.loads(p.read(p.OUT/'post_install_readback_r1/report.json'))
 idle=json.loads(p.read(p.OUT/'idle_verification_r1/report.json'))
 assert installation['passed'] and readback['passed'] and idle['passed']
 assert installation['uno_readback_verified'] and installation['nucleo_readback_verified'] and installation['calibration_unchanged']
 assert idle['start_commands']==idle['clear_commands']==idle['arm_commands']==0
 manifest=json.loads(p.read(p.OUT/'manifest.json'))
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==h,rel
 for rel,h in manifest['artifacts'].items():assert sha(p.OUT/rel)==h,rel
 saved=json.loads(p.read(p.OUT/'verification/preserved_captures_sha256.json'))
 for rel,h in saved.items():assert sha(p.ROOT/rel)==h,rel
 for rel in ('current_adc_deadline.h','motor_control.h','foc_experiment.h'):
  assert (p.OUT/'nucleo/Inc'/rel).read_bytes()==(p.BASE/'nucleo/Inc'/rel).read_bytes()
 op=urllib.request.build_opener(urllib.request.ProxyHandler({}));token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
 for name,path in (('final_status','/api/status'),('SD_trace_metadata','/api/bkin-trace'),('SD_snapshots','/api/break-snapshot')):
  req=urllib.request.Request('http://192.168.1.138:8080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
  with op.open(req,timeout=8) as response:obj=json.load(response)
  assert obj['ok'];p.write(out/(name+'.json'),json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
 s=json.loads(p.read(out/'final_status.json'))['data'];runtime=s['foc_runtime']
 assert (s['fw_build'],s['mc_fw_build'])==p.NEW
 assert s['state']=='SAFE' and s['pwm']==0 and s['run_id']==0 and s['hmi_hv_armed']==0
 assert s['vdc']<=20 and s['algorithm_selected']==s['algorithm_requested']==2
 assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011 and s['mc_current_zero_ready']==1
 for k in ('algorithm_fault','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_transport_fault','rpc_response_timeouts','rpc_send_timeouts'):assert s[k]==0,(k,s[k])
 masks=(s['mc_fault_current_mask'],s['mc_fault_occurred_mask'])
 assert all(mask in (0,4) for mask in masks),masks
 if any(masks):assert 'MC_UNDER_VOLT' in s['mc_fault_detail']
 sd=s['mc_sd_live'];assert sd['level']=='HIGH' and sd['break_irq_enabled'] and sd['config_ok']
 assert runtime['source']=='OFF_synthetic_CPU_probe' and runtime['observer_steps']==64 and runtime['first_fault'] is None and runtime['meter_errors']==0
 assert 0<s['algorithm_fast_cycles']<=4000 and 0<s['algorithm_observer_cycles']<=85000
 report=dict(passed=True,pair=list(p.NEW),installed=True,readback_verified=True,
  independent_native_readback=readback,calibration_unchanged=True,old_files_verified=len(saved),
  trip_current_A=1.35,ADC_guard_ticks=2048,controller_and_safety_thresholds_unchanged=True,
  new_START=0,new_CLEAR=0,new_ARM=0,programming_boot_resets_used=True,
  uno_flash_commands=installation['uno_flash_commands'],nucleo_flash_commands=installation['nucleo_flash_commands'],
  OFF_cases=64,fast_kernel_cycles=s['algorithm_fast_cycles'],fast_kernel_us=s['algorithm_fast_cycles']/170,
  observer_inner_max_cycles=s['algorithm_observer_cycles'],CPU_IRQ=runtime,
  current_fault_mask=masks[0],occurred_fault_mask=masks[1],low_bus_J1_OFF=any(masks),
  motor_start_ready=False,no_PWM=True,new_RUN_regular_scheduler_physically_verified=False,
  current_spike_cause_not_uniquely_proven=True,actual_5s_PWM_not_proven=True,
  stopped_commands=idle['commands'],after=s)
 p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 evidence={}
 for folder in ('hardware_install_r1','hardware_install_r2','post_install_readback_r1','idle_verification_r1','installation_verified_r1'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and f.name!='preserved_installation_evidence.json':evidence[f.relative_to(p.ROOT).as_posix()]=sha(f)
 p.write(out/'preserved_installation_evidence.json',json.dumps(evidence,indent=2)+'\n')
 manifest.update(installed=True,installation_readback_verified=True,calibration_unchanged=True,
  OFF_target_timing_measured=True,fast_kernel_cycles=s['algorithm_fast_cycles'],observer_wall_max_us=runtime['max_wall_us'],
  hardware_timing_qualification_pending=True,new_RUN_regular_scheduler_physically_verified=False,
  real_hardware_5s_not_yet_proven=True,start_commands=0,clear_commands=0,flash_commands=2,
  installation_report='installation_verified_r1/report.json',preserved_new_evidence_files=len(evidence))
 p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
 status=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';old=p.read(status);idx=old.index('## 2026-10-30:')
 note=('## 2026-10-30:3007/3008 установлены,readback и OFF64расчёта пройдены\n\n'
  'ПользовательJ1OFF/мультиметр<20В/обеUSBПК/15ВON подтвердил. НачальныйUSB\n'
  'опросещёнедождалсяenumeration,затемCOM10/13иADBнайденыбезвмешательства.\n'
  'Пассивно доflash<20В/MOE0,точный3006,32КБSRAMсохранены. Обе прошивки\n'
  'по1разу,UnoOpenOCD/NucleoCubeProgrammerverifyOK,независимыйnativeHotPlug\n'
  'readbackтакжеточноHEX,калибровкасовпадает,HMIпоставлен,связьвосстановлена.\n'
  f'OFF64пройдены:ядро{s["algorithm_fast_cycles"]}тактов={s["algorithm_fast_cycles"]/170:.3f}мкс,\n'
  f'observerinnermax{s["algorithm_observer_cycles"]},CPU_IRQwallmax{runtime["max_wall_us"]:.3f}мкс.\n'
  'ЭтоOFF_synthetic_CPU_probe,неработаRUNschedulerподШИМ;новаясхемаАЦП\n'
  'нажелезеподШИМи5секещёНЕпроверены. Coherenttimestamp/RCMreason9новые;1,35А/2048/ядро/профильпрежние.\n'
  f'SAFE/PWM0/run_id0/HVarm0,FOC2/profile128CRC1354279011,zeroReady1,маски{masks}.\n'
  'ДопустимтолькоUNDER_VOLT4принамеренномJ1OFF,этоНЕготовностькпуску.\n'
  'SDHIGH/BIE/config_ok,UARTintegrity/sequence/hardware/transport/RPCtimeouts0.\n'
  f'{len(saved)}прежнихфайловпроверены,новыелоги/readback/SRAM/SD/статусыотдельно.\n'
  'START/CLEAR/ARM0,толькоостановленнаяконфигурацияFOC5Гц/BOUNDED5сек.\n'
  'ТекущееобеUSBПК,15ВON,J1OFF. Автономныйпереносисиловойпуск—другойэтап.\n'
  'НовыйrunnerнуженсPAIR3007/3008,прежнийrun_foc_regular_adc_trial.py\n'
  'ждёт3005/3006. НеSTART/CLEARавтоматически;сохранятьстарыефайлы.\n'
  'Отчёт:foc_regular_adc_fix_r2/installation_verified_r1/report.json.\n\n')
 p.write(status,old[:idx]+note+old[idx:])
 print(json.dumps(dict(passed=True,pair=list(p.NEW),readback_verified=True,fast_kernel_cycles=s['algorithm_fast_cycles'],
  observer_wall_max_us=runtime['max_wall_us'],old_files=len(saved),new_evidence=len(evidence),fault_masks=masks,START=0,CLEAR=0)))
if __name__=='__main__':main()
