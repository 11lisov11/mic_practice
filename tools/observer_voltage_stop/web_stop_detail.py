def motor_fault_detail(data: dict) -> str:
    detail = _native_motor_fault_detail(data)
    local = int(data.get('uno_local_fault', 0))
    if local:
        detail += f'; текущая локальная ошибка Uno={local}'
    if int(data.get('uno_stop_ready', 0)):
        names = {0: 'ветка не помечена', 1: 'контроль ответа Nucleo',
                 2: 'запрос обычной остановки', 3: 'лимит времени'}
        origin = int(data.get('uno_stop_origin', 0))
        detail += (f'; первый STOP Uno, прогон {int(data.get("uno_stop_run_id", 0))}: '
                   f'{names.get(origin, "неизвестная ветка")}, '
                   f'возраст ответа {int(data.get("uno_stop_reply_age_ms", 0))} мс, '
                   f'локальная ошибка {int(data.get("uno_stop_local_fault", 0))}')
    return detail
