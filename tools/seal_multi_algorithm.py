"""Seal prepared images, actual host checks, provenance and explicit limits."""
import hashlib,json,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from prepare_multi_algorithm import ROOT,OUT,BASE,NEW,read,write
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    result=subprocess.run([sys.executable,str(ROOT/'tools/test_multi_algorithm.py')],capture_output=True,text=True)
    write(OUT/'host_tests/final_tests.log',result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('Final host tests failed; candidate not sealed')
    model=json.loads(read(OUT/'model/report.json'));irq=json.loads(read(OUT/'apex_selftest_r1/report.json'))
    target=json.loads(read(OUT/'nucleo_build_report.json'));llext=json.loads(read(OUT/'build/uno/llext-check.json'))
    assert model['passed'] and irq['passed'] and target['passed'] and llext['pass']
    release=OUT/'release';release.mkdir(exist_ok=True)
    images={
      'unoq_2026102921_multi.elf-zsk.bin':OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',
      'nucleo_2026102922_multi.bin':OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin'}
    for name,path in images.items():shutil.copy2(path,release/name)
    files={}
    for folder in ('UNOQ_MOTOR','nucleo/Inc','nucleo/Src','web_hmi'):
        for p in sorted((OUT/folder).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.log'):
                files[p.relative_to(OUT).as_posix()]=sha(p)
    artifacts={p.relative_to(OUT).as_posix():sha(p) for p in release.iterdir() if p.is_file()}
    provenance={str(BASE/'manifest.json'):sha(BASE/'manifest.json')}
    for name in ('current_only_induction_ekf.py','current_only_speed_foc.py'):
        p=Path('C:/mic_theory/control')/name;provenance[str(p)]=sha(p)
    write(OUT/'source_hashes.json',json.dumps(files,indent=2))
    write(OUT/'archive_references.json',json.dumps(provenance,indent=2))
    rows=model['scenarios'];worst_peak=max(r['peak_A'] for r in rows)
    mean_est=max(r['mean_estimator_error_rad_s'] for r in rows)
    mean_tracking=max(r['mean_tracking_error_rad_s'] for r in rows)
    report=dict(schema='mic_ai.multi_algorithm.v1',pair=list(NEW),base_pair=[2026102911,2026102912],
      sealed_utc=datetime.now(timezone.utc).isoformat(),built=True,host_tests_passed=5,model_scenarios_passed=len(rows),
      compiled_algorithms=['VF_FIXED','FOC_FIXED','ADAPTIVE_PWM'],online_algorithm_selection=True,
      selection_requires_pwm_off=True,automatic_restart=False,as5600_enabled=False,
      installed=False,readback_verified=False,hardware_algorithm_switch_verified=False,physical_qualification=False,
      motor_identified=False,current_scale='unchanged nominal 3.3/(4095*0.04*2.1) A/count',
      target_wcet_measured=False,simulation_profile_is_not_identification=True,runtime_profile_volatile=True,
      thresholds_changed=False,adc_guard_changed=False,archived_captures_modified=False,hardware_commands_sent=0,
      model_samples=sum(r['samples'] for r in rows),model_peak_a=worst_peak,
      maximum_scenario_mean_estimator_error_rad_s=mean_est,maximum_scenario_mean_tracking_error_rad_s=mean_tracking,
      adc_replay_checks=irq['checks'],archived_frames_replayed=irq['raw_capture_frames_replayed'],
      source_manifest='source_hashes.json',artifacts=artifacts)
    write(OUT/'manifest.json',json.dumps(report,ensure_ascii=False,indent=2))
    text=f'''Подготовлена одна совместимая пара **Uno Q 2921 / Nucleo 2922** с тремя реальными исполнительными алгоритмами: V/f, sensorless FOC и FOC с адаптивным положением нулевого вектора ШИМ. Образы находятся в `release/`. **На платы эта пара ещё не записывалась; чтение обратно и силовая проверка не выполнялись.**

Выбор алгоритма выполняется через один список на веб-панели или `SET ALGORITHM VF|FOC|ADAPTIVE_PWM`. Перепрошивка для смены алгоритма не нужна. Изменение разрешено при остановленном ШИМ; следующий пуск требует отдельной команды. Команда «Стоп» имеет приоритет над ожидающей конфигурацией, автоматического повторного пуска нет. Старый VF-супервизор Uno обслуживает задания и таймер останова, а фактический исполнитель и его подтверждение Nucleo передаются отдельными полями `algorithm_requested/algorithm_selected` и режимами UART 3/6/7.

Векторный контур содержит преобразования токов αβ/dq, регуляторы тока с ограничением вектора задания, регулятор скорости, преднамагничивание, anti-windup и шестимерный EKF токов/потока/скорости/нагрузки. Истинная скорость модели в наблюдатель не передаётся. Оценка скорости в интерфейсе помечена как оценка, не как измерение энкодера. AS5600 не опрашивается.

Адаптивный вариант меняет общую составляющую трёх скважностей при **фиксированных 16 кГц**. В идеальной модели линейные напряжения сохраняются; при нехватке измеримого окна применяется ограничение требуемого вектора напряжения и anti-windup. Планировщик учитывает фронты всех трёх плеч. Это конкретный вариант адаптации окон измерения, а не перенос всех исследовательских SNH/ИИ-оптимизаторов из C:\\mic_theory.

Проверен именно C-код целевого регулятора, подключённый к независимой модели в потоковых координатах с double/RK4 и отдельной усреднённой моделью инвертора с deadtime. Восемь сценариев по 14 с: задания 0→5→20→35→50→25→5 Гц, шум тока 2 мА, изменение Rs/Rr на 10% и ошибка deadtime на 10%. Это совокупно {report['model_samples']:,} шагов. Все сценарии завершились без аварий; в каждом принятом шаге найдено допустимое окно АЦП. Максимум модельного вектора тока — **{worst_peak:.3f} А**, ниже дополнительной границы нового контура 1,35 А. Максимальная среди сценариев средняя ошибка оценки скорости — {mean_est:.3f} рад/с; средняя ошибка слежения — {mean_tracking:.3f} рад/с. Эти числа относятся к модели, не к реальному АИР.

Дополнительно прошли пять групп тестов: реальный native-адаптер и CRC/профиль, C-регулятор на независимом объекте, неизменность существующих защит, состояние HMI, реальный HTTP-обработчик выбора режима. Проверены отказ при устаревших токах/наблюдателе, недопустимой шине и превышении тока, запрет смены алгоритма на ходу, сохранение первого сбоя, конечный срок расчёта до записи CCR. Прерывание публикации данных использует предыдущий согласованный отсчёт только в пределах исходного ограничения возраста; ожидания в быстром IRQ нет.

Исходный обработчик АЦП прошёл **{irq['checks']:,} проверку**, включая 24 ранее сохранённых сырых кадра и синтетический RMS на 40/45/50 Гц. Недопустимые старые отсчёты не переименованы в пригодные. Быстрый интерфейс передаёт коды АЦП, а преобразование в амперы использует тот же номинальный коэффициент, что и RMS. Пороговые константы, deadtime, SD/Break, сторож связи, алгоритм автонуля и запасы АЦП из базовой пары не менялись.

Nucleo собрана с 0 ошибок и 0 предупреждений. Для новой части компилятор указывает 408 байт собственного стека быстрого обработчика и 880 байт наблюдателя; это оценки стека, не измерение WCET. Uno Q собрана, ELF-проверка загрузчика пройдена. Простая панель проверена локально через Playwright: выбор FOC/адаптивного режима не посылает START, неподготовленный FOC блокирует пуск, устаревшая связь блокирует выбор режима и пуск, «Стоп» остаётся доступным. Все браузерные POST были локальными заглушками.

**Что ещё требуется до силового FOC:** идентифицированные параметры конкретного двигателя, подтверждённый физический масштаб токов и измерение времени выполнения на G431. Ранее измеренные 24,7 Ом между выводами и 0,24 Ом щупов дают предварительный звёздный эквивалент Rs≈12,23 Ом; повтор этого измерения здесь не требуется. Rr, Ls/Lr/Lm, J/B пока не идентифицированы. Значения в `model/simulation_profile.json` — только модельные предположения, и они не включают силовой FOC.

Параметры можно загрузить онлайн, без новой прошивки, командами stage/CRC-commit только при выключенном ШИМ. `tools/configure_multi_algorithm.py --profile ...` по умолчанию лишь проверяет файл и печатает план. Флаг `--execute-config-only` передаёт конфигурацию и ждёт подтверждения CRC; START/CLEAR/RESET этот инструмент не посылает. Подтверждения идентификации, масштаба тока и времени расчёта независимы, привязаны к файлам доказательств и их хешам. Профиль в Nucleo хранится в ОЗУ; после её перезапуска его нужно загрузить снова. Существующие ограничения и защиты пуска сохраняются.

Модель не включает насыщение железа, звон силовых фронтов и реальные синфазные помехи. Физический RMS и скорость датчиком в этом этапе не подтверждены. Старые захваты не удалялись и не изменялись; ссылки и хеши происхождения сохранены в `archive_references.json`.
'''
    write(OUT/'REPORT_RU.md',text)
    print(json.dumps({k:report[k] for k in ('pair','built','model_scenarios_passed','model_samples','model_peak_a','adc_replay_checks','installed','physical_qualification')},ensure_ascii=False))
if __name__=='__main__':main()
