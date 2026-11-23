"""Freeze the observed first cause and next offline candidate; GET only."""
import hashlib,json,urllib.request
import prepare_foc_fast_budget_fix as p

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
    out=p.BASE/'powered_FOC_CPU_IRQ_20261030_r1'
    assert not (out/'analysis.json').exists(), 'Do not overwrite a captured analysis'
    trial=json.loads(p.read(out/'report.json'))
    final=json.loads(p.read(out/'final_status.json'))
    timing=json.loads(p.read(out/'CPU_IRQ_and_first_fault.json'));fault=timing['first_fault']
    adc=json.loads(p.read(out/'ADC_peak_decoded.json'))
    assert trial['start_commands']==1 and trial['clear_commands']==0
    assert fault['reason_code']==6 and final['algorithm_fast_cycles']==5317
    assert final['pwm']==0 and final['mc_fault_current_mask']==1
    assert not timing['observer_measured'] and timing['observer_steps']==0
    observed=None
    try:
        with urllib.request.urlopen('http://192.168.1.138:8080/api/status',timeout=5) as response:
            obj=json.load(response)
        observed=obj.get('data',obj)
        p.write(out/'after_analysis_status.json',json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
        assert observed['fw_build']==2026102971 and observed['mc_fw_build']==2026102972
        assert observed['pwm']==0, 'Unexpected outputs: preserve evidence and investigate'
    except (OSError,ValueError) as exc:
        p.write(out/'after_analysis_status_error.json',json.dumps(dict(error=str(exc),GET_only=True),indent=2)+'\n')
    analysis=dict(schema='mic_ai.foc_first_fast_deadline.v1',trial_completed_5s=False,
        pair=[2026102971,2026102972],start_commands=1,clear_commands=0,flash_commands=0,
        repeated_start_commands=0,outputs_off_confirmed=True,
        exact_first_cause='FT_FAST_DURATION',reason_code=6,algorithm_fault='MA_STALE',
        MCSDK_fault_mask=1,MCSDK_fault='MC_DURATION',
        fast_elapsed_cycles=5317,unchanged_limit_cycles=5312,overrun_cycles=5,
        fast_elapsed_us=fault['fast_elapsed_us'],
        ADC_age_us=fault['adc_age_us'],ADC_age_limit_us=187.5,
        estimate_age_us=fault['estimate_age_us'],estimate_age_limit_us=2000,
        observer_ever_ran=False,runtime_CPU_IRQ_split_available=False,
        runtime_CPU_IRQ_limitation='No observer invocation occurred; zero timing is not a measured computation time.',
        old_OFF_observer_max_cycles_not_live=final['algorithm_observer_cycles'],
        ADC_frames=adc['total_samples'],ADC_retained_rows=len(adc['samples']),
        nominal_peak_A=max(abs(x) for s in adc['samples'] for x in s['nominal_currents_a']),
        ADC_binary_sha256=sha(out/'ADC_peak.bin'),
        physical_rotation_verified=False,physical_current_scale_qualified=False,
        UART_integrity_errors=final['mc_bad_integrity'],UART_hardware_flags=final['mc_uart_error_flags'],
        UART_transport_fault=final['mc_transport_fault'],
        run_elapsed_ms_session_not_PWM_duration=final['run_elapsed_ms'],
        last_confirmed_vbus_V=(observed or final)['vdc'],
        latest_observation_available=observed is not None,
        new_pair=[2026103001,2026103002],new_candidate_built=True,new_candidate_installed=False,
        target_timing_improvement_verified=False,protections_changed=False,old_captures_retained=True)
    p.write(out/'analysis.json',json.dumps(analysis,ensure_ascii=False,indent=2)+'\n')
    report='''# FOC5Гц: останов по длительности быстрого расчёта,30.10.2026

Выполнен ровно один START с заданием FOC5Гц и лимитом5сек, без CLEAR,
RESET или новой прошивки. Защита остановила пуск раньше пяти секунд.
После STOP подтверждены SAFE и ШИМ0. Силовое питание пользователь не менял.

Зафиксирован именно FT_FAST_DURATION(6):5317тактов при неизменном пределе5312,
то есть превышение5тактов (~29нс при170МГц). MA_STALE здесь обозначает
дедлайн быстрого пути, а не устаревший вход. Возраст реального АЦП29,394мкс
при пределе187,5мкс, оценки874,929мкс при пределе2000мкс.
MCSDKcurrent/occurred=0x0001(MC_DURATION). UARTCRC/аппаратные/транспортные0.
Нового захвата SD нет; после остановки SDHIGH, BIE/config_ok восстановлены.

Наблюдатель не вызван ни разу: observer_steps0. Поэтому runtimeCPU/IRQ=0
не измеряют его трудоёмкость. Старый algorithm_observer_cycles24721 — результат
OFFпроверки, его нельзя выдавать за время наблюдателя в этом пуске.
Захват АЦП получен полностью,1024байта/35страниц:16кадров, сохранены12строк,
6Атриггера нет. Номинальный максимум0,278214А не является калибровкой ампер.
Время сеанса69мс не равно длительности физического ШИМ; вращение не подтверждалось.

Подготовлена3001/3002: повторная проверка той же модели исключена только в
пределах того же приоритетного IRQ, сама проверка выполняется каждый кадр;
константа точного профиля размещена статически; общее библиотечное lroundf
заменено эквивалентным ограниченным округлением CCR; исключена лишняя очистка
полностью заполняемого снимка. Для некорректного CCR вход отвергается до окна.
Порог5312, пределы свежести, токовые/SD/Breakзащиты и автостоп5сек сохранены.

На ПК:2393218случаев округления;180000регулятора+75000модулятора побитно
равны прежнему коду;12строк текущего АЦП воспроизведены;26некорректных моделей
отвергнуты. Матмодель запущена заново:4/4центральных и54/60общих сценариев,
все численные результаты совпали с прежним отчётом. Шесть крайних вариаций
параметров остаются неуспешными; это не обещание устойчивости к любому двигателю.
Обе сборки и ELFидентичность проверены, вызова lroundf в ARMбыстром пути нет.
На Nucleo новый код ещё не установлен и его время пока не измерено.

Следующий физический шаг нужен только для записи: J1OFF, мультиметр<20В,
обе платы на USBПК;15В, двигатель и проводку можно оставить. Сначала чтение
обратно и OFFCPUпроверка; новый силовой пуск сейчас не выполняется.
'''
    p.write(out/'REPORT_RU.md',report)
    hashes={f.name:sha(f) for f in out.iterdir() if f.is_file() and f.name!='saved_files_sha256.json'}
    p.write(out/'saved_files_sha256.json',json.dumps(hashes,indent=2)+'\n')
    manifest=json.loads(p.read(p.BASE/'manifest.json'))
    manifest.update(powered_trial_20261030=dict(start_commands=1,clear_commands=0,completed_5s=False,
        first_fault_reason=6,fast_cycles=5317,limit_cycles=5312,outputs_off=True,
        report='powered_FOC_CPU_IRQ_20261030_r1/analysis.json'))
    p.write(p.BASE/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    status=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';previous=p.read(status)
    preface='''## 2026-10-30:2971/2972FOC остановлен точным FT_FAST_DURATION;3001/3002 готовы, не установлены

Один START, CLEAR0:5317тактов при неизменном5312. АЦП29,394мкс<187,5мкс,
оценка874,929мкс<2000мкс, наблюдатель ещё не работал(0шагов), поэтому liveCPU/IRQ
наблюдателя в этом пуске не измерены. MCSDKмаска1(MC_DURATION), MA_STALE3,
не прежний неподтверждённый «медленный наблюдатель». UARTCRC/hardware/transport0.
ШИМвыключен/SAFE, run_id1. J1 и15В покаON, платы на повербанках, PC/SaleaeOFF.
НовыйSDснимок не возник, SDHIGH/BIE/config_ok; старые записи сохранены.
ADC1024байта/35страниц,16кадров,12строк, номинальныйpeak0,278214А(масштаб не квалифицирован).
Пять секунд не отработаны; повторного пуска/CLEAR/RESET/flash не было.

3001/3002готовы офлайн: в одном IRQ убраны дублирующая проверка модели,
универсальное lroundf(CCR), лишняя очистка снимка; exactпрофиль staticconst.
Проверка модели остаётся каждый кадр, все пороги/окна/автостоп прежние.
2393218rounding,255000bitwisecontrol/modulation,12текущих ADCстрок,26badmodels
пройдены. Матмодельперезапуск4/4central,54/60total; сценарии полностью совпали.
Сборки безошибок, ELFпрофиль и источники подтверждены. Targettiming3002 ещё
НЕ измерен; кандидат НЕ прошит. Не обещать устранение всехruntimeотказов.

Далее только подготовленная запись: J1OFF/мультиметр<20В/обе платыUSBПК,
15В и двигатель/проводку оставить; install_foc_fast_budget_fix.py и чтение
обратно, затемverify_foc_fast_budget_idle.py. Пока силовоеON не прошивать,
не посылать START/CLEAR. Захват и анализ:
`artifacts/live_bench_20261029/foc_runtime_fix_r1/powered_FOC_CPU_IRQ_20261030_r1/REPORT_RU.md`.
Кандидат:`artifacts/live_bench_20261029/foc_fast_budget_fix_r1/manifest.json`.

'''
    assert previous.startswith('# Текущий статус стенда\n')
    p.write(status,'# Текущий статус стенда\n\n'+preface+previous.split('\n',2)[2])
    print(json.dumps(dict(trial_completed_5s=False,reason=6,cycles=5317,limit=5312,
        outputs_off=True,latest_GET_available=observed is not None,new_pair_built=[2026103001,2026103002],
        flashed=False,preserved_current_files=len(hashes))))

if __name__=='__main__':main()
