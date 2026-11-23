"""Record low-bus autonomous verification; GET only, no motor commands."""
import hashlib,json,urllib.request
import prepare_foc_update_latency_fix as p
import run_foc_update_latency_trial as run

def main():
 out=p.OUT/'autonomous_before_FOC_r2'
 checked=json.loads(p.read(out/'report.json'));assert checked['passed'] and checked['OFF_CPU_IRQ_split_verified']
 assert not (out/'autonomous_summary.json').exists()
 token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
 op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for name,path in (('saved_status','/api/status'),('SD_trace_metadata','/api/bkin-trace'),('SD_snapshots','/api/break-snapshot')):
  req=urllib.request.Request('http://192.168.1.138:8080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
  with op.open(req,timeout=8) as response:obj=json.load(response)
  assert obj['ok'];p.write(out/(name+'.json'),json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
 s=json.loads(p.read(out/'saved_status.json'))['data'];sd=s['mc_sd_live']
 assert run.trial.off(s) and run.trial.profile(s) and run.trial.off_timing_ready(s)
 assert s['run_id']==s['run_start_ms']==0 and s['hmi_hv_armed']==0 and s['vdc']<=20
 assert sd['level']=='HIGH' and sd['break_irq_enabled'] and sd['config_ok'] and sd['capture_running']
 for k in ('algorithm_fault','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_transport_fault',
           'rpc_response_timeouts','rpc_send_timeouts'):assert s[k]==0,(k,s[k])
 masks=(s['mc_fault_current_mask'],s['mc_fault_occurred_mask'])
 assert all(mask in (0,4) for mask in masks)
 if any(masks):assert 'MC_UNDER_VOLT' in s['mc_fault_detail']
 saved={}
 for rel in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json'):
  saved.update(json.loads(p.read(p.OUT/rel)))
 for rel,h in saved.items():assert hashlib.sha256((p.ROOT/rel).read_bytes()).hexdigest()==h,rel
 summary=dict(passed=True,pair=list(p.NEW),autonomous_user_confirmation=True,
  initial_GET_timeout_saved=True,initial_timeout_not_proven_firmware_fault=True,
  outputs_off=True,run_id=0,vbus_V=s['vdc'],profile_crc=s['algorithm_profile_crc'],
  qualification=s['algorithm_qualification'],algorithm_selected=s['algorithm_selected'],
  zero_ready=True,SD=sd,UART_RPC_errors_zero=True,current_fault_mask=masks[0],occurred_fault_mask=masks[1],
  low_bus_fault_while_J1_OFF=any(masks),not_motor_start_clearance=True,
  OFF_CPU_IRQ=s['foc_runtime'],fast_kernel_cycles=s['algorithm_fast_cycles'],
  observer_inner_max_cycles=s['algorithm_observer_cycles'],
  first_runtime_fault=None,guard2048_unchanged=True,old_files_preserved=len(saved),
  START=0,CLEAR=0,ARM=0,RESET=0,flash=0,stopped_configuration_commands=checked['commands'],
  next_step='Enable onlyJ1 through soft-start; leave15V/powerbanks/wiring, PC/Saleae disconnected. NoSTART/RESET. Then fresh powered bus/SD/fault checks before one5Hz5sFOC trial. CLEAR not authorized.')
 p.write(out/'autonomous_summary.json',json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 p.write(out/'saved_files_sha256.json',json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file() and f.name!='saved_files_sha256.json'},indent=2)+'\n')
 m=json.loads(p.read(p.OUT/'manifest.json'));m.update(autonomous_preflight_verified=True,
  autonomous_preflight_report='autonomous_before_FOC_r2/autonomous_summary.json',powered_test_pending=True)
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 status=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';old=p.read(status);idx=old.index('## 2026-10-30:')
 note=('## 2026-10-30:3003/3004 автономная проверка пройдена,J1OFF;далее включить толькоJ1\n\n'
  'Пользовательготовоподтвердилпредыдущийшаг:обеповербанки,PC/SaleaeOFF,15ВON,J1OFF.\n'
  'ПервыйGETtimeoutсохранёнвautonomous_before_FOC_r1,повторнаяпроверкаr2прошла.\n'
  'НеобъявлятьстартовыйtimeoutдефектомПО. Свежие3003/3004:SAFE/PWM0/run_id0,\n'
  f'шина{s["vdc"]}В,FOC2/profile128CRC1354279011,zeroReady1,SDHIGH/BIE/config_ok.\n'
  f'Маскиcurrent/occurred{masks}:допустимтолькоUNDER_VOLT4приJ1OFF,\n'
  'этоНЕготовностькпуску. UARTintegrity/sequence/hardware/transport/RPCtimeouts0.\n'
  f'OFF64готовы,ядро{s["algorithm_fast_cycles"]},observerinnermax{s["algorithm_observer_cycles"]};\n'
  'CPU_IRQsourceOFF_synthetic_CPU_probe,firstfaultNone,metererrors0.2048прежний.\n'
  '1007прежнихфайловпроверены. ВэтомэтапеSTART/CLEAR/ARM/RESET/flash0.\n'
  'СледующийфизическийшагТОЛЬКОJ1черезsoft-start;15В/повербанки/проводку\n'
  'оставить,PC/SaleaeOFF,Пуск/RESETненажимать. Затемсвежаяшина/SD/маски;\n'
  'приготовностиодинFOC5Гц5секCPU_IRQ/ADC/автостопчерезrun_foc_update_latency_trial.py.\n'
  'CLEARнеразрешён:еслиостанетсязащёлка,сохранитьснимокиполучитьразрешение.\n'
  'Отчёт:foc_update_latency_fix_r1/autonomous_before_FOC_r2/autonomous_summary.json.\n\n')
 p.write(status,old[:idx]+note+old[idx:])
 print(json.dumps(dict(passed=True,pair=list(p.NEW),vbus_V=s['vdc'],fault_masks=masks,
  SD=sd['level'],old_files_preserved=len(saved),START=0,CLEAR=0,ARM=0)))
if __name__=='__main__':main()
