# Шина исправна, пуск заблокирован сохранённым Break

Только20GET, версии1605/1606, шина322–323В, PWM0/run_id0/ARM0.
Связь/автоноль/профиль/CPU3618/4000/ADC/observer record checks пройдены.
RPC12/0 не растёт; UART/CRC/sequence/transport0.

Первый Break: PA6 LOW63,8мкс при MOE0 и до START. Полная волна320Б и
снимки сохранены; SD сейчас HIGH/config_ok1, BIE0/capture_running0.
Сохранённые MCSDK маски current0/occurred4, fault5. Общий preflight не
пройден (no_fault_latches, SD_break_IRQ_ready); мотор не запускался.
Нужны отдельно разрешённый штатный CLEAR и свежая проверка готовности.

3668 старых файлов и164 release source hashes целы. Пределы4000/2мс/
1,35А/2048 неизменны. CLEAR/START/ARM/RESET/flash/SWD=0.
