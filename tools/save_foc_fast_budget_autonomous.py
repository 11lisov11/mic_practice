"""Save autonomous low-bus preflight and SD metadata; GET only."""
import hashlib,json,urllib.request
import prepare_foc_fast_budget_fix as p
import run_foc_fast_budget_trial as run

def main():
    out=p.OUT/'autonomous_before_FOC_r2'
    check=json.loads(p.read(out/'report.json'));assert check['passed'] and check['OFF_CPU_IRQ_split_verified']
    assert not (out/'autonomous_summary.json').exists()
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for name,path in (('saved_status','/api/status'),('SD_trace_metadata','/api/bkin-trace'),('SD_snapshots','/api/break-snapshot')):
        req=urllib.request.Request('http://192.168.1.138:8080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
        with op.open(req,timeout=8) as response:obj=json.load(response)
        assert obj['ok'];p.write(out/(name+'.json'),json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    s=json.loads(p.read(out/'saved_status.json'))['data'];sd=s['mc_sd_live'];timing=s['foc_runtime']
    assert run.trial.off(s) and run.trial.profile(s) and run.trial.off_timing_ready(s)
    assert s['run_id']==s['run_start_ms']==0 and s['hmi_hv_armed']==0 and s['vdc']<=20
    assert sd['level']=='HIGH' and sd['break_irq_enabled'] and sd['config_ok'] and sd['capture_running']
    assert all(s[k]==0 for k in ('mc_fault_current_mask','mc_fault_occurred_mask','mc_fault','bp_fault',
        'algorithm_fault','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_transport_fault',
        'rpc_response_timeouts','rpc_send_timeouts'))
    preserved={}
    for rel in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json'):
        preserved.update(json.loads(p.read(p.OUT/rel)))
    for rel,h in preserved.items():assert hashlib.sha256((p.ROOT/rel).read_bytes()).hexdigest()==h,rel
    report=dict(passed=True,pair=list(p.NEW),autonomous_operator_confirmed=True,
        previous_first_GET_timed_out=True,initial_timeout_not_diagnosed_as_firmware_failure=True,
        fresh_statuses_verified=len(p.read(out/'status.jsonl').splitlines()),
        profile_crc=s['algorithm_profile_crc'],qualification=s['algorithm_qualification'],
        algorithm_selected=s['algorithm_selected'],vbus_V=s['vdc'],outputs_off=True,run_id=0,
        current_zero_ready=True,active_and_occurred_faults_zero=True,UART_RPC_errors_zero=True,
        SD=sd,OFF_CPU_IRQ=timing,fast_kernel_cycles=s['algorithm_fast_cycles'],
        observer_inner_max_cycles=s['algorithm_observer_cycles'],
        no_powered_timing_claim=True,full_powered_adapter_verified=False,
        preserved_files_verified=len(preserved),start_commands=0,clear_commands=0,arm_commands=0,reset_commands=0,flash_commands=0,
        stopped_commands=check['commands'],
        next_step='Enable J1 only through soft-start, retain15V/powerbanks, no PC/Saleae, noSTART/RESET. Fresh powered preflight then one authorized FOC5Hz5s trial; no CLEAR authorized.')
    p.write(out/'autonomous_summary.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    p.write(out/'saved_files_sha256.json',json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file() and f.name!='saved_files_sha256.json'},indent=2)+'\n')
    manifest=json.loads(p.read(p.OUT/'manifest.json'));manifest.update(autonomous_preflight_verified=True,
        autonomous_preflight_report='autonomous_before_FOC_r2/autonomous_summary.json',powered_test_pending=True)
    p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    status=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';text=p.read(status);idx=text.index('## 2026-10-30:')
    section='''## 2026-10-30:3001/3002 на повербанках проверены;J1OFF,готово к включению J1

Пользователь:обе повербанки,PC/SaleaeOFF,15ВON,J1OFF,Пуск/RESETне нажимал.
ПервыйGETtimeout сохранён вautonomous_before_FOC_r1;повторный полныйOFFтест
прошёл вautonomous_before_FOC_r2. Не выдавать стартовыйtimeout за дефектПО.
Свежие3001/3002:SAFE/PWM0/run_id0/HVarm0,10В,FOCselected=requested2,
profile128/CRC1354279011,zeroReady1,SDHIGH/BIE/config_ok/capture_running.
Маскиактивных/защёлкнутыхаварий0,UARTRPCerrors0. OFF64случаяготовы,
ядро3526тактов,observerinnermax24736;CPU/IRQsourceOFF_synthetic_CPU_probe,
firstfaultNone,metererrors0. Это не работа подШИМ; полныйадаптерпокаНЕпроверен.
908старых/установочныхфайлов поSHAсохранены. START/CLEAR/ARM/RESET/flash0.
Задана только остановленнаяконфигурацияFOC5Гц/BOUNDED5сек,разгон5/замедление1.
Следующийфизическийшаг:ТОЛЬКОJ1черезsoft-start;15В/повербанки/двигатель
оставить,PC/SaleaeOFF,Пуск/RESETне нажимать. После подтверждения питания:
свежая шина/SD/защиты и один согласованныйFOC5Гц5сек сCPU_IRQ/ADC/автостопом,
run_foc_fast_budget_trial.py --confirm-autonomous-powered с новым каталогом.
CLEARнеразрешён,самостоятельноне добавлять;еслизащёлка—сохранитьSDиуточнить.
Отчёт:artifacts/live_bench_20261029/foc_fast_budget_fix_r1/autonomous_before_FOC_r2/autonomous_summary.json.

'''
    p.write(status,text[:idx]+section+text[idx:])
    print(json.dumps(dict(passed=True,pair=list(p.NEW),vbus_V=s['vdc'],SD=sd['level'],all_fault_masks_zero=True,
        fast_kernel_cycles=s['algorithm_fast_cycles'],observer_inner_max_cycles=s['algorithm_observer_cycles'],
        preserved_files=len(preserved),START=0,CLEAR=0,ARM=0)))

if __name__=='__main__':main()
