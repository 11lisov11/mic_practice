"""Seal the measured result without rewriting failed or partial tests."""
import json,hashlib
import prepare_rpc_hmi_admission as p


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    def read(rel):return json.loads((p.OUT/rel).read_text(encoding='utf8'))
    install=read('install_r1/report.json');host=read('verification/report.json')
    linux=read('verification_linux/report.json');guards=read('safety_regressions/report.json')
    unix=read('unix_deadline_report.json');assert unix['passed']
    fanout=read('HTTP_fanout_r1/report.json');long=read('long_idle_r1/report.json')
    assert install['Linux_server_readback_verified'] and host['passed'] and linux['passed'] and guards['passed']
    protected=json.loads((p.OUT/'preserved_all_hashes.json').read_text())
    for rel,digest in protected.items():assert sha(p.ROOT/rel)==digest,rel
    base_source=json.loads((p.BASE/'source_hashes.json').read_text())
    for rel,digest in base_source.items():assert sha(p.BASE/rel)==digest,rel
    first=json.loads((p.OUT/'first_status.json').read_text(encoding='utf8'))['data']
    last=read('long_idle_r1/final_status.json')
    assert last['hmi_vbus_hv_calibrated']==1 and last['pwm']==last['run_id']==0
    report=dict(installed=True,Linux_server_readback_verified=True,PC_RPC_tests_passed=True,Linux_RPC_tests_passed=True,
        command_guard_cases=guards['command_guard_cases'],local_stop_cases=guards['local_stop_cases'],
        Linux_unix_backlog_deadline_passed=True,
        HTTP_fanout_passed=fanout['passed'],HTTP_fanout_seconds=fanout['elapsed_s'],
        long_idle_passed=long['passed'],long_idle_seconds=long['elapsed_s'],long_idle_samples=long['samples'],
        max_HTTP_seconds=long['max_HTTP_latency_s'],
        RPC_timeouts_before=first['rpc_response_timeouts'],RPC_timeouts_after=last['rpc_response_timeouts'],
        route_failures_before=first['rpc_route_failures'],route_failures_after=last['rpc_route_failures'],
        firmware_pair=[2026111609,2026111606],this_HMI_update_MCU_flash=0,this_HMI_update_MCU_reset=0,
        START=0,CLEAR=0,ARM=0,FOC_start_ready=False,FOC_five_seconds_verified=False,
        original_wire_failure_first_byte_identified=False,
        calibration_unchanged=True,protected_files_verified=len(protected),
        protection_limits=dict(OFF_fast_cycles=4000,estimate_ms=2,trip_A=1.35,ADC_ticks=2048),
        thresholds_changed=False,server_sha256=sha(p.OUT/'web_hmi/server.py'),
        qualification='Idle RPC only. Confirmed queue/lock defects corrected. Does not qualify FOC or prove the initiating serial byte failure.')
    (p.OUT/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
    m=read('manifest.json');m.update(installed=True,readback_verified=True,idle_qualified=long['passed'],
        FOC_start_ready=False,acceptance_sha256=sha(p.OUT/'acceptance.json'))
    (p.OUT/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    notes=f'''Исправлены две подтверждённые проблемы ожидания RPC.

1. Uno1609: refreshProvided отпускает bridge_mutex до ожидания ACK.
   В RAM1607 был подтверждён заблокированный updater. Исправление прошло18
   host-сценариев, записано и сверено. Первичный сбой байтового потока этим
   не объявляется устранённым: long_idle_r4 после этой правки тоже FAILED.
2. Linux HMI: timeout теперь включает ожидание mutex/соединение/send/recv,
   использует monotonic, параллельные GET объединены только на время
   текущего запроса. Завершённые ответы не кешируются; команды отделяют
   предшествующие чтения, START/CLEAR не повторяются автоматически.
   На ПК прежний timeout30мс возвращался через172мс, новый через31мс.
   16 параллельных чтений:16 запросов раньше,1 теперь (isolated fake peer).

PC и Linux тесты прошли; моторные guards после RouterClient побайтно
прежние. Дополнительно189 command guards и35 local-stop checks прошли
на mock backend. На стенде16 HTTP GET завершились за{fanout['elapsed_s']:.3f}с.
Длительный тест: passed={long['passed']}, {long['elapsed_s']:.3f}с,
{long['samples']}ответов, maxHTTP={long['max_HTTP_latency_s']:.3f}с.
RPCtimeouts {first['rpc_response_timeouts']}→{last['rpc_response_timeouts']},
route_failures {first['rpc_route_failures']}→{last['rpc_route_failures']}.
За время этого теста router не переподключался, MCU не сбрасывались.

Проверены{len(protected)} старых файлов и sealed source1609: хеши совпали.
Калибровка сохранена. В этом Linux-обновлении MCU не прошивались; Nucleo1606
не прошивалась и не сбрасывалась за разбор RAM. Пределы4000тактов,2мс,
1,35А,2048 прежние. Пусков/CLEAR/ARM нет. J1 OFF,15В ON, платы наПК.

Граница вывода: найденный первичный сбой внутреннего UART ещё не установлен
до конкретного байта/драйверного события. В RAM1609 извлечён полный GET712
уже после timeout, значит обработчик/encoder продолжали работать; это
не доказательство доставки в Linux. Предыдущие FAILED отчёты и все захваты
сохранены в rpc_short_lock_r1, включая37-ответный wire-тест с GET39 без ответа.
Прямой owned router713 GET/12мин +80 параллельных прошёл без отказа.
Нынешний результат квалифицирует только RPC в покое. Старые native
LINK_TIMEOUT7/UART-error1 не очищены. FOC_start_ready=false; силовой этап
и пятисекундный FOC этим тестом не разрешаются и не считаются пройденными.
'''
    (p.OUT/'RESULT_RU.md').write_text(notes,encoding='utf8')
    print(json.dumps(report))


if __name__=='__main__':main()
