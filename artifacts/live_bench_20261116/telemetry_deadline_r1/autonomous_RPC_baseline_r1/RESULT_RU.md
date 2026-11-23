# Проверка перед FOC при J1 OFF пройдена

Только GET,20 ответов за28,359с: версии1603/1604, SAFE/PWM0/run_id0/ARM0.
Автоноль ready1/stable3 во всех ответах. RPC baseline response12/send0,
новых timeout нет, guard ready=true/failure=null. Good frames+561,
rejected0, CRC/sequence/UART/transport0, перезапусков не обнаружено.

Max sampled ages native57/current540/detail928/quality974мс, прежние
пределы300/750/1500/1500 соблюдены. CPU3618/4000, OFF64/fault0,
meter_errors0. SD HIGH, BIE/config/capture исправны; первого Break нет.
Рекордеры ADC/observer свободны по свежему boot/run_id0 и приёмникам.
NIS-trigger в установленном release подтверждён. Фактическую запись АЦП
при отказе NIS под работающим FOC этот тест не проверяет.

Шина9В при J1 OFF, MC_UNDER_VOLT current/saved mask4 ожидаем. До START
нужна новая проверка силовой шины и восстановленных защит; пуска/CLEAR
не было. Пределы4000/2мс/1,35А/2048 не менялись. 3540 старых файлов и162
release sources проверены по SHA без изменений. Старый failed report цел.
