"""Record exact installed images and OFF timings; only GET requests on hardware."""
import hashlib,json,urllib.request
import prepare_foc_fast_budget_fix as p

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
    out=p.OUT/'installation_verified_r1';out.mkdir(exist_ok=False)
    installation=json.loads(p.read(p.OUT/'hardware_install_r1/install_report.json'))
    readback=json.loads(p.read(p.OUT/'post_install_readback_r1/report.json'))
    idle=json.loads(p.read(p.OUT/'idle_verification_r1/report.json'))
    assert installation['passed'] and readback['passed'] and idle['passed']
    assert installation['uno_readback_verified'] and installation['nucleo_readback_verified']
    assert installation['calibration_unchanged']
    assert idle['start_commands']==idle['clear_commands']==idle['arm_commands']==0
    preserved=json.loads(p.read(p.OUT/'verification/preserved_captures_sha256.json'))
    for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
    manifest=json.loads(p.read(p.OUT/'manifest.json'))
    for rel,h in manifest['artifacts'].items():assert sha(p.OUT/rel)==h,rel
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==h,rel
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    for name,path in (('final_status','/api/status'),('SD_trace_metadata','/api/bkin-trace'),('SD_snapshots','/api/break-snapshot')):
        request=urllib.request.Request('http://192.168.1.138:8080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
        with opener.open(request,timeout=8) as response:payload=json.load(response)
        assert payload.get('ok') is True,(name,payload.get('error'))
        p.write(out/(name+'.json'),json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    s=json.loads(p.read(out/'final_status.json'))['data'];runtime=s['foc_runtime']
    assert (s['fw_build'],s['mc_fw_build'])==p.NEW
    assert s['state']=='SAFE' and s['pwm']==0 and s['run_id']==0 and s['hmi_hv_armed']==0
    assert s['vdc']<=20 and s['algorithm_selected']==s['algorithm_requested']==2
    assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011
    assert s['mc_current_zero_ready']==1 and s['algorithm_fault']==0
    assert all(s[k]==0 for k in ('mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags',
        'mc_transport_fault','rpc_response_timeouts','rpc_send_timeouts','mc_fault_current_mask','mc_fault_occurred_mask'))
    assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled'] and s['mc_sd_live']['config_ok']
    assert runtime['source']=='OFF_synthetic_CPU_probe' and runtime['observer_steps']==64 and runtime['first_fault'] is None
    assert runtime['meter_errors']==0
    comparison=json.loads(p.read(p.BASE/'autonomous_20261030_before_FOC_r1/report.json'))
    old_fast=comparison['fast_kernel_cycles']
    report=dict(passed=True,pair=list(p.NEW),installed=True,images_readback_verified=True,
        uno_readback_verified=True,native_independent_readback=readback,
        calibration_unchanged=True,source_and_artifact_hashes_verified=True,
        original_captures_hash_verified=len(preserved),no_START_CLEAR_or_ARM=True,
        start_commands=0,clear_commands=0,arm_commands=0,
        programming_resets_used_for_boot=True,manual_motor_reset_commands=0,
        uno_flash_commands=installation['uno_flash_commands'],nucleo_flash_commands=installation['nucleo_flash_commands'],
        measurement_source='OFF_synthetic_CPU_probe',measurement_is_synthetic_inputs_on_actual_MCU=True,
        PWM_outputs_enabled=False,full_powered_adapter_timing_verified=False,
        fast_kernel_cycles=s['algorithm_fast_cycles'],fast_kernel_us=s['algorithm_fast_cycles']/170,
        fast_kernel_limit_cycles=4000,fast_full_adapter_limit_cycles=5312,
        old_same_OFF_kernel_cycles=old_fast,fast_same_OFF_difference_cycles=old_fast-s['algorithm_fast_cycles'],
        observer_legacy_inner_max_cycles=s['algorithm_observer_cycles'],observer_legacy_limit_cycles=85000,
        observer_CPU_IRQ=runtime,protections_changed=False,profile_crc=s['algorithm_profile_crc'],
        first_fault=None,sd=s['mc_sd_live'],after=s)
    p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    note='''# Установка3001/3002 и проверка без ШИМ,30.10.2026

Пользователь подтвердил J1OFF, мультиметр<20В, обе платыUSBПК,15ВON.
Перед записью независимое SWDчтение:10,64–10,65В,MOE0,таймерядра идёт,
прошлый2972 совпал точно с HEX(FFтолько в пропущенном заполнении).
Сохранены32КБSRAM предыдущей прошивки. Выполнена одна запись каждой платы.
OpenOCDподтвердил полную проверку Uno3001, CubeProgrammer — Nucleo3002.
Отдельное чтение Nucleo после загрузки также совпало с точным HEX:
SHA679ff5f393855b3bc77067a2dc2ff2163b9a2beb2d756fd6d363b7fa45b6d482.
SHAзапечатанногоBINbb09f1986d8b7c57cf3a7be0837c896ddb49270c75d170bb8ad6806f6e7951de.
Различаются только нулевые промежутки BIN, отсутствующие в HEX и оставшиесяFF;
каждый программируемый байт проверен. Калибровка до/после совпадает.
Вебобновление установлено, RPC/UART работают без холодногоUSBпереподключения.

Все64OFFслучая пройдены на реальном STM32 с синтетическими входами:
ядро3526тактов=20,741мкс<=4000. Прежний такойжеOFFтест3582такта;
сокращение56тактов. Это НЕ сравнение с5317тактов полного poweredадаптера:
проверки ADC/профиля/возраста и обвязка в этотOFFзамер не входят.
Полный путь под ШИМ ещё не квалифицирован; его предел5312не изменён.

Наблюдатель: внутренний старыйDWTмаксимум24748тактов=145,576мкс.
Расширенная метрика с границами профилировщика: последнийwall143,665мкс,
IRQbodylower32,765мкс,CPUupper110,900мкс. Максимальныйwall146,335мкс,
maxIRQbody34,935мкс,maxCPUupper117,771мкс; максимумы из разных вызовов
не складывать. CPUupper включает вход/выход исключений и края профилировщика,
IRQbodylower — нижняя граница времени тел прерываний. Metererrors0.
Наблюдатель не менялся, повышения его лимита85000тактов нет.

FOCselected=requested2, профиль128/CRC1354279011, автонольготов, SAFE/PWM0,
run_id0,SDHIGH/BIE/config_ok,захват вооружён,новогоSDснимка нет.
Активные/защёлкнутые MCSDKмаски0,algorithmfault0,CRC/sequence/hardware/
transport/RPCtimeouts0. На шине около10В. Пусков/CLEAR/ARM0.
Команды только остановленной конфигурации: FOC,BOUNDED5сек,5Гц,
разгон5Гц/с,замедление1Гц/с. Программные перезапуски после записи были
частью установки; ручного моторного RESET и включения ШИМ не было.
Все854прежних файла проверены и сохранены. Новые статусы/SDметаданные,
логи, SRAM и точное чтение образа сохранены отдельно.

Текущее подключение остаётсяUSBПК,15ВON,J1OFF. Автономная загрузка3001/3002
и реальныйFOC5Гц/5сек с полным адаптером — отдельные последующие проверки,
их успех этимOFFтестом не утверждается. Нового пуска сейчас не выполняем.
'''
    p.write(out/'REPORT_RU.md',note)
    evidence={}
    for folder in ('hardware_install_r1','post_install_readback_r1','idle_verification_r1','installation_verified_r1'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file() and f.name!='preserved_installation_evidence.json':evidence[f.relative_to(p.ROOT).as_posix()]=sha(f)
    p.write(out/'preserved_installation_evidence.json',json.dumps(evidence,indent=2)+'\n')
    manifest.update(installed=True,installation_readback_verified=True,calibration_unchanged=True,
        OFF_target_timing_measured=True,target_timing_measured=True,
        target_timing_measurement_scope='OFF_synthetic_CPU_probe: kernel only and foreground observer; no PWM',
        full_powered_adapter_timing_verified=False,target_timing_qualification_pending=True,
        fast_kernel_cycles=s['algorithm_fast_cycles'],OFF_observer_wall_max_us=runtime['max_wall_us'],
        flash_commands=2,start_commands=0,clear_commands=0,
        installation_report='installation_verified_r1/report.json',preserved_new_evidence_files=len(evidence))
    p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    status=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';text=p.read(status)
    marker=text.index('## 2026-10-30:')
    section='''## 2026-10-30:3001/3002 установлены и сверены;OFF64теста пройдены без ШИМ

Пользователь J1OFF/мультиметр<20В/обеUSBПК/15ВON подтвердил. Перед записью
пассивный SWD10,64В/MOE0,точный прошлый2972;32КБSRAM сохранены. Обе прошивки
записаны по одному разу, UnoOpenOCD и NucleoCubeProgrammerreadbackOK.
Отдельный HotPlugreadbackNucleoточноHEX(толькопустыепромежуткиFF),калибровка
совпадает,обновлениеHMIпоставлено,RPC/UARTбезUSBпереподключения работают.

verify_foc_fast_budget_idle.py:passed,64OFFслучая. Ядро3526тактов=20,741мкс
при прежнем лимите4000;было3582в такомжеOFFтесте. НЕсравнивать3526 с5317
прошлого полного poweredадаптера:OFFзамер обвязку ADC/профиля/свежести не включает.
Полный5312тактовыйruntimeдедлайн остаётся и на3002подШИМ покаНЕпроверен.
Наблюдатель legacymax24748тактов; полнаяметрикаlastwall143,665/IRQlower32,765/
CPUupper110,900мкс,maxwall146,335/maxIRQ34,935/maxCPU117,771мкс.
Максимумы не складывать,CPUupperнечистоеCPUвремя. Metererrors0,firstfaultNone.

SAFE/PWM0/run_id0,FOCselected=requested2,profile128/CRC1354279011,zeroReady1,
SDHIGH/BIE/config_ok,захватвооружён/новогоснимканет,всемаскиаварий0,
UARTCRC/sequence/hardware/transport/RPCtimeouts0. Шинаоколо10В.
START/CLEAR/ARM0,5Гц/BOUNDED5сек только в остановленной конфигурации.
Все854старыхфайла проверены; новые логи/SD/SRAM/readback/тайминги сохранены.
Отчёт:`artifacts/live_bench_20261029/foc_fast_budget_fix_r1/installation_verified_r1/REPORT_RU.md`.

Физически покаобеUSBПК,15ВON,J1OFF. АвтономнуюзагрузкуиFOC5Гц/5секподШИМ
согласовыватькакследующийэтап;сейчасникакихновыхSTART/CLEAR/flash.
Длятехбудущихпроверокиспользовать3001/3002(старыйrun_foc_runtime_trial.py
содержитPAIR2971/2972, его надо адаптироватьбезослабленияпроверок).

'''
    p.write(status,text[:marker]+section+text[marker:])
    print(json.dumps(dict(passed=True,pair=list(p.NEW),readback_verified=True,
        fast_kernel_cycles=s['algorithm_fast_cycles'],observer_wall_max_us=runtime['max_wall_us'],
        old_captures_preserved=len(preserved),new_evidence_files=len(evidence),start_commands=0,clear_commands=0)))

if __name__=='__main__':main()
