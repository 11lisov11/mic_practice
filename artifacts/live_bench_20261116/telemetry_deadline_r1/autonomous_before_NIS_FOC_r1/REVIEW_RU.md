# Автономная проверка без пуска

Исходный report.json сохранён с passed=false. Из20 проверок19 пройдены;
UART_RPC_clean=false из-за rpc_response_timeouts=12 во всех20 статусах.
За28,141с счётчик не вырос, rpc_send_timeouts=0. bridge.h инкрементирует
общий накопительный счётчик на admission/write-mutex/response timeout;
UNOQ_MOTOR.ino экспортирует его напрямую. Это подтверждает семантику
счётчика, но не момент/конкретную причину12 прошлых событий.

Свежие native ответы (max sampled age52мс), good+564, rejected0,
CRC/sequence/UART/transport0. Автоноль ready1/stable3 во всех20 ответах.
Max sampled age current summary584/detail908/quality908мс укладывается
в прежние750/1500/1500. Это выборочные возраста, не непрерывный максимум.
CPU3618/4000, SD HIGH, BIE1, capture_running1, config_ok1, Break не записан.
ADC/observer свободны по свежему boot/run_id0 и состоянию приёмников;
прямого SWD/RAM чтения на повербанках не было. Порог NIS-trigger установлен,
доставку реального NIS-захвата под FOC эта проверка не подтверждает.

J1 OFF, шина10В, PWM0. MC_UNDER_VOLT mask4 при этом ожидаем.
Пуск остаётся заблокирован: tools/run_observer_input_epoch_runtime.py
link_power требует абсолютный ноль накопительного RPC-счётчика.
Условия пуска и защиты не менялись. START/CLEAR/ARM/RESET/flash/SWD=0;
только GET.3523 прежних файла проверены без изменений.
