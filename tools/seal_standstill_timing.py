"""Seal a checked timing correction, retaining all prior measured evidence."""
import json,subprocess,shutil,os
from pathlib import Path
from datetime import datetime,timezone
import prepare_standstill_timing as p
from seal_standstill_commissioning import sha
def main():
 m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
 env=dict(os.environ);env['MIC_COMMISSIONING_TEST_DATA']=str(p.OUT/'model')
 v=p.OUT/'verification';v.mkdir(exist_ok=True)
 for name,command in [('native_host_tests.log',[str(p.ROOT/'.venv/Scripts/python.exe'),str(p.ROOT/'tools/test_standstill_timing.py')]),
  ('capture_tests.log',[str(p.ROOT/'.venv-research-gpu/Scripts/python.exe'),'-m','pytest',str(p.ROOT/'tests/test_acim_standstill_identification.py'),str(p.ROOT/'tests/test_commissioning_capture.py'),'-q']),
  ('web_syntax.log',['C:/Program Files/nodejs/node.exe','--check',str(p.OUT/'web_hmi/static/app.js')])]:
  r=subprocess.run(command,capture_output=True,text=True,env=env,cwd=p.ROOT);p.write(v/name,r.stdout+r.stderr);r.check_returncode()
 for name in ('nucleo_build_report.json','model/report.json','apex_selftest_r1/report.json'):assert json.loads(p.read(p.OUT/name))['passed']
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 release=p.OUT/'release';release.mkdir(exist_ok=True)
 for name,source in [('unoq_2026102933_timing.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'),
  ('nucleo_2026102934_timing.bin',p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin')]:shutil.copy2(source,release/name)
 hashes={}
 for folder in ('UNOQ_MOTOR','nucleo/Inc','nucleo/Src','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.log','.pyc'):hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(hashes,indent=2))
 reference=p.BASE/'hardware_install_r1/preserved_captures_sha256.json'
 archived=json.loads(p.read(reference))
 for rel,digest in archived.items():assert sha(p.ROOT/rel)==digest,rel
 evidence=[p.BASE/'first_dc_point_r1/raw_abort/capture.bin',p.BASE/'first_dc_point_r1/raw_abort/report.json',
  p.BASE/'first_dc_point_r1/report.json',p.BASE/'powered_preflight_r1/mc_break_wave_hex.bin']
 p.write(p.OUT/'preserved_measured_evidence.json',json.dumps({str(f):sha(f) for f in evidence},indent=2))
 p.write(p.OUT/'archive_preservation.json',json.dumps(dict(reference=str(reference),reference_sha256=sha(reference),checked=len(archived),unchanged=True),indent=2))
 model=json.loads(p.read(p.OUT/'model/report.json'));adc=json.loads(p.read(p.OUT/'apex_selftest_r1/report.json'))
 m.update(built=True,sealed_utc=datetime.now(timezone.utc).isoformat(),readback_verified=False,physical_qualification=False,
  deadline_cycles=5312,additional_preflight_kernel_limit_cycles=4800,native_timing_measured=False,
  synthetic_records_never_published_as_physical=True,first_kernel_initialization_in_irq=False,
  model_dc_points=30,model_ac_points=12,model_validation_error=model['validation_error'],
  adc_replay_checks=adc['checks'],old_captures_unchanged=len(archived),hardware_commands_sent=0,clear_commands=0,
  artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
 p.write(p.OUT/'manifest.json',json.dumps(m,ensure_ascii=False,indent=2))
 p.write(p.OUT/'REPORT_RU.md',f'''# Исправление времени измерительного контура 2933/2934

Подготовлена пара 2933/2934 из установленной 2931/2932. Пока не установлена, реальное время нового ядра ещё не измерено.

Первый физический опыт предыдущей пары остановился по MI_OVERRUN: 34 939 тактов при бюджете 5 312. Запись CRC 364317371 сохранена; готовых ячеек измерения 0, максимум вектора по номинальному масштабу 0,20154 А, DC-шина 320 В. Это программный останов до публикации новых CCR, не измеренная индуктивность. Исходные файлы включены в `preserved_measured_evidence.json`.

Из быстрого IRQ убрано обнуление 4,4 КБ и подготовка конфигурации/CRC. Подготовка выполняется до штатного MC_StartMotor, пока MOE выключен. В первый принятый отсчёт быстро привязывается только время начала. Ось sin/cos вычисляется заранее. Измерительный режим использует фиксированное общее смещение PWM с прежним планировщиком всех трёх плеч; работа отдельного алгоритма адаптивного ШИМ не менялась. Норма тока проверяется по квадрату, порог остаётся 0,45 А; максимум вычисляется sqrt только при росте. Фаза AC приведена к одному периоду для ограниченного времени sin/cos. Все исходные окна и защиты сохранены.

При загрузке, после реального автонуля, MOE=0 и DC≤20 В, в настоящем flash-коде выполняется один CPU-тест ядра на синтетических входах. Он не пишет TIM/ADC/GPIO, не запускает MCSDK и не маскирует IRQ. Синтетические данные очищаются, не выдаются в физические каналы и не освобождают реальную запись. Для IDENT требуется подтверждённый максимум не более 4800 тактов; реальный IRQ дополнительно сохраняет исходный предел 5312 до записи CCR. При перезапуске MCU проверка требуется заново. Режимы V/f/FOC/адаптивный PWM и прежние квалификации FOC не расширены этим тестом.

Отчёт E6 имеет формат 2: на месте неиспользовавшегося счётчика принятых отсчётов передаётся `id_timing_cycles`. Полное число отсчётов по-прежнему находится в CRC-буфере измерения. Буфер ID и протокол его страниц не менялись. Uno и HMI проверяют совпадение новой пары; старые изображения несовместимы по формату E6 и не принимаются как новые.

Пройдены проверки реального C-адаптера, прежних защит и HMI; 33 теста анализа. Независимая модель: 30 DC и 12 AC точек, ошибка контрольных частот {100*model['validation_error']:.3f}%. Это синтетические результаты. ADC IRQ: {adc['checks']:,} условий и 24 старых кадра. Сверены {len(archived)} старых файлов. Обе MCU собираются, ELF-проверка Uno пройдена.

Попытка временного RAM-профиля предыдущего кода не завершилась; SRAM восстановлена байт в байт и Nucleo сброшена в неизменный рабочий образ. Этот прототип отключён и не является доказательством времени. Вместо него используется постоянная проверка в настоящем flash при выключенных выходах.

После записи новой пары сначала проверить чтение обратно, автоноль и `id_timing_cycles` без J1. До успешной проверки времени нового ядра силовых пусков не выполнять. Калибровка шины и пороги защит не меняются.
''')
 print(json.dumps({k:m[k] for k in ('pair','built','installed','native_timing_measured','adc_replay_checks')}))
if __name__=='__main__':main()
