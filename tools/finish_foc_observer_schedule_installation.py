"""Record verified installation and measured OFF timing; GET-only live checks."""
import hashlib
import json
import urllib.request
import prepare_foc_observer_schedule_fix as p


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    out = p.OUT / 'installation_verified_r1'
    out.mkdir(exist_ok=False)
    installation = json.loads(p.read(p.OUT / 'hardware_install_r2/install_report.json'))
    readback = json.loads(p.read(p.OUT / 'post_install_readback_r1/report.json'))
    idle = json.loads(p.read(p.OUT / 'idle_verification_r1/report.json'))
    assert installation['passed'] and readback['passed'] and idle['passed']
    assert installation['uno_flash_commands'] == installation['nucleo_flash_commands'] == 1
    assert installation['uno_readback_verified'] and installation['nucleo_readback_verified']
    assert installation['calibration_unchanged']
    assert idle['start_commands'] == idle['clear_commands'] == idle['arm_commands'] == 0
    manifest = json.loads(p.read(p.OUT / 'manifest.json'))
    for rel, digest in json.loads(p.read(p.OUT / 'source_hashes.json')).items():
        assert sha(p.OUT / rel) == digest, rel
    for rel, digest in manifest['artifacts'].items():
        assert sha(p.OUT / rel) == digest, rel
    saved = json.loads(p.read(p.OUT / 'verification/preserved_captures_sha256.json'))
    for rel, digest in saved.items():
        assert sha(p.ROOT / rel) == digest, rel
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = p.read(p.ROOT / '.unoq_ssh/control_token').strip()
    for name, path in (('final_status', '/api/status'), ('SD_trace_metadata', '/api/bkin-trace'), ('SD_snapshots', '/api/break-snapshot')):
        req = urllib.request.Request('http://192.168.1.138:8080' + path,
            headers={'X-UNOQ-Control-Token': token}, method='GET')
        with opener.open(req, timeout=8) as response:
            obj = json.load(response)
        assert obj['ok']
        p.write(out / (name + '.json'), json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    s = json.loads(p.read(out / 'final_status.json'))['data']
    assert (s['fw_build'], s['mc_fw_build']) == p.NEW
    assert s['state'] == 'SAFE' and s['pwm'] == 0 and s['run_id'] == 0 and s['hmi_hv_armed'] == 0
    assert s['vdc'] <= 20 and s['algorithm_selected'] == s['algorithm_requested'] == 2
    assert s['algorithm_qualification'] == 128 and s['algorithm_profile_crc'] == 1354279011
    assert s['mc_current_zero_ready'] == 1
    for key in ('algorithm_fault', 'mc_bad_integrity', 'mc_bad_sequence', 'mc_uart_error_flags',
                'mc_transport_fault', 'rpc_response_timeouts', 'rpc_send_timeouts'):
        assert s[key] == 0, (key, s[key])
    masks = [s['mc_fault_current_mask'], s['mc_fault_occurred_mask']]
    assert all(mask in (0, 4) for mask in masks), masks
    sd = s['mc_sd_live']
    assert sd['level'] == 'HIGH' and sd['break_irq_enabled'] and sd['config_ok']
    runtime = s['foc_runtime']
    assert runtime['source'] == 'OFF_synthetic_CPU_probe' and runtime['observer_steps'] == 64
    assert runtime['first_fault'] is None and runtime['meter_errors'] == 0
    assert s['foc_runtime_valid'] == 1 and all('foc_runtime_w' + str(i) in s for i in range(42))
    old = json.loads(p.read(p.BASE / 'autonomous_before_FOC_r1/report.json'))['after']
    comparison = dict(previous_package='3009/3010', installed_package='3011/3012',
        source='OFF_synthetic_CPU_probe,64cases',
        observer_inner_max_cycles_before=old['algorithm_observer_cycles'],
        observer_inner_max_cycles_after=s['algorithm_observer_cycles'],
        observer_wall_max_us_before=old['foc_runtime']['max_wall_us'],
        observer_wall_max_us_after=runtime['max_wall_us'],
        CPU_upper_max_us_before=old['foc_runtime']['max_cpu_upper_us'],
        CPU_upper_max_us_after=runtime['max_cpu_upper_us'],
        limitation='Separate boots and IRQ phases; OFF measurements do not establish RUN scheduling, queue latency or five-second operation.')
    p.write(out / 'OFF_timing_comparison.json', json.dumps(comparison, indent=2) + '\n')
    report = dict(passed=True, pair=list(p.NEW), installed=True, readback_verified=True,
        independent_native_readback=readback, calibration_unchanged=True, old_files_verified=len(saved),
        START=0, CLEAR=0, ARM=0, flash_commands=2, programming_boot_resets_used=True,
        OFF_cases=64, fast_kernel_cycles=s['algorithm_fast_cycles'], observer_inner_max_cycles=s['algorithm_observer_cycles'],
        CPU_IRQ=runtime, comparison=comparison, UART_RPC_errors_zero=True, SD=sd, fault_masks=masks,
        diagnostic_rejection_counters=dict(research_native_bad=s['research_native_bad'], foc_runtime_bad=s['foc_runtime_bad'],
            unchanged_during_idle_observation=all(json.loads(line)['research_native_bad'] == idle['after']['research_native_bad']
                for line in p.read(p.OUT / 'idle_verification_r1/status.jsonl').splitlines()),
            cause_of_preexisting_counter_not_identified=True),
        profile_crc=s['algorithm_profile_crc'], qualification=s['algorithm_qualification'],
        current_trip_A=1.35, ADC_guard_ticks=2048, estimate_age_limit_ms=2,
        protections_unchanged=True, new_RUN_timing_not_measured=True,
        hardware_five_seconds_not_proven=True, after=s)
    p.write(out / 'report.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    evidence = {}
    for folder in ('hardware_install_r1', 'hardware_install_r2', 'post_install_readback_r1',
                   'idle_verification_r1', 'installation_verified_r1'):
        for f in (p.OUT / folder).rglob('*'):
            if f.is_file() and f.name != 'preserved_installation_evidence.json':
                evidence[f.relative_to(p.ROOT).as_posix()] = sha(f)
    p.write(out / 'preserved_installation_evidence.json', json.dumps(evidence, indent=2) + '\n')
    manifest.update(installed=True, installation_readback_verified=True, calibration_unchanged=True,
        OFF_target_timing_measured=True, observer_inner_max_cycles=s['algorithm_observer_cycles'],
        target_timing_measurement_required_before_powered_trial=False, RUN_queue_latency_not_measured=True,
        observer_wall_max_us=runtime['max_wall_us'], CPU_upper_max_us=runtime['max_cpu_upper_us'],
        hardware_RUN_qualification_pending=True, physical_5s_not_proven=True,
        START=0, CLEAR=0, flash_commands=2, installation_report='installation_verified_r1/report.json',
        preserved_new_installation_files=len(evidence))
    p.write(p.OUT / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    report_file = p.OUT / 'REPORT_RU.md'
    previous = p.read(report_file)
    note = f'''# Установка 3011/3012 проверена, 30.10.2026

Обе платы записаны по одному разу; проверка чтением обратно успешна.
Дополнительный пассивный HotPlug readback Nucleo точно соответствует HEX
(FF в пропусках HEX учтены); ШИМ выключен, uptime продвигается.
Калибровка сохранена. Первая попытка установки остановилась до записи:
Windows ещё не перечислила COM Uno; после enumeration установка прошла,
повторных записей успешно прошитых образов не было. RPC восстановилась
без физического переподключения; HMI установлен.

OFF проверка:64/64, ядро{s['algorithm_fast_cycles']}тактов,
observerinnermax{s['algorithm_observer_cycles']}тактов={s['algorithm_observer_cycles']/170:.3f}мкс.
Максимум wall наблюдателя{runtime['max_wall_us']:.3f}мкс,
CPUuppermax{runtime['max_cpu_upper_us']:.3f}мкс. В прошлой OFF записи
соответственно143,818мкс wall /110,141мкс CPUupper /24328тактов innermax.
Это отдельные загрузки с разными фазами IRQ, не идентичный RUN-бенчмарк.
Ускорение OFF наблюдается; длина очереди и дедлайн под ШИМ ещё не проверены.

SAFE/PWM0/run_id0/arm0, FOC2/profile128CRC1354279011, автоноль готов.
SD HIGH/BIE/config_ok; UART ORE/CRC/sequence/transport/RPCtimeouts0.
Маски MC{masks}. Постоянные диагностические счётчики research_native_bad/
foc_runtime_bad={s['research_native_bad']}/{s['foc_runtime_bad']} не росли в окне проверки;
их исходная причина не установлена, они не являются аппаратными UART ORE.
Прежние1521файл проверены SHA-256, новые записи сохранены отдельно.
START/CLEAR/ARM0; только остановленная конфигурация FOC5Гц/5сек.
Защиты1,35А/2048/2мс/RCM1мс/fast5312 прежние. Силового пуска не было.

Следующий этап: обе платы на повербанки после паузы5сек, USBПК и все
соединения Saleae сняты;15В оставить, J1 пока выключен, Пуск/RESET
не нажимать. Сначала автономная связь/SD/нулевые UART и маски.
Не включать J1 до этой проверки. Перепрошивка для переноса не нужна.

Подробная запись: installation_verified_r1/report.json.

---

'''
    p.write(report_file, note + previous)
    status = p.ROOT / 'CURRENT_BENCH_STATUS_RU.md'
    previous = p.read(status)
    index = previous.index('## 2026-10-30:')
    note = f'''## 2026-10-30: 3011/3012 установлены, readback/OFF64 пройдены

Пользователь «готово» подтвердил J1OFF/мультиметр<20В/обеUSBПК,15Воставить.
Первая попытка hardware_install_r1 завершилась доflash:COMUnoещёнеперечислен.
ADBdevice затемCOM10/13 появились, без нового подключения;
hardware_install_r2 успешно записала обе платы по1разу, verify обеихOK,
native независимый HotPlug readback точныйHEX, калибровка unchanged.
Исходные32КБSRAM сохранены. Прошивочные/загрузочныеreset использованы,
но motor START/CLEAR/ARM0. RPC вернулась без user coldboot, HMI поставлен.
OFF64готовы, fast{s['algorithm_fast_cycles']}тактов, observerinnermax{s['algorithm_observer_cycles']}тактов.
OFFwallmax{runtime['max_wall_us']:.3f}мкс, CPUuppermax{runtime['max_cpu_upper_us']:.3f}мкс;
раньшеOFF143,818/110,141мкс иinner24328. Разныеboot/IRQфазы — неRUN A/B.
Пороги1,35А/2048/2мс/5312/RCM1мс прежние. Runtime5сек ещёНЕподтверждён,
новая очередь подШИМ не измерена. 1521старыйфайлSHAпроверен, новыеотдельно.
SAFE/PWM0/run_id0/arm0, FOC2/profile128CRC1354279011,zeroReady1,
SDHIGH/BIE/config_ok/captureRunning, UART/RPC0, MC masks{masks}.
Диагностические rejected-счётчики1/1 постоянны вOFFокне, причина не установлена.
Текущее: обеUSBПК,15ВON,J1OFF. Следующийфизическийшаг: обеUSBПКотключить
на5сек, затемобенаповербанки; SaleaeвключаяGNDснят;15Воставить,J1OFF,
Пуск/RESETненажимать. Потом автономнаяпроверкаNEW3011/3012сновымoutdir.
Никакой CLEAR/START автоматически: текущая задача была запись/проверкабезШИМ.
Отчёт:foc_observer_schedule_fix_r1/installation_verified_r1/report.json.

'''
    p.write(status, previous[:index] + note + previous[index:])
    print(json.dumps(dict(passed=True, pair=list(p.NEW), readback_verified=True,
        observer_inner_max_cycles=s['algorithm_observer_cycles'], wall_max_us=runtime['max_wall_us'],
        CPU_upper_max_us=runtime['max_cpu_upper_us'], old_files=len(saved), new_files=len(evidence),
        masks=masks, START=0, CLEAR=0)))


if __name__ == '__main__':
    main()
