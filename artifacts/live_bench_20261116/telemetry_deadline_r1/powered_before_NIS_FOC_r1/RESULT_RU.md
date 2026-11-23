# Проверка шины выполнена; пуск заблокирован защёлкой

20 GET статусов: шина320–322В, SAFE/PWM0/run_id0, автоноль готов,
CPU3618/4000. RPC response12/send0 без роста, guard ready=true,
новых UART/CRC/sequence/transport ошибок нет. ADC/observer рекордеры свободны.

Первый Break до START: PA6 LOW63,4мкс, полные оба фронта, MOE_at_IRQ=false,
start_window=false. Полный SD_before_START.bin320B и decoded JSON сохранены.
SD сейчас HIGH, config_ok=true; BIE=false/capture_running=false.
MC current/saved mask4, mc/bp_fault5. Автоматический CLEAR не выполнялся.
Failed checks: no_fault_latches, SD_break_IRQ_ready. Источник импульса
не установлен; PA4 не используется для локализации без подтверждённой
перемычки TP23→PA4 (она ранее снята).

Только GET; START/CLEAR/ARM/RESET/flash/SWD=0. Защиты прежние.
Старые файлы/source hashes проверены, детали в preservation_review.json.
Нужен явно разрешённый штатный CLEAR и подтверждение восстановленных
защит до какого-либо START. Этот отчёт не подтверждает готовность к пуску.
