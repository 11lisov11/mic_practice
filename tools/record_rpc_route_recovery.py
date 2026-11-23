"""Record bounded acceptance, separating OFF RPC repair from unresolved FOC RUN."""
import json
import prepare_rpc_route_recovery as p

def main():
    m=json.loads(p.read(p.OUT/'manifest.json'))
    installed=json.loads(p.read(p.OUT/'install_r1/report.json'))
    qualified=json.loads(p.read(p.OUT/'idle_qualification_r2/report.json'))
    assert installed['passed'] and installed['uno_readback_verified'] and installed['calibration_unchanged']
    assert installed['nucleo_flash_commands']==0 and qualified['passed']
    assert qualified['native_readback_identical'] and qualified['native_tick_after']>qualified['native_tick_before']
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
    history=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
    for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
    acceptance=dict(pair=list(p.NEW),installed=True,uno_readback_verified=True,
        native_readback_identical=True,native_reset_performed=False,calibration_unchanged=True,
        OFF_route_reconnect_verified=True,START=0,CLEAR=0,ARM=0,
        OFF_fast_cycles=qualified['fast_cycles'],OFF_fast_budget=4000,estimate_limit_ms=2,
        trip_A=1.35,ADC_guard_ticks=2048,thresholds_changed=False,
        FOC_five_seconds_verified=False,original_RPC_outage_cause_proven=False,
        preserved_files=len(history),scope='Repair confirmed route-registration loss without MCU reset or erasing captures. No motor run.')
    p.write(p.OUT/'acceptance.json',json.dumps(acceptance,indent=2)+'\n')
    m.update(installed=True,installation_scope='Uno1607 only; Nucleo1606 not programmed or reset',
        OFF_route_reconnect_verified=True,OFF_fast_cycles=qualified['fast_cycles'],
        FOC_start_ready=False,FOC_five_seconds_verified=False,qualified=False,
        qualification='OFF route-loss recovery physically verified. Original RUN outage and five-second FOC remain unresolved.',
        acceptance_sha256=p.sha(p.OUT/'acceptance.json'))
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    p.write(p.OUT/'RESULT_RU.md','''# RPC1607: восстановление маршрутов без сброса Nucleo

Установлены Uno2026111607 и прежняя Nucleo2026111606. Только Uno записана
и проверена чтением обратно; образ Nucleo прочитан повторно и совпадает
побайтно. Калибровка сохранена. J1 выключен,15В включены, обе платы на ПК.
START/CLEAR/ARM=0, Nucleo reset/flash=0.

В старом коде g_bridge_cmd_ready/get_ready остаются истинными после потери
регистрации на Linux-router. Поэтому bridge_tick не регистрирует методы
повторно. Это соответствует сохранённому method get not available после
переподключения router, но НЕ устанавливает причину первого обрыва при RUN.

Добавлено обновление регистрации существующих callback раз в5с, начиная
только при локальном/удалённом PWM OFF. Нет reset, замены callback, очистки
RAM/захватов или автоматического повторного пуска/CLEAR. Обычные guards
пуска, свежесть телеметрии, новая ошибка RPC и все защиты остаются прежними.

Установлен router0.5.3: он возвращает error5 на любой дубликат, даже своего
маршрута. Код различает подтверждённую регистрацию1, EXISTS2 и отказ0.
EXISTS не доказывает владельца маршрута и не разрешает двигатель. Проверено
по точному исходнику https://github.com/arduino/arduino-router/blob/v0.5.3/msgpackrouter/router.go
и https://github.com/arduino/arduino-router/blob/v0.5.3/msgpackrouter/errors.go .
Исходники сохранены в verification. Предварительный verification/report
использовал семантику нового router; он заменён проверкой verification_router053.

18 сценариев на настоящих заголовках RPClite/RouterBridge, с UART/ядром/router
в модели;300 циклов восстановления сохранили исходный callback. Сборка Uno
и проверка динамического загрузчика пройдены. Полный расчёт FOC не изменён.

На реальном стенде выполнено одно close/open Linux-router. Четыре GET
получили HTTP503 во время восстановления; связь вернулась примерно за2,016с
после окончания команды переподключения. Счётчик подтверждённых новых
регистраций0→1. Затем20 стабильных GET, новых RPC/UART ошибок нет; автоноль
готов, SD HIGH, Break IRQ включено. Native uptime3427461→3459961мс, сброса
не было. CPU3618/4000;2мс,1,35А и2048 не менялись.5417 старых файлов целы.

idle_qualification_r1 остановился ДО reconnect из-за неверного имени ключа
в локальном скрипте; этот неуспех сохранён. Исправленный r2 прошёл.

Границы: это исправление и проверка OFF-восстановления RPC. Первопричина
обрыва под ШИМ не доказана. Пятисекундный FOC, достоверность скорости
наблюдателя и токов в новом пуске не проверены. Старый RUN не объявлен
успешным, пустой захват новой загрузки ему не приписан. Новых пусков нет.
''')
    print(json.dumps(acceptance))

if __name__=='__main__':main()
