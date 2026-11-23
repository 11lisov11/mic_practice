"""Seal prepared commissioning images and software evidence; never flash/run."""
import hashlib,json,re,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from prepare_standstill_commissioning import ROOT,BASE,OUT,NEW,read,write

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    if (OUT/'manifest.json').exists():
        assert not json.loads(read(OUT/'manifest.json')).get('installed'),'Never reseal/reset the status of an installed package'
    model=json.loads(read(OUT/'model_final/report.json'))
    adc=json.loads(read(OUT/'apex_selftest_r1/report.json'))
    llext=json.loads(read(OUT/'build/uno/llext-check.json'))
    assert model['passed'] and adc['passed'] and llext['pass']
    for name,digest in model['source_sha256'].items():assert sha(ROOT/'tools/motor_commissioning'/name)==digest
    for dest in ('nucleo/Inc','UNOQ_MOTOR'):
        assert (OUT/dest/'identify_wire.h').read_bytes()==(ROOT/'tools/motor_commissioning/identify_wire.h').read_bytes()
    assert (OUT/'nucleo/Inc/identify_core.h').read_bytes()==(ROOT/'tools/motor_commissioning/identify_core.h').read_bytes()
    assert read(ROOT/'tools/motor_commissioning/native.inc') in read(OUT/'nucleo/Src/multi_native.c')
    assert read(ROOT/'tools/motor_commissioning/hmi_completion.py') in read(OUT/'web_hmi/server.py')
    verification=OUT/'verification'
    commands=[('native_host_tests.log',[str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'tools/test_standstill_commissioning.py')]),
      ('analysis_tests.log',[str(ROOT/'.venv-research-gpu/Scripts/python.exe'),'-m','pytest',
       str(ROOT/'tests/test_acim_standstill_identification.py'),str(ROOT/'tests/test_commissioning_capture.py'),'-q']),
      ('web_syntax.log',['C:/Program Files/nodejs/node.exe','--check',str(OUT/'web_hmi/static/app.js')])]
    for name,cmd in commands:
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        write(verification/name,r.stdout+r.stderr);r.check_returncode()
    uno=json.loads(read(OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    assert uno['firmware_build_id']==NEW[0]
    for item in uno['artifacts']:assert sha(OUT/'build/uno'/item['file'])==item['sha256'].lower()
    log=read(OUT/'native_final_build.log')
    assert not re.search(r'\b(?:error|warning):',log,re.I)
    assert '87824' in log and '24592' in log
    compiler=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin')
    native=OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL'
    for fmt,suffix in [('binary','.bin'),('ihex','.hex')]:
        subprocess.run([str(compiler/'arm-none-eabi-objcopy.exe'),'-O',fmt,str(native.with_suffix('.elf')),str(native.with_suffix(suffix))],check=True)
    target=dict(passed=True,build_id=NEW[1],builder='native GNU make/GCC; no Eclipse Java launcher',
      text_bytes=87824,data_bytes=920,bss_bytes=24592,flash_limit=131072,ram_limit=32768,
      warnings=0,errors=0,hardware_validated=False,readback_verified=False)
    write(OUT/'nucleo_build_report.json',json.dumps(target,indent=2))
    reference=BASE/'hardware_install_r1/preserved_captures_sha256.json'
    archives=json.loads(read(reference));changed=[]
    for rel,digest in archives.items():
        f=ROOT/rel
        if not f.is_file() or sha(f)!=digest:changed.append(rel)
    assert not changed,changed
    write(OUT/'archive_preservation.json',json.dumps(dict(checked=len(archives),unchanged=True,
      reference=str(reference),reference_sha256=sha(reference)),indent=2))
    release=OUT/'release';release.mkdir(exist_ok=True)
    for name,source in [('unoq_2026102931_commissioning.elf-zsk.bin',OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'),
      ('nucleo_2026102932_commissioning.bin',native.with_suffix('.bin'))]:shutil.copy2(source,release/name)
    sources={}
    for folder in ('UNOQ_MOTOR','nucleo/Inc','nucleo/Src','web_hmi'):
        for path in sorted((OUT/folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.log'):
                sources[path.relative_to(OUT).as_posix()]=sha(path)
    write(OUT/'source_hashes.json',json.dumps(sources,indent=2))
    artifacts={p.relative_to(OUT).as_posix():sha(p) for p in release.iterdir() if p.is_file()}
    manifest=dict(schema='mic_ai.standstill_commissioning.v1',pair=list(NEW),base_pair=[2026102921,2026102922],
      sealed_utc=datetime.now(timezone.utc).isoformat(),built=True,installed=False,readback_verified=False,
      algorithms=['VF','FOC','ADAPTIVE_PWM','IDENT_FIXED_AXIS'],physical_qualification=False,motor_identified=False,
      host_test_groups=6,analysis_tests=33,model_dc_points=30,model_ac_points=12,model_passed=True,
      model_validation_relative_error=model['validation_error'],adc_replay_checks=adc['checks'],
      archived_frames_replayed=adc['raw_capture_frames_replayed'],old_capture_files_unchanged=len(archives),
      thresholds_changed=False,adc_guard_changed=False,archived_captures_modified=False,
      hardware_commands_sent=0,start_commands=0,clear_commands=0,
      current_scale='unchanged nominal 3.3/(4095*0.04*2.1) A/count',
      foc_qualification_unchanged=True,target_wcet_measured=False,source_manifest='source_hashes.json',artifacts=artifacts)
    write(OUT/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    report=f'''# Подготовка измерения индуктивностей без LCR-метра

Подготовлена совместимая пара **Uno Q 2931 / Nucleo 2932**. Обе сборки и проверки программного кода пройдены; образы находятся в `release/`. **Эта пара не записывалась на платы, чтение обратно и измерение двигателя не выполнялись. Установленная пара остаётся 2921/2922.** START/CLEAR/ARM/RESET в этом этапе не отправлялись.

## Причина окна STM32CubeIDE

Java запускалась; первая сборка нового кода завершилась ошибкой компилятора: `pwmHandle` не объявлен в новом модуле. Использован штатный дескриптор MCSDK `PWM_ParamsM1` из `mc_config.h`. Пересборка выполнена непосредственно через GNU make/GCC, без Java-лаунчера. Nucleo: text {target['text_bytes']} байт, data {target['data_bytes']}, bss {target['bss_bytes']}, 0 ошибок и предупреждений. Uno: проверка ELF загрузчика PASS. Предыдущие журналы ошибки сохранены.

## Измерительный метод

Мультиметр без режима L не измеряет индуктивность непосредственно. Сопротивления уже измерены: 24,7 Ом между выводами, 0,24 Ом щупы; предварительный звёздный эквивалент Rs≈12,23 Ом. Повторять это измерение в данном этапе не требуется.

Добавлен постоянный режим IDENT с фиксированной пространственной осью поля. Сначала отдельные короткие точки постоянного тока характеризуют погрешность реконструкции напряжения инвертора при известном Rs. Затем пульсирующее напряжение на той же неподвижной оси позволяет оценить частотный импеданс. Частоты 1–200 Гц здесь относятся к временному сигналу неподвижной оси; это не команда вращающегося поля 200 Гц. Подход к учёту deadtime/падений напряжения сверялся с [NXP AN5051, раздел 5.1](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/mbdt/10102/2/AN5051.pdf).

Данные напряжения вычисляются по активным CCR и измеренной DC-шине того же принятого отсчёта АЦП. Они корректируются по DC-характеризации, а не объявляются независимо измеренным фазным напряжением. Масштаб ампер остаётся прежним номинальным по шунтам. Окна, автоноль, SD/Break, deadtime, температурные/шинные пороги и сторож UART сохранены. Дополнительно новый режим ограничивает задание вектора тока 0,30 А и прерывается выше 0,45 А, при отсутствии отклика, устаревшем токе, непригодном окне или превышении срока расчёта.

Каждая точка ограничена 2–10 секундами. Nucleo самостоятельно выключает ШИМ в быстром обработчике; Uno и ПК имеют резервные остановы. Нет вращающегося регулятора скорости и автоматического повторного пуска. Только выбор режима или передача параметров никогда не запускают выходы. Требуются штатный защищённый START и одноразовое разрешение именно конфигурации измерения; обычная кнопка Пуск в режиме IDENT отключена.

## Данные и проверка

Буфер 1664 байта содержит 64 усреднённых фазовых/временных ячейки с числами отсчётов, токами, идеальным и реконструированным напряжением, синусом/косинусом и временными отметками. Доставка идёт отдельными страницами UART с CRC и затем 13 страницами HTTP. Новая запись не заменяет незабранную старую. ACK освобождает только буфер IDENT после сохранения файла на диск и проверки общего CRC; это не CLEAR защиты. SD/ADC-снимки не стираются.

Пройдены 6 групп тестов реального C-адаптера/протокола/автостопа/HTTP и 33 теста анализа. Исходный ADC IRQ прошёл {adc['checks']:,} проверку и повтор 24 старых кадров; негодные отсчёты не переименованы в пригодные. Сверены хеши {len(archives)} старых файлов захватов — изменений нет.

На независимой синтетической модели проверены 30 DC-точек и 12 частотных точек. C-ядро собрано из того же заголовка, что и целевая прошивка. При модельных Rr=9 Ом, Lls=Llr=12 мГн, LMS=0,3 Гн получены Rr={model['inferred']['RR']:.6f} Ом, Lls=Llr={1000*model['inferred']['LLS']:.6f} мГн, LMS={model['inferred']['LMS']:.6f} Гн. Относительная ошибка независимых частотных точек {100*model['validation_error']:.3f}%. **Это проверка алгоритма на модели, а не измеренные параметры нашего АИР.**

## Инструменты и следующий этап

`tools/standstill_measurement.py` по умолчанию формирует только офлайн-план. Подготовлен `first_point_plan/plan.json`: DC, ось 0, задание 0,06 А, 3 с, резерв Uno 5 с. Параметры и запись передаются штатными защищёнными API. Исполнение возможно только с явными флагами физической подготовки и неподвижного ротора; команды автоматического CLEAR/повтора отсутствуют. Пока поддержана одна точка за вызов, не автоматическая серия всех 42 точек. Файл реального результата включает CRC, SHA и исходный план.

До физического опыта нужно установить эту пару, проверить чтением обратно, связь и отсутствие самозапуска; затем отдельно проверить текущую сборку стенда перед подачей силового. Восстановление 34-контактного шлейфа после предыдущего изолированного теста в этой разработке не подтверждалось. Сейчас не требуется включать J1, переставлять щупы или измерять напряжения на U/V/W.

Результат идентификации — эквивалентная электрическая T-модель с предположением равных индуктивностей рассеяния, не уникальное разложение физических Lls/Llr. Механические J/B, насыщение и независимый абсолютный масштаб тока не определяются. Подтверждение неподвижности ротора внешнее; отсутствие поперечного тока само по себе не доказывает нулевую скорость. Время расчёта на G431 ещё не измерено на реальном пуске. Поэтому подготовка IDENT не снимает существующую блокировку силового FOC и не переводит квалификацию в 7.
'''
    write(OUT/'REPORT_RU.md',report)
    print(json.dumps({k:manifest[k] for k in ('pair','built','installed','model_passed','adc_replay_checks','old_capture_files_unchanged','hardware_commands_sent')}))

if __name__=='__main__':main()
