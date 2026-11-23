# Текущий статус стенда

## 2026-11-18: установлены Uno2026111807 / Nucleo2026111806

Отчёт: artifacts/live_bench_20261118/uart_921600_tx_contract_r1/RESULT_RU.md.
1805/1806 записаны и независимо сверены;1805 провалила реальную проверку из-за
ошибки контракта TX IRQ (ядро Zephyr включаетTC, адаптер ожидалTXE).
Исправление Uno1807 использует прямое LL TXE; TCIE0 подтверждён чтением.
Новый PC-тест по реальному ядру:137cases PASS, неизменённая1805negative control FAIL.
Uno1807 записана и сверена; Nucleo1806 повторно НЕ перепрошивалась, readback совпадает.
Калибровка неизменна. J1OFF, платыPCUSB,15В оставлены включёнными.
UART921600 в покое: 121.4с,120статусов,2391 новых ответов; CRC/sequence/hardware errors/drops/RPC timeouts0.
FIFO обеих плат и RXDMA Nucleo подтверждены; gaps/errors0.
Новый аппаратный OFF64 замер1806:3817/4000тактов, fault0, MOE0.
4000тактов/2мс/1,35А/UPDATE2048 и все защиты неизменны. Автоноль готов, SDHIGH.
Один дополнительный RESET Nucleo для чистой квалификации после сохраненияRAM,
безCLEAR/START/ARM; Linux и питание пользователю перезапускать не пришлось.
ОГРАНИЧЕНИЕ: boot/Break metadata stale, строгий readiness verifier FAIL сохранён.
UART/CPU-only qualification PASS не является START-допуском; motor_start_ready=false.
Полная скорость потока истории/работа подШИМ/NIS improvement не проверены.

--- Предыдущая запись ---

# Текущий статус стенда

## 2026-11-18: подготовлены1805/1806, UART RX исправлен и проверен ТОЛЬКО на ПК

Новый пакет: artifacts/live_bench_20261118/uart_921600_rx_r1. Оба образа собраны,
НЕ установлены. В этом ходе не было ни bench GET, ни flash/START/CLEAR/ARM/RESET.
Последняя установленная пара1803/1804 по-прежнему имеет известный UART FAIL.
Последнее подтверждённое подключение: обе платыПК,J1OFF,15В включены; свежесть
этого физического состояния в текущем offline-ходе не проверялась.
Nucleo: FIFO8 и RX DMA1ch2/DMAMUX1ch1 ring128, IDLE/HT/TC, нет CPU чтенийRDR;
ошибки/две pending границы/перезапись при копировании выявляются fail-closed.
Uno: FIFO8, свой ограниченный ISR RX/TX, без vendor handler/приватных колец/семафоров.
Ошибка/потеря на Uno защёлкивается до новой загрузки, счётчики не сбрасываются.
DMA NE невозможно привязать к байту: все PE/FE/NE/ORE являются hardUARTfault,
терпимость NE не расширялась. DDRE0 сохранён согласноRM0440; overrun detection не отключалась.
4000тактов/2мс/1,35А/UPDATE2048/SD/Break/профиль мотора не менялись. Приоритеты
TIM1/ADC/Break прежние. Fast/EKF ARM code побитно совпадает с1804; новое время
1806 на железе не измерено.3817тактов — старое измерение1804, не новое.
PC:63DMAпотока,320fault/racecases,137Uno cases,7447protocolchecks,2048TXframes,
64OFFmodelcases,659строк end-to-end с14OFF-командами и нулём потерь,4negativecontrols PASS.
Старый реальный NIS29,307 воспроизведён51/51. Старые SHA-описи2057/2220/8349 проверены.
На Nucleo остаётся240байт после прежних heap/stack резервов, Uno42970байт;
hardware high-water и реальная связь с новым кодом не квалифицированы.
После разрешённой записи нужны readback, FIFO/DMA register proof, UART quiet/load
без ШИМ и OFF DWT. Новых пусков не разрешено. Установщики1803/1804 повторно НЕ запускать.
Пользователь добавил AGENTS правило освобождения GUI capture. В этом ходе GUI/CUA/
node_repl не применялись; чужие сеансы и процессы не трогались. Рамка не проверялась.


## 2026-11-18: УСТАНОВЛЕНЫ1803/1804, OFF CPU PASS, UART921600 FAIL

Пользователь подтвердил J1 OFF, платы наПК,15В без изменений. Оба образа записаны
ровно по одному разу, независимо сверены поFlash. Калибровка совпала до/после.
Uno удерживалась HALTED до обновленияNucleo; отдельная verify/restart завершена.
Новый HMI развёрнут атомарно с резервной копией и одним перезапуском службы.
На Nucleo повторный полный readback PASS,64OFFcase PASS: fast3817/4000, запас183;
observer25319cycles, maxwall237,77мкс. BKE/BIE1, PA6HIGH, MOE0, running0;
новый журнал и NIS recorder пусты. 4000/2мс/1,35А/UPDATE2048 не изменены.
Но UART НЕ квалифицирован: фактически BRR184/Init921600, FIFO Nucleo OFF.
mc_last_uart_error_flags8=ORE, Uno hwflags1=OVERRUN, CRC/hwerror counters растут
даже без ШИМ. SoftwareRXdropped0. ПрямойRPC/HMI даёт свежие1803/1804 ответы,
однако связь с потерями; не путать доступный GET со здоровым транспортом.
Прошивок больше не было, CLEAR/ARM/START=0. Счётчики и лэтчи не очищались.
Установщик report.passedfalse из-за UART unhealthy; receiptinstalledtrue/readbacktrue,
OFF_timingtrue, UART921600false, runtimefalse. НЕЛЬЗЯ заново запускать установщик
или прошивать эту же пару ради RPC: оба образа уже записаны и проверены.
Следующий объект разбора — FIFO/DMA/задержки UART RX; конкретный максимум IRQ
пока не измерен. Новых пусков не разрешено. J1 остаётсяOFF,15В включены, платыПК.
Все результаты в observer_start_history_r1/installation_result_r1/RESULT_RU.md;
оба старых SHA-инвентаря2220/8349 проверены, захваты сохранены.


## 2026-11-18: запись1803/1804 подготовлена, J1 OFF ожидает подтверждения

Обе платы уже обнаружены на ПК: COM13 ST-LINK, COM10 UnoQ. Последние пассивные
SWD-чтения: шина10,112В, MOE0, BKE1, PA6 HIGH; GET1801/1802 SAFE, шина10В,
SD HIGH, UARTerror0. Это новое наблюдение заменяет старое предположение о повербанках.
J1 физически не наблюдаем: отправлен один вопрос о его выключенном положении.
Ни flash, ни START/CLEAR/ARM/RESET не отправлялись. Не начинать запись до ответа о J1.
Ничего кроме J1 пользователю переключать не нужно: USB ПК уже подключены,15В и проводка остаются.
Пакет observer_start_history_r1 неизменён; новые install-активы в installation_recipe_r1,
подготовительный RAM/статус в programming_preparation_r1. Установлены по-прежнему1801/1802.
install_start_history_release.py --verify-only PASS; verify_start_history_idle.py --verify-only PASS.
Порядок установки: Uno1803+verify остаётся HALTED → native1804+полное чтение Flash →
отдельная Uno verify/restart → HMI/calibration → UART921600/64OFF DWT. Не оставлять
работающую старую/новую пару с разным UART. При частичной записи не запускать установщик заново.
4000тактов и2мс/прочие защиты неизменны; новых силовых пусков не разрешено.


## 2026-11-18: подготовлен журнал START→первый NIS≥25, пара1803/1804

Работа только на ПК: START/CLEAR/ARM/RESET/flash/GET стенда=0. Установлены1801/1802.
Новый пакет: artifacts/live_bench_20261118/observer_start_history_r1.
Uno2026111803/Nucleo2026111804 собраны, НЕ установлены.
Начальное/конечное x/P, все точные входы до первогоNIS≥25, включая прогрев;
5120 вызовов, контрольные точки через16 и цепочка всех шагов. На ПК659 ARM-вызовов
восстановлены побитно. Старый реальный шаг29,307 повторён51/51. Отсутствующая
история старого пуска не выдумывалась. Контроллер/математика/пороги не менялись;
предыдущий fail-closed overlay НЕ включён. 4000тактов/2мс/1,35А/UPDATE2048/SD/Break
сохранены, fast ARM побитно прежний.
Только Nucleo↔Uno UART переводится на921600 в ОБОИХ образах: сначала после записи
нужна проверка UART/RPC и OFF-расчёта без ШИМ. На железе новый журнал не проверен.
Nucleo:392байта после прежних резервов heap/stack; Uno:остаётся44294байта,
есть предупреждение компилятора о RAM. High-water и новое время на платах не измерены.
Последнее физическое состояние прошлого хода: J1/15В включены, платы на повербанках,
после третьего пуска PWM0. Свежесть этого состояния в текущем ходе не проверялась.
Разрешений на новые пуски нет. Старые2220+8349 хеша проверены, захваты не изменены.
Подробности — RESULT_RU.md в новом пакете.


## 2026-11-18: точный raw/NIS659 разобран offline; исправлен только untrusted-publication кандидат

Аппаратных/сетевыхкоманд0: безSTART/CLEAR/ARM/RESET/flash. Установленные1801/1802
не менялись. Новая папка artifacts/live_bench_20261118/nis_exact_source_analysis_r1.
Реальные16ADC+25voltagehistory восстановили все4входа ia/ib/va/vb ПОБИТНО через
исходные C-ядра, center/dt/pairs точны. DoubleNIS29,307123vsARM29,307125, P PSD,
ошибки арифметики/whitening/окна не обнаружены. Batch-ротация в измеряемые V/W:
Vневязка+0,113435А приσ0,020989 (5,405σ), W−0,011590А приσ0,021157.
RK4variational/dt±10мкс/½PWM-ZOH даютNIS≈29,25–29,37, не исправляют событие.
Разные неподтверждённые поправки(Uβ+1В илиVoffset−12counts) обе проходят25;
это НЕ калибровка. OFF153пакета дают V1mean2067,16 приoffset2065, не−12counts.
Истинная причина несовпадения модели/измерения и дрейфа priorω/P не доказана.
Непрерывной истории prior до658 нет. Нельзя выдавать подбор параметров зафикс.

Доказан отдельный дефект: код публиковал NIS>=25 уже при validityfalse. В source
candidate/nucleo/Src/multi_native.c после первого replay/raw запроса добавлен
штатный MA_OBSERVER отказ приsteps>=500/NIS>=25 илинеfinite, доforecast/publish.
На сохранённом шаге NIS остаётся29,307, published0/firstsource сохранён/fastвозвращает
MC_SW_ERROR. Это более строгая остановка при недостоверной оценке, НЕ устранение
первичной физической причины NIS. Новыйпускможетраньшеостановиться; не рекламировать5сfix.
Baseline19/candidate21 регрессий и64OFFmodelcasesPASS; границы25/NaN, старые
>50/20steps, raw1,35А/2мсPASS. ARMoriginalflagscompilePASS; fast/observer/noise
machine sections идентичны. OFF4000/2мс/UPDATE2048/RUN5312 неизменны, Q/R/model untouched.
ARMstackfast360 прежний, service344→352, record112 отдельно; targettiming не измерен.
Кандидат НЕflashable/без новыхID/не установлен. Нужна честная оценка residual/model,
не разгон50Гц. Старые8349файлов защищены SHA. RESULT_RU.md содержит ограничения.
Последнее живоеSAFE/PWM0/HVarm0/runid3/J1ON/15ВON/повербанки прежнего хода,
в этом ходе liveGET не делался. Все прежние разрешения START/CLEAR уже израсходованы.

## 2026-11-18: FOC1801/1802 5Гц/5000мс и два визуальных повтора завершены

После J1ON свежийRPCguard254/0PASS, ровно1CLEAR восстановил все защиты,
1ARM/1START основной FOC_5Hz_r2, Unoавтостоп5000мс, finalSTOP. native_donefalse.
Оператор дважды попросил повтор: каждый ещё1START/1ARM, CLEAR/RESET/flash0,
same-bootOFF64/liveguards/5сек. run_id1/2/3 завершились5000мс. Последний3оператор
подтвердил «Да, вращался ровно»; записано отдельным operator_observation.json.
Новые разрешения CLEAR/START ИЗРАСХОДОВАНЫ, дальше только анализ без запуска.
Первый observer1888Б/schema5 SHAca56189a4eeb0c49d0f5b6050a4743644ad5c07ca8c840f8df0ec3b990b3644d.
ADC1024Б/schema3 EXACTsource16+voltagehistory25/ring60,GAPfalse, step659 иfirst/end/
center/pairs[0,0,16] точно совпали с первымNIS. 29,30712509>25; ARM51словbitexactPASS.
Захват исправлен; NIS/скорость ещё НЕ исправлены. Физическая реконструкция токов/
напряжения по raw пока не вычислялась. total4958/valid741/invalid4217 включаяпрогрев.
Основнойruntime maxage583,3мкс<2мс/maxwall496,12мкс/CPUupper155,44мкс/errors0/faultnull.
OFF3804/4000, последнийfullRUN4744/5312 — разные бюджеты, не смешивать.
После3свежийGET SAFE/PWM0/HVarm0/runid3/elapsed5000/reason1/маски0/0/transport0/
UARTновых0/RPC254/0стабильны, SDHIGH/BIE/configok, bootбезизменений.
ПервыйSD63,8мкс и первыйNIS/ADC во всех повторах сохранены побайтно; новых сырых
снимков в визуальных повторах нет. 8056старых и105свидетельств SHA PASS.
Пределы4000/2мс/1,35А/2048/NIS25/50 и все защиты неизменны. Повербанки/J1ON/15ВON,
ПК/Saleae сняты, ШИМ0. RESULT_RU.md в exact_nis_input_release_r1/FOC_5Hz_r2,
визуальные FOC_5Hz_r2_visual_repeat и FOC_5Hz_r2_visual_repeat2.

## 2026-11-18: J1OFF подтверждён; RPC1801 восстановлена, основной HMI180с/153GET PASS

Пользователь выключил толькоJ1,15В/повербанки без изменений. START/CLEAR/ARM/
MCU_RESET/flash0; прежняя1CLEAR+1FOC5Гц/5000мс авторизация НЕ израсходована.
Новый временный штатный router0.5.3 напрямую62GET/60сPASS, затем завершён и
порт основного возвращён finally. Основной42GET/48с, затем503 на55с: failed
длинная проверка сохранена. mon/connected=true приUSBnotattached; Linuxmon/reset
закрыл толькоMonitor TCPклиентов, не MCU. СразуGETещёнеотвечал;1serialclose/open
0,5с при monitorfalse восстановил связь. Основной153GET/180,062сPASS, RPC254/0
стабильны, UARTновых0, bootпрежний, zeroReady, SAFE/PWM0/run_id0/HVarm0.
Это проверенное восстановление в текущем сеансе, НЕ доказательство первопричины
или постоянный фикс после загрузки. Службы/прошивки/модель/пределы не менялись.
SD63,8мкс прежний SHA2fb01b20ea604350f26a50c6a41372b19e258eb98951845826ee67dee5f2c6c5,
SDHIGH/BIEfalse, MCSDK4/4. NIS/ADCсвободны, OFF3804/4000,2мс/защиты прежние.
J1OFF по пользователю, но телеметрия~320–321В; НЕ считать шину разряженной.
8056 прежних файлов и все свидетельства установки/CLEAR SHA PASS. Новых щупов
илиUSB не нужно. Дальше пользователь включает толькоJ1soft-start, затем свежая
проверка и уже разрешённый одинCLEAR+FOC5Гц/5с при полностью готовых защитах.
Следующая новая папкаFOC_5Hz_r2; прежний failedpreflight не переписывать.
exact_nis_input_release_r1/RPC_diagnosis_J1_OFF_r1/RESULT_RU.md и main_without_monitor_r1/.

## 2026-11-18: разрешённый CLEAR+FOC1801/1802 НЕ отправлены из-за RPC503

Пользователь разрешил ровно1CLEAR+1FOC5Гц/5000мс при готовых защитах.
run_exact_nis_input_FOC_trial остановился в GET-only RPCpreflight HTTP503,
до создания FOC_5Hz_r1 и до конфигурации/CLEAR/ARM/START: все0.
Авторизация ещё НЕ израсходована; новую свежую проверку нельзя пропускать.
UnoSSH доступен, прямойget тоже не отвечал. Пассивно снято786432БRAM (неатомарно),
без halt/reset/write; SSHtimeout30с, удалённый дамп закончил сам, повторно не запускался.
1routerserialclose/open временно восстановил GET (SAFE/PWM0/vdc322/transport0),
но затем опять503. Квалификация failed.1HMI-owned-process restart также503;
Linux boot не менялся, MCU/Nucleo не сбрасывали, прошивок/порогов не меняли.
RAM с точнымELF1801: timedrun0/controlmutexfree/decoderempty/outgoingowner worker;
неатомарный снимок НЕ доказывает deadlock. Первопричина RPC не доказана.
Сохранены SD и все прошлые записи. Пределы4000/2мс/защиты прежние.
Запрошен только J1OFF от пользователя; 15В/повербанки/проводку/RESET не трогать.
Подтверждения J1OFF пока нет: не считать силовое выключенным.
exact_nis_input_release_r1/FOC_5Hz_r1_RPC_preflight/RESULT_RU.md,
RPC_recovery_before_first_START_r1/ и trial_preparation_r1/authorization.json.

## 2026-11-18: J1ON, шина322–323В; до FOC сохранён Break63,8мкс, пуска нет

«готво» после включения J1soft-start. GET20статусов/22,422с, кадры+445,
RPC12/0стабильны, UART/transport0, bootпрежний, автонольready, OFFfast3804/4000.
SDсейчасHIGH, но первыйBreak(eventtick155722) PA6LOW319×0,2=63,8мкс приMOE0
защёлкнул BIE/capture. Полная волна сохранена; PA4HIGH не TP23, провод снят ранее.
MCSDKcurrent/occurred4/4,fault5. Poweredpreflight failed только nofault/BIE.
START/CLEAR/ARM/RESET/flash0. NIS/ADCсвободны по телеметрии; предел2мс/защиты прежние.
exact_nis_input_release_r1/powered_before_FOC_r1/RESULT_RU.md,SD_first_before_CLEAR.bin.
Новый runner run_exact_nis_input_FOC_trial.py офлайн проверен, реальных команд0.
Дляпродолжения нужен новый отдельно разрешённый одинCLEAR; прежнийизрасходован
в USB-сеансе до смены питания. Платыповербанки/J1ON/15ВON/USBПК и Saleaeсняты.

## 2026-11-18: автономная1801/1802 перед FOC проверена; J1 пока выключен

Пользователь обе повербанки/USBПК и Saleae сняты/15ВON/J1OFF/noSTARTnoRESET.
Только HTTP GET: START/CLEAR/ARM/RESET/flash/SWD0. Первый connect timeout сохранён,
затем сеть появилась без вмешательств. Новый boot после смены питания, стабилен
20статусов/21,125с; +419 кадров, брака0/transport0/UARTflags0. RPC12/0 исторические,
за окно не выросли, baselineguard PASS; причину12 не утверждать доказанной.
Автоноль ready3good, offsets2068/2065/2066/2068 spans20/37/27/28, телеметрия свежая.
SDHIGH/BIE/config_ok, нового Break нет; буферы NIS/ADC по новому boot/run_id0/
отсутствующим raw/complete/good/bad свободны. Прямой SWD на повербанках НЕ читался.
Installed config NIS5/ADC3/source16/history25/ring60 проверен; полнота под ШИМ пока
не испытана. Новый OFF64 fast3804/4000, fault0/metererrors0, предел2мс прежний.
SAFE/PWM0/run_id0/HVarm0, vdc9В, MCSDK4/4 UNDER_VOLT при J1OFF. Не START ready.
Старые записи/установка/CLEAR SHA сохранены. Дальше только включение J1 через
soft-start пользователем и новая проверка шины/SD/защит; CLEAR/пуск не выполнялись.
exact_nis_input_release_r1/autonomous_before_FOC_r1/RESULT_RU.md и qualification/.

## 2026-11-18: один CLEAR1801/1802 без пуска; активная MC_UNDER_VOLT остаётся

Выполнен ровно один штатный CLEAR по явному разрешению пользователя.
HTTPok означает доставку; диагностическая запись Nucleo1802 подтверждает попытку
tick451469/seq26, результат MCSDK_ACK_REJECTED4, current/occurred4 при J1OFF/шина9В.
Все защиты НЕ восстановлены: transport7/bad_count1 остаются. Повторных CLEAR нет.
SDHIGH/BIE/config_ok, связь прогрессирует19статусов/21,7с, RPCtimeouts0/0,
boot прежний, zeroReady1. SAFE/PWM0/run_id0/HVarm0, START/ARM/RESET/flash0.
Пассивный SWD после CLEAR: observer_trace2052Б пуст, peak1052Б пуст, running0,
BKE/BIE1/MOE0. Буферы NIS/АЦП свободны; это НЕ готовность к START.
Пределы4000/2мс/все защиты неизменны,8134 прежних файла SHA проверены.
exact_nis_input_release_r1/one_CLEAR_idle_r1/RESULT_RU.md и report.json,
NIS_readiness_after_CLEAR_r1/report.json. Платы оставить USBПК,J1OFF,15ВON.
Новый силовой этап/пуск и повторный CLEAR не разрешены этим выполненным запросом.

## 2026-11-18: 1801/1802 установлены, readback и OFF64 пройдены

Пользователь подтвердил J1OFF / мультиметр DC<20В / обе USBПК / 15ВON.
COM10/13 и старые1715/1716 определены; до записи HMI9В/SWD9,95–9,97В/MOE0.
Каждая плата записана один раз; Uno OpenOCD readback PASS, native verify и
независимый полный readback PASS. Калибровка неизменна, HMI согласована.
RAM32КБ/прежний Flash/доступные снимки сохранены. 8056 старых файлов SHA PASS.
64/64 OFF-случая: fast3804/4000 тактов, observer25521, maxwall240,85мкс,
metererrors0. Предел2мс/1,35А/UPDATE2048/NIS25/50/все защиты неизменны.
SAFE/PWM0/run_id0/HVarm0, BKE/BIE включены, SDHIGH, автоноль готов.
12 статусов и два пассивных чтения RAM: boot стабилен, NIS-буфер2052Б пуст,
новых RPC/UART ошибок нет, обычная телеметрия свежая. Остаются MC_UNDER_VOLT4
при J1OFF и стабильная programming-time transport7/bad_count1. CLEAR не было;
это не подтверждение готовности к пуску. START/CLEAR/ARM0, дополнительных
reset/перепрошивок нет. Предел4000 измерен в OFF; АЦП/IRQ под ШИМ и физическая
причина NIS новым пуском не проверялись. Платы оставить на ПК, J1OFF,15ВON.
artifacts/live_bench_20261118/exact_nis_input_release_r1/INSTALLED_RU.md,
installation_acceptance.json, post_install_idle_r1/report.json.
Исторические manifest/старые записи не переписаны. Новый пуск не разрешён.

## 2026-11-18: 1801/1802 собраны и готовы к записи; пока не установлены

Новая пара: Uno2026111801 / Nucleo2026111802. Пакет:
artifacts/live_bench_20261118/exact_nis_input_release_r1/READY_RU.md и manifest.json.
Обе сборки PASS; 108 capture / 29 adapter / OFF64 / 32 guards / 106 wire / 4 HMI,
ARM replay 51 слов bit-exact. Installer --verify-only PASS, аппаратных команд 0.
Исправлен захват точного источника первого NIS; физическая причина NIS ещё
не доказана, математика/параметры наблюдателя не менялись. Пределы OFF4000,
age2мс, ток1,35А, UPDATE2048 и все защиты сохранены. На новой паре время
на MCU не измерено; после записи нужны OFF64 и ADC/IRQ без ШИМ до START.
8056 прежних файлов проверены по SHA-256. Старые снимки не переписаны.

Физически пока остаётся установленная1715/1716. Последнее подтверждение:
повербанки, J1/15В включены; после последнего пуска SAFE/PWM0/HVarm0.
Свежих чтений платы в ходе этой подготовки не было. Новых START/CLEAR нет.
Следующий шаг пользователя: выключить J1, дождаться по мультиметру DC<20В,
обе платы перевести на USB ПК; Saleae отключён, 15В оставить включёнными,
двигатель/шлейф/проводку не менять, Пуск/RESET не нажимать.
После подтверждения — свежие USB/HMI/SWD проверки и однократная установка
с резервным копированием и независимым чтением обратно, без пуска.

## 2026-11-18: offline разбор NIS; исправлен захват источника, причина NIS ещё не доказана

User просилразобрать/исправить по записи безпусков,4000/2мс/защиты/историюсохранить.
Аппаратныхкоманд0,дажеliveGET0;платы/установленные1715/1716неизменены. Последнее
физическоесостояниепользователяJ1ON/15ВON/повербанки;последнийlive послеFOC2
SAFE/PWM0/HVarm0,ноэтимходомсвежийстатусНЕчитался. НовыйпускНЕразрешён.
Независимыйdouble NIS25,668800vsARM25,668796,51словоbitexact,PSD P —
арифметикаверна. RK4F=25,6895,dt±10мкснеустраняет;разныенепроверенные
поправки(+.5ВαилиRs+20%)дают<25,выбиратьихкак«исправление»нельзя.
Доказаныдвеошибкидиагностики: ring12/post6при~.9мсопаздываетнаполноеsource16;
первыйFLUXlossподавляетrawдляпервогоNIS. Новыйoverlayсохраняет60packedстрок/
1024Б,точные16+предыдущие9дляvoltage-average,sourcefirst/end/step,честныйGAP,
запроспривязанкпервомуNISreplayдоpublish. HMIотличаетrawCRCvalidотsourcecomplete.
108recordercases,8bitexactCmean/voltage-rebuild,29nativechecks/OFF64model,
32guards,71Uno wire,5HMIchecksPASS.4ARMobjectcompileбезwarnings;fast/observer/
noise machine sections byte-identical. DebuglinkPASS,1056Бпослерезервов,
BSS+16Б;ADCstack368vs376,service344vs352,fast360. CPUнажелезенеизмерялся.
artifacts/live_bench_20261118/nis_input_window_r1/RESULT_RU.md,summary.json,
overlay/,source_changes.patch;tools audit_nis_1716_saved_step,observer_exact_peak*,
prepare_nis_input_window_overlay,test_exact_observer_input,verify_exact_input_native.
ЭтоDIAGNOSTIC OVERLAY,НЕflashable release:IDстарые,debugELFDO_NOT_FLASH.
NIS_algorithm_fixed=false/physicalrootcause=false;необъявлятьNISисправленным.
Q/R/моторныйпрофиль/NIS25/50/1,35А/UPDATE2048/4000/2мснеизменены.
ДлябудущейзаписинужныновыеID+сборкарелиза+CPUADC/IRQпроверкабезсилового;
сейчасничегопереключатьнепросили. СтарыефайлыпровереныпофинальномуSHAinventory.


## 2026-11-18: оператор подтвердил ровное вращение FOC_5Hz_r2 до автостопа

Ответ: «Да, вращался ровно». operator_observation.json и
OPERATOR_CONFIRMATION_RU.md добавлены отдельным дополнением; прежние
запечатанные анализы/захваты не переписаны. Физическое ровное вращение
подтверждено, численная скорость наблюдателя независимо не измерена.
NIS остаётся проблемой; прежние 87,80% принятых оценок не доказывают точность.
Аппаратных команд в этом ходе0, нового пуска/CLEAR/разгона нет.


## 2026-11-18: FOC1715/1716 5Гц/5000мс завершён, новый NIS воспроизведён bit-exact

Пользователь «готово» после включенияJ1soft-start. Ранее разрешённые один
CLEAR и один START ИЗРАСХОДОВАНЫ: FOC_5Hz_r2, одинARM. Защиты восстановились,
автостоп5000мс Uno, затем штатныйfinalSTOP; native_done=false. Финально и
свежимpost-analysisGET:SAFE/PWM0/HVarm0,SDHIGH/BIEtrue,маски0/0,algo0.
Bootпрежний,RPC209/0безроста,UARTновых0,SD17,5594мссохранёнпобайтно.
Физическоевращениепоканеподтверждено: asyncвопросотправлен, ответаещёнет.
Новыйtrace1888Б/schema5 SHA c9fa2a1cf6e9fc4b0db6c08a7494df26746af9b2b44d2e13447367a9b2a38f82.
4984шагов,3938valid,1046invalid (499warmup/547после),87,80%validпослепрогрева
против80,70%старого1713/14. R/метрикаNISизменены,этоНЕдоказательствоточностискорости.
ПервыйNIS503/25,6688,все51словоARMprior/postP bitexact наПК. Системныйpython
не имелunicorn: failureNIS_step_replay.jsonсохранён;успешныйновыйотчёт
NIS_step_replay_venv.json. Использовать .venv/Scripts/python.exe для будущих
replay/run скриптов; новыхмоторныхкомандрадиreplayнебыло.
Максage897,6мкс<2мс;OFFfast3827/4000,fullRUN4766/5312 (разныеscope),
runtimewall810,9мкс/CPUupper188,2мкс,firstfaultnull. Последнее184мстоковоеокно:
RMS[.368,.347,.374],пики[.71,.70,.70]А,coverage100%. Номинальныймасштаб,
окноменьше200мс при5Гц;неfullperiodRMSи не whole-runpeaks.
ADC1024Бесть,12эпохсогласованы/безwindowqueueflags,ноrawстроки687–1375мкс
ПОЗЖЕ observerendpoint,неисходные16отсчётов. Неотбрасыватьошибкуисходногоокна
поэтимпоздним12строкам. Captureexactmean/P/inputпозволяетreplayшага.
RESULT_RU.md,analysis.json,comparison_to_1713_1714.json/analysis_files_sha256.json.
Старые5921/source/releaseхешипроверены. Пределы1,35А/2048/4000/2мспрежние.
ДальшеанализсохранённогоNIS;новыйпуск/разгонНЕразрешёнэтимжеизрасходованным
разрешением. J1/15В/повербанкипослепусканеизменялись.


## 2026-11-18: RPC сейчас восстановлена, основной канал прошёл90с/77GET; J1OFF

J1OFF пользователь подтвердил «готово». 15В/повербанки сохранены. HMI-only
перезапуск1 не помог; первый close/open UART дал временное восстановление,
после17,6с quiet-серии повторилсяHTTP503 (не скрывать этот отказ). Затем
один новый пользовательский router v0.5.3 через прежний UART:60GET/60сPASS,
основной порт возвращён вfinally. Временный router завершён. Основной RPC
затем прошёл90,86с/77статусов с неизменными timeout209/0, boot тот же,
UART0/автоноль3/3/SDHIGH/OFF3827из4000. Шина10В,SAFE/PWM0/run_id0.
BIEfalse и MCSDK current0x4/occurred0x404 остаются. СнимокSD сохранён,
NIS receiver пуст. Фактическая причина первичного отказа НЕ доказана;
свежий router отличается такжеverbose/monitor-клиентами. Не объявлять
monitor виновным или весь RPC окончательно исправленным.
RPC_recovery_J1_OFF_r1/RESULT_RU.md,report.json,main_RPC_90s_r1/report.json.
MCU/HMI code/release и5921 старая запись поSHAбезизменений. MCU RESET/halt/
flash/CLEAR/ARM/START0. Один ранее разрешённый CLEAR и одинFOC5Гц/5000мс
ещё не израсходованы: повторно разрешения не спрашивать без смены условий.
Далее толькоJ1ONsoft-start,15В/повербанки неизменны,ПК/SaleaeOFF,
Пуск/RESETне нажимать. Свежий poweredpreflight, затем максимум одинCLEAR и
START толькоесли все защитыготовы. НовыйoutdirFOC_5Hz_r2 (r1_RPC_preflight
failedсохранён). Пределы4000/2мс и прочие прежние.


## 2026-11-18: FOC1715/16 заблокирован ДО CLEAR: RPC перестала отвечать в покое

Пользователь разрешил один CLEAR + один FOC5Гц/5с при готовых защитах.
run_pair_noise_FOC_trial остановился на первом GET RPC-preflight HTTP503.
CLEAR/ARM/START0: команды не израсходованы. Прямой GET RouterClient тоже null,
Linux/HMI/router живы. Сохранена RAM Uno786432Б без halt/reset/flash,
CORE_AFTER running, fault-регистры нулевые; exact1715ELF SHA проверен.
RPC health=[76,0,0,0], рост response_timeouts при выключенном ШИМ.
Точная причина ещё не установлена; не делать вывод о deadlock по остаточным
словам стека неатомарной RAM. Нового моторного захвата и сравнения нет.
Доказательства: observer_pair_noise_r1/FOC_5Hz_r1_RPC_preflight/RESULT_RU.md,
Uno_RAM_nonatomic.bin,waits_decoded.json,failure_diagnosis.json.
5921 старая запись проверена без изменений, защиты/4000/2мс прежние.
Запрошено выключить только J1; подтверждения ещё нет, ответ «и че дальше».
15 В, повербанки, RESET и проводку не менять. Восстановление RPC ещё не
выполнялось; никаких автоматических повторов пуска. После подтверждения
J1OFF возможно программное восстановление и новая проверка. Авторизация
одного CLEAR/одного START остаётся неиспользованной, повторно не спрашивать
без изменения условий или расходования команды.


## 2026-11-18: J1 включён, шина 321–322 В; CLEAR/пуск ещё не отправлены

Только GET, powered_before_FOC_r1: связь стабильна, RPC timeout0/0, UART0,
тот же boot, SD HIGH, автоноль3/3, OFF64/3827тактов. Первый LOW17,5594мс
сохранён неизменным. BIEfalse, MCSDK current0x4/occurred0x404/fault5/reason8:
защиты ещё не подтвердили готовность. START/CLEAR/ARM/RESET/flash0.
Питание пользователь подтвердил: повербанки, ПК/Saleae отключены,
15 В и J1 через soft-start включены. Для продолжения один новый штатный
CLEAR только после разрешения, затем проверка всех защит; без готовности
START не отправлять. 4000/2мс и старые записи сохранены.


## 2026-11-18: автономный 1715/1716 preflight пройден; J1 пока OFF

Повербанки, USB ПК/Saleae отключены, 15 В ON, J1 OFF. Только чтение:
RPC/UART без ошибок, 13 статусов / 15,9 с, boot стабилен; автоноль 3/3,
OFF64 быстрый расчёт 3827/4000, наблюдатель 25013/85000. SAFE/PWM0/run_id0,
шина 9 В по ADC. SD HIGH, сохранён первый LOW 17,5594 мс без ШИМ;
BIE ещё false, MCSDK current=0x4/occurred=0x404. CLEAR/ARM/START/RESET0.
NIS receiver пуст; прямого SWD/RAM на повербанках не было. Старые 5921
файл проверены по SHA256. Доказательства: observer_pair_noise_r1/
autonomous_before_FOC_r1/RESULT_RU.md и report.json.
Далее только включение J1 через soft-start и новая проверка шины/защит.
Пуск ещё не готов; новый CLEAR пока не разрешён.



## 2026-11-18: подготовлен ограниченный FOC1715/1716 и сравнение, ожидается автономная подготовка

Пользователь проситFOC5Гц5с/NIS/автостоп/сравнитьспрошлым, спрашиваетчто
переключить. ПоследнеесостояниеUSBПК,J1OFF,15ВON,SaleaeOFF. В этом ходе
аппаратныхобращенийиликоманд0,ниClear,ниARM,ниSTART/RESET/flash.

Новый tools/run_pair_noise_FOC_trial.py готов: привязан1715/16/schema5,
прежниеbounded5сguards/heartbeat/hostbackupSTOP/сборпослеOFF, точныйARM/FMA
schema5replayпослесбора. --verify-package-only успешно,24negativeguards
(включаяOFF4001/ageсвежесть/низкуюшину/SDLOW/BIEfalse/маски/транспорт)пройдены
с заблокированнойсетью. Пакет/receipt/source/artifacts/preservedinputsпроверены.

observer_pair_noise_r1/trial_preparation_20261118_r1/PLAN_RU.md.
Предыдущийэталон:observer_nis_replay_r1/FOC_5Hz_r1(1713/14,80,70%validпослепрогрева,
первыйNIS563/28,367,полныйARMreplay). НельзясравниватьNISкакнеизменённуюметрику:
Rисправлена, болееvalidнеподтверждаетистиннуюскорость. Обаопытаархивироватьотдельно.

Следующийфизическийшаг: J1OFF, обе платы сUSBПКнаповербанки с5спаузой,
USBПК/SaleaeвключаяGNDотключены,15ВON, проводку/двигательне менять,
Пуск/RESETне нажимать. Послеего«готово» автономныйGET-onlypreflight;
затемвключениеJ1черезsoft-start и свежаяpoweredпроверка. СтарыйCLEARне
переиспользовать:одинновыйCLEARтолькопоявномуразрешениюприостаточнойзащёлке.
ОдинFOCзапрошен, доизоляции/силового/проверкизащитзапускатьнельзя.

## 2026-11-18:1715/1716 УСТАНОВЛЕНЫ, readback/OFF64 пройдены, без пусков/CLEAR

Пользователь «готово» послеинструкций J1OFF/<20В/USBПК/15ВON/SaleaeOFF.
COM10/COM13определены, freshHMI0В/directnativeSWD0,635В/MOE0/tickprogress446мс;
старый1714HEXсовпал. User meter-числа невыдумывали; HMI/SWD—двапутикодномуADC.
Обе новыепрошивки записаныпоодномуобразу, верифицированы чтениемобратно.
Matching schema5HMI установлен, калибровкаSHAдо/послебезизменений. RAM32КБ/
стараяflash/записи до записи сохранены;5921protectedfile/source/releasehashes
послезаписипроверены. START/CLEAR/ARM0; ручного/дополнительногоRESETне было,
штатныепрограммирующиеперезапуски были. Не выдаватьпослеUSBRAMзастаруюдоUSBRAM.

observer_pair_noise_r1/installation_acceptance.json иINSTALLED_RU.md —
актуальноеустановленноесостояние. manifest.json неизменныйpreinstallснимок,
егоinstalledfalse неактуален; receiptблокируетповторнуюпрошивку.

OFFtarget64/64: fast3827<=4000,observer25018<=85000,timingfault0,
2мсguardсохранён. Пределынигденеповышались;raw1,35/UPDATE2048/SD/Break/
old+correctedNIS-watchdogпрежние. FullRUNdeadline5312отдельныйscope,
подШИМновыйвариант ещёНЕизмерялся иphysicalNISfixНЕподтверждён.

8GETsameboot/progress/RPCguardready/newRPC/UART0. SAFE/PWM0/HVarm0,
автонольready3good/0bad,SDHIGH/BIEtrue/configOK. DirectreadRAM2052:NISбуфер
свободен,total0/flags0/payload0, фактическийADCpairbyteвалиден. ЭтоOFFчтение,
неполныйисторическийконтрольпарподШИМ. BKEtrue/MOEfalse.

Шина0В приJ1OFF: сохраняютсяlocal2/reason8/currentMCSDK4/transport7.
CLEAR неразрешали/непосылали; защёлкине считатьснятыми. ПлатынаПК,
15ВоставленыON по подготовке,SaleaeOFF,двигатель/шлейфне меняли.
Новыйпуск/ARM/силовойтестэтимзапросомнеразрешён.

## 2026-11-17: запись1715/1716 подготовлена; ожидается перевод в USB/низкую шину

Пользователь просит подготовить запись, сказатьчто переключить, после прошивки
сверить readback и время безШИМ. Новыхпусковнельзя,4000/2мс/защиты/старые
записи сохранить. В этом ходе тольколокальнаяподготовка, аппаратныхкоманд0.

Подготовлен tools/install_observer_pair_noise.py на базе проверенногоинсталлятора:
OLD1713/1714→NEW1715/1716, правильныеHEX/Unoelf-zsk/schema5HMI/readbackпути,
backupRAM/flash/calhash/record, безSTART/CLEAR/ARM. --verify-only успешно,
5921protectedfiles/исходники/артефакты/guardreportsпроверены. Не записывать
повторно при существующемinstallation_acceptance.json. СвежаяSWD/USB/lowbus
проверка требуется непосредственно передзаписью, а не в offlineverify.

observer_pair_noise_r1/installation_preparation_r1/PLAN_RU.md иplan.json.
Следующийфизическийшаг: J1OFF; послеразряда<20В обе платы сповербанковнаUSBПК,
15ВможнооставитьON,SaleaeOFF,проводку/двигательне менять,Пуск/RESETне нажимать.
Пользователь не обязан повторно диктовать показания: после его сообщения о
подключении проверитьUSBидентичности/HMIиnativeSWDсамим; невыдумывать
изпоказанияADCотдельное подтверждениеположенияJ1.

Последнеефизическоесостояниедо этогошага былоJ1/15ВON/повербанки/ШИМ0.
Пока новое состояние не сообщено,не считать уже выполненным переключение.
После записи: readbackобеихплат,calhashбезизменений,OFF64fast<=4000/
observer<=85000 безШИМ,свежестьсвязи/автоноль/захваты. Приошибке нет пуска,
нет подъёмапорогов. ФизическоеиспытаниеподШИМсейчасне разрешено.

## 2026-11-17: подготовлен1715/1716 pair-noise candidate, НЕ установлен, новых пусков не было

По запросу пользователя выполнено offline-исследование физического NIS563/28,367
и исправление модели измерения. Пакет observer_pair_noise_r1/RESULT_RU.md.
Установленными остаются1713/1714, стенд не читали/не прошивали, CLEAR/START/ARM/
RESET/flash0. Последнее физическое состояние:повербанки,15В/J1ON,ПК/SaleaeOFF,
SAFE/PWM0/HVarm0 после ранее завершённого5сопыта. Новаяавторизацияпуска отсутствует.

Найдена неучтённая геометрия шума: третья фаза реконструирована, alpha/beta
ошибки зависят от реальной пары и коррелированы; прежде R=.0004Iвезде.
Теперь ADCпередаётфактическуюпару(32Бструктураиспользуетстарыйpadding), окно
считаетвсе16пар, R=.0004/16*sum(Np Tp TpT), коррекция с exactwhitening/Joseph.
Q/RK4/моторныйпрофиль/регуляторы не менялись. Число.0004 трактуется какфазный
модельныйуровень, НЕизмереннаякалибровкашума. R_alpha_beta МЕНЯЕТСЯ, не говорить
«Rне менялась». Фактические независимость/равенство/временнаянезависимость
ADCшума не подтверждены на железе; единственнаяпричинасрывов не доказана.

Длянеослаблениязащиты сохранёнстарыйfixed-R NIS-watchdog, остановка при >50
20последовательныхшагов в ЛЮБОЙ из старой/новойметрик. Отдельныеpositive/negative
тестыобоихнаправленийпройдены. Raw1,35A/2мс/UPDATE2048/SD/Break иOFF4000/
старыйRUN5312порогисохранены. ДиагностическийNIS25 неповышен, егоRмодельисправлена.

ПриUWвсех16сэмплов сохранённыйstepусловнодаётNIS19,16656 вместо28,367.
Но старыйschema4 НЕсохранилвсе16пар:UWвиднавendpointи12позднихADCстроках.
Из153возможныхсоставов NIS17,50..40,44 (112ниже25,41выше). Поэтому
НЕвыдаватьусловнуюгеометрию за подтверждённыйисправленныйфизическийreplay.
Schema5сохраняетточныйсоставпарвкаждойстроке/456Бreplay,wire1888Б/63page,
старые2/3/4декодируются. НовыйARMreplayсоstablepointerABIсчитаетRнатемжеELF.

32guard+153noise/batchdouble+1,2млнADCdraws+19plantcasespervariant,
25adapter/64OFFhost+147wire/frozen+153ARM/FMAпобитныхсинтетическихreplay,
6badmetadataCLIпроверокпройдены. Номинал5с, шум±16countsvalid93,8→96,05%,
speedRMSE16,10→15,02. Bias8counts/deadtime+.5us/overcurrent/age2.1msstopretained.
ПриошибочныхRs/напряжении скоростьостаётсясмещённой; не обещатьдостоверностьдо50Гц.

Обаобразасобраны: Nucleo text117220/data976/bss30720/bin118200, +16БRAM;
стекobserver760/service352/fast360, Uno172244/globals101314. TargettimingНЕ
квалифицирован; OFF4000послеустановкидолженпройтисам,доэтогоSTARTнельзя.
releaseсодержитHEX/BIN/ELF/Unoelf-zsk/expectedreadback(4FFgap)/sha/replayer.
5921предыдущихфайла,включаяфизическийFOCиоригинальные1713/14sources,сверены.
Новаяпрошивка/hmi ещёНЕ установлены; физическийуспехновойверсии не заявлять.

## 2026-11-17: FOC1713/1714 5Гц/5000мс выполнен; физический NIS-шаг повторён побитно

Пользователь «да» разрешил ровно один новыйCLEAR иодинFOC5Гц/5с при готовыхзащитах.
run_nis_replay_FOC_trial.py выполнен:clear1/start1/arm1,passedtrue,5000мс
Unoавтостоп, native_donefalse (егоопередилSTOPUno), finalSAFE/PWM0/HVarm0,
маски/локальные/transport/algorithm0,RPCtimeouts0. Дополнительный GET подтвердилOFF.
Операторответил«Да, вращался ровно» именно проэтотопыт; operator_observation.json.
Авторизация CLEAR+START ИСЧЕРПАНА; дополнительныхпусковне делалось/не разрешено.

Папка observer_nis_replay_r1/FOC_5Hz_r1/RESULT_RU.md. Все1888Бschema4+ADC1024Б+
CPU/IRQ/bootполучены; epoch/nativeLinuxbootне менялся. Полный priorx/P/модель/
input/FPSCR первогоNISшага563/28,367168 сохранён. ActualARMELF/FMAreplay наПК
совпалпоВСЕМ51словам ma_observer иresult0, physicalcaptureSHA3041f9c11f20d3e16d089d9947f6461ec220209a5cd422ffcdc6956ea1941420.
Это первый полныйфизическийповтор, не синтетическийтест. Старый SDснимок
побитносохранён,5605старыхфайловсверены; исходныеколлекторскиеsealsне переписаны.

4960шагов,3600valid/1360invalid,499warmup =>послепрогрева80,70%valid,
861invalidостаётся. Независимойскорости нет. NISне исправлен, доразгонаFOC
не объявлятьполнуюдостоверность. Betaусловнаяневязка0,111093А даёт28,055из28,367.
Doubleэталон28,367182; Pположительны. RK4transitionтольконаэтомшагепритомже
priorx/Pдаёт28,388272 — не снимаетегоотказ. Эквивалентнаяодношаговаяподгонка
напряжений[-0,903;+8,517]В — НЕидентификацияжелеза/НЕпрошивочнаякомпенсация,
на платы не применялась. Физическаяпричинаещёне установлена.

Последнее160мсокно токов RMS0,364/0,365/0,362А,peak0,71/0,72/0,72А,coverage100%,
номинальныйнеквалифицированныймасштаб; <200мспериода,неfullperiodRMS/whole-runpeak.
Maxage832,04мкс<2мс; runtimefirstfaultnull,maxwall689,64мкс. OFF3811/4000,
полнаяRUNfast4692припрежнемdeadline5312: не говорить fullRUNвлезв4000.
Порогинеподнимались. Платы на повербанках,15В/J1ON,ПК/SaleaeOFF,ШИМ0.

## 2026-11-17: J1ON poweredpreflight1713/1714 — требуется новая авторизация CLEAR+FOC

Пользователь подтвердил J1soft-start/15ВON/повербанки/ПКиSaleaeOFF, безПуска/RESET,
просил проверить передFOC. Проверено12GET/13,062с: шина321–322В,temp51°C,
SAFE/PWM0/HVarm0/run_id0,автонольready3,OFF64/fast3811/observer24061,
RPCguardready/sameboot/UART-RPCnewerrors0,transport0/badcount0.

Пуск блокирован: SDHIGH/configOK, BIEfalse после сохранённого Break;
local5/reason8,current4/occurred1028. CLEARдиагностиканеполучена/попыткинет
вновомboot. ИсходныйSD320Б SHA сохранён, совпадает с доJ1:LOW17,6098мс,
обафронта,MOE0/внеSTARTwindow. Не выводить отсутствие новых импульсов из
неизменности первой frozen-записи; TP23перемычка снята.

Папка powered_before_FOC_r1/RESULT_RU.md. Новый tools/run_nis_replay_FOC_trial.py
подготовлен для1713/1714: прежние trialguards/heartbeat/5савтостоп, точный
ARMreplay только послеOFF и сбора.20отрицательныхguardпроверок пройденыoff-line,
реальная currentзащёлка STARTнепропускает. Никаких liveкоманд или выбораFOC
не было. Для проверки новых методов не использовали фальшивый статус на устройстве.

Теперь можно запросить ОДИНновыйCLEAR иОДИНFOC5Гц5000мс при полностьюготовых
защитах. До явного ответа START/CLEAR/ARM/RESET/flash=0. При ответеиспользовать:
 tools/run_nis_replay_FOC_trial.py --confirm-autonomous-powered --clear-once
 --outdir <новаяпапка>. Онсампроверяетпакет/связь,потомвыбираетFOCиодинCLEAR;
отдельного предварительногоCLEAR не делать. НеудавшийсяCLEAR не повторять.
Последующий replay требует actual observer_trace schema4 и sealed ELF.

## 2026-11-17: автономная связь1713/1714 проверена перед NIS-FOC, J1 покаOFF

Пользователь подтвердил повербанки/ПКиSaleaeOFF/15ВON/J1OFF, безПуска/RESET.
GET-only12статусов/12,875с: стабильные Linux/nativeboot, прогресс кадров,
RPCsend/response0,UARThardware/integrity/sequence0,transport0,badcount0.
SAFE/PWM0/HVarm0/run_id0. Автонольready3 good/0bad,spans21/32/25/22,
OFF64,fast3811<=4000,observer24061<=85000,timingfault0/algorithmfault0.

observer_nis_replay_r1/autonomous_before_FOC_r1/RESULT_RU.md. Новый сеанс после
переключения питания; RAM по SWD не читалась (USB снят). Готовность буфера NIS
выведена из нового boot/noSTART/проверенной инициализации, приёмник пуст; не
приписывать прямое чтение памяти или полученную физическую NIS-запись.

Пуск пока блокирован: шина9В/active4/occurred1028/local5reason8; SDHIGH/configOK,
BIEfalse после стартового Break. Полный PA6LOW17,6098мс сохранён с обоими фронтами.
TP23->PA4 снят, причин по PA4не делать.5605 старых файлов и sealed sources intact.
CLEAR/START/ARM/RESET/flash0; новой авторизации CLEAR/START в этом запросе нет.

На ПК исправлен release_observer_decoder.load_decoder: schema4 используетhelper
 decode_nis_replay, теперь он извлекается без импорта сервера и с math/struct.
Offline schema4 replay +старые2/3проверены с запрещённой сетью. Бинарники/HMIна
платах не менялись. Следующий физический шаг — только J1 черезsoft-start и
poweredpreflight. Прежний одноразовый CLEAR из USB-сеанса не переиспользовать.

## 2026-11-17: разрешённый один CLEAR1713/1714 доставлен; Break восстановлен, полный сброс MCSDK заблокирован низкой шиной

Пользователь явно разрешил один штатный CLEAR без пуска; выполнен ровно один
POST/CLEAR, HTTPack и диагностический firstattempt получены. START/ARM/RESET/flash0.
Авторизация ИСЧЕРПАНА; второго CLEAR не отправлять автоматически.

one_CLEAR_idle_r1/result.json и RESULT_RU.md. Перед попыткой свежая шина0В,
SAFE/PWM0/HVarm0, автонольready, SDHIGH, BIEfalse после сохранённого импульса.
Снимок валидирован/сохранён, что позволило штатную попытку восстановления BIE
без требования уже восстановленного BIE; защиты START не ослаблялись.
21 отрицательный offlineguard пройден, новый скрипт clear_nis_replay_idle_once.py.

После: SDHIGH/BIEtrue, BKEtrue/MOEfalse прямым чтением регистров; новых RPC/UART
ошибок нет, guardsameboot/stablecounters пройден. MCSDK result4 ACK_REJECTED:
в момент попытки current4/occurred1028 при0В. Финальные живые маски0/0, но
локальная ошибка5 и transport7 остались. Полной готовности к START НЕТ.
Не говорить «CLEAR снял все ошибки», не делать ещё CLEAR без новой авторизации.

Прямое пассивное чтение2052Б observer_trace (без halt/reset): total0,
frozen/sealed/seen_valid/replay_latched0, payload456Б нули. NIS-захват свободен,
автонольready. Старый SD-снимок побитно сохранён,5664 предыдущих файла проверены.
Платы по-прежнему наПК, J1/15В в этом ходе не переключались; последнее напряжение0В.

## 2026-11-17: 1713/1714 УСТАНОВЛЕНЫ и проверены, без пуска/CLEAR

Пользователь указал самостоятельно проверить USB/напряжение. UnoCOM10/NucleoCOM13
определены по серийным идентичностям. Свежий HMI10В/SAFE/PWM0 и пассивный SWD
10,118/10,163В/MOE0/progress подтверждены; нового операторского замера/J1OFF
не выдумывали. Записаны Uno2026111713/Nucleo2026111714 по одному разу, обе
проверены чтением обратно. Калибровка не изменилась, RAM32КБ и предыдущая flash,
статусы/записи до прошивки сохранены.5605 старых файлов сверены, не изменены.

Пакет observer_nis_replay_r1: installation_acceptance.json и INSTALLED_RU.md —
текущее подтверждение установки. manifest.json остаётся запечатанным снимком
подготовки с installedfalse; не считать это актуальным состоянием. Инсталлятор
теперь запрещает повтор при существующем receipt. HMI согласован со schema4.

8 свежих статусов: SAFE/PWM0/HVarm0,10В,автонольready3,SDHIGH/BIE/configOK,
RPCsend/response0,UARTrx/integrity/sequence0. Все64OFF: fast3811<=4000,
observer kernel24930<=85000, полный OFFprofile maxwall237,79мкс. Это именно
OFF-квалификация с новым захватом, не RUN/ШИМ и не подтверждение2мс под нагрузкой.
Observer recorder пуст. Никакого START/CLEAR/ARM не было, аппаратный Break включён.

Остаётся стартовая локальная ошибка2/reason13/transport7; активная и occurred
маски MCSDK0. Не стирать без соответствующей авторизации, не объявлять полностью
готовым к пуску. Платы остаются на ПК, напряжение шины последнее10В; J1/15В
оператор в этом обмене не переключал и их положение не измерено отдельно.

## 2026-11-17: подготовлен replay первого NIS, Uno2026111713/Nucleo2026111714 — НЕ установлен

Пользователь просил захват x/P до первого NIS, проверку на ПК и подготовку
прошивки, без пусков. Сообщил «платы на ПК», но J1/напряжение в этом сообщении
не подтверждал. Фактической записи/чтения MCU/START/CLEAR/RESET не было.
Только локальная сборка/тесты и перечень USB ОС (ST-LINK COM13 присутствует).

Пакет: artifacts/live_bench_20261117/observer_nis_replay_r1, READY_RU.md.
Основа установленные1611/1612, НЕ эксперимент observer_variational_r1.
Математика наблюдателя и защиты неизменны. Schema4:1888Б/63пакета,8 редких
строк/stride700 + first_loss + replay456Б. В replay полные prior x6/P36,
steps/rejected, модель52Б, ia/ib/va/vb/dt и FPSCR; после первого NIS>=25
(попытка шага500+) — полные post x/P и NIS/prediction/innovation/S/result.
Фиксируется даже без предыдущей valid-скорости, не перетирается STOP/CLEAR/START.
Старые schema2/3 декодируются. Новая wire4 требует согласованных Uno/Nucleo/HMI.

154 проверки захвата, 64 old/new ARM вызова побитно совпали, 25 adapter-проверок,
64 OFF-случая на host и19 полных модельных сценариев сохранены. Повтор одного
синтетического отказа выполняется фактическим ARM ELF/FMA в Unicorn2.1.4 на ПК:
51 слово результата побитно совпало, CLI/CRC/SHA проверены. Это не физический
захват и не измерение MCU CPU/времени/истинной скорости.5605 старых файлов
сверены по хешам. Оба образа собраны; target timing и readback ещё НЕ выполнены.

Nucleo text116356,data976,bss30704,bin117336Б; RAM не выросла. Стек observer744,
service304, как прежде. Uno flash172244/globals101314Б. Остановленная проверка
foreground включает обе диагностические копии, её85000 и OFF4000 не повышены.
Прежние2мс/1,35А/UPDATE2048/FOC5Гц5с сохранены. Ничего не объявлять исправлением
самой причины NIS: пакет даёт возможность точно повторить будущий отказ.

Release содержит HEX/BIN/ELF/Unoelf-zsk, replay_manifest/sha256 и независимый
expected_readback из HEX (4 FF-gap-байта против00 padding rawBIN). Запись на
платы в этом запросе не выполнялась; для неё нужно подтверждение J1OFF/метр<20В.

## 2026-11-17: остаточный NIS исследован на ПК; разгон FOC пока не квалифицирован

Новых START/CLEAR/RESET/перепрошивок или чтений стенда не было. Установленные
1611/1612 сохранены. 263 исходных файла последнего захвата и пакета сверены
до/после по SHA-256. Физическое состояние по последнему подтверждению:
повербанки, 15 В/J1 включены, ШИМ выключен; нового состояния не предполагать.

Результат: artifacts/live_bench_20261117/remaining_nis_offline_r1/RESULT_RU.md.
Первый отказ NIS: невязки +0,08702/−0,06228 А, sigma ~0,02104 А. Сохранённый
ADC начинается позже эффективного входа; полного x/P до шага нет. Точный replay
физического отказа невозможен, физическая причина остаётся НЕ доказана.
120 независимых математических проверок исходного C: знаки/Jacobian/NIS OK.
Исправлена методика матмодели: отдельное напряжение инвертора из CCR и истинного
тока, вместо controller.last_va/vb. 19 сценариев показали, что низкий NIS может
сосуществовать с ошибкой скорости при неточном Rs/напряжении. Это не измерение
реальных параметров стенда и не повод подставлять произвольную компенсацию.

Эксперимент observer_variational_r1 (исходники 2026111711/1712): RK4-согласованный
переход ковариации, Q/R и все защиты сохранены. 120 математических проверок,
19 сценариев, 25 adapter-проверок/64 OFF-случая на host и ARM-сборка пройдены.
НО устойчивого улучшения NIS нет. Решение HOLD: к установке/силовому тесту
НЕ рекомендован, это не готовое исправление. Собрана только Nucleo, Uno не
собиралась/не устанавливалась. Target CPU/стек не квалифицированы. Стек ma_observe
744→800 Б, глобальная RAM прежняя. Пределы OFF4000, age2мс, trip1,35А,
UPDATE2048, FOC5Гц/5с прежние. Полный RUN deadline5312 — отдельная область.
Не выдавать проверку host с модельными часами за измерение времени на MCU.

Проверен GitHub wchan29: mini_IM — конструкция/сборка/JMAG учебного двигателя,
в дереве нет исходников встроенного FOC/EKF; eMach — анализ/проектирование машин.
Ссылки и результаты в отчёте. Новых переключений/замеров у пользователя не просили.

## 2026-11-17: FOC1611/1612 5Гц/5000мс выполнен, оператор подтвердил ровное вращение

Пользователь разрешил ОДИНCLEAR иОДИНFOC5Гц/5с при готовыхзащитах.
tools/run_observer_window_FOC_trial.py --confirm-autonomous-powered
--clear-once --outdir .../observer_current_window_r1/FOC_5Hz_20261117_r1
выполнен:passedtrue,CLEAR1/ARM1/START1,flash/reset0,автостопUno5000мс,
run_id1/run_reason1,finalSAFE/PWM0/HVarm0,маски0,UART/RPC0.
Пользовательответил «Да, вращался ровно» именно об этомопыте.
operator_observation.jsonотдельно;оригинальныйsealedreportне переписывали.

ПолностьюполученыADC1024Б/observer1888Бschema3/CPUIRQ/boot,CRC/fwOK,
Linux/nativebootво времяопытане менялись. СтарыйSD63,6мксдо/послесовпадает,
предыдущиезахватынаПКсохранены. NIS4978шагов:3546valid/1432invalid
(71,23%vs42,59%встаромNov16FOC_trial_r1). После499warmupvalid79,17%vs47,33%.
Первыйотказ562/NIS25,872,финальныйсохранённыйNIS9,835(vs116,054раньше).
ПроблемаНЕрешенаполностью:933invalidпослеwarmup,оценкаскоростинезависимо
неподтверждена. Не выдавать последнийNIS за максимумвсегоопыта.

НоминальныеRMSпоследнего178мсокнаU/V/W0,375/0,356/0,359А,
peak0,700/0,720/0,767А,coverage100%. Окно<200мспериода5Гц,
неполныйperiodRMS/не whole-runpeak/амперныймасштабнезависимонеквалифицирован.
Maxresultage811,34мкс<2мс,observermaxwall680,15мкс,maxCPUupper163мкс,
firstfaultnull. OFF3811/4000; полныйRUN4689припрежнемdeadline5312.
НЕговорить,что полныйRUNвлезв4000. Пороги/прошивкине менялись.
AutoStopUno5000подтверждён; native5sflagfalse(егоопередилSTOPUno),
не приписывать обеимзащитамнезависимосработавший5сстопвэтомопыте.

Все12rawADCстрокприняты/эпохисогласованы/deadlineok; rawзахватначинается
позжецентра16samplemean,неявляетсяполнымrawreplayэффективноговходаEKF.
Подробности:FOC_5Hz_20261117_r1/analysis.json,RESULT_RU.md.
Автодополнительныхпусковне делать. Текущеефизическоесостояние:
повербанки,15В/J1ON,PC/SaleaeOFF,ШИМ0. ДальнейшийCLEARнеразрешён,
выполненнаяодноразоваяавторизацияполностьюизрасходована.

## 2026-11-17: свежий poweredpreflight перед разрешённым FOC — 320–322В,SDHIGH,но нужен новый CLEAR

Пользователь явно запросил одинFOC5Гц/5с с токами/NIS/ADC/автостопом,
подтвердил J1черезsoftstart/15ВON/повербанки/ПКиSaleaeOFF,безПуска/RESET.
powered_before_FOC_20261117_r2:20GETстатусов/22,78с,UART/RPC0,
автонольready/3блока,OFF3811<=4000/64случая,ADCиobserverсвободны,
температурныйguardpass,шина320–322В,SDHIGH/configOK. START/CLEAR/ARM=0.
Активнаямаска0,occurred4(MC_UNDER_VOLT),mc_fault5,BIEfalse:пускБЛОКИРОВАН.

ПервыйBreakэтогосеанса:789303мсboot,LOW63,6мкс,полныеобафронта,
MOE0/внеstartwindow,безDMA/overrun/timeout. SD_before_CLEAR.bin320Б,
SHA8d1b7ed7422167cc58b646245613b7f277e040060f7481fad8de10f9d2d689f3.
Не путать с сохранённым17,7144мс импульсом прежнегоboot. Всё сохранено
вreadiness_axes/extended_saved_files_sha256. PA4внешняяTP23перемычкаСНЯТА,
не делать выводыопроисхождениипоPA4HIGH.

Пользователю отправленasyncвопрос: разрешаетлион ОДИНновыйCLEAR,
проверкузащит и затем уже согласованныйFOC5Гц/5с приполномвосстановлении;
альтернатива «ТолькоCLEAR,безпуска». ОтветпокаНЕполучен. Не выводить
разрешениенаCLEARиззапроса «еслизащитыготовы» и не использоватьпрошлыйCLEAR.
Когдапридёт«Да,CLEARипуск»:tools/run_observer_window_FOC_trial.py
--confirm-autonomous-powered --clear-once --outdir <новаяне существующаяпапка>.
Онсамвыполнит ровноодинCLEAR иодинSTARTтолькопослеготовыхживыхзащит;
не делать предварительныйCLEARдругимскриптом. Приответе«ТолькоCLEAR»
выполнятьтолькоего,STARTнельзя. ПокаJ1ON,повербанки,15ВON; ничего
переподключатьнепросили,командстендувэтомпроверочномэтапенеотправляли.

## 2026-11-17: подготовлен FOC5Гц/5с runner для1611/1612, действий стенду не было

Пользователь запросил FOC5Гцна5с с записьютоков,NIS,ADC иавтостопом,
спросилчто переключить. Подготовлен tools/run_observer_window_FOC_trial.py:
биндинг установленнойпары1611/1612, её точногоschema3decoder(1888Б),
прежнийограниченныйrun/heartbeat/RPCguard/STOP/core безредактирования.
АлгоритмFOCвыбирается клиентомвSAFE. Native5с иUno5с ограничители сохранены;
hostbackupSTOP12с,нормальныйконтрольостанавливаетпри любойзащите. CLEARпоумолчанию
не отправляется,нет автоматическогоповтора. ПослеOFF собираются1024БADC,
1888Бobserver,NIS/IdIq/поток/CPUIRQ/boot/SD сCRCиотдельнымихешами.

PCflowtests verification/trial_runner_20261117_r1/report.json прошли:
mocked success5000мс+schema3collect; BIEfalse/4001тактов/newRPCtimeout
блокируютSTART;runtimefaultостанавливаетбезповтора. Все сети замоканы,
hardwarecommands0. Не выдаватьsyntheticADC/modelobserverfixtures затокимотора.
FOC_trial_preparation_20261117.json содержитхешискриптов/тестов. Firmware/HMI
исходники неизменны;5605старыхфайлов проверены. Пределы4000/2мс/1,35А/
UPDATE2048 прежние; старыйполныйRUNdeadline5312 не подменятьOFF4000.

Последнееподтверждениефизики:платыповербанки,PC/SaleaeOFF,15ВON,J1OFF.
Следующийшагпользователя — включитьТОЛЬКОJ1черезsoftstart при закрытомстенде,
не нажимаяПуск/RESET. Послеподтверждения надо свежепроверитьшину/SD/RPC,
автоноль/OFF64/свободныезахваты. СамFOCпуск пользовательэтимсообщением
запросил, но дофизическогоподтвержденияJ1 иготовыхживыхзащит не запускать.
НовыйCLEAR отдельно не разрешён (последняяодноразоваяавторизацияпотрачена).
RPC неоднократнозависала впокое: если503/нетget,не делатьSTARTвслепую
и не превращатьподготовку вциклслучайныхпусков/перепрошивок.

## 2026-11-17: разрешённый CLEAR наконец отправлен ОДИН раз, без пуска; после него всё в покое без аварий

Пользователь подтвердил: J1OFF,мультиметр<20В,перезапиталТОЛЬКОUnoотповербанка,
Nucleo/15Вне трогал; явно попросил выполнить тот же одинCLEARбезпуска.
Связь восстановилась, но первые свежие статусы показывали34В,автоноль0/CPU0.
one_CLEAR_deenergized_after_Uno_boot_20261117_r1 остановился ДО команды,CLEAR0.
Дождались снижения показания34->21->20В; при20Вавтонольготов/3блока,
новыйOFF64расчётсамостоятельнопрошёл3811<=4000. Не ослаблялиbus/CPUгейты.

one_CLEAR_deenergized_after_Uno_boot_20261117_r2:passed=true,CLEAR1,
ACK_ACCEPTED отNucleo1612,resultcode1,первыйCLEARэтогосеанса,MOE0.
Предыдущие попыткиpowered_r1 иdeenergized_r1обеCLEAR0,безPOST/ретраев.
После16контрольныхстатусов+final:SAFE/PWM0/run_id0/arm0,UART/RPC0,
маскиactive/occurred0,transport0,badcnt/CRC0,SDHIGH/BIEtrue/configOK,
автонольready/3блока,OFF3811/4000,64случаяошибка0. Предел2мс,1,35А,
UPDATE2048 иисходникизащитбезизменений. START/ARM/softwareRESET/flash0.
acceptance.json ивсехеши сохранены; manifestlatestCLEARуказываетнаэтуприёмку.
Авторизация наодинCLEAR теперь ИЗРАСХОДОВАНА, новогоCLEARнеотправлятьавтоматом.

ВАЖНО: ДО этогоCLEAR маски уже были0/0 ивRAMне было старогопервогоснимкаSD,
OFFквалификациявыполнилась заново. Нельзя приписывать именноCLEAR исчезновение
прошлойUV/Break-защёлки или утверждать,чтоnativeRAMпережилаперезапиткуUno.
Старый17,7144мсSD полностьюсохранён НАДИСКЕ,хеш980e1f0676f232a4e867362b7fb346b18b4d6bb21b8fc92a37d2fa1b9bdc7ff4.
ПослеодногоCLEARпроверены все прежниезаписи,скопированныевpreserved_before.
НикакихсбросовNucleo агентнеотправлял,причинаповторногоnativeстарта не установлена.

Текущееподтверждённое:обе платынаповербанках,ПК/SaleaeOFF,15ВON,J1OFF,
шинапоследнийстатус13В,Пуска/RESETне было. FOCподШИМ1611/1612ещё
не проверен. Передсиловымэтапом сначалаживойpreflight,не использоватьстарые
проверки как доказательство текущейсвязи: RPC уже несколькораз зависалавпокое.

## 2026-11-17: пользователь разрешил один poweredCLEAR, но команда ещё НЕ отправлена из-за RPC503

На вопрос «одинCLEARбезпуска» пользователь ответил «да». Авторизация на
ровноодинCLEAR НЕ израсходована:one_CLEAR_powered_20261117_r1/report.json
CLEAR0/START0,ошибкаAPIstatus503 ДО POST,файлаCLEAR_responseнет.
Свежийпоследнийуспешныйpoweredpreflight:319–321В,SDHIGH,BIEfalse,
activeMCUV4/occurred1028,UART0,автонольready,OFF3811/4000.

WiFiSSHработает,bootLinuxb142708d...,HMI/routerслужбыrunning. Прямой
RouterClientGET также не ответил. Архивированыслужбы/журналы/ответы.
Один restartТОЛЬКОownedHMI выполнен(SIGTERMс проверкойUID,cwd,Restartalways),
не помог:status503/noresponse. Ни serialrouteclose/open,ни MCUreset,
ни flash вэтойпопытке не делали. Не повторять уже failedCOLD-vs-HMIпетли.

Пользователю отправлена asyncинструкция: выключитьJ1,дождатьсяпо мультиметру
<20В,перезапитатьТОЛЬКОUnoQотповербанка5с;Nucleo/15В/проводкуне менять,
J1оставитьOFF,ПК/Saleaeнеподключать. Подтвержденияэтогошага покаНЕТ.
Не утверждатьJ1OFFдо ответа. После ответа проверитьавтономнуюсвязь/boot,
сохранитьстарыйпервыйSD(17,7144мс) и затем вернутьJ1по штатномуsoftstart
с подтверждениемпользователя. Толькоприживомсвежемстатусе можно расходовать
тотжеодинCLEAR. Пуск НЕ разрешён текущим «да» — оно проCLEARБЕЗпуска.
5605старыхфайлов проверены по хешам,всеnewдиагностическиефайлы запечатаны.

## 2026-11-17: после J1 шина319–321В/SDHIGH, но MC_UNDER_VOLT и Break/BIE ещё блокируют пуск

Пользователь включилJ1черезsoftstart,15ВON,обе платыповербанки,ПК/SaleaeOFF,
Пуск/RESETне нажимал. ВыполненGET-onlypowered_before_FOC_20261117_r1:
20статусов/22,52с,449новыхответов,UART/RPC0,автонольready/3блока,
CPU64pass3811<=4000,предел2мс прежний; ADC/observerзахватысвободны.
Шина319–321В,температурныйguardpass,SDвсе20статусовHIGH/configOK.
Но mc_fault_current_mask4(MC_UNDER_VOLT ещёАКТИВНОпередаётся),occurred1028,
mc_fault5,SDbreak_irq_enabledfalse. Не называть это только сохранённой
UVзащёлкой и не объявлять защиты готовыми. failedchecksno_fault_latches
иSD_break_IRQ_ready. MODE/algorithmпокаVF/1: выборFOCне отправлялся.

Полный первыйSD320Б совпал с снимком доJ1 (17,7144мс,3693мсboot,MOE0).
SD_first_boot_unchanged.bin иJSON/логисохранены,старыехеши5605 ипоследняя
CLEARприёмка проверены; старыеотчёты не переписывались.
В этойпроверке CLEAR/START/ARM/RESET/flash/SWD=0. Для дальнейшего этапа
нужен явно разрешённыйодин штатныйCLEAR с повторной проверкоймасок иBIE;
не запускатьпри неполномвосстановлении и не повторятьCLEARнаугад.
Питание/подключения оставленыкакподтвердилпользователь;USBподHVне подключать.

## 2026-11-17: автономная связь/автоноль/CPU прошли; первый Break сохранён, до пуска BIE не восстановлено

Пользователь: обе платы на повербанках,ПК/Saleae отключены,15ВON,J1OFF,
Пуск/RESET не нажимал. Выполнены ТОЛЬКО GET,20статусов за22,66с;
CLEAR/START/ARM/RESET/flash/SWD=0. Uno1611/Nucleo1612 доступны,UART/RPC0,
449новыхпринятыхответов,перезапусков в интервале нет. Автонольready/3блока,
offsets2068/2066/2066/2068,spans32/30/34/25. CPU64pass,3811<=4000,
предел2мс не менялся. RecorderADC и observer свободны, свежестьтелеметрииpass.

autonomous_before_FOC_20261117_r1/report.json ОСТАВЛЕН failed: единственный
непрошедшийпункт SD_break_IRQ_ready. SDсейчасHIGH/configOK,но BIEfalse;
activeMCmask4(MC_UNDER_VOLT приJ1OFF),occurred1028(0x404).
ПервыйBreak записан на3693мсboot,MOE0,внеstartwindow. ПолныйPA6LOW17714,4мкс,
с обоимифронтами,безDMAerror/overrun/timeout. Сохранены320БSD_first_boot.bin,
всеJSON,логи,старыехеши5605 проверены. Нельзя путать с прежними63мксимпульсами.
PA4вэтомснимкеHIGH,НОпроводTP23->PA4ранее СНЯТ: это не сравнение двухточек,
не доказательство отсутствия импульса наTP23 и не доказанная причинаBreak.
Связь/автоноль/CPU подтверждены отдельно вreadiness_axes.json; защиты до
пуска не признаныготовыми. НовыйCLEAR вэтойпроверке не разрешали/не отправляли.
Следующийфизическийэтап — J1черезsoftstart при закрытомстенде,безПуска/RESET;
сначала свежаяпроверка шины/SD и только затем штатное восстановление защёлки.
ПодШИМ1611/1612 ещё не проверялись.

## 2026-11-16: один CLEAR на1611/1612 принят, UART/Break/MCSDK восстановлены в покое

Текущая задача пользователя: один штатный CLEAR без пуска,J1OFF,ПК,15ВON.
Первый one_CLEAR_idle_r1 завершился RPC503 до команды,CLEAR=0. ПрямойGET
тоже не отвечал; один restartownedHMI и router serialclose/open не помогли.
Пользователь затем подтвердил переподключение USBтолькоUno на5с. Новую
прошивку не ставили, softwareRESETNucleo не отправляли. До восстановления
сохранены nativeRAM32КБ/прямые GPIO/TIMрегистры. Прежние записи сохранены.

После восстановления RPC получен свежий статус1611/1612. CRCсчётчики
архивированы, подтверждён тихий интервал без прироста; затем выполнена
ровно одна POSTкомандаCLEAR, без retries. one_CLEAR_after_RPC_recovery_r1:
passed=true,CLEAR1,START/ARM/flash/RESET0,диагностикаACK_ACCEPTED.
Транспортная защёлка0,mc_bad_cnt0,CRC0,UART_hw0,активная/occurredмаски0.
SDHIGH,прямое чтениеBKE1/BIE1/MOE0,автонольready/3блока.16статусов после
CLEAR плюсfinal, RPCguardstable. РасчётOFF3811<=4000,64случая,ошибка0;
observer21035тактов,maxwall124,32мкс. Исходники/2мс/UPDATE2048/1,35А прежние.
5691старыйфайл проверен по хешам. Оба исходных failedотчёта установки и
первогоRPC503 не переписаны. Итог:observer_current_window_r1/CLEAR_RESULT_RU.md
иone_CLEAR_after_RPC_recovery_r1/acceptance.json. Manifestremaininglatch0.

ВНИМАНИЕ для дальнейшего анализа: после подтверждённого переподключения
Uno изменился также nativebootidentity(старыйCSR67108864,новый201326592).
Агент не сбрасывал Nucleo, причина смены сеанса не установлена. Нельзя
утверждать, что nativeRAM пережила восстановление: её копия до события
сохранена наПК. Новый nativeсеанс вновь самостоятельно прошёлOFF64/4000.
J1OFF,обе платы наПК,15ВON. Команд включениясилового/START не было.
FOC_start_ready=false: подШИМ новую версию не проверяли, шина сейчасоколо10В.

## 2026-11-16: 1611/1612 установлены, чтение обратно и OFF3811/4000 подтверждены

Пользователь подтвердил J1OFF/по мультиметру<20В/обе платы наПК,15ВON.
Uno2026111611 и Nucleo2026111612 записаны по одному разу, обе проверены
чтением обратно. hardware_install_r1: старая RAM32КБ/Flash/HMI/калибровка
сохранены. Ошибка эталона BIN (4нулевых gap-байта против FF у HEX) исправлена
по исходному sealedHEX; не подгонять эталон по readback. HEX_padding_audit
и исходный ошибочный эталон/первый failedreport сохранены. Native повторно
не прошивалась. Калибровка без изменений.

observer_current_window_r1/installation_verified_r1/report.json:
installed_verified=true,OFF_CPU_passed=true,64случая,fast3811<=4000,
observer21512тактов≈126,54мкс,maxwindow127,12мкс. BKE/BIE1,MOE0,SDHIGH,
автонольready/3блока. В20статусах/22,08с RPC0/CRC0/seq0,новых ошибокнет.
5605старыхфайлов проверены по хешам. START/CLEAR/ARM/ручнойRESET=0.
Программные рестарты относятся только к штатной записи/верификации образов.

ВНИМАНИЕ: строгий post_install_idle_r1/report.json ОСТАЛСЯ failed:
mc_transport_fault=7(UV3_LINK_TIMEOUT),mc_bad_cnt=1,uno_rx_hw_errors=2,
все постоянны в20проверках. Первичный источник2UART_hw ошибок не установлен.
Не объявлять весь UART абсолютно чистым и не стирать эту историю ради pass.
Установка/расчёт подтверждены отдельно; FOC_start_ready=false,strict_idle=false.
Нового CLEAR пользователь не разрешал в этой записи, он не отправлялся.
Пределы OFF4000/RUN5312/возраст2мс/UPDATE2048/1,35А прежние.
J1OFF,обе платыUSBПК,15ВON,без пусков. Новую версию подШИМ не проверяли;
снижение физического NIS и достоверная скорость не доказаны.

## 2026-11-16: NIS разобран офлайн; кандидат1611/1612 собран, НЕ установлен

Запрос: без пусков/наугад-прошивок,4000тактов/2мс и защиты сохранить.
В этом сеансе НИКАКИХ команд стенду, GET/RPC/CLEAR/START/RESET/flash не было.
На платах по-прежнему Uno1609/Nucleo1606; последнее состояние после визуального
повтора — ШИМ0/SAFE, J1/15В включены, платы на повербанках. Это прежнее
подтверждённое состояние, нового чтения железа не делали.

artifacts/live_bench_20261116/observer_current_window_r1/RESULT_RU.md:
первый NIS42,408 на шаге503 воспроизводится поe²/S; остатки≈0,096/0,098А,
σ≈0,021А. ADC/observer input epochs совпадают; maxage712,76мкс<2мс.
В соседнем ADC-захвате scatterσ0,0365/0,0523А, но эти12кадров начинаются
позже входного кадра первого отказа, не считать их точным EKF replay.
Найдено нефильтрованное прореживание токов16кГц→1кГц. Среднее напряжение
интервала + мгновенный конечный ток само по себе корректно; не называть
это доказанной ошибкой уравнения или единственной физической причиной.

Кандидат1611/1612: среднее16реальныхтоков с центром окна, согласованный
интеграл напряжения между центрами и отдельный RK4прогноз на конец окна;
rawконтур/1,35А не фильтруются, EKF/Q/R/NIS25 неизменны. Пропуск окна
отклоняется вместо растяжения последней1мс истории на2мс. Новая traceABI3
показывает центр/первыйADC/count/forecastdt; старыеABI2 читаются.
209 hostchecks,64OFFcases с fakeclock (НЕ измерение тактов),9modelcases
на вариант. При simulatedADC±16counts peakNIS244,66→4,88, validпосле1с
26,45→100%, speedRMSE3,53→0,73rpm. Физический4978step replay невозможен
по12decimatedrow+12ADC, единственность причины/реальная скорость не доказаны.
Постоянный bias/ошибкаRs могут давать низкийNIS при неверной скорости.
Оба образа собраны, loadercheckUnoOK,5605старыхфайлов проверены по хешам.
Пределы OFF4000/RUN5312/возраст2мс/UPDATE2048/ток1,35А неизменны.
Перед будущим START после установки обязательно настоящее измерение OFF64
с прежним пределом4000. Пока не просить новый пуск/RESET ради этих PCтестов.


## 2026-11-16: пользователь подтвердил ровное вращение в визуальном повторе

На вопрос именно о FOC_visual_repeat_r1/run_id2 пользователь ответил
«Да, вращался ровно». Подтверждение сохранено отдельно в
rpc_hmi_admission_r1/FOC_visual_repeat_r1/operator_observation.json;
исходный report.json и его хеши не изменялись. Физическое вращение
подтверждено визуально, независимого измерения скорости нет.
Один FOC5Гц/5000мс с автостопом, без нового CLEAR/RESET/flash; новых команд
после подтверждения не отправляли. Пределы4000/2мс и захваты сохранены.
Это подтверждает вращение/автостоп в этом опыте, но не достоверность оценки
скорости: в первом полном захвате NIS терял валидность; cached raw записи
визуального повтора нельзя выдавать за новый диагностический эксперимент.

## 2026-11-16: визуальный повтор FOC выполнен БЕЗ перезапуска и БЕЗ CLEAR

Пользователь оспорил необходимость новой записи после «повтори ещё раз».
Предыдущее требование выключитьJ1/перезапустить обе платы ОТМЕНЕНО для
визуального повтора; не просить новый boot лишь ради наблюдения вала.
Ранее guard первого сеанса относился к уникальности raw записи, а не к
аппаратному запрету повторного пуска: ma_native_prepare при MOE0/IDLE
проверяет прежний профиль, переинициализирует регулятор/наблюдатель и
позволяет новый запуск. Исходный диагностический runner не редактировался.

tools/run_foc_visual_repeat.py валидирует успешный прошлый прогон и его
хеши, совпадение CRC-boot/модели/run_id, сохранённую OFF64-проверку3618<=4000
того же boot и все текущие живые защиты. Нельзя подставлять старую OFF64
после смены boot/модели. RPC guard, SD/BIE, маски,1,35А/2мс и существующий
deadline полного RUN-пути5312 не изменялись.18 негативных PC gate cases
и mocked full-flow success/SD-refusal проверены без сетевого доступа к стенду.

Один реально разрешённый визуальный повтор: FOC_visual_repeat_r1,
START1/ARM1/CLEAR0/RESET0/flash0,run_id2,autostop5000мс,SAFE/PWM0,
RPC/send0,активная и защёлкнутая маски0. Только SET FREQ5, штатный ARM/
START с runlimit5 и STOP cleanup; без изменения модели/прошивок.
Первая запись цела (все хеши analysis_files_sha256 совпали), первыйSD
сохранён. Текущие cached rawADC/observer строки не объявлялись новым
экспериментальным захватом; повтор предназначен для визуального наблюдения.
Физическое вращение пока не подтверждено — вопрос пользователю отправлен.
Питание и подключения фактически не менялись: J1/15В ON,повербанки,
ПК/Saleae отключены. Новых пусков без запроса не делать.

## 2026-11-16: один FOC5Гц/5с выполнен; пользователь запросил повтор

Явно разрешённый один CLEAR восстановил защиты; один ARM/START, без retry.
rpc_hmi_admission_r1/FOC_trial_r1: completed5s, Uno_limit_done=true,
run_id1/run_elapsed5000/run_reason1, PWM0/SAFE, аварийные маски0,
RPC/send/CRC/UART0. Native/Linux boot неизменны. CPU/IRQ,1024Б ADC,
1832Б observer и первый SD полностью получены, CRC/хеши проверены.
SD_before/after совпадают с сохранённым до CLEAR320Б снимком63,4мкс.

Результат пятисекундного выполнения не равен квалификации наблюдателя:
2120 valid/2858 invalid из4978 шагов, первая потеря на шаге503 из-за
NIS42,408>=25; финальная скорость invalid. Последнее токовое окно178мс
(меньше периода200мс при5Гц), номинальный RMS0,380/0,344/0,366А,
пики этого окна0,720/0,691/0,700А; независимой калибровки масштаба нет.
OFF64 fast3618 при неизменном пороге4000. RUN отчёт полного пути4352
такта, его существующий deadline5312 не изменён; не выдавать4352 за
прохождение4000. Max estimate age712,76мкс при неизменном2мс.

На вопрос о физическом вращении пользователь ответил «повтори еще раз»:
визуальное вращение НЕ подтверждено, не вписывать «вращался ровно».
Повторный START/CLEAR не отправлялись. Проверенный runner требует первый
run_id этого boot и OFF64/чистые raw record; старые raw записи заморожены.
Не подделывать failed-retry proof для успешного прогона, не обходить guards.
Для нового диагностического сеанса: J1 OFF, мультиметр<20В, отключить питание
ОБЕИХ плат от повербанков на5с и вернуть в те же повербанки.15В оставить
включёнными; J1 покаOFF, ПК/Saleae не подключать, проводку не менять.
Одна Nucleo RESET не сбросит Uno run_id1 и не удовлетворит текущему runner.
Перепрошивки не требуется. После подтверждения проверить свежую загрузку,
автоноль/SD/OFF64 перед повтором. Предыдущее разрешение CLEAR уже израсходовано.

## 2026-11-16: J1 ON, powered preflight пройден по шине/связи; START заблокирован

Пользователь подтвердил J1 черезsoft-start/15В ON/повербанки/ПК и Saleae OFF,
без START/RESET.6 GET: шина322–323В, RPC/send0, UART/CRC/drop0,117 новых RSP,
автоноль ready1/stable3, CPU3618/4000. SD HIGH/config_ok, но BIE0:
до Пуска при MOE0 вне start-window сохранён PA6 LOW63,4мкс. Полный320Б
SD_before_CLEAR.bin и декодированный /api/bkin-trace сохранены в
rpc_hmi_admission_r1/powered_preflight_r1; CRC/полнота записи подтверждены
декодером, DMA/sampling/overflow ошибок нет. TP23→PA4 ранее снят, его HIGH
не интерпретировать как доказательство отсутствия импульса на STEVAL.
Активная маска0, осталась occurred_mask4/MC_UNDER_VOLT (mc_fault/bp_fault5).

START/CLEAR/ARM/RESET/flash=0; FOC_start_ready=false. Требуется отдельное
разрешение на один штатный CLEAR с проверкой восстановления всех защит,
затем уже согласованный FOC5Гц/5с только при готовности. Пределы4000/2мс/
1,35А/2048 и старые записи сохранены. Питание/подключения менять не надо.

## 2026-11-16: автономная проверка перед FOC пройдена, J1 ещё OFF

Пользователь перевёл обе платы на повербанки, отключил ПК/Saleae, оставил15В
ON/J1 OFF, без START/RESET. По Wi-Fi192.168.1.138:8080 проверены8 ответов:
RPC timeout/send0, UART/CRC/drop0,158 новых RSP, native tick98775→106775мс.
Автоноль ready1/stable3, SD HIGH/BIE1/config_ok/capture_running, CPU3618/4000,
OFF64 без ошибок. Пара Uno1609/Nucleo1606, профиль CRC1354279011;
после питания выбран исходный алгоритм1, FOC ещё не выбирался/не запускался.
Активная маска аварий0, транспортная ошибка0; сохранена маска4
MC_UNDER_VOLT при выключенном J1 (mc_fault/bp_fault5). CLEAR не отправлялся.
Шина9–10В; START/CLEAR/ARM/RESET/flash=0. Пределы4000/2мс/1,35А/2048 прежние.

Отчёт rpc_hmi_admission_r1/autonomous_preflight_r2/report.json.
r1 сохранён FAILED: первый ответ нового Linux-сеанса содержал ещё неполные
страницы (RX2, CPU0/OFFcases0, quality отсутствовала), затем страницы пришли
сами без сбросов/команд. r2 прошёл все прежние строгие проверки.
FOC_start_ready=false до питания шины, выбора FOC и полного восстановления
защит. Следующий физический шаг: только J1 через штатный soft-start при
закрытом стенде;15В/повербанки/проводку не менять, START/RESET не нажимать.
После подтверждения — свежая проверка шины/SD/защит; автоматического пуска
на текущем этапе не было. Старые захваты не стирать.

## 2026-11-16: исправленный HMI прошёл1100с RPC в покое; без пусков

Последний авторитетный отчёт — rpc_hmi_admission_r1/acceptance.json и
RESULT_RU.md. Linux HMI установлен, прочитан обратно; оба MCU этим обновлением
не прошивались/не сбрасывались. MainPID HMI4670 и root-router560 стабильны.
1101,015с,1087 HTTP ответов, maxHTTP0,844с; новых RPC/send timeout нет,
route_failures147 неизменен. Native tick12606961→13706461мс,21921 новых
принятых RSP; автоноль готов, CPU3618/4000. В тесте reconnect/reset=0.
16 параллельных HTTP GET также прошли за2,812с. Все5506 старых файлов и
sealed source1609 проверены по хешам; ещё66 новых файлов захватов запечатаны
в new_capture_hashes.json. Калибровка и server.py повторно сверены на Linux.

Подтверждённые исправления: short-lock Bridge1609; Linux RouterClient включает
mutex/connect/send/recv в монотонный deadline и объединяет только текущие
одновременные GET, без кеша завершённых ответов и повтора START/CLEAR.
Точный первичный байтовый/драйверный источник отдельного UART отказа пока
не доказан. Прежние FAILED/partial отчёты сохранены, не переименованы вPASS.

Состояние: платы наПК, J1 OFF,15В ON; Uno1609/Nucleo1606. START/CLEAR/ARM=0.
Пределы4000/2мс/1,35А/2048 прежние. Native LINK_TIMEOUT7 и UART-error1
не очищались. RPC idle квалифицирован; FOC_start_ready=false, пятисекундный
FOC не проверен. Силовое автоматически не включать, новых пусков нет.

## 2026-11-16: Linux HMI admission/coalescing исправлен и установлен; идёт длительный тест

На ПК и отдельно на Linux Uno воспроизведено превышение deadline в старом
RouterClient: timeout30мс возвращался через172мс, потому что ожидание mutex
не входило в timeout. Теперь очередь/соединение/send/recv используют общий
монотонный deadline каждой попытки. Параллельные чистые GET делят только
текущий незавершённый запрос; завершённые ответы не кешируются. Любая другая
команда ставит границу между чтениями; START/CLEAR не повторяются автоматически.
Моторные guards и весь код после RouterClient побайтно прежние.

Пакет rpc_hmi_admission_r1: PC+Linux fixtures прошли,189 command guards и35
local-stop regressions прошли с mock backend. Linux server.py установлен
атомарно, прочитан обратно, SHA256 ba03ee5ae0153f70003c06be54f49148eed89954b75e3137e7c30542e23d1c79;
калибровка прежняя a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
Этим шагом оба MCU не прошивались и не сбрасывались. Canonical web_hmi/server.py
содержит тот же исправленный RouterClient, остальные пользовательские изменения
не заменялись.

Прямой owned router без UART-прокси:713 GET за12мин плюс80 параллельных GET,
без отказа; основной router восстановлен, временный завершён. Это проверка
транспорта, не двигателя.16 одновременных HTTP GET новой HMI прошли за2,812с.
Идёт long_idle_r1 на1100с с root-router и фоновой диагностикой, без reconnect/
reset/команд; при первой новой ошибке остановится. UART first-byte cause
пока НЕ доказан, предыдущие failed-отчёты не переписаны.

Платы наПК, J1 OFF,15В ON. Uno1609/Nucleo1606; Nucleo flash сверена снова,
MOE=0, tick растёт, шина~10В. Пределы4000/2мс/1,35А/2048 сохранены.
Старые LINK_TIMEOUT7/UART-error1 не очищены, FOC_start_ready=false.

## 2026-11-16: RPC1609 в покое всё ещё имеет воспроизводимый отказ; пуски запрещены

long_idle_r4 завершился FAILED: 246 ответов, затем HTTP timeout на374,8с.
Отчёт сохранён. RAM1609 снята без halt/reset: bridge/read/write/control
mutex свободны, updater жив. Следовательно, исправление короткой блокировки
подтверждено, но первичный отказ связи им НЕ устранён.

Изолированный программный UART-прокси и пользовательский router0.5.3
сохраняют точные байты обоих направлений; главный router временно закрывает
только свой serial port и восстанавливает его в finally. MCU не сбрасываются.
wire_isolation_r1: после37 успешных GET потерян ответ наGET39; Linux передал
валидный запрос после ACK регистрации344. В Go stack decoder ждёт следующий
код сообщения, а не остаток большой строки. Exact-wire replay реальным
RPClite наПК прошёл64 разбиения/порядка polling; UART/kernel в нём mocked.

wire_isolation_r2: 758 GET/12мин без нового timeout; исходный passed=false
из-за отдельных NUL при подключении сохранён как есть. Это не доказательство
исправления. wire_isolation_r3 проверяет стык ACK/GET с задержкой передачи
250мс, в пределах неизменного1500мс RPC timeout. При отказе снимаются
decoder, Serial2, потоки и UART ISR до восстановления порта.

Установлены Uno2026111609/Nucleo2026111606. Nucleo не перепрошивалась и
не сбрасывалась. J1 OFF/15В ON/платы наПК; START/CLEAR/ARM=0.
Старые LINK_TIMEOUT7/UART-error1 не очищены, FOC_start_ready=false.
4000тактов/2мс/1,35А/2048 и старые захваты сохранены.

## 2026-11-16: Uno1609 установлена, разбор RAM завершён; идёт длительный OFF RPC-тест

RAM1607 разобрана по DWARF точного loader ELF и адресам llext. Updater bridge
ждал bridge_mutex0x200196b0, owner — bridge_service_worker в refreshProvided/
RpcCall::result. Main и Nucleo продолжали работать. Mutex control/read/write
свободны; response_timeouts1201. Это подтверждённая блокировка updater,
не доказательство бесконечного CPU-deadlock или конкретной повреждённой байтовой
последовательности. Один router close/open восстановил1607 без MCU reset;
первичный источник отказа соединения пока не установлен.

Uno2026111609 записана и проверена чтением обратно: bridge_mutex отпускается
ДО ожидания регистрации.18 host-сценариев, baseline blocked602/admitted0,
candidate blocked0/admitted602. Nucleo1606 не прошивалась/не сбрасывалась.
Калибровка сохранена, START/CLEAR/ARM=0, J1 OFF/J4 ON/обе платы на ПК.
Пределы4000/2мс/1,35А/2048 и motor guards не менялись.

Найден отдельный false-positive host guard: native mc_good_cnt насыщен65535.
Для прогресса используется существующий32-битный uno_rx_count, который растёт
только при приёме RSP. Снижение старого счётчика, новый RPC timeout, stale300мс,
остановка кадров и смена boot продолжают блокировать.13 тестов прошли;
сетевой доступ в mocked runner запрещён, его START в stdout — симуляция.

Архив rpc_short_lock_r1. Идёт long_idle_r4,1100с GET-only без reconnect/reset/
CLEAR/пусков. r1/r2 остановились на старых transport7/UART-error1 после записи;
r3 обнаружил насыщение счётчика, failed отчёты сохранены. r4 квалифицирует
только RPC, а не готовность двигателя: эти старые аварии не очищены и должны
оставаться неизменными. Первый новый отказ завершает тест, без retry.
5506 старых файлов защищены хешами; DIAGNOSIS_RU.md содержит границы вывода.

## 2026-11-16: перед новым FOC найден повторный RPC timeout В ПОКОЕ; пуск не выполнялся

Пользователь запросил подготовку FOC5Гц/5с с RPC/CPU/IRQ/токами/автостопом.
Платы оставались на ПК, J1 OFF,15В ON. Добавлен wrapper для1607/1606,
с теми же guards и release observer decoder. Подготовка FOC_preparation_r1
остановилась на тайм-ауте HTTP GET; direct RouterClient GET тоже не ответил.
Новых START/CLEAR/ARM/flash/reset=0, питания и проводки не меняли.

Сохранены processes/router journal/direct RPC; без service restart и
переподключения router. Uno доступна ADB. Пассивный OpenOCD dump без halt/
reset/write:786432Б SRAM Uno, файл Uno_RAM_nonatomic.bin; снимок неатомарный.
CORE_AFTER=running, считанные CFSR/HFSR=0; это не исключает зависший поток.
Нельзя объявлять прежний OFF route repair устранением всех RPC отказов.

Пассивный ST-LINK HOTPLUG подтвердил прежний образ Nucleo1606, tick7539378→
7539828мс, шина10,02–10,05В, MOE0; Nucleo не зависла и ШИМ выключен.
5417 старых файлов проверены целыми. Пределы4000/2мс/1,35А/2048 прежние.
Архив rpc_route_recovery_r1/idle_timeout_diagnosis_r1/report.json.

Сейчас RPC не готова, FOC_start_ready=false. Пользователю указано оставить
обе платы на ПК,15В ON,J1 OFF; на повербанки/силовой этап пока не переходим.
Следующий шаг — разбор сохранённой RAM/потоков Uno до перезапуска, без пуска.
Предыдущая успешная проверка восстановления маршрутов сохранена и не переписана.

## 2026-11-16: Uno1607 установлена, OFF-восстановление RPC проверено без сброса Nucleo

Пользователь выбрал продолжать FOC/RPC без скалярного отката, без пусков.
Текущее подключение: обе платы на USB ПК, J1 OFF,15В ON.
Uno2026111607 записана один раз и проверена чтением обратно. Nucleo1606
не перепрошивалась и не сбрасывалась; повторное чтение flash совпало.
Калибровка сохранена. START/CLEAR/ARM=0.

Исправлено восстановление потерянных router-маршрутов: старые локальные
ready-флаги не означают сохранённую регистрацию на Linux. Существующие
callback обновляют регистрацию раз5с с началом при PWM OFF, без reset,
перезаписи callback, очистки захватов и автоматического пуска.
Для установленного router0.5.3 код отдельно учитывает error5 EXISTS;
это не подтверждение владельца и не разрешение пуска. Guards не менялись.

Архив artifacts/live_bench_20261116/rpc_route_recovery_r1.18 host-сценариев
и сборка прошли. Один реальный router close/open: четыре временных HTTP503,
затем восстановление примерно2,016с после команды, подтверждённая новая
регистрация0→1. Далее20 стабильных GET, новых RPC/UART ошибок нет, автоноль
готов, SD HIGH/BIE1. Native tick3427461→3459961мс, без сброса.
OFF CPU3618/4000. Пределы2мс/1,35А/2048 прежние.5417 старых файлов целы.
Локальный idle_qualification_r1 завершился ДО reconnect из-за неверного
ключа sd_high в скрипте; сохранён как failed, исправленный r2 прошёл.

Подтверждён только OFF repair. Причина первоначального RPC обрыва под ШИМ
не установлена; пятисекундный FOC и наблюдатель пока не квалифицированы.
Повтор FOC остаётся незавершённой задачей, но последняя инструкция пользователя
запрещает новые пуски. Силовое не включать автоматически, CLEAR не разрешён.
Подробности acceptance.json, RESULT_RU.md и idle_qualification_r2/report.json.

## 2026-11-16: обе платы на ПК, USB-проверка1605/1606 без пуска пройдена

Пользователь уточнил: раньше обе платы питались от ОДНОГО повербанка;
теперь обе подключены к ПК. J1 остаётся выключенным,15В включены.
Общий источник мог прервать питание Nucleo при переподключении Uno,
но этот механизм и причина первоначального обрыва RPC НЕ доказаны.

USB: Uno3880458060/COM10, Nucleo COM13. GET подтверждает1605/1606,
SAFE/PWM0/run_id0, шину10В. Native flash прочитан HOTPLUG и полностью
совпал с sealed1606;32КБ текущего RAM сохранены. Это уже новая загрузка,
а не восстановленный сырой захват потерянной первой попытки FOC.

Архив clear_recovery_r1/USB_recheck_after_shared_bank_r1. В RPC_read:
20 GET прошли, max HTTP1,172с, good_frame+515, RPCresponse12/send0
без роста, автоноль готов во всех ответах, SD HIGH, CPU3618/4000.
Прямой RPC GET сохранил7427Б JSON (~645мс идеального115200baud),
текущий send deadline2000мс; обрезка ответа здесь не подтверждена.
Это проверка в покое; прежний сбой при ШИМ не воспроизведён и не исправлен.
START/CLEAR/RESET/flash=0. Пределы4000/2мс/1,35А/2048 прежние.

Повтор FOC остаётся запрошенным, но не выполнен. Пользователь написал
«вернул ... по прошивке»; асинхронно уточнено, требуется ли продолжить
FOC/RPC или откатить рабочий скаляр. Другой образ без выбора не записан.
Нового разрешения на CLEAR нет; предыдущий единственный CLEAR израсходован.

## 2026-11-16: FOC1606 стартовал, RPC потеряна после3с; повтор запрошен, пока НЕ выполнен

Пользователь разрешил один CLEAR и один FOC5Гц/5с при готовых защитах.
run_clear_recovery_trial.py --clear-once: один CLEAR восстановил guards,
выбран algorithm2, native command mode6. Один START принят, наблюдались
PWM1/run_id1, elapsed3009мс, без algorithm/MC fault в последнем ответе.
Потом GET/RPC перестали отвечать. Подтверждения полного5с/автостопа нет,
runtime/ADC/observer записи не получены. Report.passed=false не переписан.
Архив clear_recovery_r1/powered_FOC_NIS_5Hz_r1. Пользователь сказал «ну он
и стоял вроде как», затем явно запросил один повтор «я смотрю на вал».
Физическое вращение НЕ подтверждено; повторный START пока0.

STOP/host backup/final STOP пытались выполниться, HTTP timed out; один
дополнительный safety STOP также без подтверждения. Direct RouterClient
STOP/get через SSH не ответили. Пользователь по запросу выключил только
J1,15В и питание плат оставил. Linux/SSH живы. До recovery сохранены HMI
логи441306Б и journals/процесс/thread сведения. Один owned HMI restart
не восстановил связь. Один Linux router serial close/open не помог,
GET вернул явное method get not available. MCU reset/flash при этих шагах0.
HMI_recovery_r1 — только сбор данных, restart НЕ исполнился из-за локальной
ошибки embedded NUL; реальный единственный restart в HMI_recovery_r2.

Затем пользователь по запросу переподключил ТОЛЬКО Uno к тому же повербанку,
Nucleo/15В не трогал. GET восстановился, PWM0/bp outputsOFF подтверждены;
J1 остаётся OFF. Но native uptime тоже сбросился: before_START472821мс,
после восстановления34459мс; good_count снова500, OFF64 boot probe снова
вместо runtime record, ADC/observer empty. Значит Nucleo тоже перезапускалась
между последним RUN ответом и восстановлением; момент/причина не установлены.
Early boot CRC1812657868 и retained_sequence1 совпадают при полной потере
питания: они НЕ доказывают непрерывность. Повтор не запускать по старому
run_id0 или совпавшемуCRC, не приписывать пустой новый record первому пуску.
Сырые захваты первой попытки восстановить из свежего RAM уже не удалось.

after_Uno_coldboot_r1 содержит18 свежих статусов после двух startup timeout,
прошивки1605/1606, PWM0, новая Linux загрузка, CPU3618/4000, J1 OFF/шина20→ниже.
recovery_analysis.json фиксирует границы доказательств: полный5с не проверен,
user rotation uncertain, native reboot observed, cause unknown.3679 старых
файлов и164 release sources проверены целыми. Прошивки/защиты4000/2мс/
1,35А/2048 не менялись, новых CLEAR и START не было.

Текущее внешнее условие: J1 OFF,15В ON, обе платы на повербанках, USB ПК/
Saleae OFF. Повторный bounded FOC запрошен и остаётся незавершённой задачей;
не отменён. Асинхронно задан вопрос: платы на двух разных повербанках или
двух выходах одного? Нужно исключить общий перезапуск питания/потерю захватов.
Ответ пока не получен. До новой свежей проверки и включения J1 пользователем
никакого START; прежнее разрешение на один CLEAR уже использовано.

## 2026-11-16: J1 ON на1605/1606, до FOC записан Break63,8мкс; START=0

Пользователь подтвердил J1 через soft-start/J4 ON/повербанки/USB-Saleae OFF,
Пуск/RESET не нажимал; запросил проверку шины и защит перед FOC5Гц/5с.
verify_clear_recovery_autonomous.py --rpc-baseline --powered-preflight,
архив clear_recovery_r1/powered_before_FOC_r1, только GET20ответов.
Шина322–323В, SAFE/PWM0/run_id0/ARM0. RPC12/send0 без роста, guard ready,
UART/CRC/sequence/transport0, автоноль готов, CPU3618/4000, профиль prior
и ADC/observer recorder empty checks пройдены. Пределы4000/2мс/1,35А/2048 прежние.

Первый Break до START при MOE0/start_window0: PA6 LOW63,8мкс, оба фронта
полностью записаны. SD_before_START.bin320B SHA66b42b56ccb791b71d9c523151f1de62ac95346827c3be2aafc2aa3499e8ff2b,
JSON waveform/snapshots сохранены. SD сейчас HIGH/config_ok1, но BIE0/
capture_running0, mc_fault5, retained mask current0/occurred4. Failed checks
только no_fault_latches и SD_break_IRQ_ready. PA4 не локализует источник:
TP23→PA4 ранее снят, подключение не подтверждено. Не объявлять импульс
следствием FOC или доказанным дефектом IPM: ШИМ не включался.

3668 старых файлов и164 release sources проверены без изменений.
CLEAR/START/ARM/RESET/flash/SWD=0. Общая готовность START не подтверждена.
Нужно отдельное явное разрешение на один штатный CLEAR и условный один
FOC5Гц/5с с NIS ADC capture/автостопом, только после готовых защит.
Последний разрешённый CLEAR был в предыдущей USB-загрузке и израсходован.
Питание/проводку менять не требуется. Не выполнять повторные сбросы наугад.

## 2026-11-16: автономная1605/1606 перед FOC пройдена, J1 OFF

Пользователь подтвердил повербанки, USB ПК/Saleae отключены, J4 ON/J1 OFF,
без Пуска/RESET. Только GET. Первый verify_clear_recovery_autonomous запрос
тайм-аут8с сохранён в autonomous_before_FOC_r1; затем TCP8080/2222 доступны,
сервер ответил. Никаких рестартов служб/питания/прошивки для восстановления
не выполнялось. Второе полное окно в autonomous_before_FOC_r2 пройдено.

20статусов за28,625с: версии1605/1606, SAFE/PWM0/run_id0/ARM0, шина10В.
Свежая автономная загрузка Linux/native, без перезапуска в окне. Good+565,
rejected0, UART/CRC/sequence/transport0; RPC response12/send0 постоянны,
baseline guard ready=true/failure=null. Причина12 старых RPC тайм-аутов
по этому окну не установлена; новых не возникло.19/19 check=true.

Автоноль ready1/stable3 во всех20, offsets2069/2066/2066/2069, spans32/32/30/30,
attempts3. CPU3618/4000, OFF64/fault0/meter_errors0. Профиль prior128/CRC1354279011,
native NIS ADC trigger подтверждены. SD HIGH/BIE1/config_ok1/capture_running1,
первого Break нет. ADC/observer и first CLEAR record пусты по новой загрузке
и состоянию приёмников; SWD/RAM на повербанках не читали. Сохранённый MCSDK
UNDER_VOLT mask occurred4 при J1 OFF остаётся, START readiness не заявляем.

Старые файлы/source hashes проверены, первый failed report не переписан.
START/CLEAR/ARM/RESET/flash/SWD=0, защиты4000/2мс/1,35А/2048 прежние.
Следующий операторский этап: включить только J1 через штатный soft-start,
оставив повербанки/J4 ON/USB-Saleae OFF; Пуск/RESET не нажимать. Затем
свежая проверка шины/SD/защит перед согласованным FOC5Гц/5с. При защёлке
нужен отдельно разрешённый CLEAR, прошлый один CLEAR уже израсходован.

## 2026-11-16: FOC5Гц/5с на1605/1606 подготовлен; ожидаем повербанки при J1 OFF

Пользователь запросил следующий FOC5Гц/5с с NIS ADC trigger/автостопом и
инструкцию переключения;4000/2мс/защиты/историю сохранять. Пока только
офлайн-подготовка, без обращений к платам/команд. Последняя подтверждённая
конфигурация остаётся обе платы USB ПК/J4 ON/J1 OFF, после одного CLEAR
Break/UART восстановлены, затем снова UNDERVOLT при10В. Повторный CLEAR
этим запросом явно не разрешён, при необходимости запросить отдельно.

Созданы run_clear_recovery_trial.py и verify_clear_recovery_autonomous.py:
привязка к установленным1605/1606, их HMI decoder и сохранение общего RPC
guard между этапами; bounded5с, native NIS ADC trigger, CPU4000/estimate2мс
и прежние protections без изменений. prepare_clear_recovery_trial.py прошёл
офлайн: firmware/source/artifact hashes,164release source,3656 прежних файлов,
reject другойпары, правильные driver/boot/collector bindings, bounded5с,
сохранение firstSD. Отчёт clear_recovery_r1/FOC_trial_preparation_r1/report.json.
Это не свежая квалификация автономной/силовой готовности, физический пуск
не выполнялся. Первый FOC на1606/NIS ADC delivery ещё предстоит проверить.

Следующее действие оператора: при J1 OFF перевести обе платы с USB ПК на
повербанки с паузой5с без питания при смене; снять USB ПК/Saleae,15В оставить,
двигатель/шлейф/датчики/проводку не менять, RESET/Пуск не нажимать.
J1 пока OFF. После подтверждения сначала verify_clear_recovery_autonomous.py
--rpc-baseline в новом output; лишь после автономной проверки переходить
к включению J1 через soft-start и свежей проверке силовой шины/защит.

## 2026-11-16: один CLEAR1606 принят при двух TX кадрах; Break/UART восстановлены, затем UNDERVOLT при J1 OFF

Пользователь разрешил один штатный CLEAR без пуска, J1 OFF/обе платы ПК/J4 ON.
tools/clear_recovery_idle_once.py выполнил ровно один POST CLEAR; START/ARM/
RESET/flash/SWD=0. Архив clear_recovery_r1/one_CLEAR_idle_r1. RPC baseline0/0
стабилен, тот же boot, в конце PWM0/run_id0/estop0, шина10В.

Новая запись CLEAR: ACK_ACCEPTED, tick2133711, seq131, TX head215602/tail215600,
pending2/active1, hard_error0/late0, started2133710; SD HIGH/MOE0/BIE1/SR95.
Реальные MCSDK masks в момент CLEAR current0/occurred4, state11 FAULT_OVER.
Это подтверждает успешный CLEAR при исправной непустой TX; старый helper
на таком снимке возвращает false. Не переносить это как доказательство
точного gate прошлого отказа1604: там TX snapshot отсутствует.

После CLEAR transport7→0, bad_count1→0, новые UART/CRC/sequence/RPC ошибки0.
Break: SD HIGH/BIE1/config_ok1/capture_running1 стабильно, первого Break нет.
MCSDK прошёл ACK: шесть sampled ответов fault0/masks0; затем после ~9с
от первого sampled fault-free снова записал reason8/state10/masks4/4 при
шине10В/J1 OFF. Поэтому общий report.passed=false/MCSDK_ready=false оставлен
без изменений: CLEAR принят и снял старую аварию, но позднее появилось
новое UNDERVOLT. Это не отказ MCSDK принять ACK, новый CLEAR не отправлялся.
accepted_then_UNDERVOLT_review.json фиксирует обе стадии и ограничения
временной оценки по опросам, не выдавая их за IRQ timestamp.

3640 прежних файлов/flash-RAM-install reports сохранены, SD первой записи
не менялся, source/защиты4000/2мс/1,35А/2048 не менялись. Автоноль ready1.
Пусковая готовность НЕ подтверждена; состояние остаётся обе платы ПК,
J4 ON/J1 OFF. Разрешение на один CLEAR израсходовано. Не повторять CLEAR
или START автоматически. Для силового этапа нужна отдельная подготовка
питания и свежая проверка; текущий запрос был строго без пуска.

## 2026-11-16:1605/1606 записаны/readback пройден, OFF CPU3618/4000; transport latch7 сохранён

Пользователь подтвердил J1 OFF, метр<20В, обе платы USB ПК, J4 ON и разрешил
прошивку/readback/OFF расчёт, без пусков/ослабления4000/2мс/защит/удалениязахватов.
В clear_recovery_r1/hardware_install_r1 выполнено по одной записи Nucleo/Uno,
обе readback verified. Native113848B SHA510e1a7a37f9d79abec5c30491193bff678ac96b60af0630bd1117b02744fadc.
Прежняя flash1604 проверена/сохранена, RAM32КБ и HMI backup сохранены;
калибровка до/после a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
Matching HMI установлен; RPC восстановилась без ручного USB/reset. Ручных
RESET/CLEAR/ARM/START=0, только штатные resets рецептов программирования.

post_install_idle_r1: независимый native readback совпал, два пассивных
RAM/register-снимка tick42313→42974: BKE1/MOE0/BIE1/PA6HIGH/running0,
OFF64×8 fe_complete1/case64/fault0, fast3618≤4000 (запас382), observer19860≤85000,
meter_errors0/steps64, observer/CLEAR record empty. Target timing OFF измерено,
полный FOC/PWM или физическое восстановление CLEAR не проверены.

20 статусов: zero_ready1/stable3 во всех; max sampled ages current599/detail995/
quality986мс <750/1500/1500, fresh good растёт. CRC/sequence/UART hardwareflags0,
RPC response/send0 стабильны, guard ready. Но строгий idle report passed=false:
mc_transport_fault7 LINK_TIMEOUT и bad_count1 неизменны с первого after_install
до конца20ответов; mc/bp_fault2, reason13. Защёлка не очищалась. Это не считается
готовностью к пуску; исходный failed report оставлен без изменений.
SD HIGH/BIE1/capture_running1/config_ok1, first Break нет; first retained MC
mask0/0 не означает снятия транспортной защёлки. Шина около10В/J1 OFF.

record_clear_recovery_qualification.py отдельно записал programming_passed=true
и OFF_CPU_qualification_passed=true, complete_idle_check_passed=false/UART_clean=false,
qualified=false/FOC_start_ready=false/physical_CLEAR_recovery_verified=false.
installation_acceptance.json и preinstallation_manifest.json сохранены.3581
старый файл/164 release sources проверены. Состояние остаётся обе платы ПК,
J4 ON/J1 OFF; пусков/нового CLEAR не разрешено и не выполнялось.

## 2026-11-16: запись1605/1606 подготовлена, ожидается безопасное USB-подключение

Пользователь запросил подготовку записи и инструкции переключения, после
записи readback и OFF timing без ШИМ,4000/2мс/защиты/захваты сохранять.
Установлены1603/1604; последняя подтверждённая конфигурация J1/J4 ON,
повербанки, PWM0. На устройства/сеть в этой задаче не обращались.

Подготовлены tools/install_clear_recovery.py, verify_clear_recovery_idle.py,
record_clear_recovery_installation.py. --verify-only прошёл: образы/164source/
6проверочных отчётов/3581 прежний файл проверены по SHA. Отрицательные
проверки наПК отвергают20 небезопасных/неподходящих состояний для записи;
8 отрицательных OFF CPU случаев,4000 принимается/4001 отвергается.
Отчёт clear_recovery_r1/installation_preparation_r1/report.json.

Установщик требует явное подтверждение J1 OFF + мультиметр <20В + обе платы
USB ПК, проверяет SAFE/PWM0/ARM0/BKE1/MOE0/свежую связь/нулевые service outputs,
сохраняет RAM32КБ/прежнюю flash/HMI/калибровку. Затем одна запись+verify
каждой MCU, native readback сравнение с sealed image, Uno OpenOCD verify,
совместимый HMI и проверка прежней калибровки. Никаких START/CLEAR/ARM.
Проверка после записи: независимый native readback, два пассивных RAM/регистровых
снимка, OFF64×8≤4000/observer≤85000, никаких run/захватов наблюдателя,
новая first CLEAR запись должна быть пустой.20статусов со свежим автонулём,
750/1500/1500мс freshness,UART clean и общим RPC baseline guard без роста.
Физическое восстановление CLEAR и работа под ШИМ этим не квалифицируются.

Следующее действие оператора: выключить только J1, дождаться мультиметра
ниже20В, перевести обе платы с повербанков на USB ПК.15В можно оставить,
двигатель/шлейф/проводку не менять, Saleae не подключать, RESET/Пуск не нажимать.
После подтверждения этой конфигурации выполнить install_clear_recovery.py
с --confirmed-j1-off-bus-below20-both-pc-usb и новым hardware_install_r1;
затем verify_clear_recovery_idle.py в post_install_idle_r1. Не начинать запись
по одному наличию устройств, пока последнее подтверждённое J1 ON не отменено.

## 2026-11-16:1605/1606 CLEAR recovery собраны и проверены только на ПК

Пользователь запросил разбор/исправление отказа CLEAR при нормальной шине,
без новых пусков/CLEAR, без ослабления защит и удаления захватов.
Новый отдельный пакет: artifacts/live_bench_20261116/clear_recovery_r1.
На устройства/сеть в этой задаче не обращались, flash/START/CLEAR/RESET=0.
Установленная пара остаётся1603/1604, последнее состояние — J1/J4 ON,
повербанки, PWM0, после одного прежнего CLEAR защита не восстановлена.

Доказанный дефект1604: uno_tx_clear_ready() требует полностью пустой TX
очереди. Исправная активная OFF-телеметрия отклоняет CLEAR до Break rearm
и MCSDK ACK. НаПК фактический baseline-handler воспроизвёл этот отказ
при одном здоровом активном кадре. В новом helper сохраняются hard-error,
полная очередь и прежний wall TX deadline5мс, но здоровый in-flight кадр
не блокирует CLEAR; DMA/очередь/CRC не отменяются и не переписываются.
Также MC_AcknowledgeFaultMotor1() больше не игнорирует отказ: он сохраняет
защёлку и первую диагностику. Асинхронный ACK не считается завершённым
восстановлением; прежние START guards требуют готового состояния MCSDK.

Важное уточнение интерпретации прежних отчётов: mc_fault_current_mask и
mc_fault_occurred_mask экспортируют first_current/first_occurred snapshot,
не живые маски на момент CLEAR. Поэтому4/4 при321–322В не доказывает
активную текущую UNDERVOLT. В новом HMI подписи at_first, scope explicit;
legacy keys/guards сохранены. Исторический конкретный reject-stage не
доказан: в старом захвате нет TX head/tail и точки отказа. Добавлена
отдельная неизменяемая первая CLEAR запись43Б с TX/SD/SR/MCSDK и result;
доставка только OFF, CRC/peer checks Uno/HMI, ACK_ACCEPTED не равен ready.

ПроверкиПК: фактический CLEAR+ST ACK, negative SD/MOE/BIF/TX full/error/
timeout/16fault masks/local STOP, frozen first CLEAR,344CRC bit flips;
фактический DMA2048кадров/292687проверок.7 сценариев обычной телеметрии
с восьмой OFF bulk class: max summary603,75/detail1005,75/quality1005,75мс,
ADC delivery≤3,9808с; прежние750/1500/1500 freshness неизменны.7 независимых
plant-сценариев baseline/candidate с одинаковыми траекториями;2,1мс по-прежнему
MA_STALE. FAST/ADC/ISR/timer/BKE/BKF/1,35А/2048/2мс/4000 и первый/repeat
Break writers сохранены, ARM fast call scope прежний. HMI at_first semantics
проверены на сохранённом статусе, JS syntax OK. Обе сборки и LLEXT прошли.

release содержит Uno2026111605/Nucleo2026111606 и expected readback.
native113848Б, RAM31464Б/free1304Б (stack high-water не измерен).
3581 старый файл проверен по SHA; старый снимокSD и failed trial целы.
Manifest built=true/installed=false/qualified=false/OFF_CPU_qualified=false;
target timing и физический CLEAR ещё не проверены. Для следующего этапа
нужны отдельно разрешённые запись/readback/OFF timing, не очередной пуск
или CLEAR на установленной1604. Причина физических SD/NIS не объявлена решённой.

## 2026-11-16: разрешённый один CLEAR не восстановил защиты; START=0

Пользователь явно разрешил один CLEAR и один FOC5Гц/5с только при восстановлении
защит. Выполнен проверенный tools/run_telemetry_deadline_trial.py с --clear-once,
архив telemetry_deadline_r1/powered_FOC_NIS_5Hz_r1. Перед командами RPC quiet
guard пройден, профиль выбран2 (FOC), OFF timing ready, SD HIGH. Отправлена
ровно одна HTTP-команда CLEAR; после неё четыре свежих статуса сохраняют
current/saved mask4, mc/bp_fault5, BIE=false, capture_running=false. Шина321–322В,
SAFE/PWM0/run_id0, estop0, algorithm_fault0. mc_clear_pending0, reason8 MCSDK,
fault_motor_state10; поле reason — сохранённая диагностика, не доказательство
точной причины текущего отказа восстановления Break. Не объявлять UART потерю:
good frames растут, CRC/sequence/transport0, RPC12/send0 без роста.

Скрипт завершился One CLEAR did not restore protections; no retry.
CLEAR1/START0/ARM0/RESET0/flash0; повторного CLEAR или пуска не было.
CPU/ADC runtime record received=false ожидаем: RUN не начался, NIS-тест не
состоялся. Boot audit пройден, прежний SD63,4мкс не изменился: SD_before.bin=
SD_after.bin=предыдущий SD_before_START.bin, SHA7b452e323df8549c5b2fe61afb0d853c398c69249dcd3ad1ccf95d613c82ed51.
3562 прежних файла и162 release sources проверены без изменений.
Полномочие на один CLEAR израсходовано; новый CLEAR/START не разрешён этим
запросом. Следующая работа — разбор отказа восстановления Break/MCSDK по
сохранённой записи, без повторов наугад. Подключения и питание не менялись.

## 2026-11-16: J1 ON, preflight FOC остановлен на защёлке до Пуска

Пользователь подтвердил J1 через soft-start/J4 ON/повербанки и запросил
проверку шины/защит перед FOC, без команды START/CLEAR. Только GET:
verify_telemetry_deadline_autonomous.py --rpc-baseline --powered-preflight,
новый архив telemetry_deadline_r1/powered_before_NIS_FOC_r1.
20 ответов за29,453с; шина320–322В, SAFE/PWM0/run_id0/ARM0.
Связь good+582/rejected0, UART/CRC/sequence/transport0; RPC12/send0
постоянны, guard ready=true/failure=null. Автоноль готов, профиль и OFF
CPU3618/4000 пройдены, рекордеры ADC/observer свободны.

До Пуска записан первый Break: PA6 LOW63,4мкс, полные оба фронта,
MOE_at_IRQ=false/start_window=false. Сейчас SD HIGH/config_ok=true,
но BIE=false/capture_running=false, current/saved MC mask4, mc/bp_fault5,
estop0. Проверка failed только no_fault_latches и SD_break_IRQ_ready.
Не объявлять готовность к START до штатного CLEAR и свежей проверки.
PA4 HIGH не локализует источник: TP23→PA4 ранее снят, подключение не
подтверждено. SD_before_START.bin320B и JSON-снимки сохранены.
Нового CLEAR/START/ARM/RESET/flash/SWD=0, защиты не изменялись.
Следующее действие требует явного разрешения на один CLEAR; текущая
проверка сама не даёт права на запуск или автоматический сброс.

## 2026-11-16: автономная проверка с исправленным RPC пройдена, пуска не было

Пользователь подтвердил повербанки, J4 ON, J1 OFF, без изменения подключений.
verify_telemetry_deadline_autonomous.py получил опцию --rpc-baseline,
подключающую тот же проверенный RpcCounterGuard; остальные проверки не
ослаблялись, дополнительно проверяются uno_rx_hw_errors/uno_rx_dropped.
Дефолтный legacy режим остался строгим; старый failed report не переписан.

Новый GET-only архив: telemetry_deadline_r1/autonomous_RPC_baseline_r1.
19/19 checks true,20 статусов за28,359с. Версии1603/1604, SAFE/PWM0/run_id0,
ARM0, шина9В. Good frames+561, rejected0, CRC/sequence/UART/transport0;
RPC response12/send0 постоянны. Guard ready=true/failure=null; начальный
boot CRC проверен, boot свежий на протяжении OFF-окна. Та же Linux/native
загрузка, что в предыдущей проверке; перезапусков не обнаружено.

Автоноль ready1/stable3 во всех20 ответах: offsets2068/2066/2067/2069,
spans23/30/26/22, attempts3. Max sampled ages native57/current540/detail928/
quality974мс <300/750/1500/1500. Это выборочные возраста, не непрерывный max.
CPU3618/4000, OFF64/fault0, meter_errors0. Профиль qualification128/
CRC1354279011 подтверждён. SD HIGH/BIE1/config_ok1/capture_running1,
первого Break нет. Рекордеры ADC/observer свободны по свежему boot/run_id0
и приёмникам; прямого SWD/RAM чтения нет. NIS ADC trigger установлен,
но реальный NIS-захват под FOC ещё не проверен.

MC current/saved mask4 UNDER_VOLT ожидаем при J1 OFF; это не полная готовность
к START при включённом J1. После подачи силового понадобится свежая проверка
шины/защит; текущая проверка не разрешает CLEAR или пуск. START/CLEAR/ARM/
RESET/flash/SWD=0, все сетевые запросы GET. 3540 старых файлов и162 release
sources проверены по SHA без изменений. Пределы4000/2мс/1,35А/2048 прежние.
Состояние пользователя остаётся: повербанки, J4 ON, J1 OFF.

## 2026-11-16: исправлен host-контроль накопительных RPC, проверено только на ПК

Пользователь запросил учёт новых RPC timeout без блокировки историческим
счётчиком, без пусков/изменения защит. Исправлен актуальный запускатель
tools/run_telemetry_deadline_trial.py: GET-only preflight не менее2с и3ответов
при OFF, свежем CRC-проверенном boot и продвижении native кадров. После
этого один RpcCounterGuard используется до/после CLEAR, перед START и в RUN.
Базовые response/send counters записываются в отдельный уникальный
<trial>_RPC_preflight; они не обнуляются и не принимаются повторно в ходе теста.
Изменение любого counter (вверх/вниз/wrap), смена доступной boot identity,
повреждение boot CRC, невалидные поля или stale/live frame stall блокируют
пуск; если START уже был, существующий обработчик отправляет STOP без retry.
Причина guard и baseline сохраняются в отчёте. Старые runners без явного
подключения guard сохраняют прежнюю строгую RPC==0 проверку.

Boot bulk передаётся только OFF и штатно стареет через1500мс при ШИМ;
поэтому после свежей привязки guard сверяет CRC/identity сохранённой boot
страницы, а связь контролирует по живым mc_age<300мс и good-frame progress.
При самой привязке и в течение OFF quiet preflight boot обязан быть свежим.
Стандартный decode_boot по умолчанию по-прежнему требует fresh=true.
Это не замена live-статуса историей и не изменение свежести UART/АЦП.

tools/test_rpc_counter_guard.py:11 тестов пройдены, replay20 прежних статусов
с RPC12, отрицательные инъекции response/send, reset/wrap/boot/stale/malformed,
имитация полного5с с историческим12, STOP при новом timeout после START,
отказ до START при новом timeout. Все обращения имитированы; сетевые socket
connect запрещены в тесте. Проверены прежние power/UART/SD/current/profile/
CPU guards. Отчёт artifacts/live_bench_20261116/rpc_counter_guard_r3/report.json.
3532 прежних файла и162 release source hashes совпали. MCU/HMI не менялись,
4000/2мс/1,35А/2048 и остальные аппаратные защиты прежние.
Физических START/CLEAR/ARM/RESET/flash/сетевых обращений=0.
Прежний автономный failed report не переписан: новый результат относится
к исправленному host runner, не к выполненному силовому пуску.
Пользовательское состояние остаётся: повербанки, J4 ON, J1 OFF.

## 2026-11-16: автономная проверка1603/1604 — автоноль готов, скрипт пуска блокируется RPC-счётчиком

Пользователь подтвердил повербанки, USB ПК/Saleae отключены, J4 ON, J1 OFF,
без Пуска/RESET. Выполнены только GET:20 статусов за28,141с, снимки SD/Break,
метаданные захватов и логи. START/CLEAR/ARM/RESET/flash/SWD=0.
Архив: telemetry_deadline_r1/autonomous_before_NIS_FOC_r1.

Обе версии подтверждены, SAFE/PWM0/run_id0, шина10В. Связь: good+564,
rejected0, CRC/sequence/UART flags/transport0, перезапусков в окне нет.
Автоноль ready1/stable3 во всех20 ответах, offsets2068/2066/2067/2069,
spans23/30/26/22. Max sampled age: native52, summary584, detail908,
quality908мс, прежние пределы300/750/1500/1500 соблюдены. CPU3618/4000,
64cases/fault0, meter_errors0. SD HIGH, BIE1, config_ok1, capture_running1,
первого Break нет. Рекордеры ADC/observer свободны по свежему boot/run_id0
и состоянию приёмников; это не прямое чтение RAM. NIS-trigger в конфигурации
подтверждён, фактический захват при работающем FOC пока не проверен.

Единственный провал строгого report.json — rpc_response_timeouts=12 во всех
20 ответах; send_timeouts0. По mic_rpc_health.h/bridge.h это накопительный
счётчик admission/write-mutex/response timeout, экспортируется Uno напрямую.
Когда и какой из этих путей дал12, эта запись не устанавливает. Новых
тайм-аутов за окно нет; это не доказывает их физическую/программную причину.
Действующий host link_power требует абсолютный RPC0 и пока заблокирует пуск.
Guard не меняли, счётчик не обнуляли, исходный failed report сохранён.
MC current/saved mask4 UNDER_VOLT ожидаем при J1 OFF; CLEAR не отправлялся.
3523 прежних файла проверены без изменений. J1 оставить выключенным до
разбора host-проверки; полной готовности к силовому пуску пока не заявляем.

## 2026-11-16: 1603/1604 установлены, OFF CPU и свежесть телеметрии пройдены

Пользователь подтвердил J1 OFF, метр <20 В, обе платы на ПК, 15 В включены;
разрешил запись/readback, расчёт без ШИМ и проверку свежести, без пусков.
В telemetry_deadline_r1/hardware_install_r1 выполнено по одной записи каждой MCU,
оба образа verified. Дополнительный native readback112952B SHA
59a9418fa1ed8853d0eb09eb30fd916ba78ec2826c4ec738f779d277e13556d6.
Сохранены прежняя flash1602/RAM32КБ/HMI backup; калибровка до/после прежняя:
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

OFF64×8: fe_complete1/case64/fault0, fast3618≤4000 (запас382), observer19504≤85000,
meter_errors0/steps64. Два RAM-снимка подтверждают один завершённый результат,
MOE0/BKE1/BIE1, PA6 HIGH, running0, observer record empty. Без ручного RESET,
CLEAR/ARM/START; только штатные перезапуски рецептов программирования.

post_install_idle_r1: 20 свежих ответов за около28с, zero_ready1/stable3 постоянно.
Max sampled ages summary558/detail977/quality990 мс <750/1500/1500.
Это sampled ages, не измеренные максимальные межпакетные интервалы.
Background noise_good1399→2685, control good+556. UART/CRC/sequence/RPC0,
bad_count1 неизменен, transport7 LINK_TIMEOUT сохранён. Current/saved MC mask4
UNDER_VOLT при J1 OFF, SD HIGH; ничего не очищалось. 3523 старых файла целы.
installation_acceptance.json подтверждает programming/OFF CPU/ordinary freshness.
Manifest installed=true/OFF_CPU_qualified=true/FOC_start_ready=false.
Платы остаются на ПК, J1 OFF, 15 В включены. Нового разрешения на силовой
пуск нет; NIS-достоверность/захват при FOC на1604 ещё не проверялись.

## 2026-11-16: запись1603/1604 подготовлена, ждём подключения плат кПК

Пользователь запросил подготовку записи/readback/OFF-расчёта и инструкцию
переключения. Созданы install_telemetry_deadline.py, verify_telemetry_deadline_idle.py
и record_telemetry_deadline_installation.py. Пакет прошёл --verify-only:
все хеши исходников/образов/отчётов и3523прежних файла сохранены; пределы
4000/2мс/1,35А/2048 неизменны. Отрицательные проверки установщика наПК
отвергают высокую шину, ШИМ/ARM, stale reply, UART/CRC/sequence и service output.
Отчёт telemetry_deadline_r1/installation_preparation_r1/report.json.
Пассивная проверка после записи дополнительно требует свежих summary/detail/
quality750/1500/1500мс и zero_ready1/stable3 во всех восьми ответах.
Обращений к платам/сети, прошивки, CLEAR/START/RESET не было.
Следующий шаг оператора: J1 OFF, мультиметр <20В, обе платы USB ПК,
15В можно оставить включёнными; Saleae не подключать, проводку не менять.

## 2026-11-16: подготовлены1603/1604 — приоритет обычной OFF-телеметрии, не установлены

Пользователь запросил исправление задержек и проверку наПК без пусков,
с прежними4000/2мс/защитами. В этой задаче аппаратных/сетевых обращений,
START/CLEAR/RESET/ARM/flash не было; остаётся установленная1601/1602.
Пакет: `artifacts/live_bench_20261116/telemetry_deadline_r1`.

Дефект1602 воспроизведён: normal senders вызываются только сразу после
controlreply, когда queue занята; после освобождения foreground bulk снова
занимает места. Новое единственное функциональное изменение внутри
mic_send_bulk_page: OFF-only повторные попытки current/research перед bulk,
затем одна bulk-страница с общим cap100fps и прежними резервами очереди.
RUN helper сразу возвращается. Сchedules200/100мс,750/1500мс freshness,
sequence/CRC/политика zero_ready и весь контроль/IRQ/watchdog неизменны.

НаПК тест использует фактический producer current_shunt.c,6 фактических
senders, arbiter, Uno current_wire и HMI.8сценариев×70с: cadence20–100мс,
phase/poll100мкс–2мс, HALwrap и sequencewrap.27200HMIсрезов после прогрева:
zero_ready1/stable3 без пропаданий; max gaps summary603,75мс/detail1005,75/
quality1005,75 при прежних750/1500/1500. Bad/full0; ADC/observer доставлены
в пределах20с. Отрицательные stale/CRC проверки по-прежнему дают zero_ready0.
Точные физические UART IRQ/RPC scheduling не эмулировались.

Наследованный NIS ADCcapture1024B/CRC/6post/STOPshort/frozen regression прошёл
для peer1604.7сценариев независимой модели совпали сbase,2,1мс вызываетMA_STALE.
Обе сборки прошли; RAM31416/free1352. ARM fast call scopes совпадают;
новая targetDWT квалификация ещё требуется.3523 прежних файла сохранены.
Manifest built=true/installed=false/OFF_CPU_qualified=false/FOC_start_ready=false.
NIS/SD физические причины не объявлены устранёнными; старый Break не очищен.
Платы/питание не менялись; по последнему подтверждению повербанки,15В ON,J1 OFF.

## 2026-11-16: автономная проверка 1601/1602 не пройдена, J1 остаётся OFF

Пользователь подтвердил повербанки, USB ПК/Saleae отключены, 15 В ON,
J1 OFF, Пуск/RESET не нажимались. Выполнены только GET. Отчёт и 20 статусов:
`observer_adc_delivery_r1/autonomous_before_NIS_FOC_r1`; дополнительный
разбор сохранённых ответов и binary SD: `autonomous_review_r1`.
Правильная пара, SAFE/PWM0/run_id0, свежие control replies good+591;
UART flags/CRC/sequence/transport=0, перезапусков в наблюдении нет.
RPC response_timeouts=12 уже в первом ответе и не растут; send_timeouts=0.
CPU64/fault0/fast3618≤4000, observer18700≤85000. Рекордеры ADC/observer пусты;
код запроса ADC при NIS и новый арбитр подтверждены установленной сборкой.

История автонуля содержит три успешных блока: offsets 2068/2065/2066/2069,
spans 23/32/23/25 в последнем блоке, reject=0. Но обычная токовая телеметрия
запаздывает: max ages summary3637/detail5908/quality6468 мс; HMI zero_ready
становится 0 в 8 из 20 ответов из-за штатных freshness gates. Автоноль заново
не запрашивать и не обходить его guard. Проверить конкуренцию OFF bulk
с обычными mic_send_research/current_page, которые в1602 остались привязаны
к control reply. Предыдущий тест проверял доставку bulk, но не её влияние
на предельную свежесть обычной телеметрии. Точная очередь на MCU не считана.

До пуска сохранён новый PA6 LOW 17866,2 мкс (17,8662 мс), SD сейчас HIGH,
BIE0, current MC mask4 UNDER_VOLT, saved mask1028 UNDER_VOLT+Break.
Требуется восстановление защит перед любым пуском, но CLEAR не разрешался
и не отправлялся. Не включать J1: готовность к следующему этапу не пройдена.
3296 прежних файлов проверены, 4000/2 мс/защиты неизменны. Платы и питание не менять.

## 2026-11-16: 1601/1602 установлены, OFF CPU 3618 ≤ 4000, без пуска

Пользователь подтвердил J1 OFF, мультиметр <20 В, обе платы USB ПК, 15 В оставлены;
разрешил запись/readback и расчёт без ШИМ. Первый installer r1 остановился
до flash по сохранённому soft CRC counter=1. Восемь свежих ответов из
programming_preflight_UART_r1 подтвердили: counter=1 неизменен, bad_count=0,
UART flags=0, good+192, SAFE/PWM0 и низкое напряжение шины.
Для OFF-записи допущен ровно этот сохранённый счётчик, без CLEAR и изменения
любого моторного guard. В hardware_install_r2 выполнено по одной записи каждой платы.
Оба readback проверены; дополнительный native readback 112936 B, SHA
df78597cbcb2d2bbc7527401cda81cc55ec84b855085e4a90dc8ec60f353b0f0.
Прежняя flash 1504, RAM 32 КБ и HMI backup сохранены, калибровка прежняя:
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

OFF 64×8: fe_complete=1/case=64/fault=0, fast max 3618 ≤4000 (запас 382),
observer max 18752 ≤85000, meter_errors=0/steps=64. Два пассивных RAM-снимка
подтверждают один результат. MOE0/BKE1/BIE1, PA6 HIGH, running0, observer record пуст.
Пуск/CLEAR/ARM/ручной RESET=0; MCU перезапускались только рецептами программирования.
После установки восемь свежих ответов: UART flags=0, CRC counter=0, sequence=0,
bad_count=1 неизменен, transport=7 LINK_TIMEOUT сохранён; current/saved MC mask=4
UNDER_VOLT при J1 OFF. Автоноль готов, SD HIGH, ничего не очищалось.
3296 прежних файлов проверены, защиты 4000/2 мс/1,35 А/2048 неизменны.
installation_acceptance.json и post_install_idle_r1/ содержат доказательства.
Manifest installed=true/OFF_CPU_qualified=true/FOC_start_ready=false.
Платы оставлены на ПК, J1 OFF. Новый силовой пуск не разрешён;
проблема достоверности наблюдателя по NIS ещё не объявлена решённой.

## 2026-11-16: запись1601/1602 подготовлена, ожидается перевод плат наПК

Пользователь запросил подготовку записи/readback и OFF-расчёта, попросил
инструкцию переключения. `install_observer_adc_delivery.py --verify-only`
проверил sealedпакет/всеSHA,3296старыхфайлов и прежние4000/2мс/1,35А/2048.
Подготовлены `verify_observer_adc_delivery_idle.py` (пассивныйSWD/RAM/DWT)
и `record_observer_adc_installation.py`. Отрицательные проверки установщика
наПК подтверждают блокировкуbus>20В/ШИМ/ARM/staleUART/ошибок/serviceoutput.
Отчёт `observer_adc_delivery_r1/installation_preparation_r1/report.json`.
Ни кUSB/сети/платам не обращались, ни программирования/CLEAR/START/RESET нет.
Следующий шаг оператора: J1OFF, метр<20В, обе платыUSBПК;15В можно оставить,
Saleaeнеподключать, мотор/шлейф/проводку не менять. После подтверждения —
по одной записи, readbackобоих образов и штатнаяOFFCPUквалификация безШИМ.

## 2026-11-16: офлайн-разбор NIS/ADC, готовы1601/1602, НЕ установлены

Пользователь потребовал разбор записи и исправление на ПК, без новых пусков,
с прежними4000/2мс и защитами. В этом этапе к платам не обращались:
START/CLEAR/ARM/RESET/flash0, актуальное питание/связь на16ноября не проверены.
Установленной остаётся1503/1504. Старые исходники/failed reports сохранены;
3296 прежних файлов проверены поSHA256.

Первый отказ достоверностиstep501 строгоOD_NIS, NIS38,957802, из них
β38,709181 (99,36%), eβ−.131268А, Sβ.000445147А², поток.274Вб>.125.
Endpoint/control ADC/bin метки совпадают. 12редких наблюдений+firstloss
не позволяют восстановить5000входных кадров или определить истинную скорость,
моторные параметры, физическую причину рассогласования. Не заявлять, что
математический наблюдатель починен: observer_validity_problem_solved=false.
R/Q, NIS25 и аварийныйNIS50×20, модель, знак скорости и регулятор не менялись.

Найден и воспроизведён starvation в bulkTX: отправка только приcontrolreply50мс,
observer20мс стоит передADC100мс и может всегда занять второе место очереди.
Реальные2page-sender функции с моделируемыми конкурентами/115200baud дают
old observer15/ADC0 за8с. Это не точный replay несуществующей UART timeline.
Новая OFF-only круговая отправка из uno_link_poll послеRX/команд даёт полные
observer/ADC~1,3/3,6с в модели, 6cadence/phase случаев, всеcontrolreplies целы.
В RUNbulkпо-прежнему запрещён, 2слота reserved, watchdog/IRQ/CRC неизменны.

Пакет `artifacts/live_bench_20261116/observer_adc_delivery_r1`1601/1602:
добавлен диагностический запрос ADCкольца припервомNISотказе послеvalid;
ADCIRQ единственный writer, прежний frozen сохраняется, PC_OBSERVER8 явно
декодируется. Ровно первый ADCcapture неизменяемый; это диагностика, не
подавление ошибок. Хостrunner использует decoder1832B точногоreleaseHMI,
вместо ошибочно импортированного старого decoder. Положительные/CRCnegative,
STOPshort/NO_PEAK/threshold626/firstloss и реальные рекордер/wire проверены.
7сценариев модели совпали сbase,2,1мс по-прежнемуостанавливаетMA_STALE.
Обе сборки прошли, nativewarning/error0; RAM31408/free1360. Новые ARMfast
call scopes совпадают, но targetCPU не измерен: OFF_CPU_qualified=false,
FOC_start_ready=false. Образыsealed вrelease/, README_RU содержит ограничения.
Не прошивать/пускать автоматически: текущее разрешение только на работу наПК.

## 2026-11-15: FOC1503/1504 отработал5000мс, автостоп; достоверность наблюдателя непостоянна

Пользователь явно разрешил один CLEAR и один FOC5Гц5с при готовых защитах.
`exact_profile_budget_r1/powered_FOC_5Hz_r1`: CLEAR1/START1/ARM1, reset/flash0;
после CLEAR все штатные проверки пройдены. mc_mode=bp_mode6 в RUN,
selected/requested2. Uno auto-limit5000мс/run_reason1, SAFE/PWM0 подтверждены,
native_done=false (не приписывать остановку native trial timer).
Нет native/MCfault, UARTbad0/transport0, boot/Linuxidentity неизменны,
первый SD320B сохранён побайтно; повторов не было, 3045 старых файлов целы.

OFFfast3615≤4000 до START; полный RUNfast4349≤5312 — другие измеряемые
участки, бюджет4000 не поднимался. CPU4996steps, errors0, first_fault=null;
max result age771,524мкс<2мс, max queue278,818мкс, max wall617,229мкс,
max CPU upper223,465мкс. IRQschema3/все9валидны; последнее окно преимущественно
ADC1_2/TIM1UPDATE, UARTTX/USART1 вызовов0, не экстраполировать на весь пуск.
Токовая телеметрия сохранена: max полученных фазных peaks .931/.787/.969А,
последнее RMS .653/.105/.731А coverage100%, номинальный масштаб.

Старый post-run collector ошибочно применил старый декодер; raw1832B находился
в сохранённых status. В saved_record_analysis_r1 восстановлен ABI2/CRC
точным decoder из release HMI: samples4995/valid2484/invalid2511, firstloss
step501 по NIS38,958≥25, fault0. Скорость не считать независимо измеренной
и достоверной на всём интервале. Старый failed-report не заменялся.
ADC raw good0/bad0/complete0, причина отсутствия пока не доказана; строгий
общий report.passed=false, хотя completed_5s=true и CPU/IRQ получены.
Bootauditfailed связан с отсутствием ADC_peak.bin, не с доказанным reset.

Физическое вращение ещё ожидает ответа на заданный оператору вопрос.
Два поздних GET при дополнительном разборе не соединились по сети; последняя
подтверждённая SAFE/PWM0 запись сохранена после автостопа. Не заявлять свежесть
связи после позднего timeout и не выводить из него причину/факт reset.
Новых разрешений на CLEAR/START нет, этот однократный допуск израсходован.
Пределы4000/2мс/1,35А/2048 и остальные защиты сохранены.

## 2026-11-15: J1 ON, перед первым FOC сохранён SD63,4 мкс; START не отправлен

GET-only preflight `exact_profile_budget_r1/powered_preflight_FOC_r1`:
321В, UART/RPC clean/bad0/transport0, автоноль ready, CPU3615/4000,
SD сейчас HIGH. На включении до START захвачен PA6 LOW63,4мкс, MOE_at_irq0,
start_window0; полный первый снимок и waveform320B сохранены в новом каталоге.
TP23→PA4 снят ранее, поэтому его HIGH не доказывает источник импульса.
После события BIE0/capture_running0; MCfault5/reason8, current/occurred mask4
(UNDER_VOLT). Пуск запрещён текущими штатными проверками. Никаких CLEAR,
START, ARM, RESET, конфигурации или прошивки в этом этапе не было.
3045 прежних файлов проверены. Следующий необходимый шаг — один штатный
CLEAR с проверкой BIE/SD/всех масок перед согласованным FOC5Гц5с; отдельное
разрешение на этот CLEAR ещё не получено. Питание и проводку менять не нужно.

## 2026-11-15: автономная проверка 1503/1504 перед FOC пройдена

Обе платы на повербанках, USB ПК/Saleae отключены, J4=15 В, J1 OFF;
Пуск/RESET пользователь не нажимал. GET-only проверка сохранена в
`exact_profile_budget_r1/autonomous_before_FOC_r2`: 20 ответов, good+655,
bad0, UART/RPC flags0, transport0, перезапусков во время наблюдения нет.
Первый GET до окончания загрузки был timeout, отчёт r1 сохранён отдельно;
повторная проверка выполнена без команд или переключений питания.
Автоноль ready1/stable3, offsets2068/2066/2067/2069, spans20/31/26/23,
attempts3. OFF CPU64, fault0, fast3615 ≤4000, observer19214 ≤85000.
SD HIGH, config_ok, BIE1, при наблюдении SAFE/PWM0/run_id0, около9В.
При J1 OFF активная и сохранённая маски4 UNDER_VOLT ожидаемы; CLEAR не было.
Профиль128/CRC1354279011 есть, алгоритм пока выбран1 (V/f), FOC не включался.
3045 старых файлов проверены без изменений. Следующее действие оператора —
включить только J1 через soft-start при закрытом стенде; затем свежая проверка
шины/SD/блокировок перед уже согласованным FOC5Гц5с. Пусков в этом этапе нет.

## 2026-11-15: 2026111503/1504 установлены, OFF CPU пройден — 3611 ≤ 4000

Пользователь разрешил запись/readback/OFF-замер, подтвердив J1 OFF,
мультиметр <20 В, обе платы на ПК, J4=15 В. Пакет exact_profile_budget_r1:
ровно одна запись каждой MCU, оба readback проверены; Nucleo дополнительно
прочитана независимо, SHA b09927049be0a5f5234e73f293dcf28990169610bb7eac2cb32ac8c9587eed95.
Перед записью сохранены flash 1502 и RAM32КБ, HMI скопирован в backup.
Калибровка прежняя a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

fe_complete=1, fe_case=64, fe_fault=0, fast max3611 (запас389 до4000),
observer max19781 ≤85000, meter_errors=0, observer_steps=64. Два RAM-снимка
подтвердили тот же результат без повторного запуска квалификации.
MOE0/BKE1/BIE1, PA6 HIGH, running0, recorder empty. Пуск/CLEAR/ARM/ручной
RESET не выполнялись; MCU перезапускались только рецептами программирования.
Пределы4000/2мс/1,35А/2048 и остальные защиты сохранены.

8 свежих ответов: UART flags0, bad_cnt1 неизменен; остаётся transport7
(LINK_TIMEOUT), saved fault mask4 (UNDER_VOLT), active mask0. Ничего не
очищалось. Автоноль готов, SD HIGH. Готовность к силовому пуску не оценена;
OFF-квалификация не доказывает FOC/IRQ под силовым ШИМ. 3045 прежних файлов
проверены, не изменены. installation_acceptance.json и post_install_idle_r1/
содержат отчёт, исходные RAM/регистры/readback и статусы. Manifest installed=true,
OFF_CPU_qualified=true, FOC_start_ready=false. Платы остаются на ПК, J1 OFF.

## 2026-11-15: подготовлены 2026111503/1504, на платы НЕ записаны

Задача пользователя — оптимизация на ПК без пуска, с прежними пределами
4000 тактов / 2 мс и остальными защитами. Пакет:
`artifacts/live_bench_20261115/exact_profile_budget_r1`.
Проверка профиля заменена эквивалентным сравнением всех 52 байт за каждый
вызов; два hypot регулятора вызывают то же библиотечное ядро напрямую
только для заведомо конечного результата. Пороговый hypot сырых токов
не менялся. Ни глобальной подмены математики, ни fast-math не добавлено.
Прежний sqrt уже аппаратный; отвергнутый черновик fpu_sqrt_budget_r1
НЕ устанавливать, он помечен rejected/not_for_install.

ПК: 250421 проверка профиля, 2008485 пар нормы, 200000 случаев регулятора,
семь совпавших траекторий независимой модели, ARM-дизассемблер и обе
сборки прошли. 3045 прежних файлов проверены по SHA256, сохранены.
Образы и ожидаемый readback находятся в release/, manifest built=true,
installed=false, hardware_commands=0. Пуск/CLEAR/RESET/ARM/прошивка
в этой задаче не выполнялись. Платы на ПК, J1 выключен по словам пользователя.

Фактическое укладывание нового кода в 4000 тактов пока НЕ измерено:
OFF_CPU_qualified=false, FOC_start_ready=false. Следующий шаг после команды
на запись — readback и OFF DWT-квалификация без ШИМ. Установленной остаётся
1501/1502 с сохранённым отказом 4229 > 4000, описанным ниже.

## 2026-11-15: 2026111501/1502 установлены, OFF CPU заблокирован — 4229 > 4000

Пользователь подтвердил J1 OFF, мультиметр <20 В, обе платы на ПК,
15 В оставлены включёнными; явно разрешил запись/readback/CPU без ШИМ.
В `observer_irq_budget_r1/hardware_install_r1` выполнена ровно одна запись
каждой платы. Оба readback проверены, Nucleo дополнительно прочитана ещё раз
пассивно через SWD: SHA4fc9d666283b6f03763061fb579be7c7c2ad7bd65df556c61394a6017c5d3bf8.
Перед записью сохранены SRAM32КБ и прежняя flash1408. Калибровка не менялась:
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

CPU OFF qualification НЕ пройдена: fe_fast_cycles4229 при прежнем4000,
fe_case0/fe_complete0/fe_fault3, observer_cycles0. Два SRAM-снимка сохраняют
первый результат; новых тестов через RESET, пусков или перепрошивок не было.
Не заявлять64/64, новое измерение3953 или измеренный observer runtime.
Время4229 относится к быстрому синтетическому кернелу, не к наблюдателю.
Прямое чтениеBDTR: BKE1/MOE0; DIER BIE1. HMI SAFE/PWM0/run_id0/10В.
SDHIGH, автоноль готов, FT schema3 с9страницами получен, bulk-рекордер пуст.

UART/RPC отвечает свежо: за8ответов good+205, bad_cnt всё время1,
mc_uart_error_flags=mc_last_uart_error_flags=2 (FE, НЕ NE), transport4.
Осталась одна сохранённая ошибка кадра; точная физическая причина/момент
не установлены, новых bad за наблюдение нет. Ни CLEAR, ни START, ни ARM
не отправлялись. Один перезапуск HMI входит в установку; последующих нет.
2841 прежний файл повторно проверен по SHA256. Все защиты прежние.

Основные доказательства в новом пакете: `installation_acceptance.json`,
`post_install_timing_block_r1/report.json` и дваSRAM, `post_install_link_observation_r1/report.json`.
Общий installer report.passed=false из-за runtime/UART; оба image_verified=true.
Manifest installed=true, OFF_CPU_qualified=false, FOC_start_ready=false.
Следующий технический шаг — исправление стоимости кернела на ПК и новая
контролируемая квалификация; не включать силовое для этой версии.

## 2026-11-15: подготовлены 2026111501/1502, на платы НЕ записаны

Последний аппаратный прогон установленной пары 2026111407/1408:
один CLEAR и один FOC START, остановка через 155 мс по MA_STALE,
FT_ESTIMATE_AGE = 2028,44 мкс при прежнем пределе 2000 мкс. ШИМ выключен,
run_id=1. CPU/IRQ и observer1832B сохранены; сырой ADC-захват не получен.
Новых Break/UART-ошибок и перезапусков в прогоне не было. Первый SD-снимок
сохранён побайтно. Последнее подтверждённое подключение: повербанки,
ПК/Saleae отключены, J4=15 В и J1 включены. После отказа новых пусков,
CLEAR, RESET и программирования не выполнялось.

Пользователь запросил разбор IRQ и исправление на ПК без новых пусков,
без изменения предела 2 мс и остальных защит. Подготовлен пакет
`artifacts/live_bench_20261115/observer_irq_budget_r1`:
UART TCIE теперь включается по DMA TC, затем проверяется финальный UART TC;
исправлен воспроизводимый сценарий повторных IRQ при раннем TC. Его наличие
именно в аппаратном прогоне не доказано: старый захват содержал только
суммарное IRQ-время (769,32 из 874,86 мкс предыдущего шага).
Добавлены отдельные inclusive-счётчики девяти векторов; вложенные интервалы
не складывать как загрузку CPU. Диагностика FT schema3/9pages/63words,
передача только OFF. Приоритеты и разрешения NVIC не менялись.

Контроллер специализируется на том же точном расчётном профиле после
прежней per-frame проверки; лишние вычисления намагничивания исключены.
Якобиан наблюдателя переиспользуется под ковариацию без изменения арифметики.
Статический стек ma_observe: 744 вместо 880 байт; весь вложенный стек на MCU
не измерялся. Проверки: 200000 побитных случаев регулятора, 20000 наблюдателя,
1024 сценария реальных UART/DMA handlers, вложенные IRQ, wire/CRC/peer,
семь сценариев независимой модели. Сборки обеих плат и Uno LLEXT pass.
2,1 мс по-прежнему вызывает MA_STALE, сильный ADC-шум оставляет NIS invalid.
Защиты 1,35 А / 2048 / 2 мс / runtime5312 / OFF4000 и NIS сохранены.
2841 прежний файл проверен по SHA256. RAM свободно 1360 байт сверх
статических секций и резервов линкера; это не замер stack high-water.

Release manifest и образы готовы, installed=false/OFF_CPU_qualified=false.
3953 такта относится к СТАРОЙ паре. Новую сначала записать и сверить при
J1 OFF, мультиметр <20 В, обе платы на ПК; J4 может оставаться включённым.
Сохранить SRAM перед записью. Затем проверить CPU64/связь/новый FT в покое,
без ШИМ. Нельзя заявлять устранение аппаратного MA_STALE или успешные 5 с
до целевого измерения; в этой задаче аппаратных команд было 0.

Отчёты: `verification/report.json`, `verification/ARM_scope.json`,
`model_verification/model_report.json`, `recorded_fault_analysis.json`,
`manifest.json`, `README_RU.md` внутри нового пакета.

## 2026-10-30: J1OFF подтверждён,SDLOW приразряде; ждём уточнить15В(непереключать)

Пользователь «готово» на выключитьтолькоJ1/15В+повербанкиON/неUSBнеRESET.
GETonly:10статусов301→270В всеSDLOW;далее76статусовза242сек192→26В,
всеLOW.Последниенапряжения27/27/26В,ниже20Внеподтверждено/метраневидим.
SAFE/PWM0,MCactive0/occurred1024/BIEOFF. НиCLEAR/START/ARM/RESET/flash.
Native/LinuxbootIDsтеже,SDпервыйснимокпобайтнотоже.226sourceSHA+
1848priorfileSHAпроверены. ОдносогласованноеFOCиспытаниеещёнеизрасходовано.
ПараллельноспросилиэкранБПJ4(U/I/CV/CC),пользовательответил
«я выключил питание че дальеш». Этонеподтверждает,осталисьли15Ввключены.
Сразуasyncодинвопрос: «Что сейчасвыключено: толькоJ1или15ВJ4тоже?
Поканичегонепереключай»,вариантытолькоJ1/15ВONилиJ1+15ВOFF.
ОтветещёНЕПОЛУЧЕН. Необвинятьпользователя/неприписыватьUVLOдоказаннуюпричину.
Следующийзависимыйшагждёттолькоэтогопитанияуточнения;непроситьмодельБП,
неUSB/проводку/RESET/пуск,неCLRприSDLOW. ЕслиJ4тожеOFF — LOWнепроверка
готовностидрайверов,далеесогласованновосстановитьТОЛЬКО15ВприJ1OFFи
читатьSDбезсброса,еслисоответствуетфактическомуответу. ЕслиJ4ON — нужны
действительныепоказания/питаниеJ4,а недоверятьоднойуставке;неустанавливать
причинубезданных. Физическийнизкошиновыйрежимпомеритьпередлюбойперекоммутацией.
Кодаудит:liveSDизGPIOA_IDRPA6,неизстаройволны. BKBID0/input-only
подтверждёнconfigok;ST RM0440+локальныйHALBID=1,гипотезаMCUbidirectionalhold
неподтвердилась. STGIB15CH60TS-LдаташитподдерживаетUVLOкаквозможность,
нонеисточникдоказанный. 1,35А/2048/2мс/5312/NIS/5Гц5сек неизменны.
Мониторразрядазавершёнпосвоемупределу240с,фоновыхпроцессовнет.
Данные artifacts/live_bench_20261030/observer_trace_r1/J1_off_SD_comparison_r1/
comparison_analysis.json,decay_status.jsonl,decay_report.json,REPORT_RU.md.

## 2026-10-30: послеJ1ON SDLOW в10ответах; START/CLEAR0, ждём выключитьтолькоJ1

Пользователь ответил «готово» на включение J1черезsoft-start/15ВON/
повербанки/PC-SaleaeOFF/неSTART-RESET. Fresh3015/3016 SAFE/PWM0,
323→324–325В,FOC2/profile128/zeroReady1,OD/ADCещёсвободны.
Но SDLOW в первом+10последовательныхfreshответахUARTage11–54мс.
MCactive0/occurred1024, BIEOFF/captureStopped/firstRecordReady.
Не считать active0 разрешениемпускаприSDLOW. START/CLEAR/ARM/RESET/flash0.
ПервыйBreaktick190852 приMOE0/внеSTART,context31мсстарше ещё10В.
Wave320Бсохранён: reasonrun_capacity_exceeded/post_completefalse/run_overflowtrue,
много переходов; полныйLOWwidthнеустановлен. Не копироватьстарые62,2мкс
и не выдаватькороткийвыбранныйфрагмент за полныйимпульс. DMAerrorsfalse.
PA4внешнийTP23проводснят,егоHIGHнеизмерениеинвертора.
НовыеLinux/nativebootIDsкаквautonomousreadiness,вэтомэтапеновыйresetнеустановлен.
226sourceSHA+1848priorfilesпроверены,пороги1,35А/2048/2мс/5312/NIS/5Гц5сек прежние.
Async запрошено: выключитьтолькоJ1штатнымвыключателем,15В/повербанкиON;
неRESET/неUSB/непроводка. НаписатьJ1OFF. Для удалённогочтенияSDждать
разряда не нужно; ПК/Saleaeнеподключатьипроводкуне менять.
ОтветJ1OFFпокаНЕполучен. ТекущееJ1по пользователюON,outputsOFF.
Послеответа GETSDсериябезкомандсброса/пуска,сопоставитьсHV-ON10LOW,
сохранитьпервыйзахват; еслиSDнеотпускаетсянеCLEAR/STARTнеобходить.
Один согласованныйпуск3015/3016ещёНЕизрасходован. Trialdirещёне создавалась.
Данные artifacts/live_bench_20261030/observer_trace_r1/powered_before_FOC_observer_r1/
report.json,blocked_analysis.json,SD_release_status.jsonl,SD_before.bin,REPORT_RU.md.

## 2026-10-30: первый OD-пуск3015/3016 запрошен; автономно готово, ждём J1ON

Пользователь явно запросил1FOC5Гц5сек с flux/NIS/IdIq/firstloss и спросил
переключения. Async переводнаповербанки/J1OFF/15ВON/PC-SaleaeOFF подтверждён
«готово» в процессе работы. ПервыйHTTPtimeout связан с сетевойзагрузкой;
следующийHTTP/SSHуспешенбезпереподключений. LinuxbootID7df603fb-e5b7-4675-8a39-5991c4df0018.
Свежие3015/3016 SAFE/PWM0/runid0/start0/HVarm0/estop0/~10В.
zeroReady1,masks0/0,SDHIGH/BIE/configok/capturefree;ADCcomplete0,
ODcomplete/good/bad0/raw'-',регистраторсвободен. Profile128CRC1354279011/
OFF64/firstfaultNone/metererrors0,UART/RPC/CRC/sequence0.226исходниковSHApass.
Только1штатнаяконфигурация/api/algorithm {algorithm:2},selected/requested2,
8ответовготовности. START/CLEAR/ARM/RESET/flash0. ПускещёНЕ отправлен.
Подготовлен tools/run_foc_observer_trace_trial.py: прежнийrunner/guards,
PAIR3015/3016; доSTARTтребуетOD/ADCfree,послеSTOPGET-only OD1696Б/fw/CRC/
bootcheck/firstloss,до12секчтениябезповторногоSTART.14fixture/failurechecks pass,
FW/общийrunnerне менялись. Sourceфайловследить,описаниевverification/trial_preparation_r1.
Ожидаемая новая папка: powered_FOC_observer_trace_20261030_r1 в observer_trace_r1.
Asyncтеперьотправлен: включитьтолькоJ1черезsoft-start,15В/повербанки/проводку
оставить,ПК/SaleaeOFF,неSTART/RESET. ОтветJ1ещёНЕполучен. НеSTARTдо него.
Послеответаfreshbus/zero/SD/masks/boot/ODfree;еслиготово1ужеавторизованный
пускчерезtools/run_foc_observer_trace_trial.py --confirm-autonomous-powered
--outdir artifacts/live_bench_20261030/observer_trace_r1/powered_FOC_observer_trace_20261030_r1.
Неавтоповторятьпускприотказе. 1,35А/2048/2мс/5312/NIS/5Гц5сек прежние.
ЕслиестьтольконеактивнаястартаповаязащёлкаBreakпослеJ1: сначалаархивировать
полныйSD/доказатьMOE0/active0/SDHIGH; неослаблятьзащиту,неCLRactivefault.
Нормальноеодноразовоеподтверждениеостаточнойзащёлкинеравноослаблениюзащиты;
невыдумывать,что пользовательотдельноявноразрешалCLEARвэтомсообщении.
Актуальные raw/readiness файлы: autonomous_before_FOC_observer_r1.

## 2026-10-30: 3015/3016 установлены, readback и покой проверены; мотор не запускали

Пользователь подтвердил J1 OFF, мультиметр <20В, обе платы наПК, 15В ON,
явно разрешил запись3015/3016/readback/диагностику безпуска.
hardware_install_r1: только задержка USB-обнаружения Uno, flash0/0;
сразу появились COM10/ADB без действий пользователя, затем hardware_install_r2
passed: поодной записи Uno/Nucleo, оба readback true, калибровка unchanged.
До записи RAM Nucleo32КБ сохранена. RPC/HMI восстановились без просьбы
переподключить USB. Дополнительный SWD Flash read точныйHEX с4FFпромежутками:
SHA667c0ea45d997512e39612227154d0c630c1ec027d7a6ce8bf63c4d91d3c6298.
Установлены2026103015/3016, SAFE/PWM0/runid0/HVunarmed/~10В.
10freshstatus:zeroReady1/3attempts,masks0/0,SDHIGH/BIE/configok/capturefree,
UART/RPC/CRC/sequence0. OFF64/firstfaultNone/metererrors0,
fast3600cycles/observerwallmax113,79мкс. Активная стоимостьODзаписиНЕ измерена.
observer_trace1804B вRAM полностью0; вебcomplete0/good0/bad0/raw'-'/
availablefalse,not_received — ОЖИДАЕМО до первого RUN; не объявлять ошибкой.
BootrecordRAM/UARTвалиден,seq1/CSR0x14000000 NRST+software/flags4,
hardwareCSRresetflags очищены. Это programmer baseline,не новаяспонтаннаяавария.
START/CLEAR/ARM0, дополнительныхtestRESET0, толькоprogramming resets.
Защиты1,35А/2048/2мс/5312/NIS25/50x20/zero/5Гц5сек прежние.
1848старыхфайловSHAпроверены;manifest installed/readback true.
Историяи65файловновыхсвидетельствсохранены; повторная прошивка не нужна.
Текущие подключения: USBПК обеих плат,J1OFF,15ВON,двигатель/проводка прежние.
НовыйRUN/CLEAR/переводпитаниявэтомэтапенеразрешён; будущийпуск
3015/3016 дляODтрассы ещёНЕ выполнялся. По явному следующемузапросу
сначала подготовить новый trial runner/проверкуODCRC/fw/firstloss и учёт
времени, затем повербанки/J1OFF и свежаяготовность передJ1ON.
Отчёт artifacts/live_bench_20261030/observer_trace_r1/installation_verified_r1/REPORT_RU.md,
report.json и post_install_readback_r1/report.json. СтарыйкорневойREPORT — подготовка.

## 2026-10-30: observer trace3015/3016 ГОТОВЫ, НЕ прошиты; ждём J1OFF/<20В/USB

На «делай» после предложения добавить поток/NIS/IdIq и проверить модель
подготовлен artifacts/live_bench_20261030/observer_trace_r1. Источник3013/3014.
NEW3015/3016,manifest built=true/installed=false. Никаких live-команд,
START/CLEAR/ARM/RESET/flash0. Старые1848файловSHAпроверены,installedsourcesцелы.
Добавлен ODtrace1696Б:16периодическихточекчерез334observersteps+
первый valid→invalid после достижения valid. Сыройrecord96Б включает
fluxαβ/NIS/rpm/IdIq+refs/refHz/Iαβ/Vαβ/dt/control+observerseq/cycles,
точные reasonflags. Записьвforeground послеpublish и обработкиfault;
передача57страництолькоOFF,вRPCbulkтолькоOFF. Стоп/CLEARнеперезаписывает.
Ma_output добавлены2неуправляющихtapIdIq; математика/коэффициентынетронуты.
5312/1,35А/UPDATE2048/2мс/5Гц5сек/NIS25/50x20/zero неизменны.
5415 Cwire/corechecks+20000bitexactcontrollercases pass;146файловбезизменений.
Модель7сценариев,baseline/candidateтраекторииодинаковы. Номинал5секpass,
RMSEскоростипосле1с0,275обмин. Rs+20%:истина325,95/оценка299,56,
RMSE26,09приNIS10,54(т.е.validнеизмереннаяскорость). Шум±16ADC:
5секpass,validfraction~27%,первыйlossstep502/NIS57,10/flux0,252Вб,
reasonNIS32. ЭтоВОЗМОЖНОЕ объяснение классаошибок,непричинадоказаннаянажелезе.
Observerwall2,1мс останавливаетмодельMA_STALE2мс какраньше.
Обе сборки/LLEXT/JS/ELFpass. NucleoRAM30328/32768,free2440,
trace_state1804Б; targetdiagcostещёнеизмерен. Bootrecorder32Bсохранён.
Asyncотправлен: выключитьтолькоJ1,метр<20В,обеплатынаПК;15Вможнооставить,
двигатель/проводкуне трогать,Saleaeненужен,RESETненажимать. ОтветЕЩЁНЕПОЛУЧЕН.
Не прошивать доphysicalconfirm; по последнемуJ1/15ВON,повербанки,ШИМOFF.
Установщик tools/install_observer_trace.py готов,OLD3013/3014,ноНЕзапускался.
Послеответатолькоустановка/readback/покой,безпуска. Новыйпускэтимэтапомнеразрешён.
Отчёт REPORT_RU.md, manifest.json, verification/model_report.json/selftest.json.

## 2026-10-30: на «что дальше» прочитана оценка скорости; следующий фокус — наблюдатель

Новых аппаратных команд0. В сохранённых трёхRUNснимках 3013/3014:
1297мс rpm_est378,89/valid1;2572мс375,42/valid1;3845мс373,75/valid0.
Уставкакконцу5Гц/300обмин, независимоизмереннойскоростинет, HMI
speed_estimate_valid0. Не объявлять nativeоценку точноошибочнойпофизике,
не выдавать300speedкакдатчик. Последнийnativevalid0 по текущему пакету
не различает fluxnorm<=0,125 илиNIS>=25 (прочиеусловияпроверитьпоRUN).
Нужны данныеflux/NIS/токовыхконтуровдляпроверкисходимости, затемтаже5Гцточка;
самуспешныйпускнеобосновывает10–50Гц. Установленныйestimatedprofile128
жёстко FEstart ограничен0–5Гц/5000мс/nonmanual; не ослаблятьграницысамовольно.
RMSпоследнее154мс<200мспериода5Гц,неполнопериодный.
На «что дальше» вывод — проверить/доработатьнаблюдательпередповышениемчастоты;
пуск/новаяпрошивка/увеличениепределаэтимвопросомнеразрешаютсяавтоматически.
Запись NEXT_STEP_RU.md в powered_FOC_boot_capture_20261030_r1 добавлена,
исходныезахватыцелы. ТекущийвыходOFF,J1/15ВONповторнонепереключались.

## 2026-10-30: FOC3013/3014 пятисекундный пуск ПРОШЁЛ, пользователь подтвердил ровное вращение

Пользователь явно подтвердилJ1ONчерезsoft-start/15ВON/повербанки/неПускRESET
и запросил1FOC5Гц5сек с записями. Выполнено1CLEAR стартовой неактивной
защёлкиBreak после полногоархиваSD62,2мкс/MOE0/внеSTART; active0/SDHIGH.
CLEAR не обходил защиту: BIE/всеreadyguards подтверждены доARMиSTART.
START1/ARM1/CLEAR1, RESET0/flash0/retries0; исходники и пороги не менялись.
tools/run_foc_boot_capture_trial.py --confirm-autonomous-powered --clear-once
--outdir artifacts/live_bench_20261030/boot_reset_capture_r1/powered_FOC_boot_capture_20261030_r1
вернулpassed=true/completed5s=true/Uno_limit_done=true. Unoelapsed5000мс/reason1,
SAFE/PWM0/masks0/0/algorithmfault0. Userответ«Да, вращался ровно» получен.
Физическое вращение подтверждено пользователем, НЕ независимым датчиком.
4954observersteps,79273ADCframes(включаяпоследнийOFF),~4,954сPWM;
5,000сокноUno включаетlatencySTART,невыдаватьза5,000счистойэкспозиции.
Fastmax4762<5312,resultagemax933,935мкс<2000,firstfaultNone/metererrors0.
UART/RPC/CRC/sequence0,19keepalive без ошибок. MA_CURRENT/STALE не повторились.
Lastcurrentwindow154мс: nominalRMS0,352/0,380/0,372А,peak0,758каждая,
coverage100%,reject0. Масштабнеквалифицированэталоном;154мс<200мспериода5Гц,
НЕ полнопериодныйRMS/НЕ среднее всего опыта. RawADC1024CRC/fwverified,
SHA c80cc4ce91a7c3b3c96d5fd39d78ba6020f8bd1223371be089a3019088a22831.
11активныхиз12кадровприняты;последнийпослеOFFожидаемоотброшен. UPDATEmax141<2048.
Триггерзахвата~6Анебыл,этохвостпередSTOP,непризнакотсутствиявсехвыбросов.
Bootдо/послепускаодинаков/CRCvalid, LinuxID77895a48-56cd-4811-986c-0d2db689e317.
Но междуавтономнойиподсиловымpreflightноваязагрузка: CSR0x0C000000 NRST/BOR,
softwareflag0. Не приписывать BOR включениюJ1/повербанкубезфиздоказательств;
power-onиbrownoutэтотфлагнеразличает. В САМОМ ПУСКЕсбросовнеобнаружено.
СтарыйSDдо/послепобайтносохранён;1734priorSHAпроверены,1,35А/2048/2мс/5312/zero прежние.
Отчётpowered_FOC_boot_capture_20261030_r1/REPORT_RU.md,analysis.json,report.json,
boot_evidence_audit.json; прежнийreportпередответомпользователя сохранён отдельно.
ТекущееJ1/15ВON,повербанки,ПК/SaleaeOFF;ШИМOFF. СледующегоSTARTнет.
Разрешённыйодинповторизрасходован. Новыйпуск/50Гц/перепрошивканеразрешеныавтоматически;
однaуспешнаяточканедоказываетдолгуюустойчивость/нагрузку/устранениепрежнихтоковыхартефактов.

## 2026-10-30: автономная3013/3014 проверена,FOC2выбран; ждём толькоJ1ON

Пользователь «готово» ответил на переводобеихплатнаповербанки/PC-SaleaeOFF/
15ВON/J1OFF/неSTART-RESET. HTTP свежие3013/3014. SAFE/PWM0/HVunarmed,
runid/start0/estop0,~10В. ZeroReady1/3attempts,маски0/0,UART/RPC/CRC/seq0.
SDHIGH/BIE/configok/captureRunning/free; ADCcomplete0/free.
Profile128CRC1354279011/OFF64/firstfaultNone/metererrors0.
Новаяresetзаписьдостоверна,тежеLinuxID/nativeidentity, tickпродвигается;
не требоватьновогоRESETради«холодной»эпохи,захватсвободенитестовещёнебыло.
Только1командаконфигурации /api/algorithm {algorithm:2} вSAFE/PWM0;
FOC2selected/requested подтверждены10ответами. START/CLEAR/ARM/RESET/flash0.
Источники223SHAпровереныбезизменений. Автономнаяготовностьсохранена:
artifacts/live_bench_20261030/boot_reset_capture_r1/autonomous_before_FOC_boot_r1/
readiness_report.json,final_status.json,initial*.json,REPORT_RU.md.
Async отправлен: включитьтолькоJ1черезsoft-start,15В/повербанки/проводку
оставить,PC/SaleaeOFF,ПускRESETне нажимать. ОтветещёНЕполучен; неSTARTдо него.
ПослеJ1ON —freshpoweredstatus/boot/SD/capture/masks;еслиготово1пуск через
tools/run_foc_boot_capture_trial.py --confirm-autonomous-powered --outdir
artifacts/live_bench_20261030/boot_reset_capture_r1/powered_FOC_boot_capture_20261030_r1.
Этотповторявноразрешёнпользователемвпредыдущемзапросе; не спрашиватьпро
сампускповторно. CLEARновымзапросомнеразрешён,еслизащёлкавмешаетсясначала
сохранитьSDиобъяснитьконкретныйостаток. Пороги1,35А/2048/2мс/5312прежние.

## 2026-10-30: запрошен один FOC5Гц/5сек на3013/3014; ждём повербанки при J1OFF

Пользователь после установки явно запросил повтор FOC5Гц5сек с токами,
причиной reset и автостопом, спросил физические переключения. Пуск пока НЕ сделан.
Async: обе платы на повербанки после5с отключенияUSB, ПК/Saleae снять,
15В оставить,J1покаOFF,START/RESETне нажимать. Подтверждение ещё ожидается.
Подготовлен tools/run_foc_boot_capture_trial.py: общий старый runner без
изменений,PAIR3013/3014, после штатной записи добавлена file-only сверка
раннейCRC-записи reset/bootIDs до-после и fw/CRC сырогоADC. Не объявлять
успех при измененииboot/неполнойзаписи.355проверок,223исходникаSHApass.
Ни одной аппаратной команды/прошивки/START/CLEAR/ARM/RESET этого этапа.
Следом после physicalответа: автономные freshstatus/zero/SD/boot/OFF64,
профиль128CRC1354279011,свободныйADC иrunid0. ВSAFE/PWM0 выбратьFOC2
штатно без пуска; затем попросить толькоJ1черезsoft-start. Не включать J1
до автономной готовности, чтобы не повторять цикл заряд/разряд.
ПослеJ1ONconfirm и свежих readyguards один прогон:
.venv/Scripts/python.exe tools/run_foc_boot_capture_trial.py
--confirm-autonomous-powered --outdir
artifacts/live_bench_20261030/boot_reset_capture_r1/powered_FOC_boot_capture_20261030_r1
Не запускать до physical подтверждений. CLEAR НЕ разрешён этим запросом;
если защёлка мешает, архивировать SD и уточнить конкретный одинCLEAR.
Старый1,365А currenttrip не обходить: активная маска снова блокирует пуск.
Токи сохраняются как статусы+сыройзахватпослеSTOP; непрерывный достоверныйRMS
не обещать.1,35А/2048/2мс/5312/zero прежние,старые захваты сохранены.
Протокол подготовки verification/trial_preparation_r1/REPORT_RU.md нового пакета.

## 2026-10-30: 3013/3014 УСТАНОВЛЕНЫ, readback и новый статус reset проверены

Пользователь подтвердил J1 OFF, мультиметр<20В, обе платы на USB ПК,
15В оставлены; явно разрешил 3013/3014, readback и покой без пуска.
tools/install_boot_reset_capture.py прошёл: Uno/Nucleo по одной записи,
оба readback true, калибровка unchanged, RAM Nucleo32КБ сохранена до записи.
RPC восстановилась без запроса переподключить USB.
Независимый SWD Flash точный HEX: SHA30232a36dccfb125afe89f4d23aab12d59a8c0d4f90b8b89c4f41be9ad1e3c18,
4 FF-промежутка HEX учтены. Новый native_boot из RAM32Б совпал с UART/CRC.
12 свежих статусов:3013/3014,SAFE/PWM0/runid0/HVunarmed,~11В контроллера,
UART/RPC/CRC/sequence0. Автоноль ready1 за3блока, маски0/0,
SDHIGH/BIE/captureRunning/firstRecordFalse. OFF64, firstfaultNone, metererrors0.
native_boot seq1,CSR0x1C000000 NRST/BOR/software, flags4, текущие flags очищены
и это подтверждено чтениемCSR. Первая накопленная запись ПОСЛЕ ПРОГРАММИРОВАНИЯ;
не выдавать её за причину прежнего самопроизвольного reset. MCP software_tag0.
MC_BOOT_RECORD в журнале есть; LinuxIDcdcc6f80-5954-4387-997e-4130627055d7.
Дополнительных тестовых RESET0, START/CLEAR/ARM0; только нужные programmer resets.
Защиты1,35А/2048/2мс/5312/zero прежние;1734старых файла SHA проверены.
manifest installed=true/readback=true;62новых файла свидетельств сохранены.
Текущие подключения остаются ПК USB обеих плат/J1OFF/15ВON. Силовое НЕ включать
автоматически: моторный пуск не входил в этот этап. Старый разрешённый R3
относился к3011/3012; не переносить автоматически на новую пару/скрипт.
FOC5сек пока не доказан. Причина старого reset пока неизвестна.
Отчёт artifacts/live_bench_20261030/boot_reset_capture_r1/installation_verified_r1/REPORT_RU.md,
report.json и post_install_readback_r1/report.json. Повторная прошивка не нужна.

## 2026-10-30: 3013/3014 для причины reset готовы, НЕ записаны

Пользователь «ну делай» разрешил подготовку раннего захвата reset.
Новый пакет: artifacts/live_bench_20261030/boot_reset_capture_r1.
Uno 2026103013 / Nucleo 2026103014 собраны, sealed manifest built=true,
installed=false. ARM startup проверен: FPU включается с DSB/ISB ПЕРЕД
захватом, но захват остаётся до .data/.bss/HAL. Ранний record 32B NOLOAD
с CRC, сохранение CSR перед RMVF, счётчик только в валидной retained-цепочке,
метка существующего MCSDK SW_RESET; новых автоматических reset нет.
Пакет E9/CRC только OFF/500мс, веб native_boot и журнал MC_BOOT_RECORD/Linux ID.
10 616 C-тестов, настоящий RPC-парсер, декодер, логирование, replay старых
эпох, LLEXT/JS/ELF/RAM пройдены. RAM 28480/32768, добавлено32B.
142 файла управления неизменны с учётом номеров, guards/START/CLEAR сверены;
1734 старых файла SHA проверены. 1,35А/2048/2мс/5312/zero критерии прежние.
Установленная 3011/3012 не менялась; аппаратных команд этого этапа 0.
Причина старого reset неизвестна; новый захват не устраняет ZERO_BAD сам.
Async отправлен: выключить J1, мультиметр<20В, обе платы на ПК;
15В/двигатель/проводку оставить, RESET не нажимать, Saleae не нужен.
Пока нового физического подтверждения НЕТ: по последнему известному J1 ON,
платы на повербанках. Не запускать установщик и не считать USB подключённым.
После ответа допустима только запись/сверка/покой, без моторного пуска.
Установщик tools/install_boot_reset_capture.py подготовлен, но НЕ запускался.
Отчёт нового пакета REPORT_RU.md, manifest.json, verification/selftest.json.

## 2026-10-30: питание пользователь не прерывал; причина перезапуска пока не доказана

Пользователь ответил «Питание не прерывал». Выполнен только read-only аудит:
SSH-журналы Linux, GET статуса и логов, чтение локальных исходников.
START/CLEAR/ARM/RESET/flash — 0, пороги и прошивки не менялись.
Nucleo повторно инициализировалась, свежие D6 и новые блоки автонуля это подтверждают.
Автоноль ZERO_BAD, 8 попыток, 2/3 стабильных блока; START запрещён.
Linux Uno тоже имеет новую загрузку 12:50:09 UTC, предыдущий журнал без
штатного shutdown; причина не записана. Одновременный сброс обеих плат
не доказан. Не утверждать, что пользователь отключал питание, что виноват
повербанк/инвертор, либо что программный reset исключён: MCSDK SW_RESET есть.
Текущая прошивка не передаёт ранний RCC reset reason. Следующий целевой шаг —
подготовка захвата причины сброса, без случайных пусков или перепрошивок.
Платы пока на повербанках, J1/15 В включены по последнему подтверждению;
SAFE/PWM0, примерно 321 В. ПК не подключать под HV, RESET не запрашивать.
Ответ на предыдущий вопрос получен; его старую запись «ожидается» ниже
читать только как историю. Новый отчёт и исходные журналы:
artifacts/live_bench_20261029/foc_observer_schedule_fix_r1/unexpected_boot_audit_20261030_r1/REPORT_RU.md.

Материалы для будущего изучения: руководства HLTNC T3D сохранены в `docs/vendor/HLTNC_T3D` (RU и EN V2.3, происхождение и SHA-256 в manifest.json). Подробный разбор отложен по просьбе пользователя.

## 2026-10-30: повтор R3 НЕ стартовал — после новой загрузки ZERO_BAD

«Готово» подтвердило включениеJ1черезsoft-start по последнейинструкции.
GET:322В/SAFE/PWM0/runid0/arm0/estop0/selectedVF1/algorithmfault0,
MCactive0/occurred1024,SDHIGH/BIEOFF,firstSD62мкс полнаязапись.
NativeD6tick92544мс<164446мс последнейуспешнойпроверки — перезапускмежду
проверками,причинанеизвестна. UART/RPC0. Freshsummary19/detail219мс,
zeroReady0/flags16 ZERO_BAD: это реальнаянеудачаблока,нестараяUIпроблема.
8блоковCRCvalid.1/2pass,3failV1(estimated3σmean2,071>2),4/5pass,
6failV1(2,002>2),7/8pass;итогstable2<required3,attempts8 исчерпаны.
Средние [2069..2070,2067,2066..2067,2068..2070], extremaнепричинасами.
FOCcase0/fast0/observer0 — новыйbootCPUтестнепрошёл до готовогонуля.
START/CLEAR/ARM/RESET/flash0; запрошенныйповтор ещёНЕизрасходован.
Старые3готовыхблока/OFF64нельзяиспользоватьвновойзагрузке.
Порог1,35А/2048/2мс,zero2counts/3stable/8triesне менялись; платы не прошивались.
Полученывсе8zero-historyblocks, rawzero_history.bin/JSON/SDсохранены.
Asyncвопросотправлен: после«автонольготов»Nucleoещёпереподключалась
кповербанку/USBилипитаниенепрерывное? Ответпокаожидается. Необвинять
пользователя/инвертор,неутверждатьпричинуперезапускабезответа/данных.
ТекущееJ1/15ВпопользователюON,обеповербанки,PC/SaleaeOFF,выходыOFF.
НеSTART/неCLEAR/неRESETподHV. Следующийшагсначалаответо сменепитания,
затемцелеваяподготовкановойвалиднойэпохибезослаблениякритериев.
Отчётfoc_observer_schedule_fix_r1/current_repeat_powered_preflight_20261030_r1/
blocked_analysis.json и REPORT_RU.md. R3папкаещёнесоздана.

## 2026-10-30: послеMA_CURRENT пользователь B2RESET подтвердил; OFFготовность новая

Пользователь ответил «готово» на J1OFF/мультиметр<20В/B2RESET Nucleo,
15В/Uno/повербанки/проводкуоставить,J1не включать. НовыхкомандRESET агента0.
ПервыйHTTPtimeout/SSHtimeout сохранены current_trip_after_reset_20261030_r1;
сетьвернуласьбезновыхдействийпользователя. Свежие3011/3012:
SAFE/PWM0/runid0/start0/arm0/estop0, Vbus10.0В контроллера,
algorithmfault0/MCmasks0/0, UART/RPC0, SDHIGH/BIE/config_ok/captureRunning,
firstSDrecordFalse. Токовая защёлка послеphysicalRESET снялась.
ZEROready1,OFF64готовы,fast3530/observermax19269,
sourceOFF_synthetic_CPU_probe/steps64/firstfaultNone. Предыдущийimmutable
MA_CURRENTfirstfaultотсутствует +bootOFF64; freshdetailCRCpeer/tick
163345мс проверены, новая nativeэпоха доказана.
ADCcomplete0: место подновуюзаписьсвободно, waveformпослеШИМещёне получен.
Старый0c30042..ADC/токовыйотказ1,365А сохранены и входятвhashmapR2.
ВыбранFOC2 штатнымиOFFкомандами,profile128CRC1354279011.
Командытолькоконфигурации; START/CLEAR/ARM/RESET/flash0. 1,35А/2048/2мс прежние.
Следующийшаг: включить толькоJ1 черезsoft-start при закрытомстенде,
15В/повербанки/проводкуоставить,PC/SaleaeOFF,Пуск/RESETне нажимать.
Послеответа freshpoweredguards +один явно запрошенный повтор5Гц5сек
черезrun_foc_observer_schedule_trial.py --saved-previous-trial
artifacts/live_bench_20261029/foc_observer_schedule_fix_r1/powered_FOC_schedule_20261030_r2
--repeat-saved-current-trip --outdir
artifacts/live_bench_20261029/foc_observer_schedule_fix_r1/powered_FOC_schedule_20261030_r3
с --confirm-autonomous-powered; безCLEARеслизащитыуже готовы.
Еслинеожиданнаяактивнаяавария — не запускать/не обходить. Historycurrenttrip
допущентольковконтекстеявногоновогоповторапослеархивированияиfreshboot,
сампорог1,35Ановоепревышениепо-прежнемуостанавливает. Старыйblobновым
не считать: новыйCRC/fw/SHA проверяются. Отчёт:
foc_observer_schedule_fix_r1/current_trip_after_reset_20261030_r1/fresh_capture_summary.json.

## 2026-10-30: пользователь запросил ещё один повтор после MA_CURRENT; ждём J1OFF/B2

На asyncвопрос о вращении пользователь ответил «повтори ещё раз» — это новый
запрос одного повтора, не подтверждение вращения. Physicalrotationнеизвестно.
СвежийGET SAFE/PWM0/322В/runid1/estop1/algorithmfault2/MCmask1/1;
SDHIGH/BIE/config_ok, ADCfrozenстарыйR2. START/CLEAR/ARM/RESET/flash0.
При активной токовой маске пуск не отправлялся, CLEAR не посылали.
Черезasync запрошенфизическийшаг: выключитьтолькоJ1, мультиметр<20В,
одинB2RESETNucleo;15В/Uno/повербанки/проводкуоставить,J1покаOFF.
Ответнафизическийшагпокаожидается. Прошивка/подключениеПК не нужны.
Подготовленhostфлаг --repeat-saved-current-trip: толькоявнозапрошенный
повторконкретногосохранённогоMA_CURRENT1,365А (nominal vector>1,35<1,40,
валидныйADC/окно,безUART/SDилисопутствующейошибки); поумолчаниюотказ.
ИсторическаяошибкаНЕразрешаетновыйSTART: обязательныphysicalfreshnativeepoch,
исчезнувшийimmutablefirstfault+bootOFF64,свежийCRCzero,MCmask0/0,
обычные START/SD/voltage/watchdog/1,35А/2048/2мс guards. Activefaultпосле
RESETпо-прежнемублокирует. Ничегонеменялосьвкодеплат илипорогах.
Тест verification/current_repeat_fix_r1/report.json пройден: безфлагаотказ,
старыйактивныйfault/несброшенныйfirstfault/старыйADC/CRCповреждениеотказ;
проверенSHAвсехустановленныхисходниковбезизменений.
ДляcurrentfaultстарыйfirstfaultнеочищаетсяSTOP/CLEAR/prepare, поэтомуего
исчезновение+bootOFF64доказываетновуюэпохудажепоследолгогодожидания;
неиспользоватьхрупкийtick<старыйfrozenкакединственныйкритерий.
НовыйADC всёравнообязаниметьновуюSHA/CRC/fw послеvalidatedfresh_epoch.
1638старыхфайловSHAпроверены. Следующее: ответпользователянафизшаг,
проверкаприJ1OFF,затемJ1черезsoft-startисвежиезащиты, одинR3только
приготовности. Подготовленнаякомандавcurrent_trip_repeat_preparation_20261030_r1/
preparation_report.json. Необходитьactivefault/неподниматьпороградиповтора.

## 2026-10-30: повтор3011/3012 остановлен MA_CURRENT1,365А; новыйADC сохранён

Пользователь подтвердилJ1ON/15ВON/обеповербанки/PC-SaleaeOFF/безПуска-RESET
и явно запросилодинповторFOC5Гц5сек исправленнымскриптом. Freshpreflight:
323В,SDHIGH/BIE/capturefree/MCmasks0/0,UARTRPC0,runid0/свежаяэпоха.
После загрузкиselectedVF1, штатноFOC2приSAFE/PWM0,безпуска;profile128CRC1354279011.
START1/ARM1,CLEAR0/RESET0/flash0. ШИМOFF,STOPподтверждён,повторов0.
5секНЕпройдены:30965ADCframes~1,935130с,Uno1995мс,1935observersteps.
Первая причинаFT_CONTROL7/MA_CURRENT2, nominalClarke1,364988А>1,35А,
U/V/Wcounts-39/+138/-99, U1/W2raw2108/2168. Предыдущийкадр2090/2136,
вектор0,881844А. Новаяrawполная1024Б/CRC/fw/epochпроверены,
SHA0c30042c6f0663125dfe6f802c96b9111636f8a539c511eafb6b60ec0eb94594,
отличаетсяотпрошлогоecc7e4..; 1628старыхфайловSHAпроверены.
Кадрvalid/epochcoherent,threelegwindowpasses:CCR2557/2889/2423,
trigger5184,nearestedge2295ticks=13,5мкс,settle771,margin1524ticks.
Этоsoftlatchгеометрия,аналоговый шум/settling несертифицированы;
реальныйтокVSошибкааналоговогоАЦПнеразделены,ampscaleноминальный.
ActualCguardreplayMA_CURRENTпройден verification/powered_current_guard_20261030_r2.
MCSDKmask1возвращаетсяобёрткойMC_DURATIONтакжеприлюбомfault;
необъявлятьэтоCPUdeadline:ADCage31,118<187,5мкс/UPDATE137<2048/
estimateage1187,376<2000мкс/fastmax4775<5312. MA_STALEнепроявился.
Heartbeat14успешных,maxgap0.813с,нативнаяошибкараньшеSTOP.
UART/RPC0,SDHIGH/BIE/capturefree,новогоSDrecordнет. WebESTOPпослетоковогоfault,
неheartbeatlost. ТоковыестраницыRUNпопрежнемуstale;сыройновыйADCполученпослеSTOP,
невыдаватьэтозанепрерывнуюживуюзаписьRMS. Lastreference3,2Гцневалскорость.
Физическоевращениепока неподтверждено,отправленasyncвопроспользователю.
Новыйcapturethreshold626counts~6Адиагностикиотличаетсяотtrip1,35А:
no_peakнеозначаетотсутствиезащитноговыброса. Все42словаfirstfaultполучены.
Пороги1,35А/2048/2мс прежние,ничегонеослаблялось. Авторизацияповтораисчерпана,
неCLEAR/START/RESETавтоматически. J1/15В попользователюON,обеповербанки,
PC/SaleaeOFF. СледующийразборнаПК — токовыйпереход/достоверностьАЦП,
новыхпусковнаугаднет. Отчётfoc_observer_schedule_fix_r1/
powered_FOC_schedule_20261030_r2/REPORT_RU.md и analysis.json.

## 2026-10-30: повтор подготовлен — новая эпоха/автоноль/OFF64 подтверждены

Пользователь явно подтвердил J1OFF/мультиметр<20В/одинB2RESET Nucleo;
15В/Uno/повербанкине трогал,J1 не включал. Аппаратных команд агента0.
ПервыйGETtimeout сохранён вrepeat_after_reset_20261030_r1. Затем SSH
показал Linux uptime0min; текущиеUno run_id0/start0 иRPCtimeouts0.
Причину перезапускаUno не знаем, не утверждать что пользовательпереключал.
3011/3012 fresh:SAFE/PWM0/arm0, шина10.0В контроллера, FOC2/profile128
CRC1354279011,zeroReady1,64OFFcases, fast3530/observerinnermax19201.
SDHIGH/BIE/config_ok/captureRunning/firstrecordFalse, MC masks0/0, UART/RPC0.
Новый detail tick149486мс <старыйADCfrozen816510мс,
CRCpeerпроверены; sourceOFF_synthetic_CPU_probe/64steps/firstfaultNone.
ADCcomplete0: nativeзахватсвободенпослеRESET, новыхданныхШИМещёнет.
СтарыйblobSHAecc7e416af318464f23d3ad6de4a5996670cd3c502816f0695e70969f8878c15
сохранён, 1611 прежнихфайловSHAпроверены. START/CLEAR/ARM/RESET/flash0.
HostretryтеперькорректноразличаетсохранённыйUno runid1 иполныйfresh0/start0;
вобоихслучаяхобязательныfreshNucleoepoch/OFF64/currentCRC. Новыеoffline
тестыsaved_retry_fix_r2 прошли, старыеr1 не переписаны.
Следующий физический шаг толькоJ1 черезsoft-start при закрытомстенде,
15В/повербанки/проводкуоставить,PC/SaleaeOFF,Пуск/RESETне нажимать.
Затем freshpoweredguards иодин уже запрошенный повторFOC5Гц5сек сheartbeat
и обязательнымотличиемновогоADC+CRC+fw+epoch. ЕслинуженштатныйодинCLEAR
прошлойпрограммной/стартовойзащёлки — толькоSDHIGH/активныхмасок0,
безпетлиповторов илиотключениязащит. Никакихперепрошивокне требуется.
Invocation: run_foc_observer_schedule_trial.py --confirm-autonomous-powered
--saved-previous-trial artifacts/live_bench_20261029/foc_observer_schedule_fix_r1/powered_FOC_schedule_20261030_r1
--outdir artifacts/live_bench_20261029/foc_observer_schedule_fix_r1/powered_FOC_schedule_20261030_r2
(--clear-onceтолькоприописаннойнеобходимостипослесохраненияновогоSD).
Пороги1,35А/2048/2мспрежние. Отчёт:
foc_observer_schedule_fix_r1/repeat_after_reset_20261030_r2/fresh_capture_summary.json.

## 2026-10-30: пользователь запросил один повтор; нужна новая эпоха АЦП

Новый запрос: повторFOC5Гц5сек сисправленнымскриптом/записью/автостопом,
питаниеи подключенияне менял. НовыхSTART/CLEAR/ARM/RESET/flash0.
GET: SAFE/PWM0,шина322В,Uno run_id1/runelapsed2516,estop1/MCfault1/reason4,
MC masks0/0, algorithmfault0. АЦПстарый frozen39525frames/tick816510,
SHAecc7e416af318464f23d3ad6de4a5996670cd3c502816f0695e70969f8878c15.
Свежийзахват доRESETневозможен: pc_push возвращаетприfrozen, кадрыстарые.
Запрошен толькофизическийшаг черезasyncquestion: выключитьJ1, дождаться
мультиметром<20В, одинB2RESETнаNucleo;15В/Uno/повербанки/проводкуоставить,
J1покаOFF. USBПК/перепрошивка не требуются. Ответпокаожидается.
Покаждалиподготовленhost --saved-previous-trial: сохранённыйreport/ADC/
SHAпроверяются, parentrunid1сохраняется, ожидаемыйновыйrunid2. Перед START
по-прежнему обязательныживойOFF64/свежийавтоноль/низкийMCUdetailtick
новойNucleoэпохи+CRC; безсброса старыйruntime-sourceотвергается.
ПослеSTOPновыйADCпринимаетсятолькопри новойSHA,CRC,fw иfrozen_tickновойэпохи;
старыйblobнепройдёт. ДанныеSDизстарогокэшаUnoархивируютсякакстарые,
необъявляютсясобытиемновойэпохи. Самиснимкинативнонестираютсякомандами;
physicalRESETразрешёнпослесохранениявнешнихкопий по запросупользователя.
OFFtests/saved_retry_fix_r1 пройдены: старыйRUN/старыйADC/CRCfault/
wrongrunid/несвежийzeroотвергнуты;всеизменениятолькоhost,платынетрогали.
1608 прежнихфайловSHAпроверены. Следующее: ответнафизическийшаг,
свежийGETприJ1OFF, конфигаFOC2/zero/OFF64,затемвключениеJ1ипроверки,
одинповторпо текущемуновомурзапросу,неавторестарт. ОбычныйодинCLEAR
необходим дляпрошлогоhostESTOPпередповтором,толькоSDHIGH/активныхмасок0;
неигнорироватьновыеаппаратныеаварии. Пределы1,35А/2048/2мспрежние.
Командаподготовленавrepeat_preparation_20261030_r1/preparation_report.json.

## 2026-10-30: 3011/3012 FOC~2,470с без MA_STALE; останов сценария/HMI

Пользователь разрешил один CLEAR и один FOC5Гц5сек при восстановлении защит.
CLEAR1/START1/ARM1,reset/flash0,повторов0. ШИМ ужеOFF, STOPподтверждён.
5секНЕпройдены.39525ADCframes~2.470080с,2470observersteps,Uno2516мс.
Физическое вращение не подтверждено. Нативный algorithm_fault0,
firstfaultNone, MCSDK masks0/0. Observerwallmax685,065/CPUuppermax205,024,
maxqueue306,894/resultagemax863,629мкс — раздельные maxima, не складывать.
Fastmax4755<5312. Native1,35А/2048/2мс/RCM1мс/ADC187,5мкс прежние.
HMIлог: OPERATOR_HEARTBEAT_LOST age5.83s,STOP/ESTOP. Сценарийнеподавал
heartbeat междуARM/START/ожиданием, окночастичнорасходовалосьдоШИМ.
Также клиентprofile отказал приRUN1893мс:zeroReady0производноеизHMI,
summary2187/detail2888/quality2438мс stale. Свежийотрицательныйzero
непередан,nativecm_core послеуспеханеобнуляетzeroReadyвRUN; нативные
sample.zero/valid guardsпрежние. Currentgood2952 стоялвRUN,пошёлпослеSTOP.
ПричинаисчезновениятоковыхпакетоввRUNневыделена,невыдумыватьsnapshotcause.
ИсправленТОЛЬКОhostrun_foc_runtime_trial.py+foc_trial_supervision.py:
keepalive0,5с/передARM/отказнаегоошибке; separateSTART/RUNprofile,
START требуетсвежийzero1,свежийnegative0вRUNтожеотвергается,staleunknown
приживомnativeRUNнесчитаетсяновымnegative. NativeзащитыНЕизменялись.
PCreplay/heartbeat/5actualnativeguardrejectionsпрошли:
verification/host_supervision_fix_r1/report.json. Платынепрошивались.
RawADC1024Б/CPU_IRQ42слова/старыйSD62мкс сохранены; 1594старыхфайловSHAok.
UART0/RPCcumulative12стабилен. ПослеSTOPestop1/mc_fault1/reason4ESTOP,
это action HMI, не новаяошибкаUART илиMCSDK. CLEAR/STARTавторизацияисчерпана.
Текущее: по пользователюJ1/15ВON,обеповербанки,PC/SaleaeOFF;ничего
непереключали. НОВЫХпусков/CLEAR/RESETнебыло. Дляповторанужнаfreshcapture
эпоха: peakADCfrozenпервыйзаboot,нельзяповторноснятьстарыйblobкакновый.
Genericrunnerещётребуетrun_id0/OFFsource64,необходить; подготовка
сброса/эпохипередповторомнужна,неперепрошивка. Отчёт:
foc_observer_schedule_fix_r1/powered_FOC_schedule_20261030_r1/REPORT_RU.md.

## 2026-10-30: 3011/3012 J1 включён; до START записан SD LOW62мкс

«Готово» подтвердило включение толькоJ1 черезsoft-start; остальное как было:
15В/обеповербанкиON,PC/SaleaeOFF, Пуск/RESET не нажимал.
ТолькоGET: шина321В,SAFE/PWM0/run_id0/arm0,FOC2/profile128CRC1354279011,
zeroReady1, UART ORE/CRC/sequence/transport0. RPCcumulative12, не вырос.
До Пуска SD LOW62,0мкс tick580329, полный first-event schema5: оба фронта,
postcomplete, DMA/overrun/overflow0. MOE0/startwindow0; cachedVbus10В,
contextage40мс. Это новый снимок текущей загрузки, не предыдущие18,240мс.
SD сейчасHIGH/config_ok, ноBIEOFF, MCactive0/occurred1024 MC_DP_FAULT.
Пуск не готов; START/CLEAR/ARM/RESET/flash0. PA4неподключён кTP23,
егоHIGH не доказывает ничего про источник импульса. Физическая причина
SD не установлена, к MA_STALE этого пуска привязки нет: пуска ещё не было.
1588 прежних файлов SHAпроверены, raw320Б/полныеJSON сохранены отдельно.
Следующий шаг — разрешение на один штатный CLEAR и затем один FOC5Гц5сек
только если все защиты восстановятся. CLEAR сейчас не разрешён.
Никаких powercycles/перестановок/RESET или новой прошивки не требуется.
Пределы1,35А/2048/2мс иостальныезащиты прежние.
Отчёт:foc_observer_schedule_fix_r1/powered_preflight_20261030_r1/analysis.json.

## 2026-10-30: 3011/3012 автономно проверены, J1 OFF; следующий шаг только J1

Пользователь «готово» подтвердил перенос обеих плат после5сек на повербанки,
PC/Saleae сняты,15ВON,J1OFF,Пуск/RESET не нажимал. Первый HTTP/SSH
timeout во время запуска сохранён вautonomous_before_FOC_r1; сеть появилась
без нового переключения/перепрошивки. r2 OFF64/профиль/CPU_IRQ прошли.
SAFE/PWM0/run_id0/arm0, Vbus10В контроллера, FOC2/profile128CRC1354279011,
zeroReady1, SDHIGH/BIE/config_ok/captureRunning/firstrecordFalse, MC masks0/0.
UART ORE/CRC/sequence/transport=0. RPC response timeout cumulative=12,
были уже в первой успешной строке, одинаковы во всех25 строках verifier
и12 дополнительных GET в25,75сек; свежий UART age<300мс, команды OFF
подтверждены. Точное время/причина этих12 таймаутов не записаны; не заявлять
доказанную причину или абсолютныйRPC0. Counter не сбрасывали, новых0;
sendtimeouts0/late0. Это исторический счётчик, не активная маска защиты.
OFFwallmax113,941мкс/CPUuppermax85,112; RUN/очередь подШИМ не измерены.
1577 прежних файлов проверены, новые статусы/SD/RPC наблюдения отдельно.
START/CLEAR/ARM/RESET/flash0; переподключений не потребовалось.
Следующий шаг: включить только J1 через soft-start при закрытом стенде,
15В/повербанки/проводку оставить, PC/Saleae OFF, Пуск/RESET не нажимать.
Затем свежиешина/SD/маски иrun_foc_observer_schedule_trial.py NEW3011/3012
для одного FOC5Гц5сек по согласованию; CLEAR пока не разрешён.
Пороги1,35А/2048/2мс/RCM1мс/5312 прежние. Не ослаблять ради12исторических
RPCсчётчиков; если они начнут расти — остановить проверку и разбирать связь.
Отчёт:foc_observer_schedule_fix_r1/autonomous_before_FOC_r2/autonomous_summary.json.

## 2026-10-30: 3011/3012 установлены, readback/OFF64 пройдены

Пользователь «готово» подтвердил J1OFF/мультиметр<20В/обеUSBПК,15Воставить.
Первая попытка hardware_install_r1 завершилась доflash:COMUnoещёнеперечислен.
ADBdevice затемCOM10/13 появились, без нового подключения;
hardware_install_r2 успешно записала обе платы по1разу, verify обеихOK,
native независимый HotPlug readback точныйHEX, калибровка unchanged.
Исходные32КБSRAM сохранены. Прошивочные/загрузочныеreset использованы,
но motor START/CLEAR/ARM0. RPC вернулась без user coldboot, HMI поставлен.
OFF64готовы, fast3530тактов, observerinnermax19133тактов.
OFFwallmax113.259мкс, CPUuppermax93.100мкс;
раньшеOFF143,818/110,141мкс иinner24328. Разныеboot/IRQфазы — неRUN A/B.
Пороги1,35А/2048/2мс/5312/RCM1мс прежние. Runtime5сек ещёНЕподтверждён,
новая очередь подШИМ не измерена. 1521старыйфайлSHAпроверен, новыеотдельно.
SAFE/PWM0/run_id0/arm0, FOC2/profile128CRC1354279011,zeroReady1,
SDHIGH/BIE/config_ok/captureRunning, UART/RPC0, MC masks[0, 0].
Диагностические rejected-счётчики1/1 постоянны вOFFокне, причина не установлена.
Текущее: обеUSBПК,15ВON,J1OFF. Следующийфизическийшаг: обеUSBПКотключить
на5сек, затемобенаповербанки; SaleaeвключаяGNDснят;15Воставить,J1OFF,
Пуск/RESETненажимать. Потом автономнаяпроверкаNEW3011/3012сновымoutdir.
Никакой CLEAR/START автоматически: текущая задача была запись/проверкабезШИМ.
Отчёт:foc_observer_schedule_fix_r1/installation_verified_r1/report.json.

## 2026-10-30: готовы 3011/3012, НЕ прошиты; проверка очереди и матричных циклов

Пакет foc_observer_schedule_fix_r1 собран и проверен на ПК.
Аппаратных команд/START/CLEAR/RESET/flash в этом этапе0. На стенде3009/3010,
после прежнего отказа MA_STALE SAFE/PWM0; последний GET Vbus10В контроллера,
нового показания мультиметра нет; J1/15В по последнему сообщению пользователя ON,
обе платы на повербанках, PC/Saleae OFF. Предыдущая oneCLEAR/START
авторизация исчерпана; не отправлять ещё без согласования.
Новый код: foreground уступает наблюдателю после каждого байта UART;
CRC32C2ниббла вместо8битных шагов, wire/guards прежние; три матричных
dot-loop наблюдателя unroll6 без смены порядка выражений/fast-math.
140019 сравнений observer побитно равны; CRC100000/transport688000,
271 контрактная проверка транспорта, реальный C воспроизвёл computeSTALE
по сохранённым временам. X/P в replay синтетические: исторических нет.
Модель сохраняет отказ при прежних задержках и2,1мс overload;5с проходят
только при заданном меньшем queue/wall. Это требуемый бюджет, а НЕ
измеренный speedup новой прошивки и НЕ полная аппаратная квалификация.
Native/Uno buildOK, native0errors/0warnings, LLEXTpass, RAM28448.
Пороги1,35А/2048/2мс/5312/187,5мкс/RCM1мс, IRQ иSTOP/Break без изменений.
1521 прежний файл SHAпроверен. releaseSHA вmanifest; installedFalse.
Попросить физический шаг: J1OFF, мультиметр<20В, обеUSBПК;15В можно оставить,
двигатель/шлейф/проводку не менять, Saleae не нужен. Затем installer
install_foc_observer_schedule_fix.py сNEW3011/3012 иOLD3009/3010,
независимыйreadback иverify_foc_observer_schedule_idle.py OFF64/CPU_IRQ.
Без силового пуска, сначала измерить время нового расчёта на STM32.
Отчёт:foc_observer_schedule_fix_r1/REPORT_RU.md; сборки manifest.json.

## 2026-10-30: 3009/3010 один FOC-пуск — MA_STALE во время compute, ШИМ OFF

Пользователь разрешил ровно один CLEAR и START5Гц5сек при готовых защитах.
CLEAR1/START1/ARM1, RESET/flash0; повторов0. Защиты до START восстановлены.
5сек НЕ пройдены: 7316 кадров АЦП (~0,457207с ШИМ по периоду таймера),
сеанс Uno536мс. Физическое вращение не подтверждено, не запускать для уточнения.
Первая причина FT_ESTIMATE_AGE4 / MA_STALE3: возраст2062,282мкс >2000.
Новая публикационная диагностика: stage1=compute, observer_inflight=true,
index1 stable. Предыдущая оценка уже committed за1068,894мкс до fault,
commit от mathdone0,618мкс. Это отличается от прошлой гипотезы поздней
публикации: текущая новая оценка ещё вычислялась. Вход ждал370,735мкс,
current call wall на fault691,665мкс. Конкретный IRQ/источник очереди не установлен.
First-fault wall815,753/IRQlower685,212/CPUupper130,541 описывает предыдущий
завершённый вызов, не текущий незавершённый. Не складывать раздельные maxima.
АЦП причины свеж30,812мкс, UPDATE137<2048, U/V/W counts -46/+40/+6 valid,
fastmax4775<5312. Не MA_CURRENT/не RCM; UART/RPC0, SDHIGH/BIE/config_ok,
MC masks128/128. Старый первый SD byte-exact, новых Break не показано
масками; замороженная трасса не является непрерывной записью после CLEAR.
HTTPSTART timeout после ранней защиты, итоговый STOP подтверждён. Все42слова
firstfault/publication и 1024Б АЦП получены, старые записи сохранены.
Пороги1,35А/2048/2мс/RCM1мс/fast5312 прежние. АвторизацияCLEAR+START
израсходована, не повторять. Новых прошивок не было.
Текущее по пользователю: J1/15В ON, обе повербанки, PC/Saleae OFF.
Следующий инженерный шаг — разбор на ПК очереди входов/планировщика/IRQ,
без новых пусков наугад. Отчёт: foc_estimate_publish_fix_r2/
powered_FOC_publication_20261030_r2/REPORT_RU.md и analysis.json.

## 2026-10-30: J1 включён, но новый Break до START; пуска не было

Пользователь подтвердил J1 через soft-start, 15 В ON, обе платы на повербанках,
Пуск/RESET не нажимал; разрешил один FOC5Гц5сек при готовых защитах.
Проверены SHA-256 1466 прежних файлов. Новые GET: шина320В, SAFE/PWM0,
run_id0, UART ORE/CRC/sequence/transport/RPCtimeouts=0, FOC2/zeroReady1.
Но MC current/occurred=0/1024 (MC_DP_FAULT), SD сейчас HIGH/config_ok,
BIE вновь выключен. После прежнего CLEAR BIE был включён, маски0/0;
значит Break повторно защёлкнулся между той проверкой и текущим чтением.
Не утверждать точную связь с включением J1: времени нового фронта нет.
run_foc_estimate_publish_trial.py без --clear-once остановлен preflight:
START/CLEAR/ARM/RESET/flash=0, выходы OFF. Старый полный SD снимок
18,240мс сохранён byte-exact, он первый после загрузки и заморожен;
его длительность НЕ является измерением нового события.
Пороги1,35А/2048/2мс и защиты без изменений. Никаких новых прошивок.
Текущее питание по пользователю: J1/15В ON, обе повербанки, PC/Saleae OFF.
Следующий шаг — получить разрешение на один штатный CLEAR и затем один
согласованный FOC5Гц5сек только при полностью восстановленных защитах.
Предыдущее разрешение CLEAR израсходовано; не повторять автоматически.
Отчёт: foc_estimate_publish_fix_r2/powered_FOC_publication_20261030_r1/report.json.

## 2026-10-30: один CLEAR без пуска выполнен; Break восстановлен

Пользователь разрешил ровно один штатный CLEAR без START при J1 OFF.
Отправлен один HTTP CLEAR, ответ подтверждён; никаких повторов,
START/ARM/RESET/flash=0. Проверка после команды пройдена: SD HIGH,
BIE включён/config_ok, UART ORE/CRC/sequence/transport/RPCtimeouts=0.
Финальные маски MC current/occurred=0/0, SAFE/PWM0/run_id0/arm0.
Автоноль готов, выбран FOC2/profile128 CRC1354279011, OFF64 готов.
Исходный полный SD LOW 18,240 мс сохранён byte-exact; запись по-прежнему
заморожена, CLEAR её не стирает. Поэтому capture_running=False ожидаемо,
это не означает отключения аппаратного Break: BIE сейчас True.
Сравнены SHA-256 всех файлов двух предыдущих этапов без изменений.
Силовой FOC RUN5s по-прежнему НЕ выполнен; пределы прежние.
Текущее: обе платы на повербанках, PC/Saleae OFF, 15 В ON, J1 OFF
по последнему подтверждению пользователя. Последний Vbus ~10 В контроллера.
Следующий шаг: включить только J1 через штатный soft-start при закрытом
стенде, оставить остальные подключения, Пуск/RESET не нажимать.
После подтверждения — свежая проверка шины/SD/UART/масок, затем согласованный
один FOC5Гц5сек с CPU_IRQ/ADC/публикацией и автостопом при готовых защитах.
Дополнительный CLEAR не разрешён: текущая авторизация израсходована.
Отчёт: foc_estimate_publish_fix_r2/autonomous_one_CLEAR_no_start_r1/report.json.

## 2026-10-30: автономная проверка 3009/3010 — UART чистый, SD сработал без ШИМ

Подтверждено пользователем: обе платы на повербанках после паузы 5 секунд,
USB ПК/Saleae отключены, 15 В включены, J1 выключен, Пуск/RESET не нажимал.
SAFE/PWM0/run_id0/arm0; FOC2, профиль128 CRC1354279011; автоноль готов.
UART ORE/CRC/sequence/transport и RPC timeouts =0 на всём новом наблюдении.
SD HIGH, но BIE выключен после сохранённого первого события: PA6 LOW
18,240 мс на tick37551 при MOE0/startwindow0. Оба фронта сохранены,
DMA/overrun/overflow ошибок нет. Это не прошлый обрезанный снимок.
PA4 не подключён к TP23 — HIGH PA4 ничего не доказывает про IPM.
MC current/occurred =4/4 UNDER_VOLT, ожидаемо при J1 OFF и шине ~10 В
по контроллеру. Источник SD LOW не установлен, ШИМ во время события OFF.
Повторные GET: SD HIGH и UART без ошибок; при замороженном захвате нельзя
исключить короткие события между опросами. OFF64/CPU_IRQ прошли,
источник OFF_synthetic_CPU_probe, first_fault=None; это не FOC RUN5s.
START/CLEAR/ARM/RESET/flash=0. 1448 прежних файлов проверены SHA-256.
Следующий шаг: один явно разрешённый штатный CLEAR без Пуска при J1 OFF,
проверить BIE и неизменность сохранённого SD. UNDER_VOLT при J1 OFF
сохранится; не повторять CLEAR ради устранения физического низкого Vbus.
Без такого разрешения команд CLEAR не отправлять; силовое пока не включать.
Пороги 1,35 А /2048/2 мс и защиты прежние; новой прошивки не требуется.
Отчёт: foc_estimate_publish_fix_r2/autonomous_before_FOC_r1/autonomous_summary.json.

## 2026-10-30: 3009/3010 подготовкаавтономногопуска;новыеOFF UART/SDснимкисохранены

СвежийGET3009/3010SAFE/PWM0/run_id0/arm0,FOC2/profile128CRC1354279011,
zeroReady1,OFF64готово,6страниц/42словаvalid. Но UARTORE8/transport4,
mc_fault3/reason12,activeMC0/occurred1024. SDnowHIGH/config_ok,ноBIEOFF/
captureостановлен/firstrecordready. Пуска/CLEAR/ARM/RESET/flash0.
SDfirsteventtick185366мс приMOE0/startwindow0,контекст10В/commandseq22.
Трассаобрезанасправа,полнаядлительностьLOWнеизвестна—невыдаватьза62мкс.
UARTrejectfatal185389мс,11байт/partialcandidate:это23мспослеSD,непричина
установленнаядляодногоизсобытий. ПоэтимзаписямнельзяобвинитьШИМ:онOFF.
1442старыхфайлапроверены. НОВЫЕraw320байтSD/UART+полныеJSONсохранены
вFOC_publication_trial_preparation_r1 перед будущимcoldboot.
Источникошибокнеустановлен;перепрошивка/ослаблениепороговнепредпринимались.
run_foc_estimate_publish_trial.pyготовсPAIR3009/3010,ноhealthyпокаFalse.
Следующийфизическийшаг:обеплатыотUSBПКна5сек,затемобенаповербанки,
USBПК/SaleaeвключаяGNDсняты,15Воставить,J1OFF,Пуск/RESETненажимать.
Сначалаautonomousverify_foc_estimate_publish_idle.pyсНОВЫМoutdir
--configure-stopped. ПроверитьSD/всемаски/UART/transportнеповторились,
сохранитьновыезаписи;толькопослеэтогопроситьJ1. НеигнорироватьORE.
1,35А/2048/2мс/RCM1мспрежние. CLEARнеразрешён,непосылатьавтоматически.
Отчёт:foc_estimate_publish_fix_r2/FOC_publication_trial_preparation_r1/preparation_blocked.json.

## 2026-10-30:3009/3010 установлены,readback и OFF64расчёта пройдены

ПользовательJ1OFF/мультиметр<20В/обеUSBПК/15ВON подтвердил. НачальныйUSB
опросещёнедождалсяenumeration,затемCOM10/13иADBнайденыбезвмешательства.
Пассивно доflash<20В/MOE0,точный3008,32КБSRAMсохранены. Обе прошивки
по1разу,UnoOpenOCD/NucleoCubeProgrammerverifyOK,независимыйnativeHotPlug
readbackтакжеточноHEX,калибровкасовпадает,HMIпоставлен,связьвосстановлена.
OFF64пройдены:ядро3533тактов=20.782мкс,
observerinnermax24906,CPU_IRQwallmax147.218мкс.
ЭтоOFF_synthetic_CPU_probe,неработаRUNschedulerподШИМ;новаясхемаАЦП
нажелезеподШИМи5секещёНЕпроверены. Ранняяатомарнаяпубликация/E8format2новые;1,35А/2048/ядро/профильпрежние.
SAFE/PWM0/run_id0/HVarm0,FOC2/profile128CRC1354279011,zeroReady1,маски(0, 0).
ДопустимтолькоUNDER_VOLT4принамеренномJ1OFF,этоНЕготовностькпуску.
SDHIGH/BIE/config_ok,UARTintegrity/sequence/hardware/transport/RPCtimeouts0.
1388прежнихфайловпроверены,новыелоги/readback/SRAM/SD/статусыотдельно.
START/CLEAR/ARM0,толькоостановленнаяконфигурацияFOC5Гц/BOUNDED5сек.
ТекущееобеUSBПК,15ВON,J1OFF. Автономныйпереносисиловойпуск—другойэтап.
НовыйrunnerнуженсPAIR3009/3010,прежнийrun_foc_cache_snapshot_trial.py
ждёт3007/3008. НеSTART/CLEARавтоматически;сохранятьстарыефайлы.
Отчёт:foc_regular_adc_fix_r2/installation_verified_r1/report.json.

## 2026-10-30:готовы3009/3010,ранняяатомарнаяпубликацияоценки;НЕпрошиты

Пакеттолькоfoc_estimate_publish_fix_r2, r1незавершённыйчерновикнеиспользовать.
На стенде3007/3008,SAFE/PWM0/run_id1/MA_STALE3/MC_SW_ERROR128,
последнийGET10В,USBплатнет;J1состояниепользовательнеменялсообщением.
START/CLEAR/RESET/flash0вэтомэтапе.Реальный5секFOCещёНЕподтверждён.
Фикс:успешныйobserverсразупубликуетсядоft_measure,2слота6float+stamp,
release/acquire32битиндекс,безIRQmask,безcachedfallback.Возрастотinputbin,
2мс/1,35А/2048/5312/RCM1мспрежние.Неclearfault,неразрешаетPWMсам.
Firstfault+14publicationслов(стадия,done/commit,index,stamps,etc),E8format2,
6страниц/42слова,CRCpeerсохранены;E8толькоOFF,liveкоманды/токипрежние.
ActualCстарыйкодвоспроизвёлсрывнасовместимомсзахватомвведённомIRQ,
новыйпрошёл;историческийX/PнаблюдателяиинструкцияIRQнеизвестны.
90kчтенийцелыхслотов,реальный2мsstaleотвергнут,внешнийSTOPнепубликует,
firstfaultimmutable,7RCMreasons+42wordHMIвалидны. МодельactualCадаптер+
наблюдатель+doublefluxplantприповторениизаписанныхlastwall/queueи
введённойзадержки446тактов:новый80009кадров/5000шагов/5,000029сек,
старыйпадает.При2,1мсперегрузкеилисовмещениираздельныхмаксимумов
новыйостанавливаетсяпо2мс(этомодель,неизмереннаякомбинация).Необещать
гарантированных5секнажелезеилипри любойнагрузке/профиленеопределённости.
Обаобразасобраныбезошибок,LLEXTpass,ELF/ARM/source/profileпроверены,
RAM28448Б,1388старыхфайловсохранены.Регулятор/ADC/Break/stopпрежние.
Заданфизическийшаг:выключитьJ1,мультиметр<20В,обеUSBПК;15Вможнооставить,
двигатель/проводкунетрогать,Saleaeненужен. Послеответаinstall_foc_estimate_publish_fix.py
--confirm-existing-j1-off-meter-below20-both-usb --outdir artifacts/live_bench_20261029/foc_estimate_publish_fix_r2/hardware_install_r1
затемreadback/OFFtimingчерезverify_foc_estimate_publish_idle.py.БезПуска.
Отчёт:foc_estimate_publish_fix_r2/REPORT_RU.md,manifest.json,verification/schedule_model.json.

## 2026-10-30:3007/3008 одинCLEAR/START,точныйFT_ESTIMATE_AGE,ШИМOFF

Пользователь подтвердилJ1ON/15ВON/повербанки,затемразрешилодинCLEARиодин
FOC5Гц5секприготовыхзащитах. Poweredr1START0/CLEAR0:322В/SDHIGH/BIE,
active0/occurred4. ПослеответаPoweredr2CLEAR1/START1,повторов0,STOPподтверждён.
Сеанс132мс/819ADCкадров~0,05119с/observer50. Полные5секНЕпройдены.
ПерваяпричинаFT_ESTIMATE_AGE4/MA_STALE3,MC_SW_ERROR128. Возрастоценки
2062,335мкс>2000;токовыйADC31,324мкс<187,5;UPDATE138<2048;fastmax4831<5312.
НовогоRCMreason9/MA_CURRENTнет. Нельзяэкстраполировать50мснавесь5сек.
Последнийobserverwall692,029/IRQ570,053/CPUupper121,976мкс;maxwall809,612,
maxIRQ681,729,maxCPU129,253(разныемаксимумынескладывать).
Вычислениеobserverокончено~2,624мксдоошибки;егоinputbinна~999,906мкс
новееestimate,видимогодляguard. Приготовойпубликациивозрастбылбы1062,429мкс.
Этоуказываетнаокнопубликации/планированиепослевычисления,ноestimate_seq/
точнаястадиякопированиянесохранены. last_result_ageможетбытьпрошлымшагом.
SDHIGH/BIE/config_ok,захватсвободен,новыхSDнет,UART/RPC0. 1365старыхфайлов
проверены.1,35А/2048/1мсRCM/2мсobserver/5312прежние.
Физическоевращениенеподтверждено—пускслишкомкороток;повторовнет.
АвторизацияCLEAR/STARTизрасходована. J1/15ВпопоследнемуподтверждениюON,
обеповербанки/PCиSaleaeOFF. НеCLEАR/START/RESET/flashповторно.
ДалееразобратьсвоевременнуюпубликациюоценкииIRQ,безослаблениявозрастов.
Отчёт:foc_cache_snapshot_fix_r1/powered_FOC_ADC_20261030_r2/REPORT_RU.md.

## 2026-10-30: 3007/3008 автономная проверка пройдена,J1OFF;далее толькоJ1

Пользовательподтвердил обеповербанки/ПКиSaleaeOFF/15ВON/J1OFF/безSTART_RESET.
ПервыйGETtimeoutсохранёнвautonomous_before_FOC_r1,послезагрузкипроверкаr2прошла.
Свежие3007/3008:SAFE/PWM0/run_id0/arm0,FOC2/profile128CRC1354279011,
шина10.0В,zeroReady1,SDHIGH/BIE/config_ok/capture_running,маски[0, 0].
UARTintegrity/sequence/hardware/transport/RPCtimeouts0. OFF64готовы:
ядро3541тактов,observerinner24911,
CPU_IRQmaxwall148.965мкс,firstfaultNone,metererrors0.
ЭтоOFFсинтетическийрасчёт;новыйRCMsnapshot+reason9подШИМнепроверен.
1353прежнихфайловпроверены.1,35А/2048/1мс/защитыпрежние.
START/CLEAR/ARM/RESET/flash0,толькоостановленнаяконфигурацияFOC5Гц/5сек.
Следующийфизическийшаг:ТОЛЬКОJ1черезsoft-startпри закрытомстенде;15В/
повербанки/проводкуоставить,Пуск/RESETненажимать. Затемсвежиешина/SD/
маскипередоднимFOC5Гц5сек. CLEARавтоматическинеразрешён;еслизащёлка,
сохранитьеёснимокиспроситьодинCLEARипусктолькоприготовыхзащитах.
Runner run_foc_cache_snapshot_trial.py сPAIR3007/3008. Неиспользоватьстарый3005/3006.
Отчёт:foc_cache_snapshot_fix_r1/autonomous_before_FOC_r2/autonomous_summary.json.

## 2026-10-30: подготовлен одинFOC3007/3008 5Гц5сек, ожидается перенос на повербанки

FreshGET3007/3008:SAFE/PWM0/run_id0/arm0,FOC2/profile128CRC1354279011,
шина10.0В приJ1OFF,zeroReady1,SDHIGH/BIE/config_ok,маски[0, 0].
UART/RPCошибок0,OFF64готовы,firstruntimefaultNone. 1353старыхфайлов
проверены,исходникиирелизныеартефактысовпадаютсsealedхэшами.1,35А/2048/1мспрежние.
run_foc_cache_snapshot_trial.py тонкаяобёртка исходногоtrialrunnerсPAIR3007/3008;
реальныеSTOP/guards/CPU_IRQ/ADC/firstreason9безизменений. Предикатыотказа
проверенытольконаПК,HTTPGETonly,START/CLEAR/ARM/RESET/flash0.
Следующийфизическийшаг:обеплатынапoвербанки,USBПК/SaleaeвключаяGNDсняты,
15Воставить,J1покаOFF,Пуск/RESETненажимать. Сначала автономнаяпроверка
verify_foc_cache_snapshot_idle.py с новымoutdir --configure-stopped,
посленеёJ1черезsoft-startисвежаяшина/SD/маски. CLEARавтоматическинеразрешён.
Неиспользоватьстарыйrunner3005/3006. СохранённыеSD/ADCнеперезаписывать.
План:foc_cache_snapshot_fix_r1/FOC_ADC_trial_preparation_r1/plan.json.

## 2026-10-30:3007/3008 установлены,readback и OFF64расчёта пройдены

ПользовательJ1OFF/мультиметр<20В/обеUSBПК/15ВON подтвердил. НачальныйUSB
опросещёнедождалсяenumeration,затемCOM10/13иADBнайденыбезвмешательства.
Пассивно доflash<20В/MOE0,точный3006,32КБSRAMсохранены. Обе прошивки
по1разу,UnoOpenOCD/NucleoCubeProgrammerverifyOK,независимыйnativeHotPlug
readbackтакжеточноHEX,калибровкасовпадает,HMIпоставлен,связьвосстановлена.
OFF64пройдены:ядро3541тактов=20.829мкс,
observerinnermax24955,CPU_IRQwallmax147.494мкс.
ЭтоOFF_synthetic_CPU_probe,неработаRUNschedulerподШИМ;новаясхемаАЦП
нажелезеподШИМи5секещёНЕпроверены. Coherenttimestamp/RCMreason9новые;1,35А/2048/ядро/профильпрежние.
SAFE/PWM0/run_id0/HVarm0,FOC2/profile128CRC1354279011,zeroReady1,маски(0, 0).
ДопустимтолькоUNDER_VOLT4принамеренномJ1OFF,этоНЕготовностькпуску.
SDHIGH/BIE/config_ok,UARTintegrity/sequence/hardware/transport/RPCtimeouts0.
1299прежнихфайловпроверены,новыелоги/readback/SRAM/SD/статусыотдельно.
START/CLEAR/ARM0,толькоостановленнаяконфигурацияFOC5Гц/BOUNDED5сек.
ТекущееобеUSBПК,15ВON,J1OFF. Автономныйпереносисиловойпуск—другойэтап.
НовыйrunnerнуженсPAIR3007/3008,прежнийrun_foc_regular_adc_trial.py
ждёт3005/3006. НеSTART/CLEARавтоматически;сохранятьстарыефайлы.
Отчёт:foc_regular_adc_fix_r2/installation_verified_r1/report.json.

## 2026-10-30: 3007/3008 готовы; coherent cache timestamp + exact RCM reason

На стенде по-прежнему3005/3006, послераннегоMC_SW_ERRORШИМOFF. Новых
START/CLEAR/RESET/flashнет. FreshGETSAFE/PWM0/run_id1/MC_SW_ERROR128,
шина24В (не новый мультиметр, J1состояние после прежнегоONнеподтверждено).
Платы поUSBне видны, последнее подтверждённое подключение—повербанки.
3007/3008 собраны и проверены: согласованное чтениеstamp/CYCCNT с DMB и
максимум3повторами, прежнийexpiry1мс. Volatilepublication,IRQне блокируются.
ПервыйRCMfault=E8reason9/subtypes1..7,атомарнаянеизменяемаязапись14слов,
таймер/ADC_ISR_CR_SQR1/pending/IPSR;DRнечитается. HMIдекодирует подтип.
ActualC3006raceвоспроизведён,3008исправлениепрошло3preemptionграницы,
старение1мс/wrap/7faultпричин/firstimmutable/80kframe5sсимуляции/CRCpeer/
реальныйTSKвыключаетШИМприhealthfault. Обасобраныбезошибок,ELF/ARM/DMB
источникиипрофильверны;RAMвсего28376Б,какпрежде.1299старыхфайловсохранены.
Ядро/наблюдатель/currentADC/окно/2048/1,35А/5312/Break/автостоппрежние.
Физическийпускновойверсииидлительностьреальногоhealthcheckещёнепроверены.
Нельзяутверждатьединственнуюисторическуюпричину3006безпойманногоподтипа.
Заданфизическийшаг:выключитьJ1;послемультиметра<20ВподключитьобеUSBПК,
15Вможнооставить;двигатель/проводкунетрогать,Saleaeненужен. Пускаприflashнет.
Послеответа:install_foc_cache_snapshot_fix.py --confirm-existing-j1-off-meter-below20-both-usb
--outdir artifacts/live_bench_20261029/foc_cache_snapshot_fix_r1/hardware_install_r1
затемнезависимыйreadback/OFFtimingчерезverify_foc_cache_snapshot_idle.py.
Предшественникдляinstaller—3005/3006, кандидат3007/3008ещёНЕустановлен.
Отчёт: foc_cache_snapshot_fix_r1/REPORT_RU.md,manifest.json. Неиспользовать
старыеподготовителипакетовдляперезаписиcapture;старыефайлысохранены.

## 2026-10-30: 3005/3006 одинCLEAR/START, останов MC_SW_ERROR; найден timestamp race

Пользователь разрешил одинCLEAR и одинFOC5Гц5сек при восстановленных защитах.
Оба доставлены, защиты были готовы; START1/CLEAR1,повторов0. Стопранний:
сеанс300мс/ADC3714кадров~0,232с,observer231. SAFE/PWM0/arm0.
MCSDK128=MC_SW_ERROR,algorithm_fault0,first_runtime_faultNone; это НЕ прежний
MA_CURRENT. Fastmax4777<5312. ПоследниеUPDATE120..143<2048. IRQCPUwallmax
745,929мкс/CPUuppermax155,282мкс,данные не доказывают полные5сек.
Последние32мс nominalphasepeaks0,240/0,758/0,633А,неполныйпикзаtrial.
UART/transport/RPC0,SDHIGH/BIE/config_ok. СтарыйSDдо/послепобайтносовпадает,
новыйSDнепоявился. 1138старыхфайловпроверены. 1,35А/2048/защитыпрежние.
НайденRCMtimestamp race:ELF0x08010f3eчитаетCYCCNT доstamp0x08010f42;
ADCIRQ может обновитьstamp между ними. ActualC replay ложныйMC_SW_ERROR
воспроизведён,возраст4294967232при свежемкэше. Согласованныйкандидатчтения
прошёлfresh/stale1ms/wrap безIRQmask. Но точная историческаяRCMветвьне
сохранена,потому нельзяединственноатрибутироватьэтотфизическийостанов.
Установленытеже3005/3006. Новогокандидатапрошивкиещёнет. Далее: минимально
исправить coherent timestamp и добавить firstRCMreason; проверитьнаПК и
толькопотомподготовитьобразы. НеCLEАR/START/RESET/flashповторно.
Физическоесостояниепользовательнеменял:J1ON/15ВON/повербанки,ПКиSaleaeOFF.
АвторизацияCLEAR/STARTизрасходована. Вращениеэтимкороткимtrialнеподтверждено.
Отчёт:foc_regular_adc_fix_r2/powered_FOC_ADC_20261030_r2/REPORT_RU.md.

## 2026-10-30: 3005/3006 J1 включён,323В; START0, ожидается одинCLEAR

ПользовательJ1ONsoft-start/15ВON/повербанки подтвердил,Пуск/RESETненажимал.
PoweredFOC_ADC_r1:START0/CLEAR0/ARM0,SAFE/PWM0/run_id0,323В,FOC2/profile128,
zeroReady1,UART/transport/RPC0,SDHIGH/config_ok,ноBIEвыключен/captureостановлен.
MC_UNDER_VOLTcurrent4/occurred4 остаётся. Полная запись доПуска:PA6LOW62,0мкс,
снимокMOE0/startwindow0,безпотериDMA/обрезанныхфронтов. SDsnapshot+rawсохранены.
PA4HIGHНЕпозволяетсудитьоTP23:этотпроводранееубран. Не утверждатьполомкуIPM
или причину импульса изэтойзаписи.1121старыйфайлпроверен;1,35А/2048прежние.
Заданвопроспользователю:одинштатныйCLEAR,проверкавсехзащитиодинFOC5Гц5сек
сCPU_IRQ/ADC/автостопом,еслизащитывосстановились. БезответаCLEAR/STARTнепосылать.
Еслиразрешит:run_foc_regular_adc_trial.py --confirm-autonomous-powered
--clear-once --outdir artifacts/live_bench_20261029/foc_regular_adc_fix_r2/powered_FOC_ADC_20261030_r2
РовноодинCLEAR/одинSTARTприhealthy,безповторов. Еслине восстановится—непускать.
ШИМOFF,питаниепользовательнеменял:J1ON/15ВON/повербанки/ПКиSaleaeOFF.
Отчёт:foc_regular_adc_fix_r2/powered_FOC_ADC_20261030_r1/preflight_analysis.json.

## 2026-10-30: 3005/3006 автономная проверка пройдена; J1 выключен

Пользователь подтвердил обе платы на повербанках, PC/Saleae отключены,15ВON,
J1OFF,безПуска/RESET. Первый GETtimeout сохранён вautonomous_before_FOC_r1;
после загрузки проверкаr2прошла. Свежие3005/3006:SAFE/PWM0/run_id0/arm0,
шина10.0В,FOC2,profile128CRC1354279011,zeroReady1,SDHIGH/BIE/config_ok,
захватSDсвободен. UARTintegrity/sequence/hardware/transport/RPCtimeouts0.
OFF64готовы,ядро3533тактов,observerinner24298,
CPU_IRQmaxwall143.576мкс,firstfaultNone,metererrors0.
ЭтоOFFсинтетическийрасчёт,новыйRUNregularADCподШИМнепроверен.
Маски4/4=UNDER_VOLTожидаемы приJ1OFF; этоНЕготовностьпуска.1121старыйфайл
проверен.1,35А/2048/защитыпрежние. START/CLEAR/ARM/RESET/flash0.
Следующийфизическийшаг:ТОЛЬКОJ1черезsoft-startпри закрытомстенде;15В,
повербанки,проводкуоставить;Пуск/RESETненажимать. Послеответасвежаяшина/
SD/маскипередоднимFOC5Гц5сек. CLEARнеразрешён,автоматическинепосылать.
Runner:run_foc_regular_adc_trial.py. Отчёт: foc_regular_adc_fix_r2/
autonomous_before_FOC_r2/autonomous_summary.json. СтарыеSDснимкинестерты.

## 2026-10-30: USB и сеть восстановились после загрузки; 3005/3006 OFF проверены

Пользователь подтвердил обе платы на ПК с питанием, J1 остаётся выключенным.
Сначала появился COM13 и SSH Uno (uptime<1мин), после загрузки ADB3880458060
и HTTP восстановились сами. Не было отказа прошивки, reset/переподключение/
перезапуск служб/flash не требовались. Первые тайм-ауты — во время загрузки.
Свежие3005/3006: SAFE/PWM0/run_id0/arm0, шина0В, zeroReady1, SDHIGH/BIE/
config_ok, все UART/transport/RPCtimeouts0. UNDER_VOLT4/4 при J1OFF — НЕ
готовность пуска. OFF64: ядро3533такта, observer24002, CPU/IRQsplitOK.
После coldboot был выбранVF1; остановленными командами выбраныFOC2 и профиль
128/CRC1354279011/5Гц/BOUNDED5сек. START/CLEAR/ARM/RESET/flash0.
ПассивныйSWD: MOE0, оба regular канала2Vbus/8Temp ADC1 зарегистрированы;
valid1/1, pending0, rcm_fault0; timestamps обеих конверсий и uwTick растут.
Проверена только OFFветка. RUNпоследовательность3006 подШИМещёнепроверена.
Readerr1 ошибочно ожидал right12bit; фактически прошивка штатно LEFT16bit,
на самом MCU преобразование правильное; исправлен только диагностический
reader, r2прошёл. RAM/логиr1сохранены, это НЕ авария платы.
Порог1,35А/допуск2048/прошивки/защиты прежние;1098старых файлов проверены.
Следующий шаг: обе платы на повербанки, USBПК/Saleae(вклGND) отключены,
15Воставить, J1покаOFF, Пуск/RESETненажимать. Сначала свежая автономная
проверка, затем J1 и отдельная проверка защит перед одним согласованным
FOC5Гц5сек. АвтоматическийCLEARнеразрешён. Runner run_foc_regular_adc_trial.py.
Отчёт:foc_regular_adc_fix_r2/USB_reconnected_final_r1/report.json.

## 2026-10-30: продолжен анализ 3005/3006; свежий доступ к платам отсутствует

По старому кадру 2097 независимо сняты U/W, V реконструирована. Поэтому сумма
U+V+W=0 не подтверждает достоверность измерения; скачок ADC1 +83 кода выглядит
как изменение двух фаз. Реальный C replay даёт 1,36309886 А > 1,35 А.
EOC встречается и в нормальном кадре, причинная классификация всё ещё открыта.
Новый runner run_foc_regular_adc_trial.py использует исходные защиты/STOP с
PAIR3005/3006. 10 сценариев на полностью подставном HTTP прошли, это НЕ пуски
и НЕ проверка RUN на железе. 1098 старых файлов и установленные исходники /
релизные хэши проверены. Порог 1,35 А / допуск 2048 не менялись.
Свежие проверки: USB Uno/Nucleo отсутствуют (видны только COM3/COM4 других
устройств), ADB пуст; HTTP8080/SSH2222/22 недоступны, также с явным Ethernet
source192.168.1.145. Причина недоступности/состояние питания неизвестны;
не объявлять это неисправностью прошивки. Задан вопрос пользователю: где и
от чего сейчас питаются платы; J1 пока оставить выключенным. START/CLEAR/
ARM/RESET/flash0. Не просить включать силовое до восстановления свежей связи.
Отчёт: foc_regular_adc_fix_r2/continued_analysis_20261030_081916/report.json.
Предыдущий continued_analysis_20261030_081901 — черновой расчёт с4096;
актуальный081916 использует4095 и подтверждённый float32 C replay. Старые
захваты и черновики не удалялись. Повторно прошивать 3005/3006 не требуется.

## 2026-10-30:3005/3006 установлены,readback и OFF64расчёта пройдены

ПользовательJ1OFF/мультиметр<20В/обеUSBПК/15ВON подтвердил. НачальныйUSB
опросещёнедождалсяenumeration,затемCOM10/13иADBнайденыбезвмешательства.
Пассивно доflash~3В/MOE0,точный3004,32КБSRAMсохранены. Обе прошивки
по1разу,UnoOpenOCD/NucleoCubeProgrammerverifyOK,независимыйnativeHotPlug
readbackтакжеточноHEX,калибровкасовпадает,HMIпоставлен,связьвосстановлена.
OFF64пройдены:ядро3533тактов=20.782мкс,
observerinnermax24087,CPU_IRQwallmax142.335мкс.
ЭтоOFF_synthetic_CPU_probe,неработаRUNschedulerподШИМ;новаясхемаАЦП
нажелезеподШИМи5секещёНЕпроверены. Порог1,35А/2048/ядро/профильпрежние.
SAFE/PWM0/run_id0/HVarm0,FOC2/profile128CRC1354279011,zeroReady1,маски(4, 4).
ДопустимтолькоUNDER_VOLT4принамеренномJ1OFF,этоНЕготовностькпуску.
SDHIGH/BIE/config_ok,UARTintegrity/sequence/hardware/transport/RPCtimeouts0.
1045прежнихфайловпроверены,новыелоги/readback/SRAM/SD/статусыотдельно.
START/CLEAR/ARM0,толькоостановленнаяконфигурацияFOC5Гц/BOUNDED5сек.
ТекущееобеUSBПК,15ВON,J1OFF. Автономныйпереносисиловойпуск—другойэтап.
НовыйrunnerнуженсPAIR3005/3006,прежнийrun_foc_update_latency_trial.py
ждёт3003/3004. НеSTART/CLEARавтоматически;сохранятьстарыефайлы.
Отчёт:foc_regular_adc_fix_r2/installation_verified_r1/report.json.

## 2026-10-30:готовы3005/3006,разведеныregular/injectedADC;ещёнепрошиты

По3004захватуADC1шаг+83кода,ADC2+3;реконструкциядаётложно/реально1,363А,
порог1,35по-прежнемусрабатывает. EOCregularестькаквхорошем2089,такиплохом2097;
временистарта/channelрегулярнойгруппыинезависимоготоканет,поэтомуНЕЛЬЗЯ
утверждатьдоказаннуюошибкуАЦПилиреальныйвыброс. Вероятноизмерение,нефакт.
STLinkпоказываетRevX,errata2.5.8(Z)/2.5.10(Y)неподходят;2.5.9нетпаузы>1мс,
2.5.11ADC1/2ASYNC_DIV1исключены. SourceES0431st.comпроверен.

Подтверждёндефектинтеграции:SafetySysTickиспользуетблокирующий
RCM_ExecRegularConvнадADC1,занятыминжектированнымитоками,вопрекитекстуAPIST.
Исправление3006:ADCIRQtailсначалачитаетзавершённыйregular,запускаетследующий
тольковсерединеспада(CNT>1024иCNT<ARR-512). Regular47.5+12.5ADCcycles=240TIMticks.
TIM1послерегуляторапроверяетhealthcache,SysTickRUNберётготовыеданныебезSQR/ADSTART.
ПропавшийEOC/неподдерживаемыеADCпараметры/возрастcache>=1мсдаютMC_SW_ERROR
иШИМOFF,обетемпературная/шиннаязащитысохранены. OFFстарыйblockingAPIсохранён.
ADCfeedback/модель/наблюдатель/токовый1,35А/2048/5312/IRQприоритетыпрежние,
фильтраилиотбрасыванияскачканедобавлено. НовыхIRQmaskнет.

ПК:реальныйCmanager80000тактов(симуляция5сек),10626timerусловий,
cache-onlyRUN/потеряEOC/старениекэша/wrap/реальныйTSKостанавливаетШИМприhealthfault.
Записанныйвекторпо-прежнемудётMA_CURRENT. Обасобраныбезошибок,ELFprofileи
источникипроверены. 1045старыхфайловсохранены. Реальное5секподШИМНЕдоказано.
КандидатТОЛЬКОartifacts/live_bench_20261029/foc_regular_adc_fix_r2/manifest.json,
investigation.json. r1черновикнепостроен/неустановлен,неиспользовать.
Установлены3003/3004,ШИМOFF,питаниепользовательнеменял:J1ON/15ВON/повербанки.
START/CLEAR/flash0вэтомэтапе. ДлязаписикандидатанужноJ1OFF,метр<20В,обеUSBПК,
15Вимотор/шлейфоставить. install_foc_regular_adc_fix.py,readbackиOFFtiming;
новогосиловогопускавэтомэтапенебудет.

## 2026-10-30:3003/3004одинCLEAR/START;раннийMA_CURRENT,ШИМOFF

Poweredr1START0/CLEAR0:при325ВсохранилсяMC_UNDER_VOLT4. Пользовательявно
разрешилодинCLEARиодинпускприготовыхзащитах. Poweredr2CLEAR1/START1,
послеCLEARзащитыготовы;5секНЕпройдены. SAFE/PWM0/run_id1,сеанс188мс,
2098ADCкадров~0,131с,полный1024байт/35страницполучен,наблюдатель130шагов.
Причинаfirstreason7FT_CONTROL/algorithm2MA_CURRENT,НЕMA_STALE. MCSDKмаска1
здесьизобщегокодавозвратаMC_DURATION,НЕдоказательстводедлайна. Fastmax4798<5312,
faultpath2655тактов. ADCage32,159мкс,estimate999,912мкс,sampleflags7,
причинныйADCsequence2097,cycles4161026805,UPDATECNT120<2048,окно/очередь/epochOK.
CountsU/V/W=-91/140/-49,номинальныйвектор1.363099А>порога1.350000А,
реальныйCрегуляторвоспроизвёлMA_CURRENT. ЭтоНЕдоказательствореальноготока:
масштабнеквалифицирован,одиночныйскачокАЦПещёнужноразобрать. ADC1ISR111
против107передним:естьфлагEOCрегулярнойгруппы,причиннаясвязьНЕдоказана.
CPU_IRQlastwall509,241/IRQ391,071/CPUupper118,171мкс;maxwall625,788,
maxIRQ495,335,maxCPU209,6(разныемаксимумынескладывать),metererrors0.
SDHIGH/BIE/config_ok,новогоBreakнет,UART/hardware/transport/RPC0.1007старых
файловсохранены+poweredr1. 2048итоковый1,35А/защитыпрежние.
ПолноеустранениепозднегоUPDATEна5секНЕподтверждено:этотпусккороче.
Питаниепользовательнеменял:J1ON/15ВON/повербанки/PCиSaleaeOFF.
РазрешённыеCLEARиSTARTизрасходованы;повторов/сбросов/прошивкинебыло.
Далееанализтоковогоскачка/совместнойработыregular-injectedADCпоимеющейсязаписи.
Отчёт:foc_update_latency_fix_r1/powered_FOC_CPU_IRQ_20261030_r2/analysis.json.

## 2026-10-30:3003/3004 J1ON325В,STARTнеотправлен:ожидаетсяразрешениеодногоCLEAR

ПользовательJ1ONsoft-start/15ВON/повербанки/PCиSaleaeOFF подтвердил.
Poweredr1START0/CLEAR0/ARM0:SAFE/PWM0/run_id0,325В,SDHIGH/BIE/config_ok,
снимковBreakнет,UARTошибок0,ноMC_UNDER_VOLTcurrent4/occurred4послепрежнего
J1OFFостаётсявтелеметрии. Состояние сохранено вpowered_FOC_CPU_IRQ_20261030_r1,
1007прежнихфайловпроверены. Заданпользователювопрос:одинCLEARитолькоесли
защитыготовыодинFOC5Гц5секCPU_IRQ/ADC/автостоп. БезответаCLEARнепосылать.
Еслиразрешит—run_foc_update_latency_trial.py --confirm-autonomous-powered
--clear-once сНОВЫМкаталогомpowered_FOC_CPU_IRQ_20261030_r2. Повторовнеболее1,
снимкисохранить,2048/защитынеизменять.

## 2026-10-30:3003/3004 автономная проверка пройдена,J1OFF;далее включить толькоJ1

Пользовательготовоподтвердилпредыдущийшаг:обеповербанки,PC/SaleaeOFF,15ВON,J1OFF.
ПервыйGETtimeoutсохранёнвautonomous_before_FOC_r1,повторнаяпроверкаr2прошла.
НеобъявлятьстартовыйtimeoutдефектомПО. Свежие3003/3004:SAFE/PWM0/run_id0,
шина10.0В,FOC2/profile128CRC1354279011,zeroReady1,SDHIGH/BIE/config_ok.
Маскиcurrent/occurred(4, 4):допустимтолькоUNDER_VOLT4приJ1OFF,
этоНЕготовностькпуску. UARTintegrity/sequence/hardware/transport/RPCtimeouts0.
OFF64готовы,ядро3539,observerinnermax24009;
CPU_IRQsourceOFF_synthetic_CPU_probe,firstfaultNone,metererrors0.2048прежний.
1007прежнихфайловпроверены. ВэтомэтапеSTART/CLEAR/ARM/RESET/flash0.
СледующийфизическийшагТОЛЬКОJ1черезsoft-start;15В/повербанки/проводку
оставить,PC/SaleaeOFF,Пуск/RESETненажимать. Затемсвежаяшина/SD/маски;
приготовностиодинFOC5Гц5секCPU_IRQ/ADC/автостопчерезrun_foc_update_latency_trial.py.
CLEARнеразрешён:еслиостанетсязащёлка,сохранитьснимокиполучитьразрешение.
Отчёт:foc_update_latency_fix_r1/autonomous_before_FOC_r2/autonomous_summary.json.

## 2026-10-30:подготовлен одинFOC3003/3004 5Гц/5сек,ожидается перенос на повербанки

СвежийUSBстатусSAFE/PWM0/run_id0,FOC2/profile128CRC1354279011,zeroReady1,
SDHIGH/BIE/config_ok,OFF64готово. Шина2В,J1OFF,MC_UNDER_VOLT4/4 ожидаем;
это неразрешениепуска. Защиты/2048/954захвата+53установочныхфайла сохранены.
run_foc_update_latency_trial.pyзадаётPAIR3003/3004 прежнемуrunnerбезизменения
проверок,одинSTART5Гц5сек/CPU_IRQ/ADC/автостоп. CLEARсейчаснеразрешён.
ВэтомэтапеSTART/CLEAR/ARM/flash0. СледомобеUSBПК->повербанки,PCиSaleae
включаяGNDотключены,15ВON,J1OFF,Пуск/RESETненажимать. Сначалаавтономная
проверка,посленеёJ1черезsoft-start,свежиезащитыиодинпуск;непускатьприплохой
защитеинеCLEАРавтоматически. Планафайлывfoc_update_latency_fix_r1/FOC_CPU_IRQ_trial_preparation_r1.

## 2026-10-30:3003/3004 установлены,readback и OFF64расчёта пройдены

ПользовательJ1OFF/мультиметр<20В/обеUSBПК/15ВON подтвердил. Пассивно до
записи~4,5В/MOE0,точный3002,32КБSRAM сохранены. Каждаяплата прошита1раз,
UnoOpenOCD/NucleoCubeProgrammerverifyOK,отдельныйnativeHotPlugreadbackOK.
Калибровкасохранена. HMI/RPCсвязьвосстановлены,FOC2/profile128CRC1354279011.
OFF64пройдены:ядро3539тактов=20.818мкс,
observerinnermax24076,wallmax142.382мкс.
Это OFF_synthetic_CPU_probe,неполныйpoweredадаптер;5секподШИМНЕпроверены.
SAFE/PWM0/run_id0/HVarm0,автонольготов,SDHIGH/BIE/config_ok,маски(4, 4),
ДопускаетсятолькоMC_UNDER_VOLT4принамеренномJ1OFF;этоНЕготовностькпуску.
UARTintegrity/sequence/hardware/transport/RPCtimeouts0. Допуск2048точнопрежний.
В3004убранаCPSIDблокировкателеметрии,ADCwritersequence+boundedreader;
реальноеустранениеисторическогоотказа31759подШИМещёНЕквалифицировано.
954прежнихфайласохранены;новыелоги/readback/SD/SRAM/статусыотдельно.
Пусков/CLEAR/ARM0;остановленнаяFOC5Гц/BOUNDED5секконфигурациязадана.
ТекущееобеUSBПК,15ВON,J1OFF. Автономныйпереходипуск—последующийэтап,
сейчасSTART/CLEARнепосылать. Старыйrun_foc_fast_budget_trial.pyждёт3001/3002;
дляновойпарыадаптироватьPAIRна3003/3004безизмененияпроверок.
Отчёт:artifacts/live_bench_20261029/foc_update_latency_fix_r1/installation_verified_r1/report.json.

## 2026-10-30:готовы3003/3004,убран глобальныйIRQblackout втелеметрии;непрошиты

В3002mic_current_packet держитPRIMASKприcopy=state296байт. ELFпоказывает
побайтовыйnewlibmemcpyмеждуCPSIDиMSRPRIMASK. Это конкретныйблокировщик
TIM1UPDATE,согласующийсясCNT2226напротивдопуска<2048. Какойименновызов
блокировалисторическийкадр31759,записьнефиксирует:невыдаватьатрибуциюзадоказанную.
3004:ADCwriterпубликуетsequence/DMB,mainкопируетсразрешённымиIRQ,3попытки;
приконфликтепакетпропускаетсябезизменениясчётчикаслотов. ADCfeedback/окна/
допуск2048/fast5312/защиты/наблюдатель/модельполностьюпрежние.
ПКтест297точекпрерывания,odd/wrap/bounded,все3packetтипаэквивалентны,
реальныйsenderнепосылаетbusyпакет. Recorded12строкreplay:плохой2226по-прежнему
отвергается. Nativeadapterиостальныеpathтестыпройдены. Обасобраныбезошибок;
ELF3004теперьбезCPSIDвcurrent_packet,модельCRCтаже,RAM28344.
954прежнихфайласохраненыипроверены. START/CLEAR/flash0вэтомэтапе.
Кандидатartifacts/live_bench_20261029/foc_update_latency_fix_r1/manifest.json,
разборinvestigation.json. Неустановлен,аппаратно5секещёНЕподтверждены.
ПокафизическиJ1ON/15ВON/повербанки/PCиSaleaeOFF. ДлязаписинужноJ1OFF,
мультиметр<20В,обеUSBПК;15Вимотор/шлейфможнооставить. Затем
install_foc_update_latency_fix.py,чтениеобратно,verify_foc_update_latency_idle.py,
безSTART/CLEAR. Силовойпускотдельныйпоследующийэтап.

## 2026-10-30:3001/3002 FOC остановлен после~2с;FT_ADC_INVALID из-за поздней меткиUPDATE

Пользователь после анализа подтвердил: двигатель физически вращался. Ответ сохранён отдельно вoperator_observation.json; исходные анализ/захваты/хеши не перезаписаны.

Poweredr1START0:startupSDLOW61,6мкс/MOE0,снимоксохранён. Пользовательявно
разрешилодинCLEARиодинпуск. Poweredr2CLEAR1/START1,защитыпослеCLEARготовы;
повторов/RESET/flash0. ПятьсекундНЕзавершены,SAFE/PWM0/run_id1,session2060мс.
31760ADCкадров~1,985с;полные1024байта/35страниц получены,12строкконца,
номинальныйpeak0,585208А,масштабампернефизическиквалифицирован.
Быстрыйпутьmax4880<5312,наблюдатель1984шага. Runtimewalllast565,124мкс,
IRQlower446,024/CPUupper119,100;maxwall688,724/maxIRQ561,741/maxCPU217,859,
разныеmaxнескладывать,metererrors0.
Первыйreason2FT_ADC_INVALID,MA_STALE3,MCSDK128MC_SW_ERROR. Входсвежий:
ADC19,359мкс/оценка874,912мкс,ноvalid0(sample_flags6). ПричинныйADCindex10,
sequence31759,cycles2733414013. МеткаUPDATECNT2226>=допустимого2048,
направлениевверх. ReplayнафактическихCзаголовках:bottom0/window1/publish1,
сырые2032/2120,очередь/JQOVF/epochбезошибок;context_ok0правильноотвергнут.
ПОЧЕМУсамаUPDATEметказадержанаещёНЕдоказано. Допуск2048/защитыНЕменять.
StartupSDснимокпобитносохранён;PA4отTP23снят,егоHIGHничегонеотделяет.
SDHIGH/BIE/config_ok,новогоfirst_startBreakнет,UART/hardware/transport/RPC0.
908прежнихфайловпроверены. Отчёт:
artifacts/live_bench_20261029/foc_fast_budget_fix_r1/powered_FOC_CPU_IRQ_20261030_r2/REPORT_RU.md.
ДалееанализлатентностиUPDATE/PRIMASKбезновыхпусков/сбросов/прошивок,
питаниепользовательоставилJ1ON/15ВON/повербанки/PCиSaleaeOFF.
ТекущиеразрешенияCLEARиSTARTужеизрасходованы,повторнесогласован.

## 2026-10-30:3001/3002 на повербанках проверены;J1OFF,готово к включению J1

Пользователь:обе повербанки,PC/SaleaeOFF,15ВON,J1OFF,Пуск/RESETне нажимал.
ПервыйGETtimeout сохранён вautonomous_before_FOC_r1;повторный полныйOFFтест
прошёл вautonomous_before_FOC_r2. Не выдавать стартовыйtimeout за дефектПО.
Свежие3001/3002:SAFE/PWM0/run_id0/HVarm0,10В,FOCselected=requested2,
profile128/CRC1354279011,zeroReady1,SDHIGH/BIE/config_ok/capture_running.
Маскиактивных/защёлкнутыхаварий0,UARTRPCerrors0. OFF64случаяготовы,
ядро3526тактов,observerinnermax24736;CPU/IRQsourceOFF_synthetic_CPU_probe,
firstfaultNone,metererrors0. Это не работа подШИМ; полныйадаптерпокаНЕпроверен.
908старых/установочныхфайлов поSHAсохранены. START/CLEAR/ARM/RESET/flash0.
Задана только остановленнаяконфигурацияFOC5Гц/BOUNDED5сек,разгон5/замедление1.
Следующийфизическийшаг:ТОЛЬКОJ1черезsoft-start;15В/повербанки/двигатель
оставить,PC/SaleaeOFF,Пуск/RESETне нажимать. После подтверждения питания:
свежая шина/SD/защиты и один согласованныйFOC5Гц5сек сCPU_IRQ/ADC/автостопом,
run_foc_fast_budget_trial.py --confirm-autonomous-powered с новым каталогом.
CLEARнеразрешён,самостоятельноне добавлять;еслизащёлка—сохранитьSDиуточнить.
Отчёт:artifacts/live_bench_20261029/foc_fast_budget_fix_r1/autonomous_before_FOC_r2/autonomous_summary.json.

## 2026-10-30:подготовлен одинFOC3001/3002 5Гц/5сек;ожидается перенос на повербанки

СвежийUSBстатус:3001/3002,SAFE/PWM0/run_id0,10В,FOC2/profile128CRC1354279011,
автонольготов,SDHIGH/BIE/config_ok,OFF64готово,аварий/UARTошибок0.
Пользователь запросил следующие переключения перед одним poweredFOC5Гц5сек.
run_foc_fast_budget_trial.py использует прежний проверенный runner сPAIR3001/3002;
все пороги,STOP/захват/однократныйSTART сохранены.11чистых предикатов отказа
проверены без команд на платы.854старых+54установочныхфайла проверены, сохранены.
START/CLEAR/ARM/RESET/flash0 в этом подготовительномэтапе.
Следующийфизическийшаг:обе платыUSBПК->повербанки,ПКиSaleae(включаяGND)отключены,
15ВON,J1покаOFF,Пуск/RESETненажимать. Сначалапроверитьавтономнуюзагрузку/связь,
затемпроситьвключениеJ1черезsoft-start. CLEARнеразрешён,автоматическинепосылать.
План:artifacts/live_bench_20261029/foc_fast_budget_fix_r1/FOC_CPU_IRQ_trial_preparation_r1/plan.json.

## 2026-10-30:3001/3002 установлены и сверены;OFF64теста пройдены без ШИМ

Пользователь J1OFF/мультиметр<20В/обеUSBПК/15ВON подтвердил. Перед записью
пассивный SWD10,64В/MOE0,точный прошлый2972;32КБSRAM сохранены. Обе прошивки
записаны по одному разу, UnoOpenOCD и NucleoCubeProgrammerreadbackOK.
Отдельный HotPlugreadbackNucleoточноHEX(толькопустыепромежуткиFF),калибровка
совпадает,обновлениеHMIпоставлено,RPC/UARTбезUSBпереподключения работают.

verify_foc_fast_budget_idle.py:passed,64OFFслучая. Ядро3526тактов=20,741мкс
при прежнем лимите4000;было3582в такомжеOFFтесте. НЕсравнивать3526 с5317
прошлого полного poweredадаптера:OFFзамер обвязку ADC/профиля/свежести не включает.
Полный5312тактовыйruntimeдедлайн остаётся и на3002подШИМ покаНЕпроверен.
Наблюдатель legacymax24748тактов; полнаяметрикаlastwall143,665/IRQlower32,765/
CPUupper110,900мкс,maxwall146,335/maxIRQ34,935/maxCPU117,771мкс.
Максимумы не складывать,CPUupperнечистоеCPUвремя. Metererrors0,firstfaultNone.

SAFE/PWM0/run_id0,FOCselected=requested2,profile128/CRC1354279011,zeroReady1,
SDHIGH/BIE/config_ok,захватвооружён/новогоснимканет,всемаскиаварий0,
UARTCRC/sequence/hardware/transport/RPCtimeouts0. Шинаоколо10В.
START/CLEAR/ARM0,5Гц/BOUNDED5сек только в остановленной конфигурации.
Все854старыхфайла проверены; новые логи/SD/SRAM/readback/тайминги сохранены.
Отчёт:`artifacts/live_bench_20261029/foc_fast_budget_fix_r1/installation_verified_r1/REPORT_RU.md`.

Физически покаобеUSBПК,15ВON,J1OFF. АвтономнуюзагрузкуиFOC5Гц/5секподШИМ
согласовыватькакследующийэтап;сейчасникакихновыхSTART/CLEAR/flash.
Длятехбудущихпроверокиспользовать3001/3002(старыйrun_foc_runtime_trial.py
содержитPAIR2971/2972, его надо адаптироватьбезослабленияпроверок).

## 2026-10-30:2971/2972FOC остановлен точным FT_FAST_DURATION;3001/3002 готовы, не установлены

Один START, CLEAR0:5317тактов при неизменном5312. АЦП29,394мкс<187,5мкс,
оценка874,929мкс<2000мкс, наблюдатель ещё не работал(0шагов), поэтому liveCPU/IRQ
наблюдателя в этом пуске не измерены. MCSDKмаска1(MC_DURATION), MA_STALE3,
не прежний неподтверждённый «медленный наблюдатель». UARTCRC/hardware/transport0.
ШИМвыключен/SAFE, run_id1. J1 и15В покаON, платы на повербанках, PC/SaleaeOFF.
НовыйSDснимок не возник, SDHIGH/BIE/config_ok; старые записи сохранены.
ADC1024байта/35страниц,16кадров,12строк, номинальныйpeak0,278214А(масштаб не квалифицирован).
Пять секунд не отработаны; повторного пуска/CLEAR/RESET/flash не было.

3001/3002готовы офлайн: в одном IRQ убраны дублирующая проверка модели,
универсальное lroundf(CCR), лишняя очистка снимка; exactпрофиль staticconst.
Проверка модели остаётся каждый кадр, все пороги/окна/автостоп прежние.
2393218rounding,255000bitwisecontrol/modulation,12текущих ADCстрок,26badmodels
пройдены. Матмодельперезапуск4/4central,54/60total; сценарии полностью совпали.
Сборки безошибок, ELFпрофиль и источники подтверждены. Targettiming3002 ещё
НЕ измерен; кандидат НЕ прошит. Не обещать устранение всехruntimeотказов.

Далее только подготовленная запись: J1OFF/мультиметр<20В/обе платыUSBПК,
15В и двигатель/проводку оставить; install_foc_fast_budget_fix.py и чтение
обратно, затемverify_foc_fast_budget_idle.py. Пока силовоеON не прошивать,
не посылать START/CLEAR. Захват и анализ:
`artifacts/live_bench_20261029/foc_runtime_fix_r1/powered_FOC_CPU_IRQ_20261030_r1/REPORT_RU.md`.
Кандидат:`artifacts/live_bench_20261029/foc_fast_budget_fix_r1/manifest.json`.

## 2026-10-30: питание Uno включено пользователем; автономная проверка2971/2972 прошла

Пользователь уточнил причину прежней недоступности: ошибся и не подключил
питание, теперь включил. USB/ADB отсутствует, прежнее подтверждение — обе
платы на повербанках,ПК/Saleae отключены,15ВON,J1OFF. Первый GET вернул503
при загрузке, затем свежий статус появился без каких-либо перезапусков,
USBпереподключений или прошивок. Это не доказанный дефект прошивки/WiFi.

verify_foc_runtime_idle.py прошёл в автономной загрузке:2971/2972,
FOCselected=requested2,профиль128/CRC1354279011,5Гц/BOUNDED5сек,разгон5Гц/с,
автоноль готов. SAFE/PWM0,run_id0,SD HIGH/BIEtrue/config_ok,первогоSDснимка
нет (захват вооружён). Диагностические current/occurredмаски0,algorithmfault0.
Контроллер передаёт10В. UART integrity/hardware/transport/RPCtimeouts0.

OFF64случая: ядро3582такта, старыйmaxobserver24721такта. Новая метрика
source=OFF_synthetic_CPU_probe: последнийwall138,324мкс,
IRQ_body_lower27,200мкс,CPU_upper111,124мкс. Maxwall146,129мкс,
maxIRQbody34,959мкс,maxCPUupper111,482мкс; максимумы не складывать.
Metererrors0,first_faultNone. Это OFF CPUпроверка, не новая работа мотора.
833прежних файла проверены, текущие статусы/SDметаданные сохранены в
`foc_runtime_fix_r1/autonomous_20261030_before_FOC_r1`, включаяsummary/хеши.
START/CLEAR/ARM/RESET/flash в этом этапе0.

Следующий необходимый физический шаг — включить ТОЛЬКО J1 через штатный
soft-start при закрытом стенде;15В/повербанки/проводку оставить,Пуск/RESET
не нажимать. После подтверждения свежей высокой шины/защит выполнить уже
согласованный одинFOC5Гц/5сек, CPU/IRQ/firstfault/ADC иавтостоп.
Инструмент `run_foc_runtime_trial.py` готов; сейчасSDзащёлки нет, автоматически
добавлятьCLEAR без необходимости/инструкции не надо. Новую прошивку не готовить.

## 2026-10-29: после переноса на повербанки Uno недоступна, автономный допуск НЕ подтверждён

Пользователь подтвердил обе платы на повербанках,ПК/Saleae отключены,15ВON,
J1OFF,Пуск/RESET не нажимал. Свежего статуса получить не удалось: первый
verify_foc_runtime_idle.py сохранил timeout вautonomous_before_FOC_r1.
Затем57сек ограниченных GETstatus также без ответа;TCP8080 и2222 недоступны.
EthernetПК192.168.1.145/24,шлюз.1доступен;ARPк.138Incomplete. Поиск известного
MAC14-B5-CD-E2-1B-A9 ICMP/ARP в этой/24 не нашёл плату на другомадресе.
VPNhapp имеетReachableбезMAC для.138, это не доказательство доступности Uno.
ADB пуст, ожидаемых COM10/COM13 нет; посторонние COM3/4 не использовались.

Автономная загрузка/профиль/автоноль/CPU_IRQ сейчас НЕ подтверждены. Не выдавать
старые USB-цифры123/14/108мкс за новую автономную проверку. Причину пока нельзя
разделить на питание/загрузкуLinux/WiFi без доступа. START/CLEAR/ARM/RESET/flash0,
сохранённые833файла повторно проверены, прошивка не менялась.
Отчёт: `foc_runtime_fix_r1/autonomous_boot_reachability_r1/report.json`.

Следующий необходимый физический шаг — подключить ТОЛЬКО UnoQ кUSBПК для
чтения загрузкиLinux/WiFi; Nucleo оставить на повербанке,15В как есть,J1OFF.
Шлейф/двигатель не трогать. Новая прошивка не подготовлена/не нужна для этой
диагностики; установленная пара2971/2972 уже сверена в предыдущем этапе.
Не просить включать J1,пока автономная свежая связь не восстановлена.

## 2026-10-29: подготовлен FOC5Гц/5сек с CPU/IRQ; ожидается переход на повербанки

Пользователь просит повторный опыт с записью CPU/IRQ/первого MA_STALE и
автостопом, спрашивает физические переключения. Свежий GET подтвердил
2971/2972, SAFE/PWM0,run_id0,FOC2/профиль128/CRC1354279011,автоноль,
SD HIGH/BIEtrue/config_ok,UART0,шина0В/J1OFF. CPU/IRQ остаётся OFF64пробой.
Ни START/CLEAR/ARM/RESET, ни новая прошивка в этом подготовительном этапе
не выполнялись. Старые769файлов и64файла установки повторно проверены.

Новый инструмент `tools/run_foc_runtime_trial.py` готов для2971/2972:
не требует фиктивного наличия старой SD-защёлки, CLEAR только при явном
флаге/разрешении, максимум одинSTART/одинCLEAR, прежние guards/5сек.
Сохраняет CPU/IRQ/первую причину и послеSTOP ждёт4страницы runtime и35ADCстраниц.
Если SDуже захвачен, доCLEAR требует полный сырой снимок/контекстMOE0.
При fault/потере связи/неготовойSD не повторяет пуск. Успешную длительность
и полноту записи различает; незавершённая запись не объявляется успехом.
Короткий допуск на подтверждение останова300мс не отменяет проверку аварий.

НаПК сценарии целиком исполнены с МОК-HTTP:успех,неуспехCLEAR,первыйfault,
успехбезCLEAR,отсутствиеразрешенияCLEAR; все прошли, реальныхкоманд0.
Отчёт: `foc_runtime_fix_r1/FOC_CPU_IRQ_trial_preparation_r1/host_script_tests/report.json`.
Не использовать старый runner2951/2961 для этого опыта.

Следующий физический шаг: J1 оставитьOFF,15В оставитьON; обеUSBПК отключить
на5сек и перевести платы на повербанки. ПК/Saleae включаяGND отсоединены,
двигатель/шлейф не трогать,Пуск/RESET не нажимать. Затем сначала автономная
проверка новогоboot/OFF64/профиля/SD; до неё J1 не включать. После отдельного
подтверждения J1ON — poweredpreflight и согласованный опыт. Текущий этап
не является разрешением слатьSTART до физического подтверждения питания.

## 2026-10-29:2971/2972 установлены, CPU/IRQ проверены без ШИМ

Пользователь подтвердил J1OFF,мультиметр ниже20В,обеUSBПК,15В оставлены.
Установлены2971/2972, по одной записи на плату, чтение обратно прошло.
Полный пассивный Flashreadback Nucleo также точен поHEX сFF-padding;
SHA2563502e44d1e391a3c41d43a39b2173d87da18889b418c827960547d823b17ab4a.
Калибровка не изменилась,769старых файлов проверены,64новых файла сохранены.
Совпадающий HMI установлен, RPC вернулась без USB-переподключений Uno.

При первичной проверке была защёлка UART ORE8/transport4/reason12, блокировавшая
подтверждение FOC. КонтекстUART320байт/SD/статусы/32КБRAM сохранены.
После свежей SWDпроверки низкой шины/MOE0 выполнен один контролируемый
RESET Nucleo при стабильномUSB. Без новой прошивки и без CLEAR.
Причина исходного ORE НЕ доказана. Повторная проверка и20сек/18статусов прошли:
UART CRC/hardware/transport/RPCtimeouts0. Research/E8bad1/1 не растут,
good растут. Дополнительных сбросов/START не было.

OFF64случая завершены. Новый измеритель source=OFF_synthetic_CPU_probe:
последний wall123,382мкс=IRQ_body_lower14,812+CPU_upper108,571мкс.
Максимумы по64случаям: wall143,935,IRQbody32,847,CPUupper116,324мкс;
они не обязаны относиться к одному вызову, их не складывать. CPU_upper
включает края измерения/вход-выход исключений; чистыйCPU точно не выделен.
Metererrors0, runtimefirstfault отсутствует. Ядро3582такта, старый счётчик
наблюдателя24348тактов. Это НЕ полная нагрузка под ШИМ и неWCETдоказательство.

Финал: SAFE/PWM0,run_id0,FOCselected=requested2,профиль128/CRC1354279011,
5Гц/BOUNDED5сек,автоноль готов,SD HIGH/BIEtrue/config_ok,algorithmfault0.
J1OFF,15ВON,обеUSBПК. Шина~2В,MC_UNDER_VOLT4 ожидаем; её не сбрасывали.
START/CLEAR/ARM0. Новый силовой пуск ещё НЕ проверен. Перед ним требуются
переход на повербанки/снятие ПК и Saleae и свежая автономная проверка.

Пакет `foc_runtime_fix_r1` installed=true; итог
`installation_verified_r1/report.json` и REPORT_RU.md. Сырой первый ORE
сохранён в boot_latch_diagnostics_r1, ошибки первичной проверки не затирались.
Инструмент verify_foc_runtime_idle.py проверил OFF CPU/IRQ и режим без пуска.

## 2026-10-29: подготовлен2971/2972 для MA_STALE/CPU/IRQ, НЕ установлен

Новых START/CLEAR/ARM/RESET/flash в этом этапе0. Пользователь просит исправить
MA_STALE подШИМ без новых пусков наугад, защиты не ослаблять, захваты сохранить.
Установленная пара остаётся2961/2962 после одного прерванного FOC-опыта.
Последнее подтверждённое питание — J1/15ВON,повербанки. Последний статус
после STOP был SAFE/PWM0; далее WiFi не отвечал. В конце подготовки ADB пуст,
COM10/COM13 отсутствуют; COM3/4 не трогали. Сейчас прошивать физически нечем.

Найдены/исправлены в отдельном `foc_runtime_fix_r1`:
- лишний ACIM_VF_CalcAngle/fmod(double) на каждом16кГц такте FOC; теперь толькоVF;
- observer после неограниченного RX/диагностики: теперь перед UART, RX43байта,
  yield между живыми пакетами, крупные сохранённые буферы передаются толькоOFF;
- ожидание wall1мс сверх готового16-отсчётного окна: обслуживание сразу по bin;
- публикация оценки после уже возникшего IRQ-сбоя/MOEoff запрещена.

Возраст2мс/ADC3периода/fast5312, OFF4000/85000,5Гц/5сек, модель/пороговые
файлы/ADCкод неизменны. Нет новых масок IRQ и изменений NVIC-приоритетов.
Девять реальных возвращающихся ISR учитывают корневое время с вложенными
без двойного счёта. wall−IRQ_body даёт CPU_UPPER, не «точный чистыйCPU»:
вход/выход исключений и края измерения остаются в верхней оценке.
Новый E8 содержит4страницы live/первого frozenfault: точная ветка stale,
DWT/ADC/estimate/bin, возраст/очередь, observerinflight, последний CPU/IRQ.
Снимок первой ошибки атомарен и не затирается следующими отказами.

Разделение добавлено и в64OFF-проверки с явной меткой
OFF_synthetic_CPU_probe. Следующий аппаратный этап — MOE0/низкая шина,
не силовой запуск. Сейчас аппаратных CPU/IRQ чисел на2972 ещё НЕТ.
Старый захват871,5мкс задним числом разложить нельзя, его точная ветка
МА_STALE не доказана. Нельзя объявлять проблему полностью решённой на моторе.

НаПК actual-C регрессии/таймер/защиты/5веток отказа/CRC/вложенныеIRQ/счётчики
и проверка dispatch/RX/диагностики/HMI пройдены. Построенное расписание с
сохранёнными ADCзначениями и wall148155циклов воспроизводит oldfault3;
candidatefault0. UARTзадержка/IRQрасписание там синтетические, не измеренные.
Математика ядра побайтно прежняя; прошлое исследование4/4 и54/60 переиспользовано
по хешу, не перезапущено.769прежних файлов проверены, ничего не удалено.

2971/2972 собраны/запечатаны, installed=false. Для установки нужны J1OFF,
мультиметр ниже20В, обе USBПК;15В/двигатель/проводку оставляют. Инструменты
`install_foc_runtime_fix.py` и `verify_foc_runtime_idle.py` готовы; они не
STARTят/CLEARят. Сначала запись/чтение обратно/связь/новаяOFFметрика.
Подробно: `foc_runtime_fix_r1/REPORT_RU.md`, manifest.json и verification/.

## 2026-10-29: FOC2961/2962 снова остановлен MA_STALE; повторных попыток не было

Пользователь подтвердил J1 через soft-start,15В,обе платы на повербанках,
ПК/Saleae отключены, разрешил одинCLEAR и одинFOC5Гц/5сек. Исполнено ровно
это: CLEAR восстановил BIE/маски0; перед START321В,SD HIGH/config_oktrue,
связь и автоноль исправны. Один START отправлен и прерван по MA_STALE3 /
MC_SW_ERROR128. Пятьсек НЕ завершены. Последний подтверждённый статус
после STOP SAFE/PWM0,322В. Uno99мс — время сессии, не точное время ШИМ.

Захват755кадров ADC(~47,19мс при16кГц), вместо18кадров прежнего2952.
Наблюдатель реально выполнялся под ШИМ; его максимальный DWT-интервал
148155тактов=871,5мкс, противOFF23771. Он включает вытеснения IRQ;
чистая стоимость расчёта/ожидание не разделены, точная ветка MA_STALE не
записана. Fast5133такта меньше прежнего5312, запас мал. Не объявлять
старую ошибку startup-bin единственной устранённой причиной или полностью
работоспособным FOC. Никакого ослабления возрастных/временных защит не было.

Полный ADC1024байта/35страниц/bad0 сохранён; последние12кадров:11принятых,
один после STOP, без отказа окна/эпох/очереди/deadline. Номинальный максимум
сохранённых отсчётов0,306995А, физический масштаб не квалифицирован,
RMS недостоверен. UART integrity/hardware/transport0, SD HIGH/BIEtrue,
нового захваченного SD нет. Стартовый буфер сохранён побайтно.682старых
файла и автономная запись проверены SHA256.

Каталог: `foc_start_epoch_fix_r1/powered_FOC_5Hz_5s_r1`, analysis.json и
REPORT_RU.md. После STOP новых START/CLEAR/RESET/flash=0. Запросы логов и
повторный GETstatus в конце не дождались TCP-соединения; не утверждать свежую
онлайн-связь по старому SAFE-статусу. Дополнительных перезапусков/команд
восстановления не было. Последнее подтверждённое питание: J1/15В включены,
платы на повербанках. Нового допуска на CLEAR/START нет: ровно один разрешённый
пуск и CLEAR уже использованы. Следующая диагностика — только чтение/ПК.

## 2026-10-29:2961/2962 автономная загрузка проверена, J1 ещё выключен

Пользователь подтвердил обе платы на повербанках, ПК/Saleae отключены,
15В включены,J1OFF,Пуск/RESET не нажимал. Первый HTTP-запрос не дождался
ответа при загрузке Linux; повторная проверка прошла без переподключения,
перезапуска службы/плат и без новой прошивки. Связь и автоноль готовы.

Профиль128/CRC1354279011 сохранился, остановленной конфигурацией выбраны
FOC2,5Гц,BOUNDED5сек,разгон5Гц/с,замедление1Гц/с. OFF64случая:
ядро3582такта,наблюдатель23771такта. Algorithm fault0. В серии good139→419,
research bad1→1; это не ошибка CRC UART. UART integrity/hardware/transport
и RPCtimeouts0. Последний статус SAFE/PWM0,run_id0,шина9В.

Стартовый SD LOW18,0074мс захвачен при MOE0 до первогоSTART. Сейчас
SD HIGH/config_oktrue, но BIE маскирован защёлкой Break; occurred1028,
current4 ожидаем при J1OFF. START пока не готов. TP23→PA4 физически снят,
его канал в цифровом захвате НЕ является измерением TP23 инвертора.
Снимок320байт и raw context сохранены, SHA256:
c7e267c74e377b7057372c7c38bf86234e6088f7a1d7c66b16d3a95cb830b2e8.
682прежних файла повторно проверены. Новый каталог:
`foc_start_epoch_fix_r1/autonomous_before_FOC_r2`.

Подготовлен `tools/run_foc_start_epoch_trial.py`: та же ограниченная логика
одного CLEAR/одного START, но пара2961/2962 и SD-доказательства ТЕКУЩЕЙ
загрузки. Старый запуск2951/2952 с прежним SD-буфером использовать нельзя.
На ПК15изменений проверяемых условий отвергают пуск; нынешняя защёлка также
отвергается до восстановления защиты. Это тест проверки допуска, не пуск.

Следующий физический шаг — только J1 через soft-start при закрытом стенде,
15В/повербанки не менять,Пуск/RESET не нажимать. После новой проверки
высокой шины/SD нужен штатный CLEAR с подтверждением восстановления BIE,
прежде чем согласованный FOC5Гц/5сек. В этом автономном этапе
START/CLEAR/ARM/RESET/flash=0. Защиты не менялись; нового силового пуска нет.

## 2026-10-29:2961/2962 установлены, чтение обратно и OFF-проверка прошли

Пользователь подтвердил J1OFF, мультиметр ниже20В, обеUSBПК,15В оставлены.
Записана ровно одна новая прошивка на каждую плату: Uno2026102961 /
Nucleo2026102962. Текущий пакет `foc_start_epoch_fix_r1` помечен installed=true.
Повторного подключения USB для RPC не потребовалось. Matching HMI установлен;
хеш калибровки до/после одинаковый. START/CLEAR/ARM в этом этапе0.

Перед записью две попытки проверки остановились БЕЗ flash: первая из-за
кодировки вывода ST-Link при PythonUTF8, вторая из-за4байт выравнивания
между.text и.rodata. В BIN это00, прежний HEX их не содержит, в FlashFF.
Все программируемые байты прежнего HEX точно совпали. Исправлен только
host-инструмент сравнения: строгие HEX checksum/границы/байты иFF в
пропущенных нулевых BIN-промежутках; повреждение данных не допускается.
Оба неуспешных отчёта сохранены, образы/пороги защит не менялись.

Запись/проверка: `foc_start_epoch_fix_r1/hardware_install_r3/install_report.json`.
Uno прошла аппаратный verify; Nucleo прошла verifyHEX и отдельное полное
пассивное чтение Flash. Итоговый физический SHA256 нового HEX-образа:
08fdc820c15197f9df3a59d69ba5f1d20c7ed45a37b622d5a550aa558059ce64.
Разница с BIN-хешем в manifest — только явно проверенные промежуткиFF.
32КБ SRAM перед остановом Nucleo сохранены. Старые682файла проверены SHA256.

OFF-проверка64случаев на реальной Nucleo: ядро3582такта (~21,1мкс),
наблюдатель23453такта (~138,0мкс) при170МГц. Это измеренное покрытие,
не полныйWCET и не подтверждение полного быстрого пути под реальным ШИМ.
Автоноль готов, SD HIGH, BIE включён, config_ok=true, algorithm_fault0.
FOC2 выбран остановленной конфигурацией, профиль128/CRC1354279011,
частота5Гц,BOUNDED5сек. Обмен по серии16статусов свежий без роста bad;
UART integrity/transport/RPCtimeouts0. run_id0, SAFE/PWM0, HV не разрешён.

Финальный статус при J1OFF: шина3В, MC_UNDER_VOLT4 ожидаем;
CLEAR для этой маски не отправлялся. Физическое состояние остаётся:
обеUSBПК,15В включены,J1 выключен. На2961/2962 силового пуска ещё НЕ было.
Перед ним нужно переводить платы на повербанки/снимать ПК и Saleae,
проверять свежую автономную загрузку; автоматически J1/START не включать.
Итог: `foc_start_epoch_fix_r1/post_install_readback_r1/report.json`.

## 2026-10-29: первый FOC остановлен MA_STALE; исправление2961/2962 готово, НЕ установлено

Установленная пара остаётся2951/2952. Выполнены два отдельно разрешённых
CLEAR: после первого BIE не восстановился и START не отправлялся; после
второго SD HIGH, BIE/config_ok и маски восстановлены. Затем ровно один START
FOC5Гц/5сек. Он остановился по MA_STALE3 / MC_SW_ERROR128 до завершения
пятисекундного опыта. Uno run_id1/run_elapsed79мс не означает79мс ШИМ;
в ADC18кадров около1мс. Вращение и достоверный RMS не подтверждены.

На ПК в точном C воспроизведена ошибка первой эпохи: estimate_cycles
обновляется при первом fast, завершённый bin_cycles остаётся от OFF/prepare.
До первых16валидных накоплений unsigned вычитание даёт огромный dt и
MA_STALE. Это согласуется с аппаратным захватом, но внутренние метки на
железе непосредственно не записаны. Новый пакет синхронизирует стартовые
метки и очищает накопитель, не меняя порогов/дедлайнов/модели/АЦП.

Пакет `artifacts/live_bench_20261029/foc_start_epoch_fix_r1` собран и запечатан:
2961/2962, exact-C тесты и128стартовых сценариев прошли;2отрицательных
теста сохраняют срабатывание MA_STALE. Автостоп5сек/переполнение DWT
проверены наПК. ELF проверен по исходникам/байтам профиля. На новой Nucleo
время ещё не измерено. Предыдущие636файлов и новые записи — всего682 —
проверены SHA256. Модель4/4центральных,54/60чувствительности переиспользована
по точному хешу неизменённого ядра, не выдаётся за новый аппаратный тест.

После остановки новых START/CLEAR/RESET/flash не было. Последний пассивный
статус: SAFE/PWM0,324В, UART integrity/transport0, возраст Nucleo13мс;
SD HIGH/BIE включён, E-stop защёлкнут. Старый SD-буфер идентичен до/после,
ADC1024байта получен полностью. Питание по последнему подтверждению:
J1 и15В включены, платы на повербанках, ПК/Saleae отключены.

Следующий необходимый шаг только для записи: выключить J1, дождаться
мультиметра ниже20В, перевести обе платы наUSBПК.15В, двигатель и проводку
можно оставить. Использовать `tools/install_foc_start_epoch_fix.py` с
проверкой чтением обратно, затем `tools/verify_foc_start_epoch_idle.py`.
Автоматического CLEAR/START после записи нет. Старыеr1–r4 не восстанавливать.
Отчёты: `foc_start_epoch_fix_r1/REPORT_RU.md` и
`estimated_foc_trial_r5/first_powered_FOC_5Hz_5s_r2/REPORT_RU.md`.

## 2026-10-29: автономная загрузка FOC проверена, J1 ещё выключен

Пользователь подтвердил: обе платы на повербанках, USBПК и Saleae отключены,
15В включены, J1 выключен; Пуск/RESET не нажимал. Сеть Uno стала доступна
после загрузки Linux, без вмешательства/переподключений/перепрошивки.

Пара2951/2952 свежая; расчётный профиль128 сохранился, CRC1354279011.
Автоноль:3стабильных блока из3, отказов последнего блока0. OFF-проверка
FOC завершила64случая: ядро3598тактов, наблюдатель22399тактов. При остановленных
выходах снова заданы BOUNDED5с,5Гц, разгон5Гц/с и выбран/подтверждён FOC2.
По16статусам UART/обмен стабильны, исследовательский good растёт. UART integrity,
аппаратные ошибки, transport fault и RPC timeouts равны0; один диагностический
E4-пакет был отвергнут после загрузки, этот счётчик в серии не растёт.

Зафиксирован SD/BKIN при загрузке до первого START, MOE0: PA6 LOW18,239мс.
Полный320байтный снимок и raw context сохранены в
`artifacts/live_bench_20261029/estimated_foc_trial_r5/autonomous_before_first_FOC_r1/`.
SD сейчас HIGH, config_ok=true; BIE сейчас маскирован штатной защёлкой Break.
Флаг hardware BKE при событии был включён. Выводить физическую причину импульса
из одной цифровой записи нельзя. Поля диагностических масок4/1028 сохранены;
при выключенном J1 и шине≈10В недонапряжение ожидаемо. CLEAR не отправлялся.

START сейчас НЕ готов: J1 выключен и стартовая защёлка не сброшена. Следующий
физический шаг — только J1 через штатный soft-start;15В/повербанки не менять,
Пуск не нажимать. После свежей проверки высокой шины/SD нужен один штатный
CLEAR и проверка восстановления BIE, прежде чем выполнять отдельно согласованный
пуск5Гц/5с. RESET и новые USB-переключения для этой проверки не требуются.
В автономном этапе START/CLEAR/ARM/RESET/flash=0.

## 2026-10-29: расчётный FOC установлен, проверен без силового и выбран

Действующая пара **Uno2951 / Nucleo2952**, итоговый native-пакет
`artifacts/live_bench_20261029/estimated_foc_trial_r5` (r1–r4 промежуточные,
их не использовать для восстановления). Оба образа проверены чтением обратно,
калибровка не менялась. Профиль после загрузки Nucleo постоянный, явный
тип128=`calculated_experimental`, CRC1354279011. Измерительная квалификация7
не имитируется. Новые измерения L/Rr от пользователя не требуются.

Подготовлен первый опыт FOC: плавно0→5Гц за1с, всего5сек, без нагрузки.
Экспериментальный профиль ограничен5Гц/BOUNDED5с. Native-автостоп работает
по DWT из быстрого обработчика и не зависит от веба. Полосы/пороги защит
не увеличены; исходный предел полного быстрого пути5312тактов сохранён.

На реальной Nucleo без ШИМ измерены64случая: ядро FOC максимум3598тактов,
наблюдатель23703такта при170МГц. Это тестовое покрытие, не полный WCET.
Исправлены наследуемые пути make-графа; ELF теперь проверяется по48CU и
точным байтам профиля. OFF-проверка программно запрашивает тот же TIM1 NVIC
вектор при MOE0, не меняя DIER/BDTR/BKE/BIE. Библиотечные min/max и
atan2→sin/cos заменены эквивалентными вычислениями; сырой hypotf-трип неизменен.

Проверка интерфейса прошла: алгоритм2 FOC выбран и подтверждён,
частота5Гц, разгон5Гц/с, таймер5с, BOUNDED. На16статусах хорошая
исследовательская телеметрия растёт без роста bad; автоноль готов, SD HIGH.
Текущее питание по последнему подтверждению: обеUSBПК, J1/J4 выключены.
Контроллер показывает низкий остаток шины, активен MC_UNDER_VOLT=4.
Не CLEARить при выключенном J1 ради красивого статуса. Пусков/ARM/CLEAR не было.

Перед силовым опытом пользователь переводит на повербанки и снимает ПК/Saleae;
после новой загрузки проверять профиль/автоноль/OFF-timing, затем снова
настроить FOC5Гц/5с. Расчётный профиль не теряется, выбор режима/таймер
после перезапуска задаются заново. Силовой FOC ещё НЕ проверен.

Прежние636файлов и RAM перед записями сохранены. Первый бинарник ошибочно
собрал старые2940-исходники — ошибка исправлена и честно описана в отчёте.
Подробно: `estimated_foc_trial_r5/REPORT_RU.md` и
`estimated_foc_trial_r5/idle_verification_r1/report.json`.

## 2026-10-29: пользователь выбрал расчётные параметры для первого FOC

Прямое измерение индуктивностей/Rr больше не является обязательным шагом
перед подготовкой первого экспериментального FOC. Пользователь явно просит
паспортные/средние оценки. Подготовлен отдельный расчётный профиль:
`artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json`.
Он не должен называться измеренным. Rs=12,23 Ом из прежнего измерения;
Rr≈11,0044 Ом, Lm≈0,494478 Гн, Lls=Llr≈0,0336163 Гн из паспортной
T-схемы; J=0,0002 кг·м² и механические потери12Вт — предположения.
Начальный опыт: без нагрузки, плавно0→5Гц за1с, всего5с;
поток0,25Вб, ограничение задания0,8А, сырой аварийный порог1,35А неизменен.

В независимой модели с реальным C-ядром и записанным шумом54/60 сценариев
прошли критерий точности. Центральный профиль прошёл4/4. При Rs−30% или
Lm±30% на5Гц точность ещё недостаточна; это не скрыто и не названо
аппаратной валидацией. Подробности: `air56_estimated_foc_r2/REPORT_RU.md`.

Профиль ещё НЕ передан на платы; действующая пара остаётся2941/2940.
Следующая программная работа: явная поддержка экспериментального расчётного
профиля (без фиктивной маркировки «измеренный»), автоматическая OFF-проверка
времени именно FOC и ограничение первого опыта5сек. Прежний загрузчик
выставляет этому типуqualification=0; нельзя подделывать доказательства7.
Эта особенность реализации не является требованием новых измерений L.
Пороги SD/BKIN, токовые, шина и watchdog не ослаблялись.

Диагностика VREF/смещения отложена. Дополнительный C4→PB11 не подключён
по подтверждению и сейчас не нужен. Четыре DMM-уровня уже получены:
3,30В Nucleo, 3,29В VREF+, 3,29В STEVAL, 1,645В C4. JP8 неизвестна,
но уточнять её для подготовки расчётного FOC сейчас не требуется.
Последнее подтверждённое состояние: J1/J4 выключены, обе платы наUSBПК.
В этом расчётном этапе обращений к платам/START/CLEAR/прошивки не было.

## 2026-10-29: подготовка раздельной проверки смещения и VREF; ожидаются4 напряжения

Текущая пара2941/2940 не менялась, аппаратных команд в этом этапе нет.
Проверены UM2505§7.6.3 и таблица16: VREFP=CN10-7, AGND=CN10-32,
3V3=CN7-16, GND=CN7-19. JP8 выбирает отдельный VREF (1-2) или VDD (2-3).
По UM2014 выход буфера1,65В — C4+, питание усилителей3,3В — C21+;
локальная земля STEVAL — TP11. Мультиметром запрошены именно эти4DC-уровня
и текущее положениеJP8. ПерестановкаJP8, новые перемычки и включение15В/J1
не запрашивались. Ответа о выполнении этих измерений ещё нет.

Мультиметр не разделяет быстрый мВ-шум. Подготовлен и проверен на9независимых
синтетических сценариях анализ `tools/analyze_reference_noise.py`: одновременные
VREFINT и внешнее смещение, x=B/R, y=M/R; отношениеy/x исключает знаменательR.
Анализ отвергает несогласованные окна/неустановившийся VREFINT, насыщенные
отсчёты и прежние phase/phase данные. Автокоррекции токов/защит нет.
Аппаратный режим такого захвата пока НЕ собран и НЕ установлен: нужны DC-уровни
и проверенная точка подключения смещения без конфликта с существующими сигналами.
Одни стабильные DC-показания не будут объявляться устранением шума.

Машиночитаемый план и хеши двух исходных буферов:
`artifacts/live_bench_20261029/reference_split_preparation_r1/plan.json`.
J1/J4 по последнему подтверждению выключены, обе платы на USBПК.

## 2026-10-29: сравнение15В ON/OFF без ШИМ — общий шум сохранился

Пользователь выключил15ВJ4 и нажал B2 Nucleo; J1 выключен, USB/проводка не
менялись. Получен новый полный OFF-буфер на2941/2940, CRC1605584942, SHA256
`0b43c1a9df06b0822c6db4eb07866d5be296d7b448833b35eb415458338fe997`.
Пара, регистры АЦП и размеры захвата совпадают с предыдущей записью при15ВON.
ШИМ выключен, связь свежая, ошибок страниц0. START/CLEAR/ACK не отправлялись.

Один входV на обоих АЦП: общий компонент σ5,440→5,240кода; σразности
0,732→0,740кода; корреляция0,9913→0,9902. Фиксированные и переключаемые каналы
также сохранили сопоставимый шум. Отключение15В не устранило помеху; по128парам
на режим нельзя объявить небольшой спад3,67% значимым или полностью исключить
вклад15В. Общий аналоговый вход/смещение3,3В и опорноеVREF ещё не различены.
Это не измерение ампер/индуктивности и не подтверждение исправленной аналоговой
точности. Защиты не изменены, сырые захваты сохранены.

Сравнение: `artifacts/live_bench_20261029/adc_noise_rpc_fix_r1/compare_15v_on_off_r1/REPORT_RU.md`.
Текущее физическое состояние: J1/J4 выключены, обе платы наUSBПК, проводка
не менялась. Повторный силовой пуск не выполнялся и не подготовлен.

## 2026-10-29: установлена Uno2941 / Nucleo2940; доказан общий аналоговый компонент шума

Действующая пара **Uno2026102941 / Nucleo2026102940**. Исправлена программная
ошибка мгновенного тока на границе200мс RMS-окна: регулятор больше не получает
обнулённый `window.last`, ток восстанавливается из текущей сырой пары АЦП.
Порог0,45А и прочие защиты/геометрия не менялись, фильтра в сырой защите нет.
Сырой пик прошлого опыта всё ещё останавливает точное C-ядро при replay.

В отдельном OFF-буфере проверены4 режима: исходное чередование; фиксированные
U1/V2; фиксированные V1/W2; один физический вход V на обоих АЦП одновременно.
При одном V корреляция0,9918 (повтор0,9913), отклонение разности0,74кода
(повтор0,73), общий компонент5,78кода (повтор5,44). Фиксация каналов шум не
убрала. Это указывает на общий аналоговый вход/смещение/VREF, но не различает
их. Факт снижения шума или пригодности измерения индуктивности НЕ подтверждён.

Первая пара2939/2940 записана и проверена по одному образу на плату.
В маршруте новой readonly-команды просмотра Uno была пропущена диспетчеризация;
первый буфер2176Б сохранён пассивным SWD с CRC4152267182. Затем записана только
Uno2941, Nucleo2940 повторно НЕ прошивалась; native-образ отдельно совпал чтением.
После исправления реальная RPC-выгрузка17страниц прошла, CRC и целостность
полного второго буфера проверены. При установках калибровка шины неизменна.
START/CLEAR в данном этапе не было.616 архивных и20 последних файлов сверены.

Материалы: `artifacts/live_bench_20261029/standstill_current_noise_r1/FINDINGS_RU.md`,
`idle_noise_swd_r1/capture.bin`; итоговая Uno и RPC-выгрузка:
`artifacts/live_bench_20261029/adc_noise_rpc_fix_r1/idle_noise_hardware_r1`.
Второй аппаратный буфер SHA256
`ea28b4b429bf3d752edc66cbd80026a87e579c0202c3cd10fad88f89ded69496`.

Последнее независимое состояние: J1 ранее выключен пользователем, обе платы
обнаружены на USB ПК, native-шина около10В и MOE=0 подтверждены через SWD.
Пользователю запрошено отключить только15В и нажать B2 Nucleo для такого же
OFF-захвата; выполнение ещё НЕ подтверждено. Проводку менять не требуется.
Индуктивность не измерена, силовой FOC не квалифицирован; новых пусков не делать
без установления причины шума и проверки измерения.

## 2026-10-29: действующая пара 2937/2938; первая DC-точка остановлена по сырому току

Действующая пара **Uno2026102937 / Nucleo2026102938**, пакет
`artifacts/live_bench_20261029/standstill_irq_timing_r1`. Обе записи проверены
чтением обратно, по одной записи на плату для этой пары. Калибровка DC-шины
не изменилась. В OFF проверено переключение V/f→FOC→ADAPTIVE→IDENT→V/f;
квалификация силового FOC по-прежнему 0.

За этот этап найдены и исправлены две программные проблемы: обнуление 4,4 КБ
нового измерительного состояния внутри быстрого IRQ и недостаточный стек
потока RPC Uno (500 Б при минимально наблюдаемой сумме кадров 608 Б).
Инициализация вынесена в OFF, стек RPC увеличен до 4096 Б. Измеритель времени
ядра исполняется в штатном TIM1 IRQ при MOE=0 без записи CCR и маскирования IRQ:
получено 3720 тактов при предварительном пределе 4800. Максимум адаптера в
новом физическом опыте 1923 такта; прежний рабочий бюджет 5312 не изменён.
Это проверка времени расчёта, а не точности токов/параметров двигателя.

После отдельного сохранения стартового снимка SD выполнен один штатный CLEAR
и один согласованный START неподвижной оси 0,06 А / 3 с. Точка завершилась
досрочно: ID fault2 / MI_BAD_CURRENT, MC_SW_ERROR128. В сыром кадре U=0,6044 А,
V=−0,2974 А, W=−0,3070 А по номинальному масштабу; предел векторного тока
измерительного режима 0,45 А сохранён. В 12 сохранённых кадрах нет ошибки
эпохи, публикации или окна трёх плеч. ПК-воспроизведение точного C-ядра
останавливается на том же 11-м принятом отсчёте. Причина аналогового выброса
не установлена; запись НЕ доказывает реальный бросок тока и НЕ даёт индуктивность.
Время от первого native-отсчёта до выброса около 373 мс; поле общего времени
прогона Uno около 466 мс использует другое начало отсчёта.

Буфер ID1664 Б сохранён с CRC3089571603, SHA256
`a5246c2d475efa856706ad4a26cc2f3b309cdb15e330e7c7cd93d33ad45392f9`;
сырой АЦП1024 Б и снимок SD также сохранены. Буфер ID не ACK-нут, авария
после остановки не сбрасывалась, повторного пуска не было.

Пользователь затем выключил только J1; 15 В и повербанки оставлены включёнными,
ПК/Saleae отключены, проводка не менялась. В OFF собраны 13 свежих пакетов:
размах отдельных каналов АЦП 17–25 отсчётов. Задание 0,06 А соответствует
всего 6,25 отсчёта U и 3,13 отсчёта V/W. Стабильное среднее автонуля не
квалифицирует мгновенную обратную связь такой малой точки. Нельзя считать
сглаживание тока доказательством отсутствия настоящего пика. На последней
записи шина ещё разряжалась с 223 до 191 В; это НЕ состояние для USB/перестановки
проводки. Показание мультиметра после этого не запрашивалось.

Файлы результата: `first_dc_point_r1/report.json`, `raw_abort/capture.bin`,
`adc_abort/trace.bin`, `current_abort_analysis/report.json` внутри точки;
`off_after_current_abort_r1/report.json` внутри пакета. Измерение индуктивности
и квалификация FOC остаются незавершёнными. Защиты/пороги не ослаблены.

## 2026-10-29: 2931/2932 подготовлены для измерения параметров; на платы НЕ записаны

Действующей парой остаётся **2921/2922**. Подготовлена **2931/2932** в
`artifacts/live_bench_20261029/standstill_commissioning_r1`, описание `REPORT_RU.md`,
образы `release/`. Добавлен постоянный измерительный режим неподвижной оси IDENT:
DC-характеризация инвертора при известном Rs, затем частотный импеданс для оценки
эквивалентных индуктивностей и Rr. Мультиметр без режима L для этого не нужен;
ранее полученные 24,7 Ом и 0,24 Ом использованы как предварительный Rs≈12,23 Ом.

Сборка первоначально остановилась на необъявленном `pwmHandle` в новом автостопе;
Eclipse показал окно «Java returned exit code=1». Исправлено на публичный MCSDK
`PWM_ParamsM1`; обе окончательные сборки успешны, Nucleo собрана напрямую без JVM.
Пройдены 6 групп C/протокол/автостоп/HTTP-тестов, 33 теста анализа, 30 DC+12 AC
синтетических точек и 853 161 проверка ADC IRQ с 24 старыми кадрами. Хеши 616
старых файлов захватов совпали. Модельные числа не являются параметрами АИР.

Каждая точка ограничена по току/времени, основной автостоп исполняется Nucleo.
Выбор режима и конфигурация не включают ШИМ; обычный Пуск в IDENT отключён.
Доставка нового буфера имеет CRC и сохранение на диск до его ACK; ACK не сбрасывает
аварию. Пороги, SD/Break, UART-watchdog, геометрия АЦП и автоноль сохранены.
Силовой FOC по-прежнему требует прежние независимые квалификации. START, CLEAR,
ARM, RESET и запись плат в данном этапе не выполнялись. J1 оставлен выключенным
по последнему подтверждению; восстановление ранее снятого шлейфа отдельно не
подтверждалось. Физические измерения и WCET нового режима ещё не выполнялись.

## 2026-10-29: 2921/2922 установлены и прочитаны обратно; выбор режимов проверен БЕЗ пусков

По прямому запросу пользователя записана ровно одна прошивка на каждую плату:
Uno2026102921 / Nucleo2026102922, пакет `artifacts/live_bench_20261029/multi_algorithm_r1`.
Оба readback PASS. Nucleo после записи удерживалась HALT до завершения записи/
проверки Uno, затем загружена штатно: это позволило избежать искусственного
UART-watchdog при перепрошивке. CLEAR и START не посылались.

Действующая пара теперь 2921/2922. Подтверждено на реальном native E4:
V/f(1)→FOC(2)→ADAPTIVE_PWM(3)→V/f(1), выбранный и запрошенный режимы совпали.
Во всех этапах SAFE/PWM=0, ARM=0, шина 0 В; UART/декодер без новых ошибок,
возраст native в итоговом наблюдении ≤47 мс. Маски текущей и сохранённой защиты
4/4 (низкое напряжение) не сбрасывались. Силовая квалификация FOC остаётся 0.
Это проверка записи, связи и выбора алгоритма, а не силовой работы регуляторов.

Калибровка DC-шины SHA до/после совпала. Сверены хеши 616 файлов старых захватов;
текущие снимки и история автонуля сохранены до записи. Служба и все три файла
живой панели совпали с подготовленным пакетом. Результаты:
`hardware_install_r1/install_report.json`,
`hardware_install_r1/mode_verification_r1/report.json`.
Внутри пакета первоначальный неудачный HMI-precheck сохранён отдельно: из-за
проверки идентичности калибровки HMI установлен после обновления обеих MCU;
точки калибровки не менялись, повторных записей MCU не было.

## 2026-10-29: подготовлена 2921/2922 с FOC и адаптивным ШИМ; НЕ установлена

Пакет `artifacts/live_bench_20261029/multi_algorithm_r1`, описание `REPORT_RU.md`,
два согласованных образа в `release/`. Действующей установленной парой остаётся
2911/2912; в этом этапе не было команд платам, START/CLEAR/RESET или прошивки.

В новом кандидате реализованы native sensorless FOC (регуляторы токов/скорости,
шестимерный EKF) и адаптивное положение ШИМ при неизменных 16 кГц. Выбор V/f / FOC /
FOC+адаптивный ШИМ — онлайн при выключенном ШИМ, без перепрошивки и без автостарта.
Профиль модели загружается stage/CRC-commit в ОЗУ, независимо от выбора режима.
Пока профиль конкретного АИР не идентифицирован и время расчёта на G431 не
измерено, силовой FOC заблокирован. Модельные параметры не выданы за измеренные.

Прошли 8 сценариев независимой модели с реальным C-ядром (1 792 000 шагов,
0→5→20→35→50→25→5 Гц, шум и расхождения Rs/Rr/deadtime), 5 групп тестов адаптера,
команд и защит, 853 161 проверка исходного IRQ АЦП и 24 сохранённых сырых кадра.
На стыке нового регулятора исправлены единицы: `cm_window.last` содержит коды АЦП,
в амперы они преобразуются тем же коэффициентом, что и RMS. Существующие пороги,
SD/Break, watchdog, автоноль и геометрия АЦП сохранены. Новые образы собраны,
хеши исходников/образов проверены; readback и аппаратная квалификация ещё не были.
Старые захваты сохранены, браузерная проверка выполнена только на локальных
заглушках, временный браузер и сервер заглушек закрыты.

## 2026-10-29: 2911/2912 установлены; панель упрощена, каталог опытов честно ограничен V/f

По запросу пользователя обе платы обновлены по USB: Uno2026102911 / Nucleo2026102912,
пакет `artifacts/live_bench_20261029/research_suite_r1`. По одной записи на плату,
оба чтения обратно PASS; калибровка DC-шины SHA неизменна. Первая проверка RPC
после записи получила timeout (исходный `install_usb_r1/report.json` сохранён
с passed=false). Один перезапуск принадлежащей arduino веб-службы восстановил
RPC без переподключения USB и повторной прошивки. Итоговую квалификацию смотреть
в `runtime_verification_r3/report.json`: passed=true. Второй обычный перезапуск
веб-службы применил упрощённые браузерные сессии; дополнительных MCU reset/CLEAR нет.

Новый пакет НЕ реализует все запрошенные моторные алгоритмы. На железе по-прежнему
только MAIN_VF_OL/16кГц. Режим подтверждается новым readonly E4-пакетом Nucleo
с CRC/версией/свежестью; старые управляющие кадры, ADC, V/f, watchdog, SD/Break,
deadtime и пороги сохранены. AS5600 отключён. FOC/адаптивный ШИМ не перенесены,
Rr/Lls/Llr/Lms/Imagn не идентифицированы; каталожные и модельные числа не заменяют
аппаратную квалификацию. Нейросеть не управляет инвертором, скорость не измеряется.

`tools/research_suite_runner.py`: план VF_FIXED→FOC_FIXED→ADAPTIVE_PWM→FOC_CLASSICAL→
AI_SHADOW→AI_ACTIVE→EXTREMUM_SEARCH. Полный план блокируется ДО первого START,
поскольку содержит нереализованные режимы, без подмены/пропуска. Отдельный выбор
VF_FIXED подготовлен для3×5Гц/5с с10с OFF-паузами, данными по каждому пуску,
штатным автостопом Uno и STOP при ошибке; автоматических CLEAR/RESET/повторов нет.
На новой паре силовые пуски ещё НЕ выполнялись.

Основной экран теперь: один ползунок0–50Гц, Пуск/Стоп/аварийный стоп, DC-шина,
RMS U/V/W и понятная причина остановки. Настройки и диагностика свёрнуты.
Аварийная кнопка всегда останавливает; отдельный сброс виден только в безопасном
OFF без активной маски аварии. Устаревшие/недоступные токи показываются «—».
Локальная страница автоматически выдаёт временную HttpOnly/SameSite=Strict сессию:
ручной ввод ключа не нужен. Это доступ для доверенной сети стенда, не внешний
сервис. Постоянный ключ API не передаётся браузеру; прямой POST без ключа/сессии
проверен и отклонён401. Проверки запуска и heartbeat/watchdog не менялись.

Проверены6 regressions, старые4 проверки датасета,22 проверки RMS-рендера,
обработчик АЦП853161 условий/24 сырых кадра наПК, мобильная панель390px и
реальная браузерная сессия без ключа. Офлайн UI-fixtures помечены synthetic;
живой screenshot: `output/playwright/research_suite/live-mobile.png`.
Прежние записи сохранены. В runtime_verification_r2 осталась незавершённая
проверка HTTP-клиента (повторное использование Request с автоматически добавленным
Cookie); новая независимая проверка r3 исправила сам тест, прошивку не меняли.

Последнее физическое подтверждение: J1/J4OFF,34pin-шлейф снят для Saleae,
двигатель наJ3, платы и Saleae наПК. После теста пользователю предлагалось
вернуть шлейф/15В/B2, но подтверждения выполнения ещё нет. До пуска уточнить
его фактическое состояние; автоноль, выполненный со снятым шлейфом, не доказывает
пригодность подключённого измерительного тракта. Показание контроллера0В при
снятом шлейфе не является независимым измерением шины. Силовое не включать
с USB ПК/Saleae. Текущая телеметрия SAFE/PWM0, связь свежая, E4 good растёт/bad0.

## 2026-10-29: реальные шесть выходов ШИМ записаны Saleae; 2902 восстановлена

Пользователь подтвердил выключенные J1/J4 и снятый 34-pin шлейф IHM09M2↔STEVAL;
двигатель остаётся на J3, платы и Saleae на ПК. Карта D0 UH/PA8, D1 UL/PA7,
D2 VH/PA9, D3 VL/PB0, D4 WH/PA10, D5 WL/PB1, D6 SD/PA6, D7 свободен.
Силового/вращательного теста в этом этапе не было.

Временная Nucleo2990 — отдельный изолированный тест выводов, без AS5600,
моторного приложения, ADC и UART. GPIO/TIM1/deadtime/Break взяты из2902;
один запрос SRAM на5с, выключенные выходы при загрузке. Сборка без ошибок/
предупреждений,6 проверок реальной C-машины состояний наПК прошли.

Реально выполнен ОДИН5с тест. Все6 каналов:16кГц, по80008 фронтов вверх,
автостоп DWT5000.00357мс, DONE/reason0/MOE0. Saleae12МГц,83.3нс/отсчёт.
Парных наложений не обнаружено; минимальная пауза1.333мкс соответствует
неизменённой настройке1.341мкс. Проверена вложенность импульсов между фазами,
включая различение VH/VL с одинаковым заполнением. D6 HIGH всю запись.

Пакет `artifacts/live_bench_20261029/current_only_pin_fixture_r1/`.
Итог `capture_r1/assessment_final.json` passed=true. Исходный `report.json`
оставлен с passed=false: первоначальная оценка ошибочно сравнивала длительность
HIGH сCCR/ARR без вычитания аппаратного deadtime. Пересчёт поBDTR/CR1/PSC/ARR
и сырым данным прошёл с более строгой погрешностью квантования; нового пуска
и изменения порогов не было. Сохранены.sal, CSV и оба первоначальных отчёта.

После теста Nucleo2902 восстановлена и проверена чтением обратно, Uno2901
не перепрошивалась. Пара2901/2902 снова отвечает, SAFE/PWM0, AS disabled.
Рабочие архивы и калибровка DC-шины не менялись. Текущая физика ПОСЛЕ теста:
J1/J4OFF,34pin всё ещё снят, платы/Saleae наПК. Показание Vbus при снятом
шлейфе не является измерением реальной DC-шины. Прежде следующего силового
пуска вернуть шлейф при выключенных J1/J4, подать только15В и выполнить B2
один раз: автоноль после восстановления кода проходил со снятым шлейфом
и не квалифицирует подключённый тракт токов. Затем проверить связь/ноль/SD.

## 2026-10-29: переход к опытам по токам без AS5600; запись 2901/2902

Пользователь выбрал исключить AS5600 и готовить опыты с АИР без нагрузки до
прихода сервопривода. Новая пара — Uno 2026102901 / Nucleo 2026102902,
пакет `artifacts/live_bench_20261029/current_only_r1`. Обе прошивки записаны
и проверены чтением обратно: `install_usb_r1/report.json` — passed=true,
по одной записи на плату; калибровка DC-шины побайтно сохранена.
Холодный перезапуск Uno не потребовался. Обновлены server.py, app.js и index.html.

ФИЗИКА: 29.10 пользователь подтвердил J1 выключен и по мультиметру ниже 20 В;
обе платы доступны по USB. После записи подтверждены точная пара 2901/2902,
SAFE/PWM0/ARM0, шина 1 В, автоноль стабилен 3/3 и история блоков готова,
SD HIGH/BIE/config OK, скорость=null, AS5600 disabled, FOC/MIC не включены.
При выключенном J1 ожидается MC_UNDER_VOLT (current/occurred=4); не сбрасывали.
15 В и проводку не меняли. Новых пусков, CLEAR и дополнительных RESET
оператору не предлагали. Затем пользователь подтвердил: двигатель возвращён
к J3, силовое выключено, платы на ПК. Перед переходом на повербанки прочитаны
2901/2902, SAFE/PWM0/ARM0, шина 0 В, автоноль 3/3, SD HIGH/config/BIE OK,
UART hardware errors=0. Автономное питание новой пары ещё не проверено;
силового пуска на ней не было.

Убраны активный I²C AS5600, его захват TIM4/DMA и диагностическая передача.
UART, АЦП, защита SD/Break, пороги, V/f, watchdog и калибровки сохранены.
Обработчик АЦП проверен на ПК: 853161 условий, 24 записанных кадра;
это не новый силовой опыт. Независимая проверка масштаба ампер ещё не выполнена.
Скорость вала не измеряется и не подменяется частотой поля.

Подготовлены `tools/current_only_lab.py` (пассивная запись / офлайн MLP и
базовые модели), `tools/run_current_only_trial.py` (один ограниченный пуск,
без CLEAR/повторов) и `research/CURRENT_ONLY_AIR56B2_20261029_RU.md`.
Нейросеть не управляет инвертором; датасета новых силовых опытов ещё нет.
Сборщик проверен в покое: 5 секунд без ошибок, 1 уникальное окно, повторные
отсчёты исключены, 0 допустимых обучающих окон (ШИМ выключен, ток=null).
`idle_verification_r1/report.json` — все 9 проверок passed, motor/CLEAR/reset=0.
Прежние архивы сохранены, дополнительный снимок текущих данных находится
в `current_only_r1/preinstall_idle_archive/`.

## 2026-10-28: выполнен один powered open-load5Гц/5с; пойманы LOW наI2C с периодомШИМ

ФИЗИКА: пользователь подтвердилJ1ONчерезsoftstart,15ВON,банки,ПК/Saleaeсняты,
двигательU/V/WотключёнJ3,AS/DIR/шлейф прежние. После тестаSAFE/PWM0/ARM0,
J1/J4 остаютсяONпоследнееподтверждение,шина322В. Не подключатьПК/не трогатьпроводку.
Прошивки2813/2812прежние,flash/reset0. Пользователь сейчаспроситКРАТКИЙабзац
длязнающегочеловека: hardware+wiring+чтонаблюдали+чтонеподтверждено.

ПередSTART былаsole startupUV currentmask0/occur4/fault5/state11,SDHIGH,
AS0,UART0,emptycapture. ОдинCLEARAPI200 не изменил nativefirstseq248;
ack_reportFAILсохранён. Read-onlyкод+неисполняемыйunknowncmd вернулreject500,
SETACCEL4прочитан/возвращён5 (безШИМ) =>cmdпутьреальный. Послеинформирования
оператора выполненОДИНдополнительный штатныйCLEAR, total2: fault/masks0,
firstseq0,protectedreadyOFF. ПричинапервогоACKнеподтверждена;не выдаватьзафикс.

run_i2c_wire_openload_5hz.py powered_openload_wire5hz_r1/trial/report.jsonPASS:
START1,autoSTOPровно5000мс(run_start1702124/stop1707124),OFFconfirmed,
2валидных5Гцcurrentwindows. I2C+248;приRUNreads340370постоянны,
послеSTOPчтениявозобновились. UARTbad0. ПовторногопускаНЕбыло.

ЗАХВАТПОЛУЧЕНполностью1072Б,CRCfc26d70c,parent1a60308c,manualFalse,
DMAerrorFalse,4096samples@8,5MS/sноминально481,88мкс;HMIdecode/parent/CRCвалидны.
Строгий outer wire_collection_reportFAIL из-за enc_wire_bad1 (не из-заCRCзаписи).
ОдиндиагпакетотвергнутвначалеRUNещёдоwiredata pages, receivedCRC-rejecthex'-'/ms0.
Поsourceсогласуетсясраннимarmed-status приlogicalRUN/fresh_offfalse,НОпричина
непротрассирована. СтрогийпорогНЕменяли/старыйFAILнепереписывали/неповторяли.
Отдельныйevidence_assessment.json честнообозначаетCRCvalidwave/потерянныйdiag.

waveform_analysis/decoded.json,wire.bin,wire.vcd +analysis_capture_status.json:
доадреснойпопыткиSDA LOW1,176–1,412мкс, SCL LOW1,529–1,647мкс,
кластеры каждые531–532samples=62,47–62,59мкс. PWMARR5312@170MHzcenteraligned
даёт62,494мкс/16001,5Гц. ШестькластераначалSDA258/789/1321/1852/2383/2914.
ЛегитимныйSTART3418,SCLrises3527/3640/3753/3866/3980:bits01100,
ожидалось01101для0x6C(ASaddr0x36W). На3977SDAпадаетименноу5гобита,
ошибкаARLOаппаратнонаблюдена~3,48мкспослепровала, driverage91,44мкс,
pollgap19,35мкс,cleanupARLO38,39мксбезSTOPrequest/forcedPEreset.
Это цифровыеLOW наGPIOдоrecovery,связанныеcPWMcarrier; неаналоговаяосциллограмма.
Моторисиловойкабельнеобязательныдлясбоя, UARTнеошибается, ASвпокое0errors.
Источникэлектрическоговозмущения(SCL/SDA/питание/общаяземля/подтяжки)ещёнелокализован.
НеутверждатьчтоI2CпочинениличтоэтоопределённобракAS/IPM. Номиналыподтяжекнеизмерены.

СхемаAS: NucleoG431PB8SCL/PB9SDA,3,3В/GNDотNucleo,провода~20смвдалиотсиловых,
DIRчерез1кОмGND. STEVALIPM15B/IHM09M2, V/f5Гц, PWM16кГц,driver15В/DC322В.
I2CHSI16,ANFON/DNF2,TIMINGR0x30521317,наблюдаемыйSCL~75кГц.
STFAQsource: https://community.st.com/stm32-mcus-60/stm32-i2c-does-not-work-39
(подтяжки2,2–10к,фильтры/помехидвигателей). АрбитражdocверифицированвSTM
manualRM0351/UM2570; точныйRM0440искатьпринадобности,аналогичногофлага.


## 2026-10-28: автономная2813/2812 проверена, host5с готов; ждём J1ON

Пользователь подтвердил: обе платыПОВЕРБАНКИ, ПК/Saleaeсняты,15ВON,
J1OFF, двигательснятсJ3. Затем повторил «на повере»: это НЕJ1ON.
AS/магнит/DIR/шлейф не менялись. НикакихSTART/CLEAR/reset/flashвэтойпроверке.

WiFi192.168.1.138 сначалаboot-time timeout/503двараза, затемсамвышелonline;
никакихслужб/перепрошивок/USBдлявосстановлениянеприменяли.
Uno2813/Nucleo2812, SAFE/PWM0/ARM0,Vbus10В, ASstatus103/поленормальное,
SDHIGH/IRQenabled/configOK/captureON, wire_state1/valid0/error0/empty,
peer_epoch1, все run-поля0 (ниодногопускавэтойзагрузке).

Первое автономноенаблюдение autonomous_before_pwm_r1/report.json FAIL
зафиксировалоОдинустаревшийкомплектcurrenttelemetry (summary1461/detail2062/
quality1660мс): derived zero_ready0,ноnativeготовностьвrawнепотеряна,
история3стабильныхблокаCRCвалидна, AS0/UART0. ReportFAILнепереписывали.
Далее автономный профиль autonomous_telemetry_profile_r1 PASS:
20,14с/17samples/3743новыхASчтений,errors_total0,все I2C/UART/RPCдельты0,
rawzero-readyкаждогоsummary/detail/quality1,history3блока1/2/3,
derivedready1воВСЕХ17,age summary21–512/detail36–1060/quality22–981мс:
всеисходныеfreshnessграницысоблюдены. Никакихизмененийпрошивки/TTL/защит.
Итогautonomous_readiness_assessment.json PASS честноотделяетearlystale отlaterPASS.

Подготовлен tools/run_i2c_wire_openload_5hz.py; 27offlinechecksPASS,
verify-onlyPASS, sourceSHAвwire_trial_preparation_r1. РасширеныТОЛЬКОточные
спискиверсий существующегоrun_as5600_bounded_5hz+zeroquality на2813/2812;
MCURUNLIMIT5000мс, прежнийhostwatchdog/всеVbus/temp/SD/UART/zero/STOPgates.
ДополнительноemptyWCпередSTARTиCRC+PWMparent+not-manual+noDMAerrorпослеSTOP.
NoautomaticCLEAR/noRESET/noFLASH/неповторятьпускради2currentwindows.
КомандаПОСЛЕНОВОГОJ1ONподтверждения и ПРОВЕРКИ готовности:
.venv/Scripts/python.exe tools/run_i2c_wire_openload_5hz.py
 --confirm-powered-openload-ready
 --boot-proof artifacts/live_bench_20261028/i2c_wire_epoch_fix_r2/autonomous_telemetry_profile_r1/report.json
 --outdir artifacts/live_bench_20261028/i2c_wire_epoch_fix_r2/powered_openload_wire5hz_r1
ПоддерживаетТОЛЬКОГОТОВЫЙprotectedOFF; еслиstartupUV/SDзащёлка — он НЕделаетCLEAR
иНЕSTART. Сначала архивироватьснимки/допускодногоштатногоCLEARеслипотребуется.
Не сообщатьпользователючтоSTARTбыл,покаегофактическинeбыло.

Следующийфизическийшаг: толькоJ1черезsoftstartпри закрытомстенде,
15В/повербанки/датчик/двигательснят прежние. Пуск/RESETненажимать.
До нового подтвержденияJ1ON остаётсяOFF. ПослеJ1сначалаread-onlyстатус,
сохранитьSD/первыеfaults/проверитьнепоявиласьASошибкадоШИМ, затемсогласованный
один5Гц5стестпoГОТОВНОСТИ. Старыеархивы/порогинестиратьинеослаблять.


## 2026-10-28: 2813/2812 RPC и passive capture/epoch проверены; следующий шаг — банки/J1OFF

Пользователь подтвердил холодныйUSBперезапускUno. СначалаADBещёнезагрузилась,
затем самаопределилась serial3880458060; forward18080 восстановлен.
Никакойповторнойпрошивки/служб/resetдляRPC не было. /api/statusподтвердил
Uno2813/Nucleo2812, SAFE/PWM0/ARM0/Vbus10В, ASerrors0/fieldnormal,
автонольready/history1, SDHIGH/IRQenabled/captureON/wire_state1.

Из-за старого retained timeout+lateCRC при предыдущемUSBrestart былиbad58,
firstreason13,lastreason1,transport7/fault3,hardwareflags0. Старый HOSTFLASH
precheck неподходяще отказал ПАССИВНОЙ записи; первая попытка
manual_usb_capture_r1 содержитFAIL без mailbox/reset/flash/START.
Создан tools/passive_i2c_wire_guard.py ТОЛЬКО для SRAMпассивногоcapture:
всеSAFE/PWM0/ARM0/<20В/freshSD/measurement/hardwareUARTchecks сохранены,
старыеfaultmetadataНЕобнуляютсяиНЕCLEARятся; требуетсястабильностьсчётчиков.
Флэш/STARTgate и firmwareзащиты НЕменялись.19offlineguardchecksPASS.

manual_usb_capture_r2 PASS: ровно1SRAMmailbox+1nativeRESETпослеархива,
1072БпакетHMI побайтносовпал с замороженнымRAMкольцом, CRCec36302a.
TIM4/DMA2ch4 и SD WORD→BYTEstorage/ch1 проверены. ПослеRESET Uno epoch1→2,
старыйtraceсохранёнкакpreviousCRCec36302a,currentочищен,wave_state1armed.
НовыйMCUASerrors0; SDархивдоRESETсохранён. Ручная запись попала в SCL/SDAHIGH
безпереходов: это доказывает путьGPIO-DMA-UART-RPC/immutability/epoch,
НЕадресныйосциллографическийкадр,НЕаналоговую/внешнюювременнуюквалификацию.

runtime_idle_r1 PASS: 15с/2788новыхASчтений,I2Cerrors0, всеI2C/UART/RPC
дельты0, transport_latch0, mc_fault_current/occurred0, nativebad0послеRESET,
zero_ready/history1, SDHIGH/IRQ/captureON, wire_state1/valid0/peer_epoch2,
previousCRCпрежний. Manifest/live_evidenceобновлены, runtime_evidenceSHAсохранён.
Прошивки остались2813/2812, дополнительныеflash0, START/CLEAR0.
ПричинаASошибокприpoweredPWM покаНЕустановлена, подШИМновыйзахватещёнезапускали.

ФИЗИЧЕСКИ пока обаUSBПК,15ВON,J1OFF,Vbus10В, двигательОТКЛЮЧЁНсJ3,
AS/магнит/DIR/шлейф прежние, Saleae снят. Следующий шаг — перевестиоба
контроллеранаповербанки после5сотключения, ПК/Saleaeотсоединены,15ВON,
J1покаOFF. СначалапроверитьавтономнуюRPC/AS/armedsnapshot, потомJ1
черезsoftstartпосленовогоподтверждения; следующий5Гц5стестбезмотора
должензаписатьПЕРВЫЙPWM-I2CсбойсGPIOprehistory, никакихпороговнеослаблять.
Старыеcapturessrc/records/бинарникинеудалять. НикакихпусковприUSBПК.


## 2026-10-28: Uno2813/Nucleo2812 readbackPASS; ждём холодный USB Uno для RPC

ПОСЛЕДНЕЕ ФИЗИЧЕСКОЕ СОСТОЯНИЕ: J1выключен, по оператору мультиметр<20В,
обе платыUSBПК,15ВJ4ON, двигательU/V/W снятсJ3, AS/DIR/шлейфнаместе,
Saleae снят. НикакихSTART/CLEAR в этом этапе. Не включать J1 до idlecheck.

Сначала2811/2812 записаны и обаreadbackPASS; калибровка прежняя.
Полная ручная1072Б запись GPIOB→DMA→UART→Uno→RPC→HMI в manual_usb_capture_r1
побайтносовпала с кольцомNucleo, CRCbf326e4f. SD BYTEstorage/ch1проверены.
После одного softwareRESETNucleo обнаружен РЕАЛЬНЫЙ дефект историиUno:
старый trace остался current, поскольку существующая bkw_peer_reset ветка
вызывалаct_reset до CTtimestamprollback-проверки. Снимки сохранены, старый
reportFAILоставлен, derived_assessment.json объясняетчастичныйуспех.
ПослеRESET было19BUSY/безШИМ; один штатный bootbusclear освободилSDA,
ASсновачитает, ошибкинерастут. Не скрывать этот baseline, не требовать0total
сразу послеRESETпосередине I2C-транзакции; смотреть свежесть/дельту.

Точечный Uno-only пакет i2c_wire_epoch_fix_r2: 2813/2812,
реальная старая resetветка воспроизведена native до/после, oldbugconfirmed,
новаяархивируетprevious и обнуляетcurrent преждеct_reset. Критерииreset,
I2C-драйвер/MCSDK/ADC/защиты не менялись. Nucleoнеперепрошивалась.
install_usb_r1: Uno2813 записана1раз иreadbackPASS, Nucleo2812 прежняя,
калибровкаunchanged. Но runtimepending: RPCзавислапослеUnoflash.
RPCafter_install_r1: один HMI-only SIGTERM/auto-restart не помог,
контроллеры не сбрасывались/не перепрошивалисьдлявосстановленияRPC.
Обаmanifest installed=true/readback_verified=true; уR2 live_verified=false.

Отправлен async пользователю: вынутьТОЛЬКОUSBUno на5с и вернуть; Nucleo,
15В/проводку не трогать,J1OFF. Ждём«Unoпереподключил». Это Linuxcoldboot,
повторная запись НЕ нужна. После ответа: ADBdevice/forward18080; проверить
пару2813/2812 SAFE/PWM0 иASfresh. Затем закончить --epoch-fixed проверку
кадра/сброса истории безШИМ:
.venv/Scripts/python.exe tools/qualify_i2c_wire_usb.py --epoch-fixed
 --confirm-j1-off-below20-both-usb --outdir artifacts/live_bench_20261028/i2c_wire_epoch_fix_r2/manual_usb_capture_r1
Она пишет только SRAMmailboxпасcивногоcapture, архивируетraw, одинnativeRESET
послеархива дляrearm/проверкиprevious CRC; НЕSTART/NECLEAR/NEFLASH.
HOSTисправлен: не требовать0totalAS, ждатьfreshsafe postRESETдо20с;
затем отдельное idleнаблюдение снулевымиДЕЛЬТАМИ (startup19допустимыкакbaseline).
Важно: текущий qualifier p.NEWправильно выбирается--epoch-fixed, guardexactpair.
Не выдавать новую ветку epoch за hardwareverified, покаэтот checkне пройдёт.
Не запускать poweredtest покаRPC/idle/armedrecord не подтверждены.


## 2026-10-28: запись2811/2812 прошла; точечная Uno2813 исправляет ветку cache reset

Пользователь подтвердил J1OFF/мультиметр<20В/обаUSBПК,15В оставлены.
Фактически SAFE/PWM0/ARM0/Vbus10–11В. Двигатель по-прежнему снятсJ3,
AS/DIR/шлейф подключены, Saleae снят. J1 больше НЕ включали.
install_i2c_wire_capture.py install_usb_r1 PASS: по1 записиNucleo2812иUno2811,
обаобраза readbackPASS, калибровка неизменна, RPCсама восстановилась.
12с idlePASS:2264чтенияAS, I2C/UART/RPCdelta0, SDHIGH/BKE+IRQ/captureON,
wire_state1/valid0. Никаких START/CLEAR.

manual_usb_capture_r1: одна пассивная mailbox-команда,1072Б дошли вHMI,
побайтносовпали с замороженным кольцом/памятьюNucleo, CRCbf326e4f,
DMA2ch4 WORD→HALFWORD/безIRQ/TIM4ARR19 подтверждены; SDch1 BYTEstorage
и8192samples подтверждены. Эта случайная запись попала в покой SCL/SDAHIGH,
не является осциллограммой адресной транзакции/аналоговой квалификацией.
Всё архивировано перед одним штатным softwareRESETNucleo для rearm/epochtest.
ПослеRESET были19BUSY безШИМ, busclear1раз освободилSDA, ASснова читает,
счётчик19 далее не растёт. Старый manualtrace ошибочно остался current!
Найдена точная причина: существующий bkw_peer_reset обнуляет g_current через
ct_reset ДО новой CTtimestamp-проверки, поэтому её old_quality=false.
Исходный report.json FAIL не переписывать; derived_assessment.json отделяет
работающий захват от проваленной проверки истории.

Готов Uno-only пакет artifacts/live_bench_20261028/i2c_wire_epoch_fix_r2:
Uno2813/Nucleo2812. Единственное изменение Uno кромеID: в СУЩЕСТВУЮЩЕЙ
ветке bkw_peer_reset вызвать pe_reset и очистку encoder_health передстарыми
cache reset. Критерии reset, UART/MCSDK/I2C/защиты НЕ менялись. Native replay
реальной ветки: стараяверсиявоспроизводитбаг, новаяархивируетстарыйCRC,
очищаетcurrent и принимаетНОВУЮ запись; source-isolation/loaderPASS.
NucleoНЕпересобиралась/НЕпрошиваетсяповторно. Сейчас идёт Uno-only установка
2813 через install_i2c_wire_epoch_fix.py, out install_usb_r1; ждать её результата.
После: повторить пассивный capture+archive+nativeRESET/epochcheck c --epoch-fixed,
поддержать возможные стартовые ASошибки как baseline (без новыхошибоквпокое),
не требоватьнулевого total послеRESET посерединетранзакции. НиSTART/ниCLEAR.


## 2026-10-28: сравнение без двигателя завершено; готовим пассивный захват I²C

Последний подтверждённый стенд: двигатель U/V/W снят с J3; AS5600/магнит/DIR
и шлейф оставлены на месте; обе платы на повербанках, USB ПК и Saleae сняты.
J4 15 В и J1 через soft-start ВКЛЮЧЕНЫ. После одного теста подтверждены
SAFE/PWM=0/ARM=0, шина 321–322 В. Нельзя подключать ПК или трогать проводку
до штатного выключения J1 и подтверждённого разряда. Дополнительных пусков
пока не выполняем. Производственные прошивки остаются 2709/2710.

Выполнен ровно один no-motor 5 Гц / 5000 мс с одним штатным CLEAR:
artifacts/live_bench_20261028/no_motor_powered_AS5600_5hz_r1.
UART bad=0, AS5600 errors +249, успешные чтения во время ШИМ не росли;
после STOP чтения восстановились. Новый первый PWM-снимок CRC9a5dfd8d,
NACK на адресной стадии, возраст166,953 мкс; STOP завершился за38,306 мкс
без принудительного PE-reset. Ошибка воспроизвелась без мотора/его кабеля,
но электрическая помеха или исключительно программная причина пока не доказана.
Runner report passed=false из-за только одного пригодного токового окна5Гц;
это не отменяет I²C-сравнение и не требует повторного пуска ради второго окна.

ГОТОВ И ОПЕЧАТАН пакет2811/2812: artifacts/live_bench_20261028/i2c_wire_capture_r1.
Пассивный TIM4→DMA2ch4 снимает GPIOB PB8/PB9,4096 отсчётов,8,5MS/s номинально,
около482 мкс перед первым I²C-сбоем при MOE. Ничего не пишет в SCL/SDA/I²C,
передача/CRC только после STOP и завершения родительского снимка. SD остаётся
TIM2/DMA2ch1,8192 отсчёта/5MS/s; WORD-чтение GPIO сохранено, память SD хранит
низкий байт с PA4/PA6 вместо halfword, что освобождает место для нового кольца.
PA4 больше НЕ подключена к TP23; её бит нельзя выдавать за сигнал инвертора.
Пороги, BKIN, PWM, ADC, дедлайны, восстановление I²C и калибровка не меняются.
Исправляется история Uno после независимого RESET Nucleo: старые записи
сохраняются в previous-epoch, текущие очищаются по native timestamp rollback.
Старые архивы/рабочие образы сохранены. Новый пакет ещё НЕ записан на платы.
Native tests, target builds, RAM/stack и checksum seal завершены PASS.
verification/report.json: Nucleo0errors/0warnings, RAM+80Б/запас3240Б сверх
heap+stack0x600; freeze stack12Б, ADC IRQ376Б прежний. Uno llext PASS,
RAM87610/262144Б, patched RPC dependencies проверены. Native HMI1346checks,
проверены реальные adapter/recorder/receiver, CRC/parent/epoch, неисправности
DMA/clock, все65536входных SDword для храненияbyte, старые записи не изменены.
verify_i2c_wire_capture_package.py PASS(1524source/13build/47verificationfiles).
На железе новая2811/2812 ещё НЕ проверена. Причина poweredI2C НЕ устранена.
Предусмотреть LOW-BUS проверку нового GPIO-DMA и SD до очередного HVпуска.
Manual capture тоже immutable доRESET; передRESET сохранять записи. Новый
захват только firstPWM error; около482мкс не покрывают полный3мсBUSYtimeout.

Отправлен один async физический шаг: выключить толькоJ1, после подтверждения
мультиметром ниже20В подключить обе платы наUSBПК;15В оставить, motorJ3снят,
AS/DIR/шлейф неизменны, Saleae пока не нужен. Ждём фактического ответа.
Пока последняя подтверждённая J1ON, USBнет — НЕЛЬЗЯ прошивать или начинатьпуск.
Далее: проверить sealed package; архивировать доступные live записи; записать
ТОЧНЫЕ образы Uno2811/Nucleo2812 и сверить чтением; HMI из ЭТОГО пакета,
калибровку сохранять. Не выполнять START; проверить RPC/AS в покое, затем
квалифицировать пассивный sampler на низкой шине. Если нужен productionrestore,
использовать оригинальный i2c_persistent_pe_r1 buildNucleo2710/hash28948cab…,
НЕ full_mcsdk_edges_busy_wait_r1/restore (там diagnostic2792!).


## 2026-10-28: мотор J3 снят; B2Nucleo выполнен, ждём J1 для open-load AS-сравнения

Пользователь подтвердил предыдущий шаг: J1/J4OFF/разряд,моторU/V/WснятсJ3,
банки/15ВON,J1OFF,AS/магнит/DIR/шлейфоставлены,ПК/Saleaeотключены.
Первый `no_motor_AS5600_autonomous_before_power_r1` увидел Vbus25В и СТАРУЮ
загрузку Nucleo: enc_errors249,enc_reads337895,старые first/PWM hex точно
совпали с прошлым run,Uno run_id1,UARTbad37/firstreason12/flags8(ORE).
Никакихпусков/очисток/сбросовотагента небыло. Это НЕноваяошибкаI2Cбезмотора.

Доп.12с `no_motor_existing_boot_archive_r1`:2305новыхASчтений,ошибкиI2C/UART/RPC
НЕросли,SD HIGH/поленорма,Vbusснизился5В. Все старыеI2C/SD/USARTrawсохранены.
Попросили ТОЛЬКО B2 RESET Nucleo при15Встабильных/J1OFF,Unoнетрогать.
Пользователь ответил«готово» — B2физическиподтверждён.

`artifacts/live_bench_20261028/no_motor_after_Nucleo_B2_r1`:
initialenc_reads13857/errors0/UARTbad0,доB2былоreads387231/errors249;
это подтверждённый сброс Nucleo.12с:2376новыхчтений/I2C0/UART0,
полеMD1/ML0/MH0,угол343,4°,Vbus2–3В,SDHIGH/BreakIRQenabled/capture_running,
обаSDsnapshotsпустые. Uno осталасьнапрежнейзагрузке:run_id1,предыдущийпуск
полностьюзавершён(run_start90399/stop95399/elapsed5000/reason1).
Это нормальная независимость двухMCU; НЕтребоватьнулевогоrun_idUnoпослеB2Nucleo.

НАЙДЕН КОНКРЕТНЫЙ ДЕФЕКТ ИСТОРИИ Uno2709: g_i2c_fault/g_release_capture/
g_bus_clear не сбрасываются при перезапуске Nucleo. Статусы enc_errors0/новые
reads идут,ноenc_fault_first_hex/PWM/release всёещёстарыеCRCизпрошлогопуска!
UNOQ_MOTOR.inoFC/EWобработчики3075..3094 толькопринимаютпакеты,нетepochreset;
fc_receive позволяетзаменитьcache приНОВОМCRC(поэтомуновыйсбойможетдоставиться).
Старыеhex НЕозначаютчтонаNucleoужеестьошибка; невыдаватьихзаcaptureновогопрогона.
Никакихfirmwareизмененийдляэтогоещёнеделали. Историюархивируем,rawнеподделываем.

Готов `tools/run_openload_as5600_comparison.py`:
--confirm-powered-openload-ready --boot-proof artifacts/live_bench_20261028/no_motor_after_Nucleo_B2_r1
--outdir artifacts/live_bench_20261028/no_motor_powered_AS5600_5hz_r1
ПОКА НЕЗАПУЩЕН,ЖДЁТ НОВОГО ПОДТВЕРЖДЕНИЯ J1ON.
Proof связывает фактический RESETNucleo со старым ПОЛНОСТЬЮЗАВЕРШЁННЫМ
run_idUno1(архивdir_fixed_powered_5hz_r1/trial/report.json), не подменяетсчётчики.
ИспользуетТОТЖЕload_trial()/MCU5000мс/hostWatchdog/всеnative/liveSD/UART/
voltage/temp/zero/armchecks; передSTARTдобавленоусловиеASerrors0/validfresh.
Запускает документированныйcounts-onlyрежимстарого m.main БЕЗ
--collect-first-i2c-fault,чтобыстарыйнеинвалидированныйUno cacheнеблокировал
сравнение. Rawbefore/afterhexостаютсявидимыми; новыйfirstсбойучитыватьТОЛЬКО
еслиCRC/hexизменилсяотархивного. Ничегонестирать/неизменятьвстатусах.
ПередпускомодинштатныйCLEARтолькоеслиpendingUV/SDstartup:
проверяетточныйstampзавершённогоUno run,транспортчистый,AS0/fresh,SDHIGH,
storedmaskUV4/occurred4или1028,ESTOP0,вседругиепроверки;послеобязательный
реальныйreadyOFFсIRQenabled/ошибками0. Новыйpre-STARTSDпослеJ1можно принять
лишьприMoeOFF/outsideSTART/пустомstart-windowиimmutablefingerprint,каквстаром
cold_boothelper,доказательствонепуска—B2Nucleo+неизменённыйcompletedUnostamp.

Offline:12bootproof+13CLEARnegative/positivecases PASS,py_compile PASS;
никакихизмененийпрошивки/защит/дедлайнов/калибровки. reset_identity_evidence.json
показывает387231→13857reads и249→0errors. Впервомcollector report поле
MCU_counters_reset_verified=false было неверным поздним сравнениемсоченьстарым
end-of-runreads19029(новыечтенияужевыросливыше19029);raw/reportнепереписывали,
runner явноиспользуетправильноеinitial-vs-immediate-priorresetдоказательство.

Отправлен async: включитьТОЛЬКОJ1черезsoftstartпри закрытомстенде,
моторостаетсяОТКЛЮЧЁННЫМ,J4/банки/DIR/ASбезизменений,ПК/Saleaeотключены,
Пуск/RESETне нажимать;ответ«силовоевключено,двигательотJ3отключён».
Ждёмответа. ПокаJ1OFFпоследнееподтверждение; невызыватьrunбезэтогоответа.
Будущийтест—стационарныйASприкоммутацииинверторабезмотора,НЕвращение/FOC.

## 2026-10-28: powered5Гц послеDIR —249 ошибок снова; следующий тест без двигателя

Пользователь подтвердил новый перевод на повербанки/15ВON/J1OFF,DIRоставлен,
TP23→PA4снят,Saleae/ПКотключены,магнитзакреплён. Автономный контроль
`artifacts/live_bench_20261028/dir_fixed_autonomous_before_power_r1`:2265 ASчтений,
errors0/UART0/RPC0,MD1/ML0/MH0,status39,угол300,8°,run_id0,Vbus10В.
Свежий startupSD приMOE0/context_valid0/внеSTART сохранёнполностью320B,
новыйcold-bootcertificate созданизЭТОЙзагрузки. RunnerSHAсовпалспредыдущим
проверенным5ссценарием; новый анализатор отделяет успехSTART/STOP от I2Cкачества,
провереннастаройфактическойзаписи249ошибок(невыдаётеёзаsensorPASS).

Пользователь затем подтвердил J1ONчерезsoftstart,15Ви банкипрежние,
ПК/Saleaeотключены,Пуск/RESETне нажимал. Выполнен
`tools/cold_boot_sd_trial.py --boot-proof .../dir_fixed_autonomous_before_power_r1`
с out `artifacts/live_bench_20261028/dir_fixed_powered_5hz_r1`.
ФАКТИЧЕСКИ CLEAR0 (доотправкикомандужеreadyOFF),START1,flash/RESET0.
Штатныйавтостопровно5000мс(run_start90399/stop95399/run_reason1/run_id1),
SAFE/PWM0/ARM0подтверждены. СтарыйSDwave неизменен,UARTbad0.

AS5600подpoweredPWM сноваFAIL: errors_delta249 (какдобоработкиDIR),
NACK92+BUSY16+deadline1+ARLO140=249;BERRclears13дополнительно.
В4RUNстатусах на1135/2262/3388/4515мс счётчикуспешныхчтений17390неизменен,
errors55/111/167/224,enc_ok/bus_ok0. Послестопа чтениявосстановились,
последнийenc_reads19029/errors249,enc_ok1/status103,Vbus324В.
FIRSTfault: ARLO,ISR0x201,PE1,CR2=0x1006c (address0x36,NBYTES1),
SCL/SDAHIGHнапоследовательномснимкепослеARLO,MOE1,age59,718мкс,
pollgap7,971мкс,maxgap125,676мкс. CleanupARLO корректный безSTOPrequest,
безforcedreset/timeout,36,282мкс. Это аппаратныйфлагарбитража,
неустановленнаяпервопричина; невыдаватьзаопределённодоказаннуюпомеху.
СтандартныеGPIO/AF/OD/clockmuxвпервомснимкепрежние,ошибокконфигурации0.

Результаты `assessment.json`,trial/first_i2c_capture.json,trial/report.json,
trial/release_capture_result.json и14локальныхфайловSHA сохранены.
AS5600_under_PWM_passed=false несмотрянаmotor_trial_passed=true.
НеутверждатьчтоDIRилиснятиеTP23починилисвязь: улучшениявэтомпрогоненет.
Никакихновыхзапусковпослеодного5снебыло,прошивки/пороги/калибровканеменялись.

Сравнёнархив старогопускабезмотора 24окт:
`artifacts/live_bench_20261024/no_motor_to_50_run_r1/report.json` — инвертор
дошёл50Гц,ноASтогдабылнаUnoI2C2 и НЕработалУЖЕДОпуска(reads0/errors2203),
послеreads0/errors2850. Этотархив неотвечаетнавопросработыASнаNucleoбезмотора.

ОтправленНОВЫЙasyncфизическийшаг длясравнениятойжештатнойMCSDKRUNбездвигателя:
выключитьJ1и15В,дождатьсяразрядаDC; снятьТОЛЬКОU/V/WмоторасJ3; датчик/
магнит/DIR/шлейфнеизменять. Отключитьпитаниеобеихплатна5с ивернутьбанки
(полныеснимкипредыдущейзагрузкиужесохранены),включить15В,J1оставитьOFF,
ПК/Saleaeнеподключать. Ждём «двигательотJ3отключён,платынаповербанках,
15Ввключены,J1выключен». Этоцеленаправленноесравнениевлияниямотора/кабеля,
неподготовкакперепрошивке. Новойпрошивкинепланировали.

ПокаэтотшагНЕподтверждён: последнееизвестноеJ1/J4ON,банки,моторподключён,
ШИМOFF. Послеответапроверитьновуюхолоднуюзагрузку иполныйархивнизкойшины,
неиспользоватьстарыйcertificate. ЕслинезаписанstartupSD/контексттеперьвалиден,
необходитьпроверкивслепую: выбратьштатнуюветвьready/одноголегальногоCLEAR,
сохранивнативныепороги иявнуюархивнуюидентичность. Новоеизмерениебудет
СТАЦИОНАРНОГОASприкоммутацииинверторабезмотора,непроверкойвращения/FOC.

## 2026-10-28: магнит после поправки в норме; ждём перевод на повербанки для DIR-теста

Пользователь подтвердил, что отодвигал датчик для DIR, затем «закрепил».
Первый контроль `dir_fixed_magnet_mounted_idle_r1`:2200 чтений/errors0,
status55=0x37,MD1/ML1/MH0,угол ещёinvalid. На вопрос о зазоре ответил
«а сейчас», тоесть попросил новое чтение после изменения положения.
Новая проверка `artifacts/live_bench_20261028/dir_fixed_magnet_mounted_idle_r2`:
5 свежих статусов,980 чтений/errors0/UARTbad0, status39=0x27 во всех5,
MD1/ML0/MH0,enc_ok1,RAW3422 неизменен,угол300,8°. SAFE/PWM0/ARM0,Vbus10В.
Пусков/CLEAR/RESET/прошивок не делали. Нормальный статический угол НЕ доказывает
устранение249 ошибок I2C при poweredPWM; после подключенияDIR такого теста ещё не было.

Подключения пока: платы наПК,DIRчерез1кОмкGND по подтверждению,TP23→PA4снят,
Saleaeснят,датчик снова установлен,двигатель/шлейф подключены,J1OFF по контексту
и низкойшине,15В вероятноON/впоследнейинструкции оставитьON. Подтверждение
готовности нового poweredтеста пока отсутствует.

Отправлен async-запрос: перевести обе платы сUSBПК на повербанки,15ВON,
J1покаOFF,Пуск/RESETне нажимать; DIR/положение датчика не менять,TP23снят,
Saleae остаётся отключённым. Ждём «платы на повербанках,15Ввключены,J1выключен».
После ответа сначала read-only статус/полевыефлаги/полныйархив и холодныйrun_id0,
затем отдельно согласовать физическое включениеJ1; один5Гц/5с с уже проверенным
MCUdeadline,не делать повторныхпусков без новых оснований. Старый холодныйSD
certificate из прошлой загрузки НЕ переносить: создать из новой низковольтной
загрузки со свежим raw/wave fingerprint (tools/cold_boot_sd_trial.py).
Не считать исправлениеDIR причиной до реального сравнения; одновременно
снята временнаяPA4ветвь, поэтому даже при улучшении разделить два воздействия
по текущему прогону не получится.

## 2026-10-28: TP23 снят, DIR подключён, платы наПК; I2C чистая, поле сейчас слабое

Пользователь подтвердил снятие TP23→PA4 («готово»), затем уточнил «к пк и дир
включил» в ответ на вопрос о DIRчерез1кОмкGND и питании. Считать платы наПК,
DIR подключённым по данной инструкции; отдельного измерения уровняDIR нет.
Новые силовые START/CLEAR/RESET/flash не выполнялись. Силовое не разрешать
включать при USBПК. Последние наблюдения vdc9–10В/PWM0/SAFE/arm0.
Состояние15В отдельно в последнем ответе не уточнено; не выдавать за OFF.

USB: adb serial3880458060 online,STLinkCOM13 доступен. Восстановлен только
локальный ADB daemon и port-forward localhost18080→Uno8080, без перезапуска
RPC/веб/MCU. WiFi192.168.1.138 тоже отвечает. Установленная пара2709/2710.

`artifacts/live_bench_20261028/dir_connected_usb_idle_r1`:12с наблюдениячерез
USBADB,10полныхстатусов,2201новыхASчтений,errors_total0,приращениявсехI2C/
UART/RPC ошибок0; enc_bus_ok1/configmatch1/свежесть<100мс. Угол при этом
НЕвалиден: во всех статусах enc_status51=0x33,MD1/ML1/MH0,enc_ok0/speed_ok0.
Это сообщение самого AS о слабом магнитном поле, не NACK/ошибкапередачи.
raw около916–917. До переделки у закреплённого датчика было status103=0x67
(MD1/ML0/MH0) иraw3969; нельзя объявлять DIR доказанной причиной изменения
поля — возможно модуль отодвинут для подключения, физическое положение неизвестно.

Отправлен async-вопрос: после подключенияDIR магнит напротив центра датчика
или плату отодвигал/снимал? Варианты «Плату отодвигал или снимал» / «Датчик
закреплён напротив магнита». Пока ждём ответа; J1 оставитьOFF. Не просить
вращать вал руками (пользователь ранее отказался), не запускать двигатель
черезПК. После подтверждения/исправления положения читать MD/ML/MH пассивно,
не перепрошивать и не менять калибровку для устранения слабого поля.
AS послеDIR подШИМ ЕЩЁНЕпроверен; чистый покой этого не доказывает.

PA4 теперь INPUT/NOPULL без проводаTP23: не трактовать его waveform какSD
IPM, не делать вывод о расхождении PA4/PA6. Штатный SDPA6 остаётсячерезшлейф,
сейчасHIGH/configOK, startup записьсохранена, BreakIRQ после событиямаскирован
до штатногоCLEAR. Никаких обходов этой защёлки/порогов не делалось.

## 2026-10-28: пользователь хочет убрать временный TP23→1кОм→PA4

Проверен исходник реально установленной2710: main.c295 задаёт PA4 пассивным
GPIO INPUT/NOPULL безEXTI; используется только в GPIOA DMA waveform вместе
сPA6. uno_rearm_break_irq(main.c692) и sd_live_encode(main.c999) проверяют
PA6; аппаратныйTIM1BKIN/штатныйшлейф от PA4 не зависят. Поэтому временную
ветвь TP23→1кОм→PA4 можно снять, прошивка для этого не нужна.
ШтатнуюSD→PA6 в шлейфе не отключать. После снятия PA4 будет floating/NOPULL:
его бит в новых waveform больше НЕ является измерениемTP23, нельзя выводить
задержку/расхождение двух точек SD поPA4. Старые осциллограммы не менять.

Пользователь ещё НЕ подтвердил фактическое снятие TP23 или добавление DIR.
Последнее известное питание J1/J4ON,ШИМOFF. Инструкция на снятие провода:
сначала J1/J4OFF и разрядDC; сам мотор/шлейф не отсоединять. Для осмысленного
следующего сравнения не добавлять другие изменения одновременно; состояние
DIR перед новым пуском при необходимости уточнить, не утверждать что оно
осталось четырёхпроводным или уже исправлено без фактического подтверждения.

## 2026-10-28: пользователь прислал изображение типа белого AS5600, проверяем DIR

Картинка `codex-clipboard-8a90c750-b9cb-4043-bb2e-44ea123e977e.png` просмотрена
и сохранена в `artifacts/live_bench_20261028/as5600_module_identification_r1`.
Это изображение несмонтированного модуля: VCC/OUT/GND слева,DIR/SCL/SDA/GPO
справа; DIR верхний справа. C1/C2,R1..R4 видны; R1 маркирован0.
Фото не доказывает наличие/отсутствие DIR bias на реальном установленном
экземпляре и НЕ подтверждает выключение питания стенда.

Найдено описание такого белого OEMмодуля у поставщика Mechasolution605131:
R1 — перемычка режима3.3В/5В, а не доказанная подтяжка DIR; оставляем R1 и
питание AS3.3В как есть. Прямого указания менять питание на5В НЕ давать.
SimpleFOC driver README требует фиксировать DIR кVDD/GND. Производитель
reference board использует другой layout/обозначенияR, не переносить их
номера на это PCB. Внутреннее соединение DIR по одному фото не установлено.

Следующий предложенный обратимый тест без перепрошивки: после J1/J4OFF,
разряда DC и отключения повербанков добавить DIR →1кОм→ GND Nucleo CN7-19
(контакт19GND подтверждён UM2505). Четыре прежних провода датчика не менять;
провод TP23→1кОм→PA4 и мотор/шлейф не трогать. Резистор именно в НОВОЙ ветви
DIR, чтобы ограничить ток при возможной существующей подтяжке; без гарантии
что это физическая причина NACK. Затем вернуть повербанки и15В, J1 покаOFF,
и только после подтверждения читать покой перед новым пуском.
Этот физический шаг ЕЩЁ НЕ подтверждён. Никаких новых START/CLEAR/RESET/flash,
записей в MCU или переключений питания в ответ на изображение не выполнялось.
Последнее подтверждённое J1/J4ON,ШИМOFF; перед работой с контактами требовать
выключить указанные источники, не считать изображение подтверждениемOFF.

## 2026-10-28: автономная связь OK, один powered5Гц5с завершён — AS5600 снова ошибается

Пользователь подтвердил: обе платы на повербанках, USB ПК отключены,
Saleae снят с Nucleo включая GND,15 ВON,J1OFF,шлейф/двигатель/датчик прежние.
`artifacts/live_bench_20261028/autonomous_2710_before_power_r1`:12с,2236 ASчтений,
I2C/UART/RPC ошибок0; SD HIGH, сохранён startup Break при MOE0/start-window false,
run_id/limit/start/stop/elapsed/reason0,context_valid0. Полный320B SDснимок сохранён.

Затем пользователь подтвердил включение J1 через soft-start при тех же
повербанках/снятом Saleae; никаких новых подключений/прошивок/RESET не было.
Шина322→325 В, AS5600 до Пуска errors0,UART0,SD HIGH.

ВАЖНОЕ уточнение семантики: в штатной2710 поля HMI mc_fault_current_mask/
mc_fault_occurred_mask — это uno_link.first_current_faults/first_occurred_faults,
первый ЗАМОРОЖЕННЫЙ снимок, НЕ текущие MCSDK маски. main.c743/971.
При325В старая4 в этом поле сама по себе не доказывает активную UV. Старые
read-only записи сохранить дословно; интерпретацию исправить. Диагностический
mic_full_report2805, напротив, считывал действительные текущие маски.

Подготовлен `tools/cold_boot_sd_trial.py` с27 offline/admission кейсами PASS.
Один штатный CLEAR разрешён только для сохранённого стартового SD/UV,
при холодном run_id0 и низковольтном архивном доказательстве до первого START;
полный waveform+raw/event fingerprint неизменен, first_start_window пуст.
cached_context НЕ подделывали/не заполняли нулями. Эта узкая привязка к архиву
заменяет лишь отсутствующий ранний context в host archive_before_start;
все live-проверки SD/BKE/IRQ/токов/UART/шины/zero/watchdog сохранены.
MC_AcknowledgeFaultMotor1 и аппаратный Break не менялись. После CLEAR проверены
ready OFF,SD HIGH/IRQ enabled, все новые диагностические маски0,старый SDнеизменен.

`artifacts/live_bench_20261028/powered_2710_after_logic_comparison_r1`:
ОДИН CLEAR,ОДИН START5Гц, штатный MCU RUNLIMIT5000мс;
completion run_elapsed_ms=5000/run_reason1/run_stop-start5000,SAFE/PWM0/ARM0.
UARTbad0,MCSDK новыхаварий0,SD HIGH/BreakIRQenabled. Новый физический факт
вращения независимо не подтверждался, повторного пуска/опроса пользователя не было.

АС5600 под poweredPWM НЕ квалифицирован: errors_delta249 = NACK104+BUSY21+
ARLO124; BERR clears26 (это дополнительные флаги, не прибавлять к249).
В4 активных снимках на1240/2467/3693/4919мс успешные чтения стояли127918,
ошибки60/122/183/245,enc_bus_ok/enc_ok0. После STOP опрос восстановился:
754чтения без новыхошибок,счётчик249 нерастёт. Никаких повторныхSTART после этого.

Первый НОВЫЙ frozenI2C: tick639595 Nucleo (не сравнивать напрямую с Uno tick),
cause NACK,state1/stage4/received0,CR2=0x1006c (адресная запись0x36,NBYTES1),
ISR0x8011,PE1,SCL HIGH/SDA LOW,MOE1; age177,282мкс,pollgap24,412мкс,
maxgap716,4мкс. Cleanup STOP действительно увиден через38,294мкс,forced=false,
stop_requested=false,expired=false. Следовательно в ЭТОМ прогоне первичный
отказ не был вызван зависшим STOP/принудительным PEсбросом; источник адресного
NACK пока не установлен. GPIO/clock-mux не поменялись в первом снимке.
Нельзя объявлять электрическую помеху/брак доказанными: полноценный poweredRUN
отличается также от низковольтного fixture. Фильтры/тайминги/прошивки не меняли.

Первичные источники прочитаны: ST FAQ про I2C(signal integrity/фильтры),
RM0440(ARLO/NACK/DNF),ES0431(ошибкиядра; известныйBERR clear уже реализован),
SimpleFOC driver README AS5600: DIR должен быть подтянут к VDD/GND.
Пользователь раньше подтвердил только4провода; это НЕ доказывает floatingDIR,
поскольку на PCB может быть bias. Модель/фото модуля не найдены в workspace.
Следующая необходимая информация — крупное фото действительного AS5600 сдвух
сторон для проверки DIR/подтяжек/режима питания, без новой прошивки наугад.
Планируем попросить J1/J4OFF перед осмотром,после разряда фото; шлейф/двигатель
не снимать. Пока пользователь НЕ подтвердил выключение: последнее J1/J4ON,
повербанки,Saleae/ПКсняты; двигатель остановлен,ШИМOFF. Не просить работать
с контактами/переставлять датчик при включённом J1.

Доказательства: powered.../assessment.json,trial/first_i2c_capture.json,
trial/report.json,post_stop_idle/report.json;17файловSHA preserved. Главное:
trial/report.json passed=true относится к bounded motor/STOP тесту и валидным
токовым окнам, НЕ к AS5600. В assessment AS5600_qualified_under_PWM=false.

## 2026-10-28: тест с подключённым IPM без J1 пройден; штатная 2710 восстановлена

Пользователь: «ну делай тогда». Никаких новых перестановок щупов не требовали.
Исходные подтверждения: J1 физически отсоединён от источника, 15 В включены,
шлейф IPM подключён, Nucleo доступна через USB, Uno доступна по Wi-Fi.
D4 на UART НЕ подключён; D5=SDA, D6=SD, D7=SCL. Для квалификации PWM взяты
только неизменённые D0–D3 (две комплементарные пары); все 8 сырых каналов сохранены.

Свежая инспекция 2805 до действий: PWM OFF, bus0, native active4/occurred1028,
AS reads478069/errors0, UART rx_bad0 (не переносить старые32 как текущее значение),
команды приходят, TX ошибок0. Все старые SD/I2C/UART снимки сохранены до сброса.
`connected_lowbus_trial_r1/trial`: один программный RESET при стабильных15 В,
после чистого boot/SD HIGH/UV4 один5с fixture-запрос. Итог PASS:
5000,025541 мс; MC_Run/Safety10000, Medium2500,HFT80008; ADC80008/bad0;
99 штатных команд, UART ошибок0. Физический PWM16кГц на4 проверенных каналах
4,000499с, AS5600 800 полных чтений в окне PWM, NACK/BUSY/deadline/ARLO/BERR0.
SD не падал, MOE обоих таймеров OFF после. Моторных START/CLEAR не было.
Это MCSDK OFF/FAULT + отдельный TIM1 fixture, НЕ production RUN/проверка вращения.
Силовое питание/причина старой ошибки AS5600 под сетью не проверены и не доказаны.

Затем временная 2805 заменена ОДИН раз на исходную штатную Nucleo2710.
Uno2709 и веб не перепрошивались. Использован оригинал из
`artifacts/live_bench_20261027/i2c_persistent_pe_r1/build/nucleo`:
BIN SHA256 `28948cab3eca2f0df3eaa74ca2637816e4fde924d584dab9f4cb852c0b8478e7`.
Полный raw readback FLASH совпал. Важно: папка `full_mcsdk_edges_busy_wait_r1/restore`
фактически содержит диагностический2792, вопреки старому metadata production_restore;
её НЕ использовали и НЕ переписывали. Для восстановления брать только оригинал2710!

Сейчас установлена и по веб подтверждена пара 2709/2710, SAFE/PWM0/arm0,
native UV current4/occurred4, bus0, SD HIGH/configOK/BreakIRQ enabled.
Штатная2710 после тёплого reset получила15 стартовыхBUSY: первый8мс,PE0,
CR2=0,SCL HIGH/SDA LOW; один bus-clear9тактов/300мкс освободилSDA. Это сохранённые
реальные ошибки и повторы старого preflight при закрытом допуске, НЕ нули.
Дальше 1952 чтения за10с, приращение всех I2C/UART/RPC ошибок0; сбросов контроллера
I2C/лишних парковок0. Улучшение ожидания startup из2805 в2710 не переносилось.
Исходники штатной2710 не менялись, пороги защит/калибровка не изменялись.

Доказательства: `full_mcsdk_edges_busy_wait_r1/connected_lowbus_trial_r1/assessment.json`,
`trial/full5s/full5s.sal`, `production_restore_2710_r1/report.json`,
`production_restore_2710_r1/idle_check/report.json`;173 файла SHA сохранены в
`connected_lowbus_trial_r1/stage_sha256.json`. 15 reset-admission и12 restore-admission
offline отрицательных/положительных случаев PASS; полные исходные manifests проверены.

Отправлен async-запрос следующего физического этапа: обе платы на повербанки,
USB ПК отключены, щупы Saleae сняты с Nucleo ВКЛЮЧАЯ GND; шлейф IPM/двигатель/AS5600
остаются подключёнными;15 В оставитьON, J1 покаOFF, Пуск/RESET не нажимать.
Ждём подтверждения этого состояния, затем сначала read-only автономная связь.
Пока НЕ считать перевод на повербанки или снятие Saleae выполненными; не включать
J1 автоматически и не запускать двигатель. Повторная прошивка не нужна.

## 2026-10-28: уточнение подключения — D4 на UART не перенесён

Пользователь сообщил: PB7 занят проводом TX Uno, Y-разветвителя/возможности
подключить третий провод нет. Требование переставить D4 на PB7 снято;
UART-соединение не разрывать. Карта D4 не подтверждена как UART_RX.
`capture_uart_power_event.py` НЕ запускался; его флаг D4_RX сейчас недопустим.
Никаких новых RESET/CLEAR/прошивок/импульсов в ответ на это уточнение не было.

Пользователь также уточнил, что обычно оставляет шлейф IPM подключённым и
обесточивает инвертор. Для дальнейшей работы считаем шлейф подключённым;
не требовать снимать его или двигатель при каждом тесте. Формулировка
«всегда» создаёт неопределённость о физическом отсоединении шлейфа в старых
тестах с ответом «готово»: их цифровые записи/счётчики сохраняют силу, но
отсутствие электрического подключения IPM из осциллограмм не следует.
Старые отчёты не переписывать; эту оговорку учитывать при выводах об изоляции.

Последнее явно подтверждённое питание: J1 физически снят, только J4 15 В
включены; новых переключений пользователь не сообщил. UART ORE при событии
15 В не доказан как причина ошибок AS5600; последующая связь продолжалась,
bad_count оставался 32. При подключённом шлейфе и стабильных 15 В сохранено
1209 полных I2C-чтений без target NACK/неполных кадров и без роста I2C-ошибок.
Не представлять исторический ORE как постоянную потерю команд или доказанную
помеху на проводе. Продолжать анализ I2C по существующим данным без требования
UART-разветвителя; любые новые физические подключения требуют отдельного
подтверждения их фактического выполнения.

## 2026-10-28:шлейф подключён,15ВON/J1 физически снят; пойман UART ORE после SD

Пользователь подтвердил оба физ.шага: шлейф34pin возвращён при J1/J4OFF,
J1 физически отсоединён; затем включеныТОЛЬКО15В. Обе платы/USB/датчик/Saleae
оставлены какбыли. На2805 реальныйTIM1/TIM8MOE0, никакихPWM/CLEAR/RESET/flash
вэтихдвухпассивныхпроверках. Исходныйизолированный5сPASSсохранён ниже.

`connected_15off_idle_r1`:6сSaleae,1209полныхASчтений,targetNACK/partial0,
счётчикиI2C/UARTdelta0,MCcurrent/occurred4/4,bus0,SDHIGH.
`connected_15on_idle_r1`:6сSaleae,1209полныхASчтений,targetNACK/partial0,
I2Cdelta0,UARTbad_count32 НЕРОС междуbefore/after,TXerrors0,bus4→5В,
MCcurrent4/occurred1028,pinreason4. SDпереходпри15ONдоэтогозахватасохранён.

Доп.сыройдамп `uart_after15_context_r1` беззаписей: first_break.tick_ms512944;
fatalUART.tick_ms512945,UV3_HARD_UART=4,last_uart_flags8=ORE,5принятыхбайт
aa55030000,ISRошибкиужеочищенывIRQ. Тоесть аппаратноеRXпереполнениечерез1мс
послеSD,непростоошибкаCRC. НельзяобъявлятьдоказаннымипомехуилиIRQзадержку!
Вfirst_reasonUno_link=8MCSDKпервое,first_uart_errors0;этоотдельнаязащёлка,
еёвремяневходитвструктуру,неприписыватьеёавтоматическипитанию.
ФактпередSD: UARTbad0, после15ONbad32 идалее32; живыевалидныекадрыпродолжаются.

ОтправленНОВЫЙasyncзапрос: переставитьТОЛЬКОD4 сWH/PA10 CN10-33 наPB7/RX
CN7-21,самUARTпроводнеотключать. D5SDA/D6SD/D7SCL иD0..3PWM прежние.
Ждём «D4 наPB7готов». Питание15непереключатьпоканеобъявленготовыйзахват.
КартаD4RX пока НЕподтверждена. J1физическиснят,15ON,ШИМOFF.

Подготовлены `tools/analyze_uart_rx_capture.py` (1152008N1,CRC32C; native3
back-to-backframes+CRCbitflip+badSTOP PASS) и `tools/capture_uart_power_event.py`.
Последнийпока НЕзапускался: проверяетстабильныйSDHIGH/UV4/bus<20/MOE0/свежие
кадрыибезростаисторическихUARTerrors; архивирует ВСЕснимки,потомОДИН
программныйRESETNucleoприJ1снятом/15устойчивых,3сbootcheckRXbad0/MCfault4/4.
ДалееManualSaleae8MS/s,trim40с,max120с,печатаетCAPTURE_READY иready.json.
ТОЛЬКОпослеэтого попросить пользователя15OFFна2с→15ON,безJ1/RESET/Пуск.
Поответуготово записатьstop.flag вкаталогcapture,скриптпишетещё2с иостанавливает
capture.stop() (НЕвызыватьcap.wait()дляmanual),сохраняет.sal/CSV/сырыеMCU/
wireUART/I2C. Во времясобытияникакихSWDчтений,чтобыисключитьвлияниедебаггера.
Никакойперепрошивки/PWM/CLEARэтотсценарийнеделает. ЕгоCLI:
`.venv/Scripts/python.exe -u tools/capture_uart_power_event.py
--j1-unplugged-15v-stable-d4-rx --allow-one-recorded-reset --outdir <new-folder>`.

Не запускатьнизковольтныйактивныйPWMнастарыхошибках32. Подготовленный
`low_bus_full_edges_trial.py`поканеприменялся/неразрешёнтекущимготовымдопуском:
сначалаидентифицироватьUARTсобытиенапроводеиCPU. Неперепрошиватьнаугад,
FIFO/приоритеты/пороги пока НЕменялись. Силовойпуск/FOCещёнепроверены.

## 2026-10-28:2805 установлена, совместный физический PWM-тест PASS; ждём подключение шлейфа

Пользователь попросил продолжать до рабочего результата. Подтверждённое исходное
состояние: J1/J4 OFF, шлейф34pin снят, NucleoUSBПК/Unoповербанк, Saleae подключён.
Карта: D0UH/D1UL/D2VH/D3VL/D4WH/D5SDA/D6SD/D7SCL. Мотор остаётся на J3.

2804 записана один раз/readback PASS. Первый совместный5с запрос завершён:
5000,032559мс; MC_Run/safety10000, medium2500,HFT80008, ADC80008/bad0,
100 штатных команд. Физический PWM16кГц4,000479с, 800полных чтений AS во время
фронтов, I2C/CRC/UART ошибок в прогоне0; SDHIGH, U/V перекрытий нет. WL не записан.
На старте2804 было15 BUSY: первый на8мс, PE0, ISR1, CR2=0, SCLHIGH/SDALOW,
START ещё не послан. Через290,994мс девятьклоков освободилиSDA, bus_clear347мкс.
Это отдельный стартовый случай, не ошибка приPWM. Снимки/осциллограммы сохранены:
`artifacts/live_bench_20261028/full_mcsdk_edges_r1/assessment.json`.

В драйвере найдены повторные preflight-попытки каждые20мс, пока существующий
допуск bus-clear ждёт Vbus<20 (фильтр MCSDK стартует от среднего порогов).
2805: после первого frozenBUSY/PE0probe и при неизменноSDALOW/SCLHIGH драйвер
ждёт разрешение bus-clear, не отправляя START/STOP/клоки и не сбрасывая счётчики.
Успешныйпуть чтения, encoder_core, тайминги и ошибка/STOPcleanup не менялись.
Actual-driver A/B при300мс закрытомдопуске: старый15BUSY, новый1BUSY;
оба девятьклоков+успешноечтение, первыйснимок сохранён. Регрессии retainedPE,
lostPE/missinghook, busclear failed/noPWM и полный fixture/race/math PASS.

2805 записана один раз/readbackPASS с12с Saleaeзаписью загрузки. Эта загрузка
была ссвободнымилиниями, ошибок0/609чтений наboot; физическаяветвь stuckSDA
наэтойзагрузке не понадобилась, не выдавать native replay за измерение железа.
Повторный совместный5с:5000,015706мс, MC_Run/safety10000, medium2500,HFT80007,
ADC80008/bad0,99штатныхкоманд; 800полныхASчтений прифизическомPWM16кГц,
I2Cerrors/NACK/BUSY/ARLO/BERR/CRC/UART0 сзагрузки. PWMокно4,000486с;
все5записанныхвыходов64006положительныхфронтов, SDHIGH, partial/NACKframes0.
573старыхархива SHAпроверены; источники2804 и первыйBUSYснимокнеизменны.
`artifacts/live_bench_20261028/full_mcsdk_edges_busy_wait_r1/assessment.json`,
`startup_capture_r1/startup_install.sal`,`run_r1/full_mcsdk_edges.sal`.

На плате сейчас2805,DONE/reason0/attempted1,MOE0 обоихтаймеров. MCSDK по-прежнему
OFF/FAULT с реальнымMC_UNDER_VOLT=4; владеет невыведеннымTIM8, реальныйTIM1 —
отдельный диагностический генератор на прежних6AF6. Это не production RUN,
не проверка вращения/FOC/RMS; powered inverter I2C cause ещё не установлена.
Защиты/пороги/Break/deadtime не ослаблялись. Два flash —2804 и целевоеисправление2805;
поодномузапросу5с накаждойзагрузке. НикакихмоторныхSTART/CLEAR/авторетраев.

Отправлен async-запрос пользователю: вернуть ТОЛЬКО34pinшлейф при J1/J4OFF,
J1 физическиотсоединитьотисточника,15В покаOFF; платы/Saleae/датчикнепереставлять.
Ждём точногоответа «шлейфподключён,J1отсоединён,15Ввыключены»; пока не считать
новоефизическоесостояние подтверждённым. Следующий шаг ТОЛЬКО passive6с I2C
capture `tools/connected_idle_i2c_probe.py --j1-physically-unplugged --supply15 off
--outdir <new-folder>`: безPWM/RESET/CLEAR/flash. Затем отдельно запланировать
15В-only/J1физическиснят, сохранив guarded <20В; силовойпуск сейчаснеразрешён.

## 2026-10-28:2804 готова на ПК, НЕ записана — MCSDK + отдельные реальные TIM1 фронты

Текущий установленный образ остаётся2803, состояниеDONE/MOE0 после прошлого5с.
Новых обращений к программатору, FLASH, RESET, CLEAR, START или PWMrequest нет.
Подключения прежние:J1/J4OFF,34pinшлейфотсоединён,NucleoUSB,Unoповербанк;
SaleaeD0..4PWM/D5SDA/D6SD/D7SCL. Ничего включать/переставлять не требуется.

Подготовлен пакет artifacts/live_bench_20261028/full_mcsdk_edges_r1,build2026102804.
Полная штатнаяMCSDKboot/SysTick/scheduler/safety/обработкакоманд сохранены.
Выполненоразделениевладения: MCSDK PWM_Handle.TIMx=реальныйTIM8 безGPIO,
CEN0/CCER0/MOE0. ADC/backendPWMC остаётсяна исходныхпериферийныхцепях,
моторныйSTART дополнительноблокирован. TIM1 принадлежитТОЛЬКО изолированному
генератору на прежних6выводахAF6. Это диагностическое совмещение MCSDK OFF/FAULT
среальнымифронтами, НЕобычныйproductionTIM1моторныйRUN.

ШтатныйMC_UNDER_VOLT=4 должен оставатьсяАКТИВНЫМ, реальнаяшина<20В; значения
Vbus и маскиаварий неподменяются. Другойтекущий/сохранённыйfault немедленно
передаётсяизштатнойsafetyкостановкеTIM1;таймернаяпривязка/состояниеTIM8
контролируются. TIM1BKE/deadtime/фильтр иинициализаторыTIM/ADC неизменны.
SD/B1,UARTошибки/300мс,ADCсвежесть5мс/JEOS/JQOVF,main5мс иDWT5с соблюдены.
PanicError/HardFault отключаютобаMOE; моторнаяUARTтелеметриячитаетTIM8, чтобы
нетрактоватьдиагностическиефронтыкакмоторныйпуск. AS5600/ADCисточникинеизменны.

Подготовленныйпрогон:1сфон+2сфиксированныйPWM16кГц+2сV/fмодуляция16кГц,
ровноодинзапроспозагрузке; Saleae8MS/s10с,старыйпорядокщупов. WLне записан
(егоD5используетSDA). МоторноеRUN/силоваячасть/квалифицированныйRMSнепроверяются.
Пакетвключаетtools/full_mcsdk_edges_host.py:отдельныеinstall/status/run;run
требуетявногофлагаодного5сзапроса,никакихавторетраев/автоCLEAR/моторногоSTART.

НаПК:target0errors/0warnings;RAMзапас2688байтсверхheap/stack,лимит2600не снижен.
ДиагностическиеstackframesIRQ272/main280байт. МодельдвухреальныхCпутей320257
проверок/80kобновлений/10kштатныхPWMoff,35инъекцийаварий; IRQrace15 иmath513505
PASS. Всего833777native,73негативныхhost/CRCcases.461старыхархивныхфайлов и
sealedисточники2803 SHAпроверены. verification/report.json/manifestssealed.
Реальныефронты/времяIRQ/I2Cна2804 ЕЩЁНЕизмерены;онибудутрезультатомотдельного
пятисекундногозапросапослезаписииreadback. Текущиестарыеосциллограммыцелы.


## 2026-10-28:2803 — полный защищённый MCSDK OFF/FAULT + ADC/VF/UART/AS5600,5с PASS

По запросу пользователя добавлены полнаяMCSDKboot/SysTick/scheduler/safety,
штатныйuno_link_poll/uno_handle_valid_frame и штатные ответы/телеметрияUART.
J1/J4OFF,шлейф34pin отсоединён; NucleoUSB/Unoповербанк, картаSaleae прежняя.
2803 записанаОДИНраз/readbackPASS; Unoнеперепрошивалась. НикакихCLEAR/START.

Важно: это ЗАЩИЩЁННОЕOFF/FAULT приложение. Реальнаяшина0В,MC_UNDER_VOLT=4
сохранён. UV/температурныепороги и безопасностькоманд не изменены; кроме них
оставлен дополнительныйfixtureSTARTinhibit и GPIOlockedLOW/MOE0. Физических
фронтов в ЭТОМпрогоне нет. Нельзя выдаватьего за нормальныйMCSDKRUN подШИМ.
ПолныйнаборMCSDK задач работает вместе с приватнымV/f вычислением/активной
веткойобработкиADC;327Весть только в приватной нормализации, не вVbusMCSDK.

Одинзапрос завершёнDONE/reason0/attempted1 через5000,021624мс. Внутри5с:
MC_Run10000,safety10000,medium2500,HFT80007,TIM80007,ADC80008/accepted80007,
99кадровпереданы штатномуобработчику. MaxTIM12,14мкс,ADC18,56мкс,main309,12мкс.
I2Cошибки/NACK/BUSY/deadline/ARLO/BERR/resets/parks delta0. RXbad0,TXошибки0.
2320чтенийAS и975TXcompleted — интервалhost до/после10сcapture, НЕточные5с.
Saleae8MS/s10с:2011полныхчтенийAS,ошибочныхNACK/неизвестныхкадров0,
всеD0..4LOW иSDHIGHвоВСЕХCSVстроках. Первыйобменнеполонпристартеcapture;
сохранён/исключёнизквалификации,причинанеполнотынеустановлена.

ИсточникAS/ADC,инициализаторыTIM/ADC/UART иMCSDKзащиты проверены сравнением;
nativecore15149/platform200038/newguard17/math513505 PASS; target0errors/
0warnings,RAMзапас2616байт сверхreservedheap/stack,лимит2600неуменьшался.
381старыйархивныйфайл иpredecessorsealedbytes SHAпроверены. Записи:
`artifacts/live_bench_20261028/full_mcsdk_diag_r1/run_r1/full_mcsdk.sal`,
`assessment.json`,`runtime_sha256.json`. ПредыдущийфизическийPWM2802цел.

Вывод: ошибканевоспроизвелась при полнойпрограммнойнагрузке вOFF/FAULT;
раньшеотдельноPWM+ADC+UARTтожеI2C0. ЭтоНЕдоказательствоработыAS приинверторе
поднапряжением или устранениясиловойпричины. RMS/амперы/вращениенеизмерялись.
Текущийобраз2803 — диагностический,не длясилового. J1/J4/шлейфоставитьOFF.


## 2026-10-28: AS5600 + физический TIM1 + реальные ADC IRQ + UART RX/TXDMA — полный5с PASS

По запросу пользователя добавлены ADC иUART в изолированный тест; J1/J4OFF,
34-контактный шлейф отсоединён, NucleoUSBПК/Unoповербанк, карта Saleae прежняя:
D0UH/D1UL/D2VH/D3VL/D4WH/D5SDA/D6SD/D7SCL. Пользователь ничего не переключал.
Текущий образ2026102802: DONE/reason0/attempted1, MOE0/UIE0 после окончания.
Силовое/15В/шлейф с этим изолированным образом не включать/не возвращать.

Добавлены исходныеMX_ADC1/2_Init, калибровка/включение реальныхADC, штатный
current_shunt IRQ и егоTIM1 epoch; исходныеUSART1 RXISR/ring, TXDMA/TC,
CRC32Cparser. Приёмочные кадры НИКОГДА не передаются моторному обработчику;
MCSDK моторное приложение не инициализируется. TX43bytes50Гц и реальныйRX
отUno≈20Гц; DMAMUX1 clock включён отдельно перед штатнымUART/DMAinit.
Источник AS5600, Break/deadtime/фильтр, ADC/UART и защитные пороги не изменены.
Добавлены только измерения и fail-stop5мсADC/main,300мс свежегоUART кадра.

Первый2801: одна запись/readbackPASS (первый install_r1 отказал лишь по
разорванномуCRC чтениюSRAM, flash0; install_r2 записал один раз). Его первый
совместный запрос АБОРТ через1000,051мс,reason32 при переходе1с→ШИМ;
на Saleae лишь один импульс/окно4,375мкс. ADC16002/bad0, I2C/UART errors0,
SDHIGH/Break0. Это НЕ полный5с PASS, файл `combined_io_diag_r1/run_r1/`
целиком сохранён, отрицательные deltas в незавершённых фазах исходного
host report НЕ использовать как измерения. UART/ADC причину не доказали.

В диагностическом guard найдена реальная гонка: main читает phase=PRE,
TIMIRQ публикует phase=ON/MOE1, main сравнивает старыйphase с новымMOE и
ложно получаетreason32. Также stop мог публиковатьMOE0 перед terminal state.
В2802 три чтения phase/state/MOE делаются в коротком PRIMASK-снимке;
terminal state и отключениеPWM публикуются атомарно. Внутри маски нет циклов
и вызовов, hardwareBKIN независим; ограничения5с/5мс/300мс не повышались.
Принудительное IRQ-воспроизведение настоящих старого/новогоC bodies наПК
подтвердило обе старые гонки, исправление и7контролей настоящих нарушений.
Это ошибка самого тестового контроля, не доказанная причина прежних
AS5600 ошибок в силовомRUN. ADC IRQ дизассемблирован: неожиданныйMCSDK_HFT
в нём отсутствует, альтернативная гипотеза исключена.

2802:0errors/0warnings, RAMзапас4456байт сверхheap/stack; nativeguard192050,
ADC240008(80kIRQ), UARTDMA292520(2048кадров, старый39byteобрыв), parser271,
race15проверок PASS.2802 записана один раз/readbackPASS; после живого
подтверждения роста ADC/RX/TC выдан ОДИН повтор незавершённого5с запроса.

`artifacts/live_bench_20261028/combined_io_diag_r2/assessment.json` PASS:
5000,004035мс;80008TIMIRQ/80007реальных ADC_IRQ во время5с, ADC_bad0,
guard0; maxTIMIRQ12,965мкс, ADC19,794мкс, foreground244,047мкс.
ASчтения по фазам1с/2с/2с:200/400/400, всего1000 и800 при физических
фронтах, errors/NACK/BUSY/deadline/ARLO/BERR/forced-reset/park deltas0.
UART в интервале до/после записи:247принятых CRCвалидных кадров и620
завершённых DMAпередач; RXbad/hardware/overflow/TXtimeout/DMA/queue errors0.
Эти UARTdeltas включают хвост до/после5с — не выдавать их за точное число
кадров внутри5с. Guard контролировал свежесть кадров300мс во время запроса.

Saleae8MS/s10с `.sal`/CSV: пятьPWM≈16кГц, по64005..64006положительных
фронтов, физическоеокно4,000456625с; U/V одновременныхHIGHнет, WL не виден.
SD HIGH во всех сырых строках, послеавтостопаPWM0..4LOW.2011полных AS
чтений в10с, ошибочныхNACK/неизвестных кадров0; конечныеNACK ведущего
нормальные. Первый обмен захвачен неполно при старте записи (начальное
SCLLOW, partial6bits до1,078мс); он исключён из квалификации, не выдан за
успешное чтение. Это до запроса/ШИМ, источник неполноты не установлен.
303 старых архивных файла и все sealed-байты SHAпроверены, новый runtime
получил отдельный runtime_sha256.json; неудачный2801 и старые захваты целы.

Вывод: одновременная работа TIM1+ADC+UART+AS5600 в ЭТОМ изолированном
режиме не воспроизвела I2Cсбой. Не объявлять прежнюю силовую проблему
исправленной или строго аппаратной: полный производственныйMCSDK
планировщик/обработка моторныхкоманд, подключённыйинвертор и вращение здесь
не проверялись. ADCвходы при снятомшлейфе плавающие; амперы/RMS не квалифицированы.

## 2026-10-28: реальные фронты TIM1 + AS5600 без инвертора — PASS, новых ошибок0

Пользователь подтвердил окончательно D5→PB9/SDA, D7→PB8/SCL, D6SD остаётся;
J1/J4OFF,34-контактный шлейф отсоединён. Выполнен ОДИН разрешённый запрос
изолированного2795, без перепрошивки/CLEAR/RESET/моторногоSTART в этом этапе.
До запроса свежий MCUreport2795 IDLE/reason0/attempted0/MOE0/ASflags7,
ASerrors0 в этой загрузке (прежний стартовыйBUSY1 остался в старых записях).
Пассивная2с запись8MS/s реально декодировала411 чтенийAS5600 безNACK адреса.

`artifacts/live_bench_20261028/as5600_pin_pwm_5s_r1/assessment.json` PASS:
MCU DONE/reason0,5000,004659мс;80008 TIM IRQ, максимумIRQ12,018мкс,
max foreground gap85,212мкс, локальныйMOE0 иUIE0 после окончания.
Тест5с:1с тихих расчётов/MOE0 +2с фиксированныхPWM +2с модулированныхPWM.
Успешные ASчтения по границам MCU:201/400/399 соответственно, всего1000;
при физических фронтах799, новыхerrors/NACK/BUSY/deadline/ARLO/BERR/forced
reset/normal park0. Бюджет5с не расширялся: реальныеPWM фронты были4с.

Saleae `.sal` иCSV сохранены в `.../run/`, запись8MS/s10с успешна.
5наблюдаемых линийUH/UL/VH/VL/WH имеют по64006 положительных фронтов,
медиана несущей16кГц, окно фронтов4,00047с по часам анализатора. ПарыU/V
без наблюдённого одновременногоHIGH; WL не записывался (его щупD5 занятSDA).
Фиксированные high-duty UH/VH/WH≈22,8/47,8/72,8% с учётом deadtime;
после перехода реально меняются примерно41,6..54%, то есть модуляция есть.
SD HIGH во всех сырых строках (min=max1); Break не зафиксирован.
В10с осциллограмме декодировано2010 полных чтений AS5600, адрес/данные без
ошибочныхNACK и неизвестных кадров; нормальные2010 последнихNACK ведущего
после чтения не выдаются за неисправность датчика. Один неполный обмен справа
совпал с концом записи и отмечен как right-censored, не как ошибкаI2C.

165 старых архивных файлов и все sealed-байты провереныSHA; новые записи
получили отдельный sha256.json, исходные отчёты не подменялись. Текущее:
2795 DONE/attempted1/MOE0, питание/шлейф/щупы не менять автоматически.
Это отрицательный контроль для минимальных AS5600+TIM1 при отключённом
инверторе. ADC/UART/производственный планировщик не выполнялись. Он НЕ
доказывает исправление/локализацию прежнего сбоя полного моторногоRUN,
не квалифицирует вращающийся датчик/FOC и аналоговые/суб125нс помехи.

## 2026-10-28: установлен изолированный AS5600/TIM1 тест2795; ШИМ ещё НЕ запускался

Пользователь разрешил продолжать поиск с физическим ШИМ и подключил Saleae.
Подтверждённое новое состояние: J1/J4OFF, ниже20В, NucleoUSBПК, Unoповербанк,
34-контактный шлейф IHM09M2↔STEVAL ОТСОЕДИНЁН; AS5600 и двигатель оставлены.
Не включать силовое/15В и не возвращать шлейф с изолированным образом.

Вместо вспомогательных выводов2793 создан минимальный2794: реальные6штатных
TIM1 выводов, исходные AF/BKIN/DTG/фильтр, расчёт V/f, one-shot5с с DWT,
B1STOP и остановкой приBreak/утрате main freshness. Моторное приложение,
ADC/DMA/UART не инициализируются. ШИМ не запускается при загрузке/из веба.
Порядок будущего запроса:1с расчёты/MOE0 →2с фиксированных25/50/75% PWM →
2с модуляции по исходному MCSDK →MOE0. Это не полный производственныйRUN.
Исходные моторные защиты/пороги в производственных файлах не изменены;
моторный режим в образе не запускается, физический шлейф отсоединён.

2794 была записана/readbackPASS. При загрузке обнаружилась собственная
ошибка тестового режима: безусловный mic_encoder_allow_bus_clear(false)
запрещал существующее восстановление и в покое. До первогоШИМ:
ASreads0, BUSY растёт, PE0/CR1=0x200, ISR1, SCLHIGH/SDALOW, CR2=0.
Raw first fault иrelease_probe сохранены в
`pin_pwm_diag_r1/idle_first_fault_r1/`; это не воспроизведение старогоPWMсбоя.
Возможное удержание незаконченного байта после сброса ведущего — гипотеза,
без временной осциллограммы причину исходного LOW не объявлять доказанной.

2795 меняет только разрешение уже проверенного bus_clear в изолированном
main: mic_pin_poll(); mic_encoder_allow_bus_clear(!mic_pin_active());
mic_encoder_poll(). Весь5с запрос, включая тихую секунду, запрещает clear;
сам драйвер дополнительно требует MOE0/PE0, первый сохранённый BUSY и
завершённыйPE0 probe. Один clear за загрузку,9открытостоковых тактов+STOP.
encoder_core/platform, время3мс/фильтры/первичные записи не менялись.
Native192044 тестов PWM-bound/STOP/BKIN, исходные I2C-тесты,92 bus-clear
сценария и3 full-driver casePASS; сборка0errors/0warnings.2795 записана
с readbackPASS. На железе clear result2=CLEARED,9тактов, линии1→3;
затем ASчитает с valid_flags7, стартовыйBUSY1 сохранён, новых ошибок нет.
165 прежних файлов сохранены в `pin_pwm_diag_r2/preserved_records/`.
Тестовый запрос ШИМ ещё НЕ выдан; attempted0, MOE0.

Saleae A7D1BB81883C0092 реально доступен. Запись загрузки24MS/s получила
ReadTimeout — НЕ выдавать её за состоявшийся захват. Пассивные2с и10с
8MS/s успешно сохранены (`passive_saleae8m_r1`, `passive_saleae8m_10s_r1`).
При первой проверке все каналы были статичны: I2C тогда не был подключён.
8MS/s=125нс, не квалифицирует аналоговые/суб125нс помехи.

Пользователь уточнил, что свободен толькоD7, D6 занят авариейSD, и просит
сохранить её. Окончательная предложенная карта: D0UH/D1UL/D2VH/D3VL/D4WH
оставить; D6SD оставить; только щупD5 снять сWL и подключить кPB9/SDA CN10-5;
D7→PB8/SCL CN10-3; GND прежний. Это перенос щупа, не выходовPWM/проводаSD.
Будут измеряться5PWM+SD+SCL+SDA; шестой физическийWL в этом захвате не виден.
Ждём подтверждения «D7=SCL, D5=SDA готовы» на последний async-вопрос.

Хост: tools/run_pin_pwm_diag.py run --isolation-confirmed --scl-sda-ready
--outdir <НОВЫЙкаталог>. Новая идентичность/CRC64wordSRAM, запись Saleae
начинается раньше единственного запроса,10с8MS/s, никакогоSWD опроса внутри
5с, никакого автоматического повтора при неоднозначном ответе. Затем
анализ tools/analyze_pin_pwm_i2c.py: картаD5SDA/D6SD/D7SCL, нормальныйNACK
ведущего после последнего байта чтения не считается ошибкой датчика;
ошибкаNACK адреса/записи отделена. Семантические positive/negative тестыPASS.

## 2026-10-27: AS5600 на установленной2792 в покое60с — новых ошибок0

По последнему указанию пользователя сначала проверен датчик без новых
ШИМ-тестов. Подготовленная2793 отложена, не установлена; щупы и перемычку
по её карте сейчас не подключать. Подключения и питание не переключались.

`artifacts/live_bench_20261027/as5600_installed2792_idle60_r1/report.json`:
PASS,60,062с наблюдения; счётчик успешных чтений446609→458649 (+12040,
около200Гц). Ошибки0→0; дельты NACK/deadline/BUSY/ARLO/BERR_clears,
forced_resets иnormal_parks равны0. В начальном/конечном снимках угол3969,
magnet_status103 (0x38 mask=0x20), bus/angle flags valid. Свежесть доказана
ростом sequence/sample_ms и чтений, это не застывший отчёт. Во время60с
не было SWD-опроса; исходный и конечный отчёты прочитаны поCRC/sequence.
Сырые288-byte отчёты,320-byte fault_record,144-byte release_probe илоги
сохранены в новом каталоге. Два сохранённых захвата побайтно не изменились.

Это установленная2792 в покое: TIM1MOE0, прежние6 фазныхGPIO LOW, реальная
шина10В, вычислительный запросDONE/reason0 от прежнего теста не повторялся.
ФоновыеADC/связь продолжают работать, то есть это НЕ отдельный минимальный
образ «толькоAS5600». START/новые запросы нагрузки/CLEAR/RESET/прошивки0.
Неподвижный датчик читается без зарегистрированных I2C ошибок в этом
наблюдении. Виновность физическихPWM фронтов, инвертора или вращения этим
контролем не установлена; квалификации датчика дляFOC/вращения пока нет.

## 2026-10-27: подготовлен2793 для реальных логических фронтов; НЕ установлен

Пакет `artifacts/live_bench_20261027/logic_edges_diag_r1/`: build2793,
target0errors/0warnings, native1272745 проверок PASS, host orchestration5
случаев и отдельные5 случаев Saleae/неоднозначной записи PASS. Машинные
секции V/f/ramp/PWM арифметики идентичны2710. RAM запас2704 байта сверх
прежней резервации heap/stack. Это проверки наПК, не аппаратный результат2793.

Цель: один запрос5с, из них2с тишины и3с физических PWM фронтов на свободных
PC6/PC7/PC8 отTIM8. РеальныеTIM1/ADC расчёты и AS5600 работают непрерывно.
TIM8 копируетARR/PSC/CCR1..3 TIM1, но фаза несущей относительноADC независима.
Оригинальные6 фазныхGPIO LOW иTIM1MOE0 на всём интервале. Команды моторного
ENABLE запрещены. ПорогиUV/защит, BKIN TIM1, UART PB6/7, I2C PB8/9 не менялись.
ДляTIM8 дополнительный активныйLOW BKIN наPD2, AOE0/LOCK1; одна перемычка
PA6 CN10-13 → PD2 CN7-4. Исходное SD/PA6 подключение остаётся. Пуск повторно
не разрешается в этой загрузке. Нет новых моторныхSTART/CLEAR/RESET/прошивок.

Перед записью2793 пользователь должен оставить J1 иJ4/15В OFF, прежнее
подтверждённое независимым прибором напряжение<20В; NucleoUSBПК,
Unoповербанк. Двигатель, шлейф, TP23→1кОм→PA4, AS5600 не менять. Перенести
щупы Saleae с прежних шести фазныхPWM на следующую карту, затем USB SaleaeПК:

| CH | Сигнал | Разъём Nucleo |
|---|---|---|
| 0 | TIM8_CH1 PC6 | CN10-4 |
| 1 | TIM8_CH2 PC7 | CN10-19 |
| 2 | TIM8_CH3 PC8 | CN10-2 |
| 3 | AS5600 SCL PB8 | CN10-3 |
| 4 | AS5600 SDA PB9 | CN10-5 |
| 5 | SD PA6 | CN10-13 |
| 6 | TIM8 BKIN PD2 | CN7-4 |
| 7 | Маркер PC9 | CN10-1 |
| GND | Логическая GND | CN7-19 |

Распиновка: официальный ST UM2505 Rev7 table16; AF: DS12589; отсутствие
подключения PC6..9 к силовомуMC разъёму — схема IHM09M2 DB4728 page2.
Перемычку и щупы подключать ДО записи2793: приLOW/floatingBKIN новый образ
защёлкнет отказ и не будет автоматически снимать его. Не нажиматьПуск/RESET.

129 прежних файлов (включая2792 raw/build/install/compute) сохранены иSHA
проверены. Установщик сначала дополнительно читает текущие fault_record и
release_probe с2792 в новый каталог, затем одна запись2793+readback+boot check.
Тестовый runner начинает10с захват24MS/s до одноразового запроса, безSWD
опроса во время5с нагрузки; сохраняет.sal/CSV и новые raw records. При
недоступном физическомSaleae запроса нет, при неоднозначном ответе нет повтора.
АнализCSV проверяет3с маркер, реальные~16кГц фронты всех3каналов, SD иI2C
активность. ДекодерI2C протокола в этом анализаторе НЕ реализован: ошибки
оцениваются отдельно по неизменённым счётчикам драйвера и первому захвату.

Отрицательный результат2793 не исключает связь по исходному шестипроводному
жгуту, силовуюEMC или влияние питания/вращения: здесь3 вспомогательные линии
и неподвижный датчик. Измерение аналоговых выбросов Saleae не подтверждает.
Пакет готов, но физическая запись/проверка2793 ещё НЕ выполнены; наNucleo
по-прежнему2792, её одноразовый вычислительный тест уже завершён.

## 2026-10-27: полный вычислительный контроль2792 5с PASS, I2C ошибок0

После «окей» продолжен подготовленный диагностический этап при прежнем
подтверждённом J1/J4OFF/мультиметр<20В/NucleoUSBПК/Unoповербанк/SaleaeOFF.
Это вычислительный запрос, не команда моторного START; фазные выводы LOW.

Первый запрос2791: ABORTED reason8 через17,946мс,287 TIM/ADC циклов,
ошибок I2C0. Это НЕ полный5с контроль и не доказательство исправности при
нагрузке. Установлена ошибка в собственном диагностическом guard:
аргумент now считывался до volatile adc_at; ADC IRQ между ними публиковал
метку позже now, unsigned разность давала ложный возраст>5мс. Зарегистрированные
max gapsADC64мкс/foreground310мкс и native воспроизведение согласуются с этим.
Новый порядок: ISR/foreground timestamps читаются перед текущим DWT clock.
Оба порога5мс прежние, настоящие stale-события по-прежнему отклоняются.

Исправление2792 в `no_switch_diag_r3/`:20000 preemption/wrap случаев,
два настоящих5мс+ stale negative controls,968699 native проверок PASS;
target0 errors/0 warnings, прежние арифметические машинные секции и I2C,
порогиUV/BKIN/калибровка/аппаратныеGPIO locks сохранены.2792 записана один
раз с readback; Uno не прошивалась. Никаких моторных START/CLEAR не было.
В2792 только один повтор вычислительного запроса после установленной причины.

`no_switch_diag_r3/compute5s_r1/report.json` аппаратный PASS:
DONE/reason0,5000,012мс;80008 TIM updates/80007 ADC IRQ/80006 accepted,
2500 medium ticks500Гц, частота приватной копии достигла5Гц, CCR2330..2980.
max TIM/ADC execution11,21/18,62мкс; max foreground gap318,1мкс.
За полный интервал чтения до/после +1230 успешных AS5600, ошибок0;
NACK/BUSY/deadline/ARLO/BERR/reset/normal-park дельты0. Реальный MOE0,
фазныеGPIO LOW, localstop0/guard0, активная/сохранённая маскиMC0,
реальная шина10В, отдельная приватная replay-нормировка327В не выдаётся
за физическую шину. Все94 архивных файла SHA-проверены, первичные записи
и отчёт короткого отказа2791 оставлены без подмены.

Вывод ограничен этим контролем: сам расчёт V/f+синхронный ADC не воспроизвёл
сбой I2C. Простая нехватка CPU под этой нагрузкой не подтверждается.
Причина при настоящем RUN пока не доказана: здесь отсутствуют и логические
PWM фронты на фазных выводах, и силовые переключения, и вращение/магнитное
поле двигателя; Nucleo питается черезUSBПК, а прежние HV-прогоны были на
повербанках. ФронтыGPIO и силовую часть этот тест по отдельности не разделяет.
Не объявлять AS5600 квалифицированным при вращении/дляFOC, токи калиброванными
или электрические помехи/брак доказанными. Полный вывод: assessment.json.

Текущее: диагностическая Nucleo2792 наUSBПК, Uno2709 на повербанке,
J1/J4OFF, SaleaeOFF, двигатель/AS/TP23 неизменны. Полный вычислительный тест
завершён и одноразовый запрос использован. С2792 силовое/15В не включать;
для моторного этапа сначала вернуть сохранённую рабочую2710 отдельным шагом.

## 2026-10-27: установлена диагностическая2791, readback/GPIO locks PASS; нагрузки ещё не было

Пользователь явно подтвердил Nucleo наUSBПК, Uno на повербанке, J1/J4OFF,
мультиметр<20В, SaleaeOFF и попросил записать2790 с readback, захваты сохранить.
Доступность точного ST-LINK serial003A002C3335510933383531/COM13 проверена.
Перед записью свежие status/SD/AS raw hex/декодированные снимки заархивированы
отдельно с SHA. Текущий исходный статус2709/2710 SAFE/PWM0/ARM0/DC10В,
ASerrors0; это текущая загрузка, прежние387 ошибок остались в старых архивах.

Первая запись2790 и чтение обратно успешно прошли (Download verified
successfully), но boot guard отказал: phase_pins_gpio_low0/guard4.
Причина установлена реальными SWD регистрами и исходником: mc_lock_pins()
в MX_MotorControl_Init запирает конфигурацию фазныхGPIO; поздний HAL_GPIO_Init
не меняет AF2 на GPIO OUT. LCKR A0x107c2/B0x10003, все6 фазных выводов
имели MODER2, ODR/IDR LOW, реальный MOE0. Диагностических запросов/START0.
Это ошибка порядка настройки в2790, не первопричина AS5600 при ШИМ.

Исправление выполнено отдельным образом2791 в `no_switch_diag_r2/`,
исходные2790 и полные логи/регистры сохранены. GPIO LOW настраивается сразу
перед MX_MotorControl_Init, затем MCSDK сохраняет собственные аппаратные
блокировки. Захват protection snapshot/рабочий init остаются после boot.
Ни LCKR, ни BKIN, ни UV/пороги/калибровка не отключались. Модель с настоящим
поведением lock воспроизвела отказ2790 и PASS ранней настройки;928697 native
проверок и target build0errors/0warnings PASS. Арифметические машинные секции
V/f/фазы/рампы/CCR прежние, драйвер I2C прежний.

Исправленная2791 записана один раз и проверена чтением обратно. Всего за
этот этап2 записи Nucleo (2790, затем обоснованное исправление2791), Uno0.
`no_switch_diag_r2/install_usb_r1/report.json` PASS: реальный MOE0,
GPIO LOW и OUTPUT mode1 всех6 фаз проверены SWD, все lock bits сохранились,
BKIN BKE включён. Boot report build2026102791, IDLE/attempted0/guard0/DC10В,
AS5600 errors0, чтения продолжаются, adc_quality_flags1, ADC heartbeat свежий.

`no_switch_diag_r2/post_install_preflight_r1/report.json` PASS: только чтение,
запросов вычислительной нагрузки0, START/CLEAR/Uno-reset0. Старый HMI намеренно
не поддерживает нормальный motor-control peer2791; НЕ чинить это перепрошивкой
Uno/RPC, не запускать обычный Пуск. Контрольная нагрузка запускается только
отдельным SRAM-request через ST-LINK с исходными physical OFF условиями.
Пять секунд ещё НЕ выполнялись.53 архивных файла повторно SHA-верифицированы.

Текущая конфигурация: диагностическая Nucleo2791 на ПК; Uno2709 на повербанке;
J1 и15В выключены, Saleae отключён, мотор/AS5600/TP23 неизменны. С этой
диагностической прошивкой силовое/J4 не включать. Рабочая2710 сохранена в
restore для отдельного возврата. Полное доказательство: installation_evidence.json.
Готовый следующий запрос, только при авторизации пользователя на прогон:
`python tools/run_no_switch_diag_lockfix.py --confirm-j1-j4-off-meter-below20-nucleo-usb --request-once --outdir <new-folder>`.

## 2026-10-27: диагностическая Nucleo2790 собрана и проверена на ПК, НЕ записана

Пользователь подтвердил J1/J4OFF, независимый мультиметр<20В, обе платы
на повербанках, USBПК/SaleaeOFF и поручил подготовить диагностическую прошивку.
Пакет: `artifacts/live_bench_20261027/no_switch_diag_r1/`. Меняется только
Nucleo; Uno2709/Linux/HMI не перепрошивать и не перезапускать. Текущая
аппаратная конфигурация ещё2709/2710. Реальных START/CLEAR/RESET/flash=0.

Предварительный полный Wi-Fi статус/SD/AS first-fault/PE0 сохранён отдельно
в preserved_live (SAFE/PWM0/ARM0/DC10В, enc_errors0 текущей загрузки).
22 прежних архивных файла плюс отчёты/сырые записи двух пусков и покоя
сохранены в36 файлах preserved_records, все SHA проверены. Нулевая текущая
история не подменяет старые387 ошибок в сохранённых файлах. Рабочие2709/2710
и калибровка не менялись; исходные образы Nucleo2710 сохранены в restore.

Новый образ2026102790 — исключительно вычислительная диагностика:
все motor ENABLE запрещены, mic_local_stop_enable_outputs всегда отключает
MOE, шесть фазных выводов принудительно GPIO LOW. PA6/BKIN, PA4/TP23,
AS5600 PB8/PB9 не переназначаются. Реальные MCSDK fault masks/UV/BKIN/
пороговые параметры и voltage telemetry не подменяются/не ослабляются.
Обычный силовой RUN и нормальная совместимость с HMI у2790 намеренно
не поддержаны; не пытаться чинить RPC/пару прошивкой Uno из-за этого.

Один отдельный SRAM-request через ST-LINK, не автоматический старт при boot.
При шине>=20В, плохой конфигурации защит/пинов, устаревшем ADC>5мс,
неожиданном MOE, локальном STOP или ошибке расчёта тест отказывает/прерывается.
Один запрос на загрузку; лимит5с по DWT проверяется в TIM IRQ и foreground.
Новый тест ещё не запускался. Реальные импульсы на фазных выводах не выдаются.

Копия ACIM/VF исполняет настоящие функции угла/контроллера/CCR и приватную
MCSDK рампу500Гц: 0→5Гц за3000мс, затем до общего лимита5000мс. Нормировка
приватной копии327/2 как в рабочем ACIM_VF_Clear; это явно отдельная величина,
физический Vbus остаётся измеренным. TIM1/ADC и исходный оконный планировщик
используются для вычислительной активной ветки при физическом MOE0.
Токи/RMS нулевой силовой схемы не объявляются измеренными токами двигателя,
CM_VALID в диагностике снят. Покрытие вычислительной ADC-ветки на железе
нужно проверить, особенно при возможной негодной нулевой точке без15В.

`verification/report.json` PASS: target build0 errors/0 warnings,
928694 проверок на ПК; настоящий ADC IRQ исполнен на80000 модельных
конверсиях при MOE0, принято79999. Настоящие MCSDK ramp/angle/VF/PWM функции:
80000 расчётов,2500 medium ticks, CCR2330..2980. Их5 машинных секций
совпадают с установленной2710 побайтно до релокаций. I2C драйвер сохранён:
200 нормальных чтений, PE enable1/disable0, ошибки/cleanup/frozen records
проверены на модели.76 отрицательных проверок CRC/sequence/admission,
5 сценариев host с полностью fake ST-LINK (реальных аппаратных обращений0).
Размер стека ADC IRQ368Б, load_poll328Б; запас RAM сверх heap/stack2768Б.
Это offline-проверки, не измерение электрических фронтов/частоты/stack watermark.

Готовы install_no_switch_diag.py (одна запись Nucleo и readback, без запуска),
run_no_switch_diag.py (один SRAM-request, чтение до/после без SWD-поллинга
во время5с, локальный стоп независим от хоста), CRC/sequence decoder,
символы и хеши HEX/BIN/ELF. Установщик ещё НЕ запускался.

Единственное ожидаемое действие пользователя: подключить только Nucleo
к ПК по USB вместо повербанка. Uno оставить на повербанке, J1/J4OFF,
SaleaeOFF, мотор/AS5600/TP23 не трогать. После сообщения о подключении
сверить физическую доступность и записать2790 с readback; затем отдельный
контролируемый диагностический запрос, не обычный Пуск. Не включать15В/J1
с диагностическим образом; рабочую2710 восстанавливать отдельным этапом.

## 2026-10-27: подготовка проверки вычислительной нагрузки без силовых переключений

Пользователь запросил подготовить тот же TIM1/ADC/AS5600 без силовых
переключений, защиты не ослаблять, захваты сохранить. Запрошено выключить
J1 и15ВJ4, оставить платы на повербанках и всю проводку, USBПК/SaleaeOFF,
не нажимать Пуск/RESET, подтвердить по независимому мультиметру DC<20В.
Пассивный архив перед сменой питания: SAFE/PWM0/ARM0, DC45В (разряжается),
errors387. Отправленных команд0. Старые22 файла проверены по SHA, полный
SD и все AS first-fault/PE0 hex сохранены в отдельном новом каталоге.

`i2c_persistent_pe_r1/no_switch_workload_preparation_r1/plan.json` — план,
ограничения и SHA исходников, не отчёт аппаратного теста. Новый режим/образ
ещё не собран/не установлен. Обычный START при пустой шине штатно блокируется
UV и softstart. Исторический prepare_mcsdk_logic_bench.py маскирует
MC_UNDER_VOLT и поэтому для этого запроса не подходит. Для сравнимой
вычислительной нагрузки нужен отдельный диагностический расчёт/ADC schedule
при принудительно запрещённых выходах, с реальными защитами и телеметрией.
Не выдавать простой idle при MOE0 за эквивалент активного PWM/ADC: текущий
TSK_HighFrequencyTask при MOE0 возвращается до расчёта V/f.

## 2026-10-27: сверка BUSY при ШИМ с документацией и первичными сообщениями

`i2c_persistent_pe_r1/pwm_busy_documentation_review_r1/research.json`:
новых Пусков/CLEAR/RESET/прошивок0. Проверены AS5600 datasheet, ST ES0431,
исходники SimpleFOC и сообщения авторов на форуме. Инициализация TIM1
использует PA7/PB0/PB1/PA8/PA9/PA10, I2C1 — PB8/PB9; прямого конфликта
этих выводов не найдено. I2C kernelHSI16, ANF/DNF2, фоновой неблокирующий
опрос. Первый BUSY: gap31,5мкс, максимальная записанная пауза693,6мкс при
бюджете3000мкс. Полного голодания foreground на3мс в этом захвате нет;
ошибки последовательности/обслуживания событий этим не исключаются.
AS5600 не поддерживает clock stretching, SCL у него вход. Ложный BERR по
ES0431 уже обрабатывается clear/continue; известный first-byte-stall требует
APB/I2C1,5..3, у нас10,625. F1/F4 BUSY workaround не считается erratumG431.
Форум G431 содержит измеренные плохие уровни/звон и отдельный AS5600 случай
даже с15см проводом; это другая плата. Автор исправил470R на47R — номиналы
чужой платы не переносить автоматически. Причина нашего BUSY пока не доказана.
Для разделения CPU/состояний и силовых помех нужен одинаковый TIM1/ADC
сценарий при исключённых силовых переключениях и затем сравнение с ними.

## 2026-10-27: пассивная проверка AS5600 в покое после двух пусков

На вопрос пользователя об ошибках статично выполнено только чтение Wi-Fi,
без START/CLEAR/RESET/перепрошивок.11 свежих ответов, между первым и последним
19,328 с: успешные чтения439205→443076 (+3871), ошибки387→387 (+0).
Дельты NACK/BUSY/deadline/ARLO/BERR/controller resets/UART/CRC/RPC также0.
ШИМ0/SAFE/ARM0, силовая шина325В, enc_bus_ok/enc_ok/enc_speed_ok1, rpm0.
В этом интервале в покое новых ошибок не наблюдалось; это не доказывает
отсутствие редких сбоев или конкретную причину ошибок при ШИМ.
Полная запись: `i2c_persistent_pe_r1/idle_after_pwm_repeat_r1/report.json`.

## 2026-10-27: разрешённый пользователем повтор 5 Гц завершён автостопом5001 мс

На просьбу «повтори ещё раз» выполнен ровно один дополнительный скалярный
пуск без CLEAR/RESET/прошивок и без изменения защит. Свежий Wi-Fi preflight:
SAFE/PWM0/ARM0/DC325В, SD HIGH/BIE1, автоноль и все исходные motor/transport
проверки готовности пройдены. Старый первый I2C-захват уже заполнен: повтор
снимал телеметрию существующим bounded runner без запроса нового first-event
capture; неизменяемые слоты не очищались. Энкодер только для наблюдения.

`i2c_persistent_pe_r1/powered_as5600_5hz_repeat_r1/report.json`:
один START, run_id2, elapsed5001 мс/reason1, нормальный MCU автостоп;
OFF подтверждён, затем SAFE/PWM0/ARM0, motor active/occurred0, шина325В.
Общий passed=false сохранён: за пять секунд получено только одно различное
допустимое окно токов на5Гц вместо требуемых двух. Это не моторная авария;
таймер завершился штатно, повтор ради числа окон не выполнялся.

I2C снова +195 ошибок: BUSY155/NACK20/deadline13/ARLO7, отдельно BERR17,
controller forced resets172. Итоговый счётчик387. В одном свежем ответе
после STOP enc_ok/enc_speed_ok1, но работа AS5600 при ШИМ остаётся
не квалифицированной. Пользователь подтвердил после повторного прогона:
«вращался ровно». Подтверждение сохранено отдельно в repeat_assessment.json;
исходный машинный report.json и все захваты оставлены без изменений.
Все пять raw-записей first-fault/PE0/SD совпали с preflight побайтно,
22 прежних архивных файла снова проверены по SHA-256. Доказательства и
дельты сохранены в `repeat_assessment.json`; исходные отчёты не подменялись.

## 2026-10-27: один скалярный пуск 5 Гц/5000 мс завершён; AS5600 при ШИМ не прошёл

Пользователь подтвердил: J1 включён через soft-start, 15 В включены,
обе платы на повербанках, USB ПК и Saleae отключены, Пуск/RESET не нажимал.
Разрешён один пуск с записью AS5600 и автостопом; старые захваты сохранить.
Использован только Wi-Fi, установленная пара Uno2709/Nucleo2710; без прошивок,
сбросов MCU, перезапусков служб или изменения защит.

До Пуска сохранён полный SD LOW 61,6 мкс на обоих входах TP23/PA4 и PA6,
без расхождения отсчётов. Событие при MOE=0, задании0 и motor_state0;
активная маска0, occurred1024, текущее SD HIGH. Полные снимки сохранены в
`i2c_persistent_pe_r1/powered_as5600_5hz_r1_preflight/`. Выполнен ровно один
штатный CLEAR как подготовка согласованного пуска, без стирания снимка.
После CLEAR три свежих ответа подтвердили все исходные проверки готовности,
SD HIGH/BIE1, автоноль3/3, маски/аварии/transport0. Повторного CLEAR не было.

`i2c_persistent_pe_r1/powered_as5600_5hz_r1/report.json`: скалярный тест PASS,
ровно один START, MCU run_id1, run_start597048/run_stop602048, elapsed5000 мс,
reason1 (лимит времени). Два различных допустимых окна токов на5 Гц,
абсолютный масштаб ампер по-прежнему не квалифицирован. После STOP свежие
ответы SAFE/PWM0/ARM0, SD HIGH/BIE1, active/occurred0, DC326–327 В.
Новых SD/защит двигателя, ошибок UART/CRC или RPC не зафиксировано.
Физическое вращение ожидает отдельного ответа пользователя; показания
AS5600 его пока не подтверждают. Повторного пуска не выполнялось.

Результат AS5600: +192 ошибки I2C, из них BUSY156, NACK20, deadline11,
ARLO5; отдельно BERR clears46, controller resets170, normal success PE parks0.
Устранение отключений PE после успешного чтения проблему при ШИМ не решило.
Первый сбой теперь BUSY, driver_state0/stage4, CR2=0, ISR0x8001,
SCL/SDA HIGH, возраст попытки3001,4 мкс. Это иной первый сценарий, чем прежний
NACK с незавершённым STOP; новый захват не позволяет называть его причиной.
После PE=0 ISR=1, SCL/SDA HIGH во всех трёх отсчётах примерно0,09/7,24/31,92 мкс.
Первичный и PE0 захваты полные, связаны CRC и декодированы; по одной
отклонённой диагностической странице сохранено в счётчиках, а не скрыто.
Эти цифровые отсчёты не устанавливают электрический источник сбоя.

После STOP ошибки остались192, успешные чтения продолжились, однако
enc_ok/enc_speed_ok остались0: угол и скорость для обратной связи не допущены.
AS5600 используется только для наблюдения, режим управления остаётся VF.
Все22 прежних архивных файла повторно проверены SHA-256; исходный SD захват
сохранился неизменным. Полный вывод и SHA новых файлов: `assessment.json`.
Новых пусков, изменений проводки или перепрошивок этот результат не разрешает.

## 2026-10-27: автономная2709/2710 перед5Гц PASS, J1 ещё выключен

Подтверждение пользователя: обе платы на повербанках, USBПК/SaleaeOFF,
15ВON,J1OFF,Пуск/RESET не нажимал. Проверка толькоGET поWiFi192.168.1.138:8080,
безUSB/ADB/SWD, командRESET/CLEAR/START, перепрошивок или перезапусков служб.

`i2c_persistent_pe_r1/autonomous_before_pwm5hz_r1/report.json` PASS:
20.078с/17 свежих ответов, +3744 успешных чтения AS5600, ошибокI2C0,
controller_resets0/normalparks0, bus/angle/config valid. Дельты NACK/BUSY/ARLO/
BERR/порчиI2C-страниц/UART/RPC=0. SAFE/PWM0/ARM0, DC10В, свежесть peer<300мс.
Всеmc/bp fault/active/occurred/ESTOP/transport=0 — в новой автономной загрузке
прежнего latch7 нет; CLEAR не выполнялся. Старые UART/AS захваты сохранены
в прежних архивах,22 исторические копии вновь проверены по SHA.

Первый HTTP ответ содержал ещё только1 страницу истории автонуля (valid0,
Waiting) при уже готовых3 стабильных блоках. Во время пассивного наблюдения
штатно пришли все3 страницы: historyvalid1, stable1/2/3, reject0,
means[2067,2067,2066,2069], оценка3sigma среднего1.546count. Точный
current_zero_quality для2710 прошёл; rawspans43/29/45/25 не подменялись.
Ни калибровка, ни лимиты, ни прошивка ради ожидания страниц не менялись.

SD HIGH/configOK/BIE1, DMA capture running, first_record_ready=false;
первыйPWM I2C слот пуст, capture_ready=true. Захваты не стирались.
Полные initial/monitor статусы и SHA сохранены; run_request/START=0.

Следующий единственный физический шаг: включить J1 через штатныйsoft-start
при закрытом стенде, оставив повербанки/15В и отключённыеПК/Saleae как есть.
Не нажимать Пуск/RESET. После явного подтверждения проверить свежую HV-шину,
устойчивое питание/SD/аварии, затем выполнять уже согласованный один
scalar5Гц/5000мс тест с записью; пока HV не подтверждено, START не отправлять.

## 2026-10-27: подготовлен AS5600 PWM5Гц/5с, пуск НЕ отправлен

Пользователь запросил один5Гц тест с записью/автостопом5с и инструкции по
переключениям; защиты не ослаблять, старые захваты сохранить. Платы ещё USBПК,
15В ON/J1OFF по последнему подтверждению. Пассивный GET:2709/2710,
SAFE/PWM0/ARM0/DC10В, enc_ok1,417782 reads/errors0/resets0/normalparks0,
SD HIGH/configOK/BIE1, маскиMC0, RPCtimeouts0. UART watchdog latch7/reason13
сохраняется после программирования; CLEAR/RESET/START в этом этапе0.

`i2c_persistent_pe_r1/pwm5hz_preparation_r1/`: исходный свежий полный статус,
plan.json, runner_selftest.json. Хеши22 старых копий и всей установленной
source/build/verification таблицы повторно проверены; архивы не изменены.

`tools/run_persistent_pe_as5600_5hz.py`: версия-обёртка существующего
run_as5600_bounded_5hz.py. Добавляет только точную пару2709/2710 в pair/owner/
capture и current_zero_quality whitelist, не меняя пороги/проверки/таймеры.
Режим scalar VF,5Гц, явно MCU RUNLIMIT5000мс; AS5600 только наблюдение.
Штатные SD/BKIN/BIE, ток/автоноль/температура/UART/current windows/heartbeat
и STOP при ошибке сохранены; только один START и никаких автоматических
CLEAR/повторных START/режимов энкодера/прошивок/сбросов. После подтверждённого
OFF дополнительно собирает PE0 extension, не стирая исходный отчёт PASS/FAIL.

Selftest PASS:15 проверок, реальный orchestration код со ВСЕМИ HTTP/heartbeat
объектами заменёнными на fake, аппаратных вызовов0. Задержанный HTTP ACK6.2с
не продлевает MCUrun5000мс; один START,0CLEAR, OFF подтверждён, без резервного
hostSTOP. Проверены отказ приSDLOW/BIEOFF/плохомавтонуле/UART/lostpeer/ARM/
PWM/высокойшине/stale/температуре и полнота дополнения PE0.

СЛЕДУЮЩИЙ шаг только физическое переключение: обе платы на повербанки,
USBПК и все Saleae соединения включаяGND отключены,15В оставитьON,J1OFF,
Пуск/RESET не нажимать. Сначала проверить автономную загрузку/связь/AS5600
поWiFi при J1OFF; только затем давать включение J1 для согласованного теста.
Не включать HV до проверки автономной связи, чтобы не создавать лишний
цикл заряда/разряда при возможной проблеме загрузки. Запуск ещё не разрешён
физическим состоянием: текущие250–350В/start-clean guards не пройдены,
сохранённыйUART7 сначала потребует штатного отдельного разрешённого этапа.

## 2026-10-27: 2709/2710 установлены, оба readback и AS5600 в покое PASS

Явное разрешение пользователя: прошить2709/2710, проверить чтением обратно,
затем связь/AS5600 в покое. J1OFF, независимый мультиметр<20В, обе платы USBПК,
15В оставлены. Двигатель, AS5600, TP23→1кОм→PA4 и остальную проводку не меняли.
COM10/COM13 и точные serial IDs подтверждены, Uno ADB device. Пусков/CLEAR=0.

Пакет `artifacts/live_bench_20261027/i2c_persistent_pe_r1/` теперь installed=true.
`install_usb_r1/report.json` PASS: по1 записи Uno/Nucleo, оба образа проверены
чтением обратно. Nucleo programmer: Download verified successfully; Uno:
UNO Q verification PASSED; restarting unchanged images. Обновлены HMI server/
app.js для новой пары с сохранением прежних ABI/калибровки. Исторический
router serial close/open fallback НЕ применялся. RPC восстановилась сама;
дополнительных перезапусков MCU/служб или переподключений пользователя не было.

Uno2026102709 SHA256
5b638581b965e72738963a6da176fc20f4252e0a6b07fe1906ce4d2e784c439e;
Nucleo2026102710 HEX SHA256
dd2bd577036bd4f1e374ae0c5852a5fc2cf0a7e2278af010dd553482fe974430.
Калибровка DC-шины до/после прежняя SHA256
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

До ЛЮБОЙ записи полный текущий first-fault/PE0/bus-clear/SD/UART статус
сохранён в `install_usb_r1_preserved_live/`, три полных свежих OFF-ответа,
исходные hex/счётчики стабильны. Старые19 BUSY, first record/PE0/bus-clear
и сохранённая UART/FE2/transport4 присутствуют в архиве, а не обнулены командами.
22 исторические копии ещё раз проверены по SHA-256; исходные файлы не менялись.
MCU RAM естественно создаёт новую историю при программировании; прежняя
история остаётся в файлах. Установщик не отправляет стирание захватов/CLEAR.

Особенность допуска записи: `tools/install_i2c_persistent_pe.py` распознаёт
строго текущий сохранённый FE-снимок (оба peer fault5/transport4, reason12,
flags2, badcnt1, маскиMC0, локальныхRXошибок0) при свежих SAFE/OFF/низковольтных
ответах. Исходные поля статуса не подменяются. Это только программирование
при явно подтверждённом J1OFF/мультиметр<20В, а НЕ разрешение пуска/очистка
аварии или изменение защиты. Отдельные24 negative/positive проверки PASS:
RUN/ARM/PWM/высокая шина/stale/invalid/иные UART события блокируют запись.
Стабильность диагностик/замороженных записей проверена до flash.

`runtime_idle_r1/report.json` PASS: 20с (фактически20.312),16 свежих ответов,
3713 новых успешных чтений AS5600. Суммарные ошибкиI2C0, controller_resets0,
normal_parks0, cfg_match1, bus/angle valid, все проверяемые дельты NACK/BUSY/
ARLO/BERR/доставки/RPC/UART-reject=0. Это подтверждает работу нового жизненного
цикла в покое; прямой аналоговый захват PE/SCL здесь не снимался. Первые слоты
новой загрузки пусты и неизменны, потому что ошибок датчика в ней не было.
SD HIGH, BIE включён, конфигурацияBKIN корректна; active/occurred MCmasks0.
SAFE/PWM0/ARM0, DC10В. Штатный UART watchdog latch7 после программного
перезапуска Uno остаётся сохранённым; CLEAR не отправлялся. Свежая связь
работает, mc_uart_error_flags0 и RPCtime-outs0; это не команда разрешения пуска.

Итог/хеши новых записей: `installation_evidence.json`, `final_idle_status.json`.
Motor_start_ready=false до отдельного дальнейшего штатного этапа; реальный
пуск/помехоустойчивость AS5600 при ШИМ в этом запросе НЕ проверялись.
Пороги/ШИМ/АЦП/Break/watchdog/автостоп не изменены относительно готового пакета.

## 2026-10-27: 2709/2710 собраны и проверены на ПК, НЕ записаны

Явный запрос: собрать прошивки без лишних сбросов I2C после успешного чтения,
проверить на ПК; без новых пусков, ослабления защит или стирания записей.
За этот этап аппаратных действий НОЛЬ: ни GET стенда, ни ADB/SWD/serial,
ни START/CLEAR/RESET/service/flash. Установленная пара остаётся2707/2708.
Новых физических подтверждений/переключений/фото у пользователя не просили.

Готовый пакет `artifacts/live_bench_20261027/i2c_persistent_pe_r1/`:
Uno2026102709 / Nucleo2026102710, manifest built/selftest_pass=true,
installed=false. Это целевые ARM-образы, а не только предыдущий native-патч.

Изменение: нормальный STOP/успешное чтение очищает флаги/CR2 через отдельный
completed callback, но не выключает PE. Программное pe_on учитывается при
проверке конфигурации и следующем preflight. Для первого чтения остаётся
предварительное наблюдение обеих линий до и после включения. При последующих
здоровых чтениях PE не переключается. При ошибке сохранены ограниченное
ожидание STOP, однократный запрос STOP, обработка ARLO и прежний forced PE0
после500мкс; pe_on сбрасывается синхронно с этой веткой. NACK не выдаётся за
угол. Тайминг0x30521317, ANF/DNF2, бюджеты3мс/500мкс/backoff20мс прежние.
Автоматическое освобождение SDA остаётся однократным, OFF/DC<20В, после
заморозки первоначального снимка; его допуски не расширены.

Uno-код, весь Nucleo main/PWM/ADC/Break/watchdog/автостоп/UART-команды и
библиотеки RPC сверены с установленной парой: только FW/peer идентификаторы.
HMI расширяет все парные и отдельные whitelist для2710 (включая SD/Break),
сохраняя старые версии; калибровочная совместимость проверена. UI без изменений.
Форматы исходного160Б, дополнения100Б и bus-clear кадра43Б сохранены.

`verification/report.json` PASS:
- Настоящий production driver с моделью MMIO:200 успешных чтений, одно
  включение PE и0 выключений после успеха. Config/пакет энкодера валидны
  также в здоровом idle приPE1. Порча каждого байта пакета отбрасывается.
- NACK после здоровых чтений, чистый STOP и forced cleanup при пропавшем
  STOP проверены. Первые записи/PE0 probe не изменяются поздними ошибками.
- Неожиданное аппаратное отключение PE и отсутствие completed hook
  дают SETUP/невалидное измерение, а не молчаливое продолжение.
- Прежние400 сценариев восстановления /32767 assertions,92 bus-clear случая,
  replay настоящего startup SDA LOW через production driver и450 HMI/
  совместимости/CRC-проверок PASS. Старые сохранённые записи тоже декодируются.
- Обе целевые сборки PASS, Nucleo0errors/0warnings; RAM прирост0, остаток3320Б
  сверх reserved heap/stack. Stack: poll56Б/terminal40Б/release144Б; ADC IRQ376Б
  без изменений. Loader relocation и реальные зависимости локального RPC
  override для sketch/Bridge singleton проверены.
- 22 исторических файла скопированы и проверены SHA-256. Исходные установленные
  source/build/verification таблицы SHA повторно проверены, оригиналы не менялись.

`tools/verify_i2c_persistent_pe_package.py` PASS, только локальные файлы:
Uno `build/uno/UNOQ_MOTOR.ino.elf-zsk.bin`, SHA256
5b638581b965e72738963a6da176fc20f4252e0a6b07fe1906ce4d2e784c439e;
Nucleo `build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex`, SHA256
dd2bd577036bd4f1e374ae0c5852a5fc2cf0a7e2278af010dd553482fe974430.

Это готовый проверенный на ПК пакет, НЕ разрешение/отчёт о новом пуске.
Работа при реальном ШИМ и устранение происхождения первого NACK пока не
квалифицированы. Старый installer runtime FAIL/FE latch не переписаны в PASS
и не сбрасывались. Для последующей записи потребуется отдельный запрос;
в текущем запросе платы не прошивали и никаких переключений не требуется.

## 2026-10-27: повторный поиск причины ошибок при ШИМ, без пусков и записи образов

Запрос пользователя: искать по интернету/кодам причину первичного NACK/ARLO
при ШИМ и исправлять, а не выдавать исправление вторичного зависания SDA за
решение всей проблемы. Подтверждено: четыре внешних провода VCC/GND/SCL/SDA
только между Nucleo и AS5600; отдельного внешнего провода DIR нет. Это НЕ
доказывает, что DIR плавает: на неизвестном модуле может быть своя подтяжка.
Внутренняя схема питания/подтяжек и фото обеих сторон модуля пока неизвестны.

Новых стендовых команд не было: START/CLEAR/RESET/flash/router/service=0.
Один пассивный GET: 2707/2708 SAFE/PWM0/ARM0, 10 В, enc_ok1,
258156 успешных чтений, enc_errors19 без роста, NACK0/ARLO0 в этой загрузке.
Ранее сохранённая transport4/FE2 остаётся защёлкнутой. Установленные исходники,
образы и архивы проверены по SHA, ничего в них не изменено.

Новые артефакты: `artifacts/live_bench_20261027/pwm_i2c_lifecycle_audit_r1/`.
`research.json` содержит ссылки/границы применимости, `current_status.json` —
свежий ответ, `persistent_pe.patch` — НЕ УСТАНОВЛЕННЫЙ исходный патч,
`report.json` — результаты native A/B и регрессии, `sha256.json` — хеши.
ARM-образы для этого патча НЕ собирались и новых номеров прошивки НЕ назначено.

Выявлены лишние программные PE-reset после каждого здорового STOP/read:
при 200 чтениях/с это 200 выключений/включений периферии в секунду. В ST HAL
нормальный конец обмена очищает STOPF/CR2 без постоянного выключения PE.
Подготовлен патч: здоровое завершение сохраняет PE, отдельный completed hook
очищает CR2, программное состояние PE учитывается в config/preflight; ошибки
сохраняют прежнее ограниченное восстановление/PE0/захват. В OFF bus clear
условия не ослаблены. Регрессия400 случаев /32767 assertions PASS.
В A/B модели200 чтений: установленный код200 enable/200 disable; патч1 enable/
0 disable. При специально смоделированном ложном BUSY на новом enable старый
код1 BUSY, патч0. Это модель конкретной точки воздействия, НЕ доказательство
происхождения аппаратного сбоя. Один и тот же NACK остаётся ошибкой в обоих
вариантах — этот факт сохранён, а не объявлен устранением первого NACK.

Повторно сверены первичные источники:
- ES0431 Rev9 2.11.1–2.11.6: стандартный tSU;DAT250нс при HSI16=62.5нс
  удовлетворяет нормальным условиям; BERR workaround уже есть; условие
  first-byte stall APB/I2C1.5–3 не выполнено (170/16=10.625); slave/SMBus
  errata не являются объяснением данного controller-обмена.
- Локальный LL_I2C_HandleTransfer уже содержит tmp-fix volatile UB; переносить
  найденный старый fix из release notes повторно бессмысленно.
- AS5600: адрес0x36, pointer0x0B и3байта STATUS/RAW корректны; первый NACK
  появляется на stage5 до RX и до3мс deadline. Номер отклонённого на проводе
  бита/точный ACK slot снимок не доказывает. Длинный poll-gap не объясняет
  NACK как простой тайм-аут программы. BERR сам по себе может быть errata;
  ARLO означает несоответствие переданного HIGH прочитанному LOW на SDA.

Найдены первичные сообщения авторов на SimpleFOC:
https://community.simplefoc.com/t/as5600-jamming/727 — Nucleo+AS5600 зависал
при моторе, автор устранил заменой кабеля.
https://community.simplefoc.com/t/bldcmotor-loopfoc-does-not-return-when-i2c-bus-locks-on-b-g431b-esc1/3577
— на B-G431B-ESC1 (ДРУГАЯ плата) измерены плохие уровни/звон I2C, помогла
аппаратная коррекция pullups/series resistors. Эти номиналы/позиции R75/R77
НЕ переносятся на нашу Nucleo64 без измерений. Это поддерживает необходимость
проверки реальных фронтов/модуля, но не доказывает конкретную нашу неисправность.

Следующее недостающее наблюдение: схема реального модуля AS5600 — нужны
различимые фото обеих сторон для DIR, pullups и схемы3.3В. Нельзя на основании
четырёх проводов объявить DIR плавающим или замкнуть его на GND, не исключив
его прямое соединение с питанием на самой платке. Нельзя приписывать NACK
магниту только по магнитным флагам. Пороги защит/фильтры наугад не менялись.

## 2026-10-27: 2707/2708 — SDA освобождена без ШИМ, чтение AS5600 в покое восстановлено

Пользователь попросил разобрать/исправить SDA LOW после PE0 без новых пусков,
случайных перепрошивок и удаления записей, состояние стенда не менял.
J1 OFF по прежнему подтверждению, обе платы на USB ПК, 15 В оставлены,
шина по свежему ответу 10 В. AS5600 на PB8/PB9, остальные подключения прежние.

Подтверждён программный пробел: при SDA LOW до первого START прежний драйвер
исчерпывал 3 мс preflight, оставался PE0, ждал ещё 20 мс и повторял ожидание.
Ни одного SCL такта/STOP в этой ветке не было, поэтому незавершённая передача
отдельно питаемого target не могла завершиться. В новом первом захвате PE уже
0, ISR=1 без аппаратного BUSY, SCL HIGH/SDA LOW. До предыдущего программирования
датчик читался. Сброс MCU посреди чтения — правдоподобный исходный триггер,
но не снятая осциллограмма и не доказательство отсутствия помех/проблем питания.

`artifacts/live_bench_20261027/sda_idle_recovery_r1/analysis.json` содержит
ссылки на первичные источники: NXP UM10204 3.1.16 (bus clear), ST RM0440/LL.
Исправление: один неблокирующий bus clear за загрузку, только при выключенном
ШИМ, отсутствии команды START и DC<20 В; исходные fault/PE0 записи сначала
замораживаются. PB8/PB9 переключаются в OD GPIO с заранее отпущенными уровнями,
SDA остаётся отпущенной во время всех 9 тактов (ранний HIGH мог быть битом данных),
затем NACK/STOP, проверка обеих HIGH, возврат AF и прежнего ODR. Каждый poll
ограничен одним шагом; нет delay-loop, IRQ mask, активного HIGH или записи
регистров датчика. При SCL LOW / 9 тактах без освобождения / timeout / потере
допуска попытка заканчивается видимой ошибкой, без вечного перезапуска.
Доставка результата — отдельный CRC32C кадр 0xDE в OFF, привязанный к CRC
замороженного исходного снимка. Код защит/PWM/ADC/автостопа/команд не менялся.

Проверки: 92 случая core (включая обрыв каждого шага, полный LOW, запаздывания,
переполнение DWT), настоящий production driver с моделью MMIO и возвратом к
чтению 0x0B, 608 проверок HMI/совместимости SD/порчи кадров, прежние 400 случаев
core / 32761 assertions. Обе целевые сборки PASS, Nucleo 0 ошибок/предупреждений,
RAM +48 Б, остаток 3320 Б сверх heap/stack; ADC IRQ stack 376 Б без изменений.
Точные защищённые исходники сверены обратно после удаления диагностических
добавлений. Проверки и хеши: `verification/report.json`, `manifest.json`.

Установлены Uno 2026102707 / Nucleo 2026102708, по одной записи каждой;
обе проверены чтением обратно. Uno SHA256
3c2042690545a5eecd9e1b7e7773b30832867e430f01acdc598a68bbc170b5c5,
Nucleo HEX SHA256
500914301c4304f1bee846765bd98f3b3825f9d646a56a3559df3e67444ac847.
Калибровка до/после прежняя SHA256
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
Старые файлы не изменены, копии проверены SHA. Текущие записи архивированы
перед записью в `install_usb_r2_preserved_live/`, исходные ответы также отдельно.

ПРОВЕРКА НА ЖЕЛЕЗЕ В ПОКОЕ PASS: до GPIO release линии 1 (SCL HIGH/SDA LOW),
после самого переключения GPIO всё ещё 1; после 9 тактов/STOP стали 3 (обе HIGH).
Длительность 293 мкс. Датчик начал читаться. В `runtime_idle_r2/report.json`:
20 с, 3731 новое успешное чтение, 0 новых ошибок I2C, все проверяемые счётчики
порчи/тайм-аутов без роста, исходные записи неизменны. Всего 19 BUSY до
восстановления сохранены, а не обнулены. Пуски/CLEAR=0. Это квалификация
конкретного восстановления SDA в покое; исходные ошибки при PWM НЕ решены
этим доказательством, датчик для FOC при вращении НЕ квалифицирован.

Проблемы установщика сохранены честно:
1. Первая попытка `install_usb_r1_preserved_live` остановилась ДО записи:
   HMI 2705 не включала2706 в отдельные SD/Break whitelist, хотя ABI прежний.
   Исправлена совместимость для2706/2708; до замены HMI старые сырые флаги
   локально декодированы проверенным декодером, исходные ответы сохранены.
   Ни архивный барьер, ни условия защит не ослаблялись.
2. `install_usb_r2/report.json` остаётся passed=false: mc_uart_error_flags=2
   представляет сохранённый first UART/FE снимок, transport latch4/причина12,
   а не квалификацию текущего регистра USART.ISR. Автоматика сочла его текущей
   аппаратной ошибкой и ненужно вызвала serial close/open. После close router
   стал отвечать "method get not available". Исходный отчёт НЕ переписан в PASS.
3. Для восстановления регистрации выполнена одна verify/restart операция
   неизменного MCU образа Uno (в cfg нет erase/write), Nucleo после установки
   НЕ сбрасывалась и её записи сохранились. RPC снова работает, тайм-ауты0.
   Ненужное автоматическое serial reopen в новом установщике отключено.

Итог в `installation_evidence.json`: оба readback/калибровка и I2C idle PASS,
но motor_start_ready=false, сохранённая UART/FE авария НЕ сброшена, защиты
действуют. SD HIGH, BIE/config OK, активная маска MC0, SAFE/PWM0/ARM0.
Для дальнейшего пуска потребуется отдельный штатный этап, в этом запросе
он не выполнялся. Питание/подключения пользователю менять не предлагались.

## 2026-10-27: 2705/2706 установлены и проверены; AS5600 сейчас не отвечает в покое

Пользователь ответил «готово» на подготовку к записи: J1 выключен, независимый
мультиметр ниже 20 В, обе платы уже на USB ПК. COM10/COM13 и ADB Uno проверены.
15 В и проводку оставили как есть. Пусков, CLEAR, ARM и изменения защит не было.

`artifacts/live_bench_20261027/pe_release_capture_r1/install_20261027_r1/report.json`:
PASS, Uno 2026102705 и Nucleo 2026102706 записаны по одному разу, оба образа
проверены чтением обратно. Обновлены HMI server/app.js. Калибровка до/после
SHA-256 a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
RPC восстановилась автоматически; serial reopen, перезапуск службы для
восстановления или холодное переподключение USB после записи не потребовались.

До записи текущие статусы/записи сохранены в
`install_20261027_r1_preserved_live/`. Все десять исторических копий проверены
по прежним SHA-256. Установщик/прошивка не посылали команд стирания захватов;
перезапуск при программировании естественно создал новые RAM-слоты.

Пассивная проверка после записи: 12 статусов, SAFE/PWM0/ARM0, 10 В,
активная маска MC=0, свежая телеметрия, UART hardware flags=0,
RPC timeouts=0. Остался транспортный watchdog latch 7 после перезапуска Uno;
он не сбрасывался ради проверки. Диагностика после PE0 доставлена и
декодирована корректно: за интервал 97 принятых страниц, 0 новых bad.

ВАЖНО: работоспособность AS5600 сейчас НЕ подтверждена даже без ШИМ.
До записи enc_ok=1/errors=0/raw=1891. После записи enc_ok=0, +722 ошибки за
пассивный интервал (3944 в последнем статусе). Новый first_since_boot:
tick 8 мс, причина BUSY/stage4/state0, PE уже был 0, ISR=1 (BUSY бит=0),
SCL HIGH/SDA LOW в начале/конце, истёк 3 мс preflight, cleanup_no_transfer.
Новый захват после park: SCL HIGH/SDA LOW при фактических 0.088, 7.194,
24.641 мкс после PE0; PE остаётся 0, ISR=1, CR2=0. Это НЕ тот же доказанный
случай SCL LOW/STOP pending при PWM в прежней записи. Источник SDA LOW
по цифровым отсчётам не определён; физическая причина не установлена.
Сырые/декодированные данные сохранены в `install_20261027_r1/idle_first_capture.json`
и `idle_samples.json`; итог `idle_summary.json`, SHA — `installation_evidence.json`.
Поле record_crc32c расширения в текущем декодере имеет значение residue 48674bc7;
для идентичности/ссылки использовать parent_crc32c и SHA сырого файла,
а не считать это residue уникальным CRC конкретного дополнения.

Установка/чтение обратно и доставка observer в покое PASS; исправление
физического сбоя/работа датчика при PWM НЕ заявляются. Новые моторные пуски
в этом запросе не разрешены и не выполнялись. Текущее физическое состояние:
J1 OFF по подтверждению пользователя, обе платы USB ПК, 15 В как были.

## 2026-10-27:2705/2706 подготовлены — SCL послеPE0 интегрирован, НЕ записаны

Запрос:встроить postPE0 захват,проверить наПК,подготовитьобразы,сказать
подготовкукзаписи;безновыхпусков,ослаблениязащитилиудалениязаписей.
Пользователь уточнил,что USB-доступность плат означает,что он их подключил;
повторно спрашивать факт подключения не надо. COM10/COM13 реально обнаружены.
Только WiFiGET перед/после подготовки:свежая2703/2704SAFE/PWM0/ARM0,шина10В,
enc_errors0,transport0,current/occurredMCmasks0. Текущие I2Cслоты в ОЗУ пусты
после выполненного пользователем подключения/перезапуска. Прежние210ошибок
и CRC338c2b55 сохранены в исходных артефактах и новой архивной копии.
Последнее явное физическоеJ1подтверждение былоON; USB и ADC10В не являются
независимым подтверждением размыкания J1/мультиметра. В этой работе
START/CLEAR/ARM/RESET/flash/service/serialreopen/SWD/ADB=0.

Кандидат artifacts/live_bench_20261027/pe_release_capture_r1:
Uno2026102705/Nucleo2026102706,manifestbuilt/selftest_pass=true,
installed/hardware_validated=false. На платах по свежему ответу ещё2703/2704.
Образы запечатаны и install_pe_release_capture.py --verify-package-only PASS:
Uno49d7037182138f8f8ad8b0a6db9b3a34b4c50b7791e4cd34d18e8f1f0c033711;
NucleoHEX7a2c42a8d55c17b8a666c55b52d7600ef0c2d61731946069092c2337a4811329.

В productionNucleo добавлен независимый observer:
- capture_terminal сохраняет исходные160Б как прежде и armдвухfirstprobeслотов;
- существующийpark после PE0/readback/DSB снимает ISR/CR1/CR2/GPIOB_IDR/DWT;
  сохраняется также фактический DWTмомент сразу после отключенияPE;
- главнаяпетля получает следующие реальные наблюдения≥5/≥20мкс;
  latepoll538мкс явноlate,невыдаётсяза5мкс. Если PEвключили/наблюдение
  неполное/просрочено,результатUNKNOWN. Никаких дополнительных GPIOwrites,
  импульсов,delay,IRQmask,переповторовSTART или изменениятаймаутов.
- старый encoder_core.h и восстановлениеI2C byte-identical; защиты/PWM/ADC/
  Break/автостоп/UART-команды и RPCбиблиотеки сохранены кроме FWidentity.

Старыйcaptureformat2/160Б не переопределялся. Новое дополнение0xDD/format1:
100Б,5CRC32Cстраниц,CRCpayload96Бвнутри,ссылка на CRCисходного160Бснимка,
егоtick/terminalcycle/GPIO/SYSCLK. Доставка толькоприOFF,exactpeer2706,
отдельные staging/published буферы и проверка parentlink. НаUno/HMI
enc_release_first_hex/pwm_hex/good/bad/records/status. В строке энкодера
появляется наблюдённый HIGH/LOW/mixed/UNKNOWN послеPE0; виновник автоматически
не объявляется. При сменеparentCRC старыйchild не приклеивается к новому.

verification/native_report.json:полныйproductionCdriver с W1CMMIO,сценарии
HIGH/LOW/late/timeout/cancel,защитаfrozenзаписей,битовые повреждения всех
страниц,переупорядочивание,плохаявнутренняяCRCприправильнойвнешней,
520HMI corruption/link checks и регрессия400coreсобытий(32761assertions)PASS.
verification/report.json:обецелевыесборкиPASS,Nucleo0errors/0warnings,
RAMрост160Б/остаток3368Бсверхreservedheap/stack,ADCIRQstack376Б безизменений,
encoderpoll56Б,terminalcapture40Б,extensionproducer144БstackOFFonly.
Проверены loaderrelocations, реальное подключение пакетных RPCheaders для
sketch И bridge singleton, калибровочнаясовместимость и current/zero/UI.
Worst-case аппаратный stackwatermark и PWM-помехоустойчивость не измерялись.

preserved_records:10исторических файлов копированыbyte-for-byte,SHAпроверены.
Установщик tools/install_pe_release_capture.py перед ЛЮБОЙ прошивкой пассивно
архивирует полные текущие RAMзаписи в sibling *_preserved_live и откажется
писать,если онинеполные/программноенизковольтноесостояниенеподтверждено.
Архивация не посылаетCLEAR/START/RESET. Это сохраняет историю в файлах;
перезапускMCU при будущей записи естественно создаст новые RAMслоты.

Физическая причина исходногоLOW/NACK всёещёНЕдоказана. Это измерительный
пакет,а не заявленное устранение первопричины/квалификацияAS5600 дляFOC.

Для записи:обаUSBПК уже видны;J1OFF,независимыймультиметр<20В;15В можно
оставить,двигатель/AS5600/TP23→1кОм→PA4безизменений. Никаких новыхпусков
послезаписи в этом запросе не разрешено. Явный флаг установки используется
только после подтверждения физического состояния;USBдоступность сама его
не устанавливает. После записи обаreadback+калибровка+покой,безSTART/CLEAR.

## 2026-10-27: офлайн-аудит SCL/STOP — физическая причина пока не идентифицируется

Пользователь запросил разбор и исправление причины SCLLOW/STOPpending БЕЗ новых
пусков и перепрошивок наугад; питание/подключения не менял. За этот этап
СТЕНДОВЫХ КОМАНД0:ниSTART/CLEAR/ARM/RESET/flash/serial/service,ниUSB/SWD/ADB.
J1/15В по последнему подтверждению ON,повербанки,PC/SaleaeOFF; последний
подтверждённый SAFE/PWM0/ARM0. Установленные2703/2704 и исходники/образы
проверены по SHA и НЕ изменялись. Текущий датчик под PWM не квалифицирован.

artifacts/live_bench_20261027/scl_stop_audit_r1/analysis.json:
точный разбор first record, errata/clock audit, дедукция счётчиков,
границы наблюдаемости и результат тестов отдельного диагностического модуля.

Новые результаты:
1. AS5600datasheet p10:SCL вход, normalclockstretching не предусмотрен.
   Это исключает штатное ожидание датчика, но НЕ внешнюю нагрузку/питание/
   повреждение и НЕ доказывает виновникаLOW.
2. В первом и конечном ISR TXIS/RXNE/TC/TCR0. Обычное программное ожидание
   загрузки TXDR/чтенияRXDR/reload/restart по этим флагам не соответствует
   этому случаю. NOSTRETCH в controller mode должен оставаться0.
3. ES0431 Rev9 §2.11.5 stall workaround по частотному отношению неприменим:
   сохранённыеCCIPR/CFGR и source дают APB1=170МГц,I2CkernelHSI16МГц,
   ratio10.625 вне1.5..3. РевизияX подтверждена прежним programmerlog.
   Не объявлять найденную похожуюerrata доказанной причиной.
4. Ветка forcedPEreset=cleanup_expired+preflight(prepare2). SETUP0.
   Первый:88−47=41,повтор:72−30=42,ровно все BUSY41/42. Значит83из210
   ошибок получены ПОСЛЕ включения PE,но ДО START I2C;до enable код уже видел
   обе линииHIGH в двух наблюдениях. Это аргумент против объяснения только
   неправильным чтением регистра AS5600,но не доказательство физической
   причины/источника сигнала. Простой постоянныйLOW не согласуется с теми
   HIGH наблюдениями; переменная помеха/нагрузка остаются возможными.

Уточнение прежней формулировки «SCL оставалсяLOW505мкс»: запись содержит
два GPIO readback,а не непрерывную осциллограмму. LOW в начале/конце и
неподтверждённый STOPF известны; непрерывныйLOW все505мкс НЕ доказан.
Главное:последний снимок ДО PE0. Нет GPIO после отпускания мастером линий.
Две разные модели(controller output LOW либо external line LOW) дают
одинаковые сохранённые GPIO/ISR/CR1/CR2. Физическую причину и её устранение
по этой записи честно подтвердить невозможно. Root-cause fix НЕ объявлен.

Подготовлен отдельно tools/scl_stop_audit/pe_release_probe.h:
read-only наблюдения сразу после существующегоPE0 и далее с фактическими
DWTtimestamps ≥5/≥20мкс; late538мкс явно помечаетсяlate,не выдаётся за5мкс;
при PE1/неполном/просроченном наблюдении результатUNKNOWN. Никаких GPIO
импульсов/задержек/IRQmask/повторныхSTART. Два first-record слота144Б,
26native проверок PASS,wrap/frozen/late/cancelled/mixed levels покрыты.
Это ОТДЕЛЬНЫЙ ПРОВЕРЕННЫЙ МОДУЛЬ,не встроенный в production и не новая
готовая прошивка. Wire extension/exactpeer интеграция ещё не выполнена.
Следующее обоснованное измерение — дифференциальный SCL послеPE0;HIGHпосле
поддерживает версию контроллера,не даёт абсолютного доказательства,LOWпосле
при корректной AF/OD конфигурации фиксирует сохранение внешнего уровня.

Первоисточники:amsdatasheetv1.06(primary PDF наSparkfun,официальныйams URL
сейчас404);RM0440 I2Ccontroller sections;ES0431 Rev9 2.11.1–2.11.6.
Попытки локального скачивания полных STPDF дали timeout;прочтение всегоPDF
не заявляется. Релевантные разделы доступны через webиндекс/ES0431PDF.
Без новой явной команды пользователя дополнительных пусков/записи не делать.

## 2026-10-27:2703/2704 — два разрешённых5Гц/5с пуска, STOP PASS, AS5600 PWM FAIL

Пользователь подтвердил J1softstartON/15ВON/повербанки/PC-SaleaeOFF и запросил
один5Гц/5с пуск с первым I2Cсбоем. Перед START:327В,автонольREADY,enc_errors0,
SDHIGH,но сохранён preSTARTBreak occurred1024/current0,IRQdisabled.
Rawevent tick198872,MOEfalse/start_windowfalse/motorstate0/ref0/предшествующие
MCmasks0. Полный совместный захват:PA6LOW61.8мкс,TP23PA4LOW61.4мкс,
два несовпадающих отсчёта0.4мкс. Оба импульса завершены. Снимки архивированы
до ОДНОГО штатного CLEAR как подготовки запрошенного одиночного пуска.
После CLEAR три подтверждения readyOFF/SDHIGH/IRQenabled/masks0; SHA
сохранённого SDtrace и rawevent неизменны. Нового SD в самих пусках нет.

artifacts/live_bench_20261027/nucleo_i2c_stop_recovery_r1/powered_first_fault_5hz_r1:
before_preflight.json,prestart_bkin_trace.json,prestart_break_snapshot.json,
prestart_sd_ack.json(PASS,CLEAR1/START0),runner_guards.json(30 offline checks).
Hostrunner только получил exact2703/2704 identity:пороги и аппаратные gates
не изменялись. Никакой прошивки/RESET/смены шины/тактовGPIO не было.

trial/report.json:START1/CLEAR0,run_id1,Uno411112→416112=5000мс,reason1.
Пользователь попросил «еще раз пробуй», поэтому выполнен ОДИН отдельный
повтор:repeat_trial/report.json,START1/CLEAR0,run_id2,
Uno600552→605552=5000мс,reason1. ARM был штатной частью явно запрошенного
повторного пуска; CLEAR не нужен.
Пользователь подтвердил повтор:«Да, вращался ровно»; запись
repeat_trial/operator_confirmed_result.json. Первый физически отдельно
не подтверждён. Достоверность скорости AS5600 этим не подтверждается.

Оба автостопа подтверждены MCU и свежим OFF; независимый host backup не
потребовался. Обе raw report.passed=false ИЗ-ЗА неполноты измерений токов:
за5с/разгон в HTTPмониторе по одному различному valid5Гц окну вместо двух;
остальные active окна на разгоне, следующее5Гц окно уже в OFF snapshot.
Критерий не ослаблялся, это не авария/сбойавтостопа. Повтора ради критерия
не было — второй старт был отдельным прямым запросом пользователя.

I2Cза первый5с:110ошибок =NACK38+BUSY41+DEADLINE21+ARLO10;
BERRclears43 дополнительно, cleanSTOP15,forcedPEreset88,
softwareSTOPrequests25,cleanupdeadline47. За повтор100ошибок=
NACK31+BUSY42+DEADLINE15+ARLO12;BERRclears63,cleanSTOP20,
forcedPEreset72,softwareSTOPrequests17,cleanupdeadline30.
Итого210 первичных ошибок,ОВR/SHORT/SETUP0,послеSTOP ошибки не растут.
Чтения во время ШИМ прогрессировали, но с потерей bus/angle/speed валидности.
Скорость для обратной связи/FOC НЕ пригодна. Подробно analysis.json.

Первый160Б I2Cзахват обоих слотов одинаков,CRC338c2b55,первыйerror0,
NACK ISR0x8011,stage5/state2/n0:после записи0x0BвTXDR,ожиданиеTC.
CR2=0x0001006c START0;возраст278.465мкс(<3мс),предыдущийpoll23.853мкс,
maxpollgap538.888мкс. На первомGPIO SCL/SDA LOW. Конечный cleanup снимок
доPEreset:ISR0x8001(BUSY1/STOPF0),CR1=0x201(PE1),
CR2=0x0001406c(STOPpending1),GPIO0x250(SCLLOW/SDAHIGH).
cleanupflags26=REQUESTED+EXPIRED+FORCED,длительность505.506мкс.
Значит новый драйвер реально ждал STOP и запросил его, не делал прежнего
немедленного PEreset. Но STOP не завершился при SCLLOW. КТО держит/искажает
SCL и первопричина NACK по этим последовательным цифровым снимкам не доказаны.
Не приписывать факт исключительно вебу/IRQ или аппаратному браку.

Первый I2Cзахват не стёрт и не изменился во втором пуске; новогоfirstcapture
на повторе не запрашивали, т.к. слоты уже заняты. enc_fault_bad1→3,
полные записиCRC-valid; точная причина отказа отдельных страниц не
зафиксирована, не называть это CRCаварией силового UART.

Финальный свежий SAFE/PWM0/ARM0,bp_status1,transport0,currentmask0/occurred0,
326В,enc_errors210. J1/15В по подтверждению остаютсяON,платы на повербанках,
PC/SaleaeOFF. Без новых START/CLEAR/RESET, без USB/SWD при J1ON.
Прошивка остаётся2703/2704. Следующий анализ — STOPpending/SCLLOW и реальные
I2Cлинии, используя сохранённые данные; не обещать полное решение программой.

## 2026-10-27:2703/2704 автономно — связь/AS5600/автоноль/SD в покое PASS

Пользователь подтвердил: обе платы на повербанках, PC USB и Saleae отключены,
15ВON,J1OFF,RESET не нажимал. В этом этапе только WiFiHTTP GET и SSH read-only;
START/CLEAR/ARM/RESET/flash/service restart/serial reopen/USB/SWD/ADB=0.

runtime_powerbank_r1/report.json сохранил первый HTTP timeout без статуса.
Затем8080/2222 доступны; без вмешательства runtime_powerbank_r2/report.json
PASS:20секунд,3параллельных клиента,27ответов,reads+3693. Финально reads18388,
enc_errors0, NACK/deadline/ARLO/BERRclears/forced reset0, новых UART/RPC/
diagnostic rejection0, maxHTTP2.5с. Точная причина первого HTTP timeout не
установлена; не называть его доказанным новым RPC/I2C зависанием.

boot_metadata.json:Linuxuptime86.30с; unoq-hmi.service и arduino-router.service
active/running,NRestarts0. Программного восстановления связи после этого
автономного включения НЕ потребовалось. Калибровка SHA прежняя
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

Последний2703/2704SAFE/PWM0/ARM0,шина10В,mc_age21мс,bp_status1.
MCfault0/reason0/transport0,currentmask0/occurredmask0. CLEAR сейчас не нужен.
Автоноль READY/история валидна; SDHIGH/configOK/IRQenabled/capture_running,
SDfirst_record_readyfalse. Оба I2C first-fault слота пусты; категорийные
счётчики доступны и нулевые. AS5600 имеет свежие bus/angle-valid чтения;
это НЕ подтверждение вращения/правильного масштаба скорости и НЕ PWM/FOC
квалификация. manifest.autonomous_idle_validated=true, underPWM=false.

Сейчас J1OFF/15ВON/повербанки/PC-SaleaeOFF. Следующий физический шаг — J1
через штатный soft-start,без Пуск/RESET; свежая проверка шины и защит перед
одним коротким5Гц/5с прогоном. Проводку/датчик не менять. Ранние захваты
сохранены в предыдущих файлах, новые слоты пригодны для первого сбоя.

## 2026-10-27:2703/2704 записаны, оба readback PASS, покой AS5600 PASS

Пользователь ответил «готово» на J1OFF/независимыймультиметр<20В/обеUSBПК,
15В можно оставить. USB inventory подтвердил Uno3880458060/COM10 и
Nucleo003A002C3335510933383531/COM13. ADB после запуска сервера определился
сам; никаких физических переподключений для этого не понадобилось.

tools/install_nucleo_i2c_stop.py:
artifacts/live_bench_20261027/nucleo_i2c_stop_recovery_r1/install_usb_r1.
Один flash Nucleo2026102704, один flash Uno2026102703; обе проверки чтением
обратно PASS. Калибровка до/после одинаковая, SHA
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
Начальный runtime report.json сохранил timeout после прошивки. Один
документированный router serial close/open восстановил RPC; результат
post_flash_recovery.json PASS. Дополнительных flash/MCU reset0, START/CLEAR0.
Итог обоих этапов install_usb_r1/verified_result.json PASS. Не выдавать
начальный timeout за непроверенную запись образов; он относится к RPC.

runtime_usb_r1/report.json:20секунд проверки покоя,3параллельных клиента,
27HTTP ответов,successful_reads+3974, enc_errors0 и новых ошибок/таймаутов/
forced resets/STOP requests/отвергнутых diagnostic страниц/UART/RPC0.
Новые category snapshots полностью принимаются и доступны. maxHTTP2.406с.
Автоноль READY, история валидна. SDHIGH/configOK/IRQenabled/capture_running,
первый SDслот свободен. Свежий SAFE/PWM0/ARM0, шина около10В при15ВON.
Это USB-покой без J1, НЕ проверка датчика под ШИМ или достоверности скорости.

После reset/flash сохранены latch transport7=LINK_TIMEOUT и occurredMC4=
startup undervoltage; currentMCmask0. CLEAR не отправляли. Не объявлять
эти latch новой CRC-ошибкой или действующим аппаратным SD; перед будущим
пуском сначала проверить свежие masks/SD и архив, штатный CLEAR по согласованному
сценарию. Не ослаблять защиты и не подменять stale данными.

manifest.installed=true, hardware_idle_validated=true,
sensor_under_pwm_qualified=false. Исторические снимки до перепрошивки
сохранены в install before/status и предыдущих powered trial артефактах.
Сейчас по последнему подтверждению J1OFF,15ВON,обеUSBПК. Следующий физический
шаг — обе платы на повербанки, PC/Saleae отключены, J1 покаOFF; проверить
холодную автономную загрузку/связь до подачи силового. RESET не требуется.

## 2026-10-27: кандидат2703/2704 — NACK→STOP cleanup проверен офлайн, НЕ установлен

Запрос: полностью разобрать NACK→STOP→восстановление по реальному захвату,
подготовить проверенные образы; без очередных пробных пусков/перепрошивок.
В этой работе команд к стенду, START/CLEAR/RESET/flash/USB/SWD/ADB нет.
Текущее физическое состояние по последнему подтверждению остаётся:
J1ON/15ВON, платы на повербанках, PC/Saleae отключены, последнее PWM0/SAFE.
Установленные образы по-прежнему2701/2702; не выдавать2703/2704 за записанные.

Кандидат: artifacts/live_bench_20261027/nucleo_i2c_stop_recovery_r1.
manifest built/selftest_pass=true, installed/hardware_validated=false.
Образы Uno2026102703/Nucleo2026102704 запечатаны и verify-package-only PASS:
Uno22e9a21298f644c4e0a5a3643a4016fa5617896d38a5083dce07103ae4f86431;
NucleoHEX aeb8a22c0c6819d89e111cc3423e4b0223553bf44a0b17170f60ddb9b5c3490d.

Точный вход первого реального события replay: ISR0x8011=NACKF+BUSY+TXE,
STOPF0, state1/stage4/n0, до передачи0x0B. Старый2702 немедленно выключал PE.
Новый автомат сохраняет снимок, инвалидирует всю выборку/скорость, очищает
только NACKCF и неблокирующе ждёт STOPF+BUSY0+HIGH. После100мкс допустим
один softwareSTOP только если START/STOP0 и нет ARLO. При ARLO STOP запрещён,
ждём свободную шину и два HIGH наблюдения с интервалом≥5мкс. После500мкс
незавершённой очистки один forced PEreset. Это программные бюджеты, не
жёсткая аппаратная гарантия500мкс при произвольной задержке вызова poll.
Бюджет чтения3мс/период5мс/backoff20мс сохранены. Исправлен configured0 во
время pending cleanup; лишний RXNE вне RX-состояния отвергается.

160Б first-fault format2: прежние два слота; footer35..39 теперь состояние
ДО очистки STOPF/PE в конце cleanup, флаги в meta26..31. Старый формат1
декодируется по прежней post_reset семантике. Сохранённые слоты не затираются.
Новый0xDC формат1:14 счётчиков двумя CRC32C страницами, единый snapshot,
низкоприоритетная отправка в очередь только при OFF. Доступны только свежие
полные данные exact peer2704, TTL2с; под PWM категории недоступны. EW total/
cause остаются текущими. Primary counts не равны всем физическим событиям;
BERR counter считает очищения, deadline насыщается на65535 как прежде.

verification/core_report.json:400 комбинаций событий плюс граничные случаи;
32761 assertions, реальный вход старого/нового кода, продолжение МОДЕЛИРУЕТСЯ.
Весь production C driver с W1C MMIO: terminal capture до park, frozen slots,
config failure cleanup, корректный регистр/трёхбайтовое чтение — PASS.
verification/report.json: обе целевые сборки PASS; Nucleo0errors/0warnings,
RAMрост112Б, запас3528Б сверх reserved heap/stack, ADC IRQ stack376Б без
изменений, оба capture callback24Б. Проверены реальные HMI/CRC/peer/TTL,
current/autozero contracts, калибровочная совместимость и зависимости
пакетных RPC-библиотек для sketch И bridge singleton. Полные main/Uno после
удаления явно перечисленных диагностических вставок и FWID совпадают со
старыми; PWM/ADC/Break/защиты/UART-команды/watchdogs/автостоп/display/UI не
изменялись. Источник калибровки и её SHA прежние.

verification/review.json и references/source_review.json содержат границы
доказательств и первоисточники ST/AS5600. RM0440 просмотрен по релевантным
разделам; полный PDF локально не скачан, прочтение всего руководства не
заявляется. Порядок NACKCF→STOPF сверён с локальным pinned HAL и ST upstream.
ФИЗИЧЕСКИЙ ИСТОЧНИК ПЕРВОГО NACK НЕ ДОКАЗАН. Датчик под PWM/для FOC не
квалифицирован; офлайн тесты не являются доказательством помехоустойчивости.

Следующий шаг, когда пользователь решит записывать: J1OFF, независимый
мультиметр<20В, обе платы на USB ПК,15В можно оставить, двигатель/AS5600/
TP23→1кОм→PA4 без изменений. tools/install_nucleo_i2c_stop.py с явным
подтверждением этого состояния; проверка обоих образов чтением обратно,
сохранение калибровки. При нынешнем J1ON установщик НЕ запускать.
После записи сначала покой без J1; никакого автоматического пуска установщиком.

## 2026-10-27:2701/2702 — один5Гц/5с пуск завершён; первый сбой теперь адресный NACK

Пользователь подтвердил J1softstartON/15ВON/повербанки/неПускнеRESET и разрешил
пуск5Гц/5с с первымI2Cзахватом. Свежий preflight325В,transport0,autonullREADY,
AS5600busOK/errors0, SDHIGH/configOK. Остался только прежнийstartupUV:
mc/bp fault5,reason8,currentmask0,occurredmask4; поэтому IRQBreak был выключен.
Архивировали состояние и отправили ОДИН штатный CLEAR в пределах необходимой
подготовки согласованного пуска. startup_uv_only predicate PASS; затем readyOFF,
SDIRQenabled,маски0,снимки неизменны. Никакого ослабления guards/защит.

artifacts/live_bench_20261027/nucleo_i2c_idle_r1/powered_first_fault_5hz_r1:
startup_uv_ack.json — CLEAR1/START0,снимки сохранены;
trial/report.json — START1/CLEAR0,MCUrun314300→319300=5000мс,normalreason1,
STOP/ARMoff подтверждены,2разных валидных токовых окна5Гц. Пользователь ответил
«Да, вращался ровно». trial/operator_confirmed_result.json сохраняет ответ.
Точное электрическое время выключения затворов независимо не измерялось.
Итог: механический пуск/автостоп PASS, AS5600подШИМFAIL. ФинальноSAFE/PWM0/ARM0,
peer bp_status1,всеactive/occurredMCmasks0,link/RPCчистые,послеSTOP AS5600читался.

I2C:122 ошибки и122 PEreset, из них24 EC_DEADLINE. Категорийные счётчики
NACK/BERR/ARLO/BUSY на этом backend не доступны; их нули в HMI не доказывают
отсутствие. Во время PWM чтения реально прогрессировали:между наблюдениями
1171→4627мс successful_reads62703→63029(+326). ПослеSTOP errors122 не росли.
RPC response/send и UART bad приращения0. Скорость датчика не квалифицирована.

Первый160Б снимок одинаков в first_since_boot/first_with_pwm,MOEtrue,CRC32C3eed2798.
CauseNACK2,state1,stage4,received_bytes0,errors_before0. ISR=0x8011
(BUSY+NACKF+TXE),безBERR/ARLO/OVR/STOPF в этой записи. CR2=0x0001206c:
WRITE,адрес0x36,NBYTES1; ожиданиеTXIS до передачи регистра0x0B.
Возраст156.59мкс,предыдущийpoll6.98мкс,SCL/SDAHIGH в момент снимка;
это не тайм-аут3мс у первого сбоя. ПослеPEresetISR1,CR1=0x200,CR2=0.
Одна диагностическая страница отвергнута; причина отдельно не зафиксирована.
Итоговые записи полностью реконструированы и CRC проверен; не объявлять
отвергнутую страницу CRC-ошибкой силового UART.

Сравнение с2609/2604:243ошибки/первыйIDLEBUSY →122ошибки/первыйактивныйNACK,
оба5сек. Это два отдельных прогона; физическая причина NACK и все остальные
категории ошибок не доказаны. Не утверждать, что весьBUSY/помехи устранены
или что датчик уже пригоден дляFOC. Подробности comparison_previous_run.json,
analysis.json,trial/first_i2c_capture.json,final_status.json.

Никаких повторных START/RESET/flash после этого пуска не было. Силовое и15В
по последнему подтверждению остаютсяON,платы на повербанках,PC/Saleae отключены.
Снимки не стирать и повторно двигатель автоматически не запускать.
Следующий анализ на ПК:адресныйNACK и завершениеNACK/STOP доPEreset по этому
первому снимку. Не просить физические переключения, пока не готова конкретная
следующая проверка или сборка; USB/SWD при нынешнем J1ON не использовать.

## 2026-10-27: автономная2701/2702 и AS5600 прошли покой, UV latch сохранён

Пользователь подтвердил: обе платы на повербанках, PC/Saleae отключены,
15В ON,J1OFF,RESET не нажимал. Только WiFi/SSH read-only: START/CLEAR/ARM/
flash/reset/serial reopen/service restart=0. Никаких USB/ADB/SWD в этом этапе.

Первый запрос во время загрузки не ответил; runtime_powerbank_r1/report.json
с timeout сохранён. Затем получен свежий2701/2702SAFE/PWM0 ответ без вмешательства,
Linux uptime43.08с; router и HMI active. SHA калибровки по SSH прежний
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

artifacts/live_bench_20261027/nucleo_i2c_idle_r1/runtime_powerbank_r2/report.json:
40секунд/3параллельных вебклиента,+8318 чтений AS5600, новых ошибок RPC/UART/I2C,
сбросов I2C контроллера, потерь RX и shortTX=0. enc_errors после coldboot0;
bus/angle/configOK,магнит0x67. maxHTTP2.859с. Автоноль готов:3 стабильных блока,
история и качество валидны. SDHIGH/config/IRQ/captureOK, firstPWM I2C слот
свободен и декодер валиден; захваты за40с не изменились. SAFE/PWM0/ARM0.
Одна холодная автономная загрузка подтверждена; устойчивость под ШИМ ещё НЕ
проверялась. Исторические15723ошибки USB-сессии исчезли после аппаратной смены
питания, агент счётчики не стирал. Не выдавать0 после загрузки за доказательство
того, что таких ошибок никогда не было.

Есть сохранённая MC_UNDER_VOLT: mc_fault=bp_fault5,reason8,current_mask0,
occurred_mask4,transportfault0,estop0 при шине10В/J1OFF. Это не чистый допуск
пуска и не SD-авария. CLEAR не отправлялся. После включения J1 проверить новый
статус и только затем разбирать оставшийся UV latch; не ослаблять ready guards
и не запускать trial, пока требуется ACK. Новый/активный fault не обходить.

Итог runtime_powerbank_r2/qualification.json и manifest:
autonomous_coldboot_rpc_verified=true(count1),autonomous_sensor_idle_verified=true,
autonomous_coldboot_pending=false,sensor_under_pwm_qualified=false.

Следующий физический шаг для ранее согласованного5Гц/5с теста с первымI2Cсбоем:
включить ТОЛЬКО J1 через soft-start, оставив15В/повербанки/датчик как есть;
Пуск и RESET вручную не нажимать. Попросить «силовое включено», затем powered
read-only preflight и сохранение состояния до любых действий. No automatic
CLEAR/START в рамках только что завершённой проверки автономной загрузки.

## 2026-10-27:2701/2702 записаны/сверены; AS5600 после подключения проходит покой на USB

Пользователь подтвердил J1OFF, DMM<20В, обеUSBнаПК,15В оставлены, разрешил
записать2701/2702. Фактически установлены Uno2026102701/Nucleo2026102702.
В artifacts/live_bench_20261027/nucleo_i2c_idle_r1/install_r2:
flash_verify_nucleo.log — Download verified successfully;
verify_uno.log — UNO Q verification PASSED. ПоОДНОЙ записи каждой платы.
SHA калибровки до/после прежний a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
install_r1 был неудачным перечислением ADB во время USB загрузки, flash0.
Начальный install_r2/report.json с post-flash RPC timeout сохранён;
одно опубликованное serial close/open восстановило RPC, post_flash_recovery.json
PASS, дополнительных записей образов/команд двигателя не было.

Важная диагностика: после записи AS5600 сначала не отвечал даже в покое.
Первоначально заподозрили новый PE0-режим, но сохранённый BEFORE FLASH статус
ещё2609/2604 уже имел enc_reads0/errors4202/SCL0/SDA0. Эта проблема существовала
до новой пары; НЕ объявлять её регрессией2702 или следствием ШИМ без доказательств.
Первый снимок2702 — PE0, ISR1, GPIO обеLOW, state0/stage4, около3мс ожидания,
без PWM. PE0→PE1→PE0 при halted MCU не поднял линии. РежимGPIO input такжеLOW;
временные слабые pullup подняли обеHIGH. Временный pullup-тест с работающим
ядром дал cause2/NACK,stage4,ISR0x8011, чтений0: отсутствовал ACK адреса0x36.
PUPDR0x510a,MODER0xfffaaeba и PE0 восстановлены, это не постоянный обход.

Аудит диагностики: один вызов программатора использовал неверное mode=HOT,
tool предупредил и перешёл в NORMAL; его startup-like чтение не использовали.
Затем явно HOTPLUG, resume и два ограниченных halt/probe/restore/run. Не писать
безоговорочно «MCU никогда не прерывался»: режим NORMAL мог повлиять на запуск.
Эти пробы писали только I2C/GPIO регистры, не flash и не PWM/защиты. Все снимки
до проб сохранены. В будущих read-only вызовах использовать mode=HOTPLUG, не HOT.

Попросили измерить VCC-GND на AS5600. Пользователь ответил «готово подключил»;
точное напряжение НЕ сообщено. После этого AS5600 появился без новых прошивок:
reads4731→5420,errors15723 не росли, SCL/SDAHIGH,bus/angle/configOK,магнит0x67.
Не объявлять, какой именно провод был отключён; пользователь этого не уточнил.
Повторное измерение питания сейчас не требуется для проверки покоя.

runtime_usb_r2/report.json:40секунд/3вебклиента,+7768 успешных чтений, все
приращения ошибок RPC/UART/I2C/сбросов I2C контроллера/потерьRX/shortTX=0.
Autonull READY,3 стабильных блока/история/качество валидны. SDHIGH/configOK,
захват работает, первый PWM I2C слот свободен; прежний boot-fault сохранён.
Ошибки15723 исторические, их не стирали. Привод SAFE/PWM0/ARM0, активных
fault masks0, transportfault0; START/CLEAR/ARM не посылали. Файл калибровки прежний.
Итог installation_result.json: programming/readback иusb_sensor_idle PASS.
Manifest installed=true/usb_sensor_idle_verified=true; hardware_validated=false,
sensor_under_pwm_qualified=false, autonomous_coldboot_pending=true.

Следующий шаг: обе платы→повербанки, PC/Saleae отключены,J1 ОСТАВИТЬOFF,
15В ON, RESET не нажимать. Сначала только WiFi автономный read-only boot/idle
check2701/2702 (tools/check_rpc_coldboot_idle.py --i2c-idle --powerbank
--url http://192.168.1.138:8080); до его PASS не просить включить J1.
Никаких повторных прошивок или сбросов для этого перехода не требуется.

## 2026-10-27: подготовлены2701/2702 — I2C в паузах выключен, BUSY ожидается ограниченно

Запрос пользователя: исправить BUSY по реальному снимку и подготовить прошивку;
питание/подключения не менял. Последнее физическое состояние: J1 и15В включены,
обе платы на повербанках, PC/Saleae отключены. Привод после прошлого автостопа
SAFE/PWM0. В этом этапе агент НЕ подключался к стенду и НЕ посылал команды:
никаких START/CLEAR/ARM/RESET/flash/USB/ADB/SWD/serial reopen.

Готовый пакет: artifacts/live_bench_20261027/nucleo_i2c_idle_r1.
Uno2026102701 / Nucleo2026102702. built/selftest=true, installed=false,
hardware_validated=false, sensor_under_pwm_qualified=false.
Установщик tools/install_nucleo_i2c_idle.py --verify-package-only PASS:
Uno imageSHA669a7086c6336e708d908b627ca65139e23efcf30d0626e6bf7085e0bf5f894a,
NucleoHEXsha dea39df57d599befc4ffc94278a111e14b487ad3955f7f075fb44939f3ffdb37.
Фактически установлены по-прежнему2609/2604; новые номера не выдавать за live.

Разбор: старое ядро оставляет PE1 между измерениями и немедленно сбрасывает
периферию на BUSY передSTART. Реальный первый вход0x8001/SCLHIGH/SDAHIGH/IDLE
воспроизведён на исходном коде. Это подтверждает обработку, а не физический
источник помехи. Не объявлять ложный START или BERR доказанной первопричиной.

Новый драйвер Nucleo оставляет PE0 в паузах. Подготовка неблокирующая:
дважды HIGH с интервалом>=2мкс, затем PE1 и ожидание BUSY0/свободной линии.
Вся подготовка и обмен входят в прежние3мс; сбой не выдаётся за измерение,
backoff20мс прежний, повтор того же измерения и ручные импульсы отсутствуют.
Первый сбой сохраняется перед PE-reset. BERR-alone в master очищается без
срыва обмена по ES0431§2.11.2; NACK/ARLO/OVR/deadline остаются фатальными,
их регистры сохраняются прежде очистки BERR. PE0 минимум три APB цикла
из RM0440 покрыт неблокирующим интервалом>=2мкс.

Телеметрия датчика получила формат2: свежие данные допустимы при PE0 в паузе.
Код Uno меняет только идентификаторы и приём статуса датчика; CRC/config/TTL/
quality сохраняются, смешанные peer/format отвергаются. RPC libraries точно
из2609, проверены .d скетча и singletons. Вывод дисплея/UI без изменений.

Проверки:2928 проверок настоящего C-ядра; полный nucleo_encoder.c с MMIO-макетом;
реальный первый вход и отдельно моделируемые последующие ошибки;200штатных
чтений, LOWлинии, BUSYtransient, NACK/ARLO/OVR, deadline/BERR, wrap, CRC43байта.
Снимки160Б/2слота/OFF-only сохранены; ADC/PWM/Break/deadtime/watchdog/силовойUART
сравнены с установленными исходниками. Пороги и калибровка не менялись.
Обе целевые сборки PASS, Nucleo0errors/0warnings, RAM+24Б, запас3640Б,
ADCIRQstack376Б прежний, capturestack24Б.22AS5600hosttestsPASS: только новый
identity добавлен к прежним guards, все условия защит и сроков сохранены.
Детали verification/report.json, verification/cause_evidence.json, README_RU.md.

Следующий физический шаг — только для записи готовых образов:
выключить J1; после независимого DMM<20В подключить обе платы кПК.15В можно
оставить включёнными; двигатель/AS5600/TP23→1кОм→PA4/прочую проводку не менять.
Попросить подтверждение этого состояния; текущий J1ON не разрешает прошивку.
Установщик проверяет образы/чтение обратно обеих плат/калибровку. При timed-out
RPC только после обеих readback и сохранённой калибровки допустимо ОДНО
документированное serial close/open Linux в подтверждённом J1OFF состоянии,
без повторной прошивки и MCUreset; начальный отчёт сохраняется отдельно.
После установки сначала проверить покой, затем автономную загрузку при J1OFF,
и только затем просить силовое для нового согласованного5Гц/5с испытания.

## 2026-10-26: выполнен один5Гц/5с пуск, первый I2C BUSY сохранён до PE reset

Пользователь подтвердил: обе платы на повербанках, PC/Saleae отключены,
15 В и J1 черезsoft-start включены; Пуск и RESET не нажимал. По свежему
WiFi preflight:2609/2604,325В,SAFE/PWM0,SDHIGH,нулевыеfault/transport masks,
валидный автоноль и свободный first-PWM слот. Ни CLEAR, ни reset не требовались.

tools/run_as5600_bounded_5hz.py выполнил ОДИН START:5Гц, локальный Uno
RUNLIMIT5000мс. В TimedRun зарегистрированы456199→461200мс, итого5001мс.
Это время MCU-события, физическое выключение затворов отдельно не измерялось.
STOP и снятие ARM подтверждены; финально SAFE/PWM0, peer bp_status=1,
ARM0 и нулевые MC fault masks. Пользователь подтвердил: «Да, вращался ровно».
Защитные пороги/прошивки/калибровка/проводка не менялись; повторных START не было.

Результат механического пуска и автостопа PASS; AS5600 под ШИМ НЕ прошёл:
+243 ошибки и243 PE-reset периферии, показания скорости в этих интервалах
недостоверны. RPC response/send и UART bad приращения0; двигатель не упал
по защите. После STOP AS5600 снова читался (enc_bus_ok1). Никаких повторов
пуска автоматически не делать, сохранённые снимки не стирать.

Первый реальный160Б снимок получен в обоих слотах: first_since_boot и
first_with_pwm идентичны, CRC32C0424379b. Флаг PWM MOE был установлен.
Первый зарегистрированный сбой:EC_BUSY11, state0/IDLE,stage4 перед START,
received_bytes3 от прошлого обмена, errors_before0. ISR=0x8001 (BUSY+TXE),
без NACKF/BERR/ARLO/OVR/STOPF; оба чтения ISR вокруг GPIO совпали.
SCL/PB8 и SDA/PB9 HIGH в последовательном снимке. Это не исключает коротких
помех на линии, но постоянного LOW в этот момент нет. CR1=0x201,
CR2=0x0203046c (прошлый3Б AUTOEND READ, START/STOP уже0), TIMINGR0x30521317.
После PE-reset ISR0x1:BUSY снялся. Между poll32.39мкс, измеренный max107.81мкс;
задержка планирования3мс в этом захвате не проявилась. Это не доказывает
первичную электрическую причину, ошибку датчика или конкретное erratum.

enc_fault_bad вырос на1 в доставке; точная причина отклонения страницы не
записана. НЕ называть это CRC UART без доказательств. Полные итоговые записи
проверены CRC и валидны, дальнейшие страницы приняты. Категорийные
enc_diag_busy/nack/berr/arlo счётчики на Nucleo-backend не доступны: их0 в
общем HMI нельзя интерпретировать как отсутствие этих ошибок.

Все данные: artifacts/live_bench_20261026/rpc_boot_retry_r1/powered_first_fault_5hz_r1/
  trial/report.json — исходный отчёт, trial/operator_confirmed_result.json — ответ пользователя;
  trial/first_i2c_capture.json — сырые160Б и регистры;
  analysis.json — выводы/ограничения; final_status.json — свежий SAFE/OFF.

Далее на ПК: разобрать обработку BUSY перед новым START и STOP/PE-reset на
настоящем encoder_core, воспроизвести захваченный контекст, затем готовить
обоснованное исправление. Никаких новых физических переключений для анализа
не требуется. Силовое по последнему подтверждению остаётся включено; платы
на повербанках, USB/ADB/SWD не использовать и не просить ПК до отдельной
подготовки к записи. Скалярный привод остановлен; FOC не запускался.

## 2026-10-26: автономная загрузка 2609/2604 прошла без восстановления канала

Пользователь перевёл Uno Q на повербанк; J1 выключен, 15 В и Nucleo не трогал,
RESET не нажимал. Проверка только по WiFi: никаких USB/ADB/SWD, START/CLEAR/ARM,
перепрошивок, перезапусков служб или $/serial/close/open в этом этапе.

Первый HTTP-запрос во время загрузки истёк по тайм-ауту; исходный failed-report
runtime_powerbank_r1/report.json сохранён. Примерно на49-й секунде Linux uptime
получен свежий SAFE/PWM0 статус Uno2609/Nucleo2604, RPC response/send timeout=0.
Затем runtime_powerbank_r2/report.json: 40секунд, 3 параллельных веб-клиента,
+8113 чтений AS5600, максимум HTTP1.843с; приращения RPC/UART/I2C ошибок,
потерь RX, коротких TX и сбросов I2C контроллера=0. Новые снимки не возникли.
Это ОДНА успешная холодная автономная загрузка, не доказательство всех вариантов
сбоев и не результат работы AS5600 под ШИМ.

Автоноль готов:3 устойчивых блока, история и качество валидны. SD HIGH,
конфигурация и IRQ Break исправны, захват работает; first-PWM I2C слот свободен,
декодер корректен. Активные/защёлкнутые MC fault masks=0, transport fault=0,
E-stop=0, ARM=0. ШИМ не запускался. SHA файла калибровки по SSH прежний:
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

После перехода счётчики Nucleo enc_reads/mc_good_cnt/mc_bad_cnt тоже начались
заново; агент RESET не отправлял. Причина предполагаемого перезапуска Nucleo
не установлена. Использована свежая валидная история автонуля; прежние записи
сохранены на ПК. Не приписывать это изменение действию пользователя без данных.

Пакет artifacts/live_bench_20261026/rpc_boot_retry_r1: installed/readback и
usb_runtime проверены, autonomous_coldboot_rpc_verified=true (count1),
observed_coldboot_root_cause_proven=false. Подробности runtime_powerbank_r2/qualification.json.
Хост run_as5600_bounded_5hz.py подготовлен к2609/2604+NUCLEO+первомуI2Cзахвату:
добавлены только проверенные identity пары; защитные условия/таймеры сохранены.
21AS5600 host test PASS, в том числе deadline/fault/stale/mixed identity checks.

Далее: только J1 через штатный soft-start при прежнем автономном подключении;
подтверждение пользователя перед powered-read/ранее согласованным5Гц/5с пуском.
15 В/датчик/магнит/Nucleo не переставлять, RESET/Пуск вручную не нажимать.
Повторная прошивка, сброс Nucleo или калибровка для этого перехода не нужны.

## 2026-10-26: Uno 2609 / Nucleo 2604 — RPC восстановлена на USB, автономную загрузку ещё проверить

Последнее подтверждённое физическое состояние: J1 выключен, мультиметр <20 В,
Uno Q на USB ПК; Nucleo остаётся на повербанке, 15 В включены. Двигатель,
AS5600 (PB8/PB9) и TP23→1кОм→PA4 не переставляли. Пусков в этом этапе НЕ было.

Готовый пакет: artifacts/live_bench_20261026/rpc_boot_retry_r1.
Uno 2609 записана и сверена чтением обратно; Nucleo 2604 не прошивали и не
сбрасывали. SHA калибровки прежний a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
Код управления двигателем, аппаратных защит, автостопа, ADC/SD и первого I2C
захвата сохранён. Локальные библиотеки в пакете, глобальные Arduino libs не менялись.

Проверки на настоящих заголовках RouterBridge/RPClite воспроизвели бесконечное
ожидание потерянного ответа исходной версии. Добавлены границы ожидания ответа
1500 мс и отправки 2000 мс; исходящие вызовы сериализованы, просроченные ответы
убираются только в этом сериализованном пути. Неизвестный метод отвечает ошибкой,
известный вызов с safe-tag сохраняется. Повтор begin использует тот же транспорт
и поток. При сбое RPC begin больше нет автоматического NVIC reset в setup/idle
bridge_tick; попытка соединения повторяется только при local+peer PWM OFF.
10 native сценариев PASS; target LLEXT проверка PASS; .d обеих единиц трансляции
подтверждают одинаковые локальные заголовки; моторный код сравнен с установленным.

Промежуточная 2607 выявила цикл reset после bounded timeout: он сохранён в
rpc_coldboot_fix_r1/diagnosis/read_boot_cycles.log. В 2609 этого reset пути нет.
При недоступной 2609 RAM показала 34 RPC response timeout, 0 send timeout,
целые входящие get и отсутствие sampled PE/FE/NE/ORE LPUART. После прошивки снова
потребовалось ОДНО штатное переоткрытие /dev/ttyHS1 через опубликованные методы
router0.5.3 $/serial/close/open (один параметр с путём). Без sudo, MCU reset и
переподключения USB. Это восстановило связь; точная первопричина Linux stream
и прежнего автономного отказа пока НЕ доказана.

runtime_usb_r1/report.json: 40 секунд, 3 одновременных веб-клиента, +8280 чтений
AS5600, приращения RPC/UART/I2C ошибок и controller reset =0; сохранённые SD/I2C
снимки не менялись. Калибровка доступна; SAFE/PWM0. Начальный install_r1/report.json
с timeout сохранён, итог installation_result.json объясняет восстановление.

СЛЕДУЮЩЕЕ действие пользователя: перевести ТОЛЬКО Uno Q с USB ПК на повербанк,
J1 ОСТАВИТЬ выключенным, Nucleo/15 В/датчик не трогать, RESET не нажимать.
Затем только WiFi read-only проверка новой загрузки и свежего автонуля/захватов.
Не просить включать J1 одновременно с переводом на повербанк. Холодная автономная
RPC пока не квалифицирована; до её проверки мотор не запускать.

## 2026-10-26: powered capture пуск НЕ отправлен — автономная RPC послеcoldboot не отвечает

Пользователь подтвердил powerbanks/PC+Saleaeoff/15В+J1softstartON/неSTARTнеRESET
для одного5Гц/5сек первогоI2Ccapture. ТолькоWiFi GET5attemptstimеouts.
LinuxдоступенпоWiFiSSHpin/8080open; uptime154сек, HMIpid557.
ОдинownedHMIrestart поUID/cwd/Restartalways(SIGHUPнепосылали,SIGTERMautoRestart),
затем3GETtimeouts. Прямой RouterClient get черезHMIvenv наLinux тожеNone/timeout.
START0/ARM0/CLEAR0/MCUreset0/flash0. USB/ADB/SWDнаpoweredbenchнеиспользовали.
Провереныread-only appCLIhelp/routerlogs; штатногоmcuresetвsystemCLIнет,
apprestart(можетперешить)невызывали. Linuxrouterлоги показываютreconnects,
не устанавливаютпервопричину. Captureнеполучен — потому что пускане было,
не объявлять этоошибкойI2CподШИМилирезультатомновогопрогона.

report.jsonв i2c_first_fault_r1/powered_first_fault_5hz_r1 фиксируетfailedpreflight.
Manifest autonomous_coldboot_rpc_verified=false/rpc_pending=true.
Прошлыйidle30secUSBtestне доказывалнадёжностьавтономногоcoldboot; пользователь
получилуточнение: былоошибкойпроситьвключитьJ1сразупослепереходанаповербанк,
нужносначаладоказатьRPCприpowerbanks/J4ON/J1OFF. Не повторятьэтотпорядок.

Нужно: выключитьтолькоJ1, дождатьсяDMM<20В, подключитьтолькоUnoUSBПК;
Nucleoоставитьpowerbank/15Вкакесть/датчикне трогать/RESETне нажимать.
Это следующийзапроссостояниядляRPCdebug, не новаякалибровка/неотсоединениемотора.
До новогоявногоподтвержденияэтогосостояния никакогоSWD/USBконтроляMCU.
ЗатемисследоватьконтекстRPCdecoder/Bridgeчерезread-onlyruntimeпамятьиустранить
coldbootзависание, вместоочередноговременногоreconnectираннегоHVвключения.
ПоследнеефизическоесостояниепокасиловоеONпопользователю, MCUсостояниеизRPC
неподтверждено; мыникакихпусковыхкоманднеотправляли. Моторпослеcoldboot
самозапускатьсяпрошивкойне должен, ноэто незаменяетживойпредпусковойстатус.

## 2026-10-26: 5Гц/5000мс first-I2C capture runner готов; ждём powerbank/powered состояние

Пользователь попросил один5Гц прогон/автостоп5сек с первымсбоемI2C, спросилчто
переключить. До свежегоподтверждения powered-state START/CLEAR/ARMне отправляли.
run_as5600_bounded_5hz.py теперь принимает2605/2604+NUCLEO, optional
--collect-first-i2c-fault требуетdecodevalid/emptyfirstPWMslot/badpages0доSTART.
Реально сохранённыйпереходSAFE/bp0x61/TimedRunLIMIT5000 теперь распознаётся
отдельным deadline_stop_observed: peerMOEbitOFF/newrunid/reason1/точныетаймстампы,
всеphysical/SD/zero/UART/faultguards прежние. Это разрешает только STOP/disarm;
completed(require_request_off)/finalremoteOFF по-прежнему требуютcommandbit5OFF.
Никаких synthetic статусов дляобходаchecks. ТестыотвергаютremotePWMON/stale/
fault/wrongtimer. ПослеOFFсобираютсяpassiveI2Cpagesдо12сек(не продлеваетпуск),
first_i2c_capture.json+after_logs. ПриI2Cerrors иневозможностиполучитьrecord
capture_error, аRMS<2windowsпо-прежнемунеPASS. ПовторныхSTART/CLEARнет.
20AS5600hosttests PASS, firmwareimagesне менялись.

Далееинструкцияпользователю: обеUSBПК→повербанки,всеPC/SaleaeвключаяGNDсняты,
датчик/магнит/проводкуне трогать.15ВJ4включить/оставить,при закрытомстенде
J1черезsoftstart. RESET/Пускне нажимать; подтвердитьpowerbanks/PCoff/15В/J1on.
Послеэтогопроверитьсвежее состояние/архивироватьдоCLEAR; одиночноснятьтолько
известныйresetwatchdog7 приSDHIGH/нулевыхhardwaremasks/исправнойсвязи, еслион
остался. Новую/активнуюзащитуне обходить. Затемодинсогласованный5Гцпуск.
powered_capture_preparation.jsonсохранён. ТекущийстендпокаJ1OFF/PCUSB какбыло.

## 2026-10-26: 2605/2604 RPC восстановлена без новой прошивки; idle30с PASS

После userUSBUno coldstart сначала API503: [2,methodgetnotavailable]. Linux
службывработе, rootarduino-router0.5.3/devttyHS1; MCUdebugsnapshot безflash:
core idle running,SCBfaults0. Не просилиещёpowercycle. Один controlledbootrelease
MCUизпрежнихпроверенныхобразов привёлкрегистрацииget/cmd,ноGETтаймаутам.
ПрямойзапросчерезHMIvenvRouterClientподтвердилпроблемунеHTTP. Read-onlyLLEXT
snapshot: bridgeflagsregistered,mutexcontrolfree,Bridge.startedtrue,threadsживы.
Это не доказательствокорневойпричины,ноисключаетпростоеотсутствиеметодоввэтойфазе.

Проверенmanufacturerarduino-router API иименноsource tagv0.5.3: в установленной
версии $/serial/open иclose требуют['/dev/ttyHS1']; текущаяREADMEбезпараметров
неподходит. Первыйзапросбезпараметровотклонён,портнеизменён. Затемодинреальный
close/open черезобычный UnixRPCподтверждён [null,true], безsudo/пароля.
Выполненвторой unchangedimagesverify+bootrelease MCU иодинownedHMIrestart
текущегобута. Flashwrites0, START/CLEAR0, NucleoReset0. Это compositerecovery,
не утверждать чтооднаоперациясамаустранилаконкретныйдоказанныйдефект.
Всядиагностика/конфиги/логи в i2c_first_fault_r1/boot_verify_r1,
recovery_summary.json фиксируетшаги. Длябудущегоpostflashнеобязательноповторно
проситьUSB; восстановлениевнутреннегопорта возможноштатнымAPIнаобесточенном
стенде. Не применять MCUreset/serialreconnect на включённомсиловом безпроверки
состояния; это programming/idle recovery, не частьмоторногопуска.

После recoveryполучена2605/2604/sourceNucleoI2C1/mode6. Read-only30сек,
3параллельныхstatusклиентапоUSBADBforward PASS: +6015чтений,0I2Cerrors,
0новыхencoderreject,1rescuedbyte,0HTTPerrors. zero/history/calvalid,SAFE/PWM0/
ARM0,Vbus10В. Старыйresetwatchdog7/fault2/badcnt1сохранён, НЕCLEARed;
этомунеприписыватьновуюаварию. Capturedecodevalid1, first/pwmhex '-',
statusожиданиепервогосбоя — интерфейсснимковпроверен,реальныйошибочныйcapture
нажелезеЕЩЁнепроверен. hardware_capture_validated/sensor_under_pwm_qualifiedfalse.

runtime_completion.json иruntime_idle_r2/report.json PASS; старыеfailedboot
иruntimeidle1сохранены. Manifest rpc_pending=false, idle_runtime_verified=true
толькодляread-only, motor_start_qualified=false. Последнееподтверждение: J1OFF,
DMM<20В,обеUSBПК,15Вкакбыло. Никакихновыхфизическихпереключенийнепросили.
Будущий5Hzrunner пока НЕ поддерживает2605/2604: расширитьownershippairguard,
сохранитьвсеSD/zero/защиты. Такжеучестьпрежнийfalseabort наSAFE/bp0x61 после
TimedRun5000: физическийOFF/новыйrunreason1есть, bitcommandrequestещёпереходный.
Не менятьтребования finalOFF/RMS и не объявлять старыйfailedreportPASS.

## 2026-10-26: 2605/2604 записаны/readback PASS; после первого ответа RPC нестабильна

Пользователь подтвердил J1OFF/DMM<20В/обеUSBПК,15Вможнооставить. Выполнен
install_i2c_first_fault.py одинраз installation_r1: Nucleo flash1+Cube verify
Downloadverified, Uno flash1+независимыйreadbackUNO QverificationPASSED.
HMIserver/appjsновые, калибровкаbefore/afterSHAравны. Installer report.json
passed=true: реальный runtimeответ Uno2026102605/Nucleo2026102604 былполучен,
SAFE/PWM0/ARM0/Vbus10,enc_reads5708/errors0,sourceNucleo,zero/historyvalid,
enc_fault_first_hex/pwm_hex '-',decodevalid1,statusожиданиепервогосбоя.
Сохранёнwatchdog7/fault2отпрошивки; CLEAR0/START0/прочихfirmwarewrites0.

Однако следующие GETпоUSBforward иWiFi зависли. Один restartownedHMI(UID/cwd/
Restartalways проверены,PID1059) выполнен безMCUreset; 3повторныхRPCGETtimeouts.
runtime_idle_r1/report.json failed, не стирали успешныйпервичныйinstallreport.
Manifest installed/readback/runtime_pair_verified=true, rpc_pending=true,
rpc_unstable_after_flash=true, idle_runtime_verified=false,
hardware_capture_validated=false. Не объявлять устойчивуюсвязь/новыйcapture
нажелезе подтверждёнными. installation_summary.jsonразделяетэтифакты.

Пользователю нужен толькоUSBUno coldstart5сек; Nucleo/AS5600/проводку/15В
не трогать, J1OFF. Повторногоinstaller/flashне делать. Послеответавосстановить
ADBforwards18080/12222, дождатьсязагрузкиLinux(ранние503нормальны), проверить
2605/2604/newcapturefields,развитиеreads/enc_errors/peerbad/zero/history/cal,
толькоread-only. Никакого моторногостарта/CLEAR безследующегосогласованного
poweredэтапа. Снимкиfirstboot/firstPWMпокаожидаютсобытия.

## 2026-10-26: пакет первого I2C-сбоя готов2605/2604, ещё НЕ записан

Пользователь поручил captureдоPEreset ипоискGitHub/StackOverflow/мануалы.
Проверены STES0431rev9 G431 (физическая ревизияX), STG4HALsource/G4examples,
StackOverflowCMSIS/F1lockup иlibopencm3issue1613. Конкретное несоответствие:
ES0431§2.11.2 требуетприspuriousmasterBERR очиститьфлаг/продолжить; наш
G431ec_poll безусловноaborts/resetBERR. Это гипотеза цепочки BERR→reset→BUSY,
а не установленная причина245ошибок. При16MHzI2CCLK/APB170ratio10.625 условия
erratumfirstbyte ratio1.5..3 не совпадают; permanentwrongGPIO не доказан.
F1/F4аналогfilterworkaround не переносили вслепую. research_sources.json сохранён.

Подготовлен artifacts/live_bench_20261026/i2c_first_fault_r1: Uno2605/Nucleo2604.
Обе сборки иLLEXT PASS, Nucleo0errors/0warnings. Fixed2x160байт slots:
first_since_boot иfirst_with_PWM (MOE), immutableдоresetMCU, CLEAR/STOPне стирают.
ec_io.fault callback вызывается до ec_finish измененияstate/счётчиков/PEreset.
Пишутся cause/stage/state/n,decisionISR,ISR/GPIO/ISRbracket,CR1/CR2/TIMINGR,
GPIOmode/otype/AF,RCCmux/CFGR,SystemCoreClock,TIM1BDTR/CNT/CR1/ARR/CCR1..3,
pollgap/maxgap,attemptage,errors/reads,previousISR/CR2/GPIO/cycles;
после reset отдельныеISR/CR1/CR2/GPIO/cycles. НикакихRXDRread/IRQmask/блокожиданий.
Текущая recovery/BERRpolicy намеренно сохранена, чтобы первым capture выявить
исходное событие. Это диагностический пакет, не объявлять BUSYисправленным.

Новая passive0xDBtelemetry:7pages24bytes,frameCRC32C+recordCRC32C160bytes,
peer4/format1/OFF/fresh gates, unknown/corrupt/mixed/paddingrejected. Отправка
только приMOEOFF черезсуществующуюTXочередь; Uno собирает2records, HMIdecode
enc_fault_records ивидимыйAS5600status показываетсохранённыйcause. Исправление
UARTrescued сохранено. КомандныйUART/MCU5sUno/ADC/PWM/SD/калибровка/пороги прежние.
Тестhookbeforestate/reset,2slots/freeze/CRC43positions/511legacychecks/realzero/
calibration/UI PASS. RAMgrowth352 вбюджете512; headroom3664сверхпрежних
heap/stack, capturestack24байт, ADCIRQ376 прежний. Негейтящий общийHVpreflight
по-прежнемунеимеетHILreleaseevidence; не объявлятьобщуюHVквалификациюпройденной.

Manifest sealed, installer verify-package-only PASS; flash0/START0/CLEAR0.
Текущийустановленныйпакет ещё2603/2602, последниеусловияpowerbanks/15V/J1ON,
послеодногопрогонаSAFE/PWM0/ARM0. Длязаписипользователюпередаётсяинструкция:
выключитьтолькоJ1, поDMM<20V обеUSBПКвместоповербанков;15Вможнооставить,
датчикPB8/PB9/TP23→1k→PA4/двигатель неотсоединять, Saleaeненужен.
После явногоподтверждения записать install_i2c_first_fault.py одинразсreadback
наобеихплатах/калибровкаpreserved. Никакой записи при текущемсиловомON.

## 2026-10-26: один powered5Гц прогон выполнен; UART clean, AS5600I2C BUSY при ШИМ

Пользователь подтвердил обе платы powerbank, PC/Saleae сняты,15В/J1 ON,
безRESET/START. ТолькоWiFi: пара2603/2602,323В,softstartready,SDHIGH/IRQready,
свободные snapshots, нулевые аварии/transport/CRC,zero/historyready,магнитvalid.
CLEAR не потребовался. До пуска сохранены logs/breaksnapshot/bkintrace.
Один START через run_as5600_bounded_5hz.py --uno-build2603 --sensor-modeNUCLEO,
runlimit5000мс. Новых CLEAR/flash0, повторного старта0. Итог SAFE/PWM0/ARM0,
MCfault/masks/transport0,SDHIGH. Независимый post-stop диагностики snapshot
иlogs сохранены в uart_rx_handoff_r1/powered_5hz_r1.

ВАЖНОЕ УТОЧНЕНИЕ к прежним ответам: TimedRun start/stop/run_reason илимит
5000мс реализованы в STM32U585 Uno (g_timed_run/control_step), НЕ в G431Nucleo.
Uno выдала STOP по своему таймеру ровно5000мс; Nucleo фактическийOFF подтверждён
свежей UART телеметрией. Точную длительность gate-PWM осциллографом не мерили.
Вложенный trial/report.json passed=false сохранён: первое SAFE/LIMIT5000
наблюдение имело bp_status0x61 (MOEoff,commandrequestbit5 ещёon), guardcompleted
его отверг, затем финальный иbackup STOP. Это host false-abort при нормальном
TimedRunLIMIT, а не авария привода. Позднее remoteOFF0x01 иARM0 подтверждены.
Дополнительно только1distinct5Hzcurrentwindow вместо2; не ослаблять эту проверку.

AS5600 приШИМ НЕ прошёл: ошибки0→245, активные снимки cause11=EC_BUSY,
stage4,ISR0x8001,timeout0, resets до245; GPIOSCL/SDA snapshots HIGH/HIGH,
configmatch1. Ни в одном активном статусе angle/speed не valid, enc_rpm0
НЕ означает неподвижныйвал. ПослеSTOP чтение/MDvalid/скоростьvalid восстановились,
счётчикошибок245 пересталрасти. EncoderUARTreject0→0/controlCRC0/SDtripнет.
Последнее RMSокно около[.430,.432,.425]А (номинальный datasheet scale).
Физическое вращение пользователем в новом прогоне ещё не подтверждено.

analysis.json отдельно фиксирует timer request proof/remoteOFF иI2Cfail;
manifest sensor_under_pwm_qualified=false. Причина первичного I2Cсбоя ещё не
установлена: текущая telemetry хранит последнее BUSY, GPIO не обязательно
в момент первичной помехи. Следующий полезный capture — первое событиедоPEreset
с ISR/CR1/CR2/одновременнымиGPIO/стадией/контекстомPWM иmainloopgap. Не объявлять
аппаратный дефект/помехи/исправленностьдатчика доказанными и не делать новыйпуск
без согласованного следующего шага. Питание и подключения оставлены какбыли.

## 2026-10-26: подготовлен AS5600/Nucleo 5Гц/5000мс, ожидается автономное питание

Пользователь попросил poweredAS5600 проверку5Гц с записью и автостопом5000мс,
спросил переключения перед пуском. Runner run_as5600_bounded_5hz.py расширен:
--uno-build2026102603 --sensor-modeNUCLEO жёстко выбирает mc2602/sourceNucleo/
mode6/configmatch/init0. Старые POLL/FILTER/SW режимы не применяются кNucleo.
16host тестов PASS (4новых+12старых). MCU5000мс, host watchdog ивсе drive/
SD/UART/zero/TTL/MCUcompletion условия сохранены. NoSTART/CLEAR/flash этого
этапа. Новые сенсорные ошибки только записываются, датчик неfeedback скаляра.
Последний watchdog7 после перезапускаUno остаётся известным сохранённым
событием; runner сам его НЕ стирает и с ним пуск блокирует. До пуска нужно
проверить свежее poweredсостояние, архивировать snapshots ипри необходимости
один штатный CLEAR только известного остаточного watchdog, затем повторно
проверить SD HIGH/IRQ/masks/zero/связь. Новую/активную защиту не обходить.

Пользователю далее инструкция: обе платы наповербанки, всеUSBПК иSaleae
включаяGND сняты; затем15ВJ4 иJ1черезsoftstart, закрытыйстенд. AS5600/
магнит/проводку не трогать; RESET/Пуск не нажимать. Ожидается новое явное
подтверждение этого состояния; до него моторные команды не отправлять.
powered_5hz_preparation.json сохранён, повторная прошивка не нужна.

## 2026-10-26: Uno2603/Nucleo2602 — RX исправление подтверждено без силового

После подтверждённого userUSBUno coldstart Linux сначала ещё грузился:
ADB появился, ранние GET503, затем RPC восстановилась сама. Перепрошивок/
RESET/START/CLEAR в этом этапе0; J1/15В OFF, обе платы наUSBПК.
Текущая пара2026102603/2026102602, sourceNucleoI2C1/mode6, SAFE/PWM0/ARM0,
Vbus10В, AS5600MD1/ML0/MH0, angle/speed valid, I2Cerrors0, zero/historyready,
калибровкаvalid. Nucleo сохранила один watchdog от перезапускаUno: transport7,
fault2,last_bad13,bad_cnt1, integrity/sequence0, hardware masks0; НЕ очищали.

Поэтому обычный strict idle preflight report false (сохранён): он требует
нулевую аварию для будущего пуска. Это не CRC-дефект и не повод скрывать latch.
Отдельный read-only telemetry stress проверяет именно UART при сохранении
строго известного reset-watchdog и всех lowbus/OFF/zero/CRC/freshness условий.
Минутный тест с3 параллельными web/status клиентами поWiFi PASS:
12302 новых чтения AS5600,3068 принятых encoder-пакетов,0 новых rejected/CRC,
0 I2Cerrors/overflow/hwerrors/shortwrites/weberrors. maxGET2.391сек;
uno_rx_rescued вырос2→4: два реально поздних байта возвращены из base-ring,
вместо потери. На позднем progress снимке rescuedtotal6, enc_peer_bad0.
Это подтверждает работу исправления на железе именно при выключенном ШИМ.

Пакет uart_rx_handoff_r1/runtime_completion.json и runtime_telemetry_r2/report.json
содержат доказательства; исходные false installer/boot/strict idle отчёты не
стирали. Manifest runtime_pair_verified=true/rpc_pending=false;
idle_uart_telemetry_verified=true, но motor_start_qualified=false и
sensor_under_pwm_qualified=false. Не объявлять датчик проверенным при вращении.
Платы/проводка остаются как есть. Для следующего согласованного powered5Hz
испытания runner должен принять2603/2602/sourceNucleo/mode6; старый5Hzrunner
ещё только2516/17/18. Никакой новый пуск этим тестом не разрешался.

## 2026-10-26: UART RX handoff исправлен, Uno2603 записана и сверена; RPC pending

По прямому поручению пользователя исправление подготовлено в отдельном малом
пакете artifacts/live_bench_20261026/uart_rx_handoff_r1: только UNOQ_MOTOR/HMI,
без копии дерева Nucleo. Nucleo2026102602 и подключение датчика PB8/PB9 прежние.
Адаптер после vendor IRQ забирает поздние байты из base-RX ring в основную
bounded очередь, сохраняя порядок; saturation/drop/CRC остаются прежними.
Добавлен read-only счётчик uno_rx_rescued. Других consumers base RX в коде нет.
Новый UnoFW2026102603. Host тест настоящего заголовка прошёл все43 позиции
позднего байта, rescued==1, overflow сохраняется. 511 driver/wire checks,
recorded ADC/zero/calibration/STOP/UI guards PASS; пороги и моторный код прежние.
Target build/LLEXT PASS, image SHA256
332ae5f3f1e271cb7421c9bb17d7ae7884de60ea175b27930759cc2605517349.

На подтверждённом J1/15ВOFF/DMM<20В/USBПК выполнен один Uno flash плюс
независимый readback verify; Nucleo flash0, START0/CLEAR0. HMI whitelist
дополнен2603/2602, калибровка before/after SHA равны. Installer report false
только из-за Runtime verification pending/timed out после записи.
Вызван один restart только принадлежащего пользователю HMI процесса (UID/cwd/
Restart=always проверены). Не повторять прошивку для восстановления RPC.
Нужно проверить результат post_hmi_restart.json; при RPC timeout нужен только
USBUno coldstart5сек, Nucleo/проводку/J1/15В не менять. После coldstart проверить
2603/2602 и запустить check_nucleo_as5600_idle.py --uno-build2026102603 --seconds60
с новым outdir: enc_peer_bad НЕ растёт, I2Cerrors0, rescued виден в HMI.
Наличие исправления на железе подтверждено readback, устранение реальной потери
байтов ещё НЕ подтверждено. Никакого powered run в этом этапе не было.

## 2026-10-26: RPC восстановлена; 2601/2602 подтверждены, idle-тест выявил потерю байтов телеметрии

После подтверждённого USB cold-start Uno связь восстановлена. Реальный Wi-Fi
статус: Uno2026102601/Nucleo2026102602, source=nucleo_g431_i2c1, mode6.
J1/15В OFF, обе платы USB ПК; новых START/CLEAR/flash/reset не выполняли.
SAFE/PWM0/ARM0, Vbus10В; SD HIGH, активных аварий0, автоноль и история готовы,
калибровка valid. На позднем снимке 88079 чтений AS5600, I2C errors0,
MD1/ML0/MH0, угол valid. Это НЕ квалификация датчика при ШИМ.

Read-only stress с двумя параллельными web-клиентами НЕ пройден:
enc_peer_bad 10→11, позднее23. Во время stress успешных I2C чтений+5287,
ошибок I2C0; control UARTbad/drop/hwerrors0. У отклонённых DA-пакетов CRC
неверен; один потерянный байт и начало следующего пакета согласуются с записью.
Не объявлять всю связь стабильной и не ослаблять критерии ради PASS.

В установленном nucleo_buffered_serial.h свой receive_irq сначала читает FIFO
в queue, затем вызывает vendor ZephyrSerial::IrqHandler(), который снова читает
FIFO, но в отдельный base.rx.ringbuf. Этот base ring наш parser не читает:
поздний байт может потеряться без queue.dropped и hardware error. На настоящем
заголовке адаптера с mock vendor RX воспроизведена потеря для всех43 позиций
пакета. Кандидат переносит base-RX suffix после vendor IRQ в основную очередь:
43/43 CRC-valid; overflow/drop guard сохранён. Это host-модель, не доказательство
причины каждого реального CRC. Кандидат только в rx_handoff_audit_r1, НЕ записан,
target build ещё не проверен. Sealed установленный пакет не меняли.

Сохранены runtime_idle_r1/report.json (исходный failed stress), status_after.json,
completion_report.json, rx_handoff_audit_r1/report.json. Manifest обновлён:
runtime_pair_verified=true, rpc_pending=false, idle_runtime_verified=false.
Первичный installation_r1/report.json с RPC-timeout сохранён как история;
installer повторно НЕ запускать. Следующий шаг — подготовка/target-проверка RX
исправления без силового; пользователь пока оставляет подключения и питание
как есть. Новый моторный пуск не выполнялся.

## 2026-10-26: перенос AS5600 на Nucleo записан; RPC Uno ожидает USB cold-start

Пользователь явно подтвердил J1/15В OFF, DMM<20В, обеUSBPC; AS5600 уже
перенесён SCLPB8/SDAPB9/VCC3V3/GNDNucleo. Подготовлен один новый пакет
artifacts/live_bench_20261026/nucleo_as5600_r1, Uno2601/Nucleo2602. Старые
SDKдеревья для экономии места hardlink только read-only; патчи в Src/Inc.
NucleoI2C1 неблокирующий mainloop state machine, период5мс/deadline3мс
поDWTлибоHALtick, ошибки/backoff20мс, HSI16 timing0x30521317 ANF/DNF2.
Не использует DMA/IRQ каналы, PWM/ADC/SD/командныйUART ипороги прежние.
Новая telemetryframe0xDA каждые20мс при свободнойTXочереди. UnoI2Cworker
отключён, получает статус/угол/скорость/ошибки отNucleo, TTL100мс; source
nucleo_g431_i2c1, diag_mode6. СтарыеwhitelistыHMI дополнены, калибровка
совместима. 511модельных проверок, CRC/возраст/некорректныеflags/unknownpeer,
реальныеADC/zero_history/peak/manual/MCU5секcompletion иUItests PASS.
ADCIRQstack376байт прежний. RAM static+80байт вявном бюджете128; свободно
4016байт сверх прежнихreservedheap/stack, исходныйпроектимелровно4096.
Пороги защит/zero/RMS не менялись. Обе сборки0errors/0warnings, LLEXT PASS.

Optionbytes прочитаны HOTPLUG: nSWBOOT0=0/nBOOT0=1, PB8pullup не меняет
BOOT0; optionbytes НЕ изменяли. Один вызовinstall_nucleo_as5600.py выполнил
ровно1Nucleo flash+verify и1Uno flash+independentreadback. КалSHAсохранён.
installation_r1/report.json passed=false ТОЛЬКО runtime pending/timedout;
повторноinstaller НЕ вызывать. Manifest installed/readback=true,
runtime_pair_verified=false/rpc_pending=true. Один ownedHMIrestart выполнен
по проверкеUID/cwd/serverhash/Restart=always; не помог. Rootrouter/reboot
не пытались обходить. Пользователю передан asyncзапрос: толькоUSBUno вынуть
на5сек/вернуть, Nucleo/датчик/проводку не трогать, J1/15Вoff. Ответожидается.

При этом прямойread RAM Nucleo безRESET уже подтвердил encoderstate:
address0x200068b0, reads37021/errors0, timeouts/resets0, raw3746,
status103=MD1/ML0/MH0, configured/bus/angle/speed1, transaction692мкс.
Сыройstate.bin иI2C1registers.log сохранены. Это idleуспех, не проверка
подШИМ. Новых motorSTART/CLEAR во всём этапе0. ПослеUSBответа восстановить
ADBforward18080/12222, проверить2601/2602/sourceNucleo, UART/ADCzeroисторию,
непрерывность чтений датчика иHMI, обновитьruntime metadata. Не прошивать
повторно для устранения RPC. Все будущие runner должны учитывать новуюпару
иsource/mode6; прежний5Hzrunner пока принимает только2516/17/18.

## 2026-10-26: обсуждён перенос AS5600 с Uno Q на Nucleo

Пользователь предложил перенос «как раньше». Проверены текущий2510код и
официальные UM2505/UM3030/IHM09M2schematic. Целевой I2C1 PB8SCL(CN10-3,
CN5-10/D15) иPB9SDA(CN10-5,CN5-9/D14), VCCNucleo3V3CN6-4, GNDCN6-6.
PB8/9 не используются просмотренными GPIOветками текущего проекта, на
IHM09M2не назначены силовым сигналам. PB8 такжеBOOT0: перед развёртыванием
проверить optionбайты, не менять вслепую. В2510 HAL_I2Cотключён, опросAS5600
не найден; старый драйвер в BluePillF103проекте не является готовымG431кодом.
Нужен неблокирующий драйверNucleo/телеметрия и переключение источника вUno/HMI.
План сохранён в nucleo_sensor_transfer_plan.json. Firmware НЕ реализована,
не собрана/не записана, аппаратных команд0. Датчик физически ещё наUno,
режимSW25; шина оставалась под силовым, пользователь предупреждён ничего
не переподключать. Не считать перенос или устранение ошибок выполненными.

## 2026-10-26: пользователь сообщил питание/землю/подтяжки исправными

На предложение их проверки ответил «это всё ок». Принято как сообщение
пользователя; повторные физические измерения не запрашивались. Без аппаратных
команд проверены2518sketch, worker, SWreader и ArduinoZephyr0.90.0overlay:
явного второго владельца PB10/PB11 в проверенных ветках не найдено; UART
PB6/7, matrixGPIOF, localPWManalogWrite ветка при externalPWM обходится.
Вoverlay есть потенциальное совместное назначениеtimer2PB10/11, но вSW25
записанная конфигурация неизменна, переключенияmux не доказано. Совпадение
8битGPIOecho не квалифицирует START/длительностиSCL/ACK у самого датчика.
Отдельный software_ownership_audit.json содержит выводы и ограничения.
Следующий полезный программный шаг — временная запись START/переходовSCL/
SDA/ACK одной ошибочной SWтранзакции и сравнение с idle. Такой захват ещё
не реализован; новых прошивок/START/CLEAR в этом этапе0. Модуль неисправным
не объявлять, физическую причину либо чисто программную ошибку не считать
доказанными. Текущий установленный режим остаётся SW25(mode2),2518/2510.

## 2026-10-26: SW25 проверен; GPIO подтверждает NACK при ШИМ

Пользователь разрешил предложенный SW25. Hostrunner расширен на mode2:
обязательны PE0/I2C2released, PB10/11 GPIOoutputs+open-drain (cfg&0x3f=0x35),
cfgmatch1, priority4/init0; все drive/zero/SD/UART/MCU5сек проверки прежние.
12hostтестов PASS. Переключён один ENC BUS SW25 при readyOFF, без CLEAR/
RESET/flash. Idle прошёл: mode2, CR10, cfg1114485match, tx/echo0x6d/8бит,
магнитstatus39valid, новых ошибок0. sw25_preflight_r1/report.json сохранён.

Один START5Гц/5000мс выполнен в sw25_powered_5hz_r1: MCUrun6,
start3403403/stop3408403/elapsed5000/reason1. Host backup не сработал,
OFF/ARM0/masks/fault/UART0 подтверждены. Report passed=false сохранён из-за
только1distinct5Hzокна вместо2; MCUcompletion отдельно true.
AS5600 ошибок130→180 (+50). Во всех3активных hostснимках cause2NACK/stage4
ADDRESS_WRITE, tx_byte=tx_echo=108(0x6c), tx_bits8, CR1PE0, GPIOcfgmatch1.
Успешные чтения между этими снимками НЕ росли (1270019). Значит, NACK
наблюдается и в GPIOsoftwareобмене, не только как ARLO/BERR аппаратного I2C.
Это не доказывает дефект модуля или конкретную помеху/провал питания.
Poll-NACK/BERR/reset counters иfirsteventring вmode2 не обновляются: нельзя
их нулевой delta выдавать за отсутствие SW25NACK; категории известны только
из sampledsoftwarediag. Скорость nominalSW25, реальнаяidletransaction~3,1мс.

После STOP обмен восстановился, магнитstatus39/angle_ok1. Первый ответ после
STOP содержал raw3704/325,5°, speed_ok1/rpm−68,5; позже raw3503/307,9°/
rpm0. Это данные после выключения ШИМ, а не скорость во время пуска.
Assessment/logs/SD/UART/recovery сохранены. Режим оставлен SW25(mode2).
Следующие проверки — питание3,3В непосредственно на модуле, земля/подтяжки/
качествоSDA/SCL; физический источник пока не установлен. ОбычныйSaleae
к включённому HVстенду не подключать. Новых START/CLEAR не выполнять.

## 2026-10-26: магнит в покое нормальный; запрошенный тест5Гц снова сорвал I2C

Пользователь спросил поле: три свежих чтения status39(0x27), MD1/ML0/MH0,
enc_ok/speed_ok1, новых IOошибок0. Шина324–326В, PWMoff; предупреждён
не касаться датчика/проводки. Затем явно попросил скалярный медленный пуск
с чтением датчика, вращать рукой не будет. Выполнен один START POLL1005Гц,
CLEAR0/flash0, архив poll100_aligned_magnet_5hz_r1. Предпусковой angle~11,5°,
статус39валиден. MCUrun5/start2755289/stop2760289/elapsed5000/reason1,
host backup не сработал, SAFE/PWM0/ARM0, faults/UART0 после STOP.

AS5600 новых ошибок43: NACK22/ARLO7/BUSY12/deadline2, отдельно advisoryBERR14,
controllerReset14. Все3активные hostвыборки enc_bus_ok0/enc_io_error-5,
enc_ok/speed_ok0, raw0 недостоверен. Успешные чтения тоже были между
выборками — не утверждать, что каждая транзакция провалилась. После STOP
сначала status55weakfield/raw347invalid, затем status39/raw92(8,1°)valid.
Магнит в одном положении в норме, полный оборот магнитно не квалифицирован.
По moduloуглам до/после нельзя вывести число оборотов; подтверждения
вращения по датчику нет. Физический вопрос повторно не задавался по просьбе
смотреть датчик. report passed=false оставлен из-за1distinct5Hzокна вместо2;
MCUcompletion отдельно true. Последний активный RMS~0,435/0,440/0,432А,
покрытие99%, номинальная шкала. Логи/SD/UART/assessment.json сохранены.
Новых START/CLEAR автоматически не делать. Возможный следующий разделительный
опыт — программный SW25 в том же установленном образе; ещё не выполнен.

## 2026-10-26: пользователь подтвердил неподвижный тихий вал в последнем пуске

На вопрос о poll100_powered_with_j4_r2 пользователь прямо ответил «вал не
вращался», затем «Оставался тихим». report.json обновлён: rotation=false,
наблюдение явно записано. Нельзя считать ни RUN, ни RMS~0,44А доказательством
физического вращения. AS5600 автоматически записывался, но при этом пуске
44новые I2Cошибки, enc_ok/speed_ok0, MD+MLweakfield; нули в ошибочных
транзакциях не являются углом0. В покое сейчас успешный raw210/status55,
по-прежнему angle/speed invalid. Пользователь просит смотреть по датчику;
объяснено, что его невалидные данные не подтверждают остановку/скорость.

Без новых START/CLEAR проверен исходник установленного Nucleo2510:
acim_vf_parameters.h VOLTAGE_OFFSET20, MIN_FREQUENCY_TH10; C1 envelope
задаёт20В phase-peak на5Гц. Это расчёт кода, реальное фазное напряжение не
измерялось. Запускать повышенную частоту или увеличивать boost вслепую нельзя.
Связь/маски/SD исправны после STOP; новые аппаратные команды не отправлялись.

## 2026-10-26: по просьбе пользователя повторён реальный POLL100пуск5000мс

На ответ «повтори ещё раз» выполнен один START5Гц/5000мс, CLEAR0/flash0,
в poll100_powered_with_j4_r2. Preflight ready, mode4, run_id3→4.
MCUstart2082852/stop2087852/elapsed5000/reason1, host backup не сработал.
После STOP SAFE/PWM0/ARM0, faults/masks/transport0, Vbus323В. Последний
RMS номинально0,413/0,425/0,463А. Получено только одно distinct5Hzокно;
original runner passed=false (нехватка выборки) сохранён, completion отдельно
помечен подтверждённым. AS5600 новых ошибок44: NACK16/ARLO10/BUSY15/deadline3,
отдельно BERR-advisory9/reset20. MD+ML, angle/speed invalid. ДиагностикаSD/
UART/логи сохранены. Физическое вращение пользователь ещё не подтвердил;
ответ на предыдущий вопрос был просьбой повтора, а не подтверждением.
Дальнейших START/CLEAR автоматически не делать.

## 2026-10-26: пользователь обнаружил забытые15В; реальный POLL100пуск5000мс

Пользователь сообщил «а точно я забыл15в», затем «теперь готово». Это объясняет
предыдущий малый ток; сравнение0ошибок в POLL100 безJ4 с FILTER100 при J4ON
не является подтверждением программного исправления. После подачи15В
fault5/reason8/occurred0x400 при current0,SD HIGH/BIE0; UART/zero исправны.
Снимки сохранены. Один штатный CLEAR восстановил masks/fault/transport0,
BIE1; восемь ready ответов. Выполнен один START POLL1005Гц с неизменным
MCUlimit5000, без прошивок/RESET/смены подключений. Пользователь только что
подтвердил подачу15В, платы/J1 оставались в прежнем автономном состоянии.

Архив as5600_followup_r1/poll100_powered_with_j4_r1: run_id3,
start1795738/stop1800738/elapsed5000/reason1, MCUautoSTOP подтверждён,
host backup не сработал. SAFE/PWM0/ARM0/ESTOP0, masks/fault/UART0.
Номинальный RMS при5Гц~0,438/0,443/0,436А, последний доставленный после
STOP~0,434/0,445/0,441А. Исходный runner report passed=false СОХРАНЁН:
получено только одно distinct5Hzокно вместо двух, это ограничение выборки
RMS, не доказанная авария привода или сбой автостопа. Completion отдельно
помечен mcu_timed_trial_completed=true, current_full_window_qualification=false.

AS5600 ошибок43: NACK22/ARLO5/BUSY14/deadline2; отдельно BERR-advisory11,
controllerReset18/cleanup25/postResetBusy0. Первые4 события ISR/CR2/GPIO
сохранены; после STOP2635чтений/0новых ошибок. Режимы FILTER100 иPOLL100
при реальной коммутации оба дают ошибки; источник электрически не доказан,
одними таймингами проблему не устранили. MD+ML слабое поле сохраняется,
angle/speed invalid. Защиты не менялись, новые CLEAR/START не отправлять
автоматически. Вопрос о ровном физическом вращении передан, ответа пока нет;
не ставить rotation_verified до ответа. Данные в comparison.json.

## 2026-10-26: разрешённый повтор POLL100;0 ошибок, вращение не подтверждено

Пользователь явно разрешил один полный5сек повтор без CLEAR. Выполнен один
START, CLEAR0/flash0, в poll100_powered_5hz_r2. Предварительное состояние
полностью ready, mode4, run_id1. Новый run_id2/start1275788/stop1280744,
elapsed4956/reason2: резервный host STOP сработал от HTTP-запроса раньше
MCUlimit5000 на44мс. START HTTP занял6,877с, первый activesample пришёл
через7,5с от запроса при MCUelapsed1258. Полный MCUautoSTOP НЕ подтверждён;
runner report passed=false сохранён, не превращать его в PASS.
BackupSTOP HTTP500, затем normal finalSTOP HTTP200 и SAFE/PWM0/ARM0 подтверждены.

AS5600 ошибок0 за наблюдавшийся ШИМ, NACK/ARLO/BUSY/BERR/deadline/reset0.
Но пользователь ответил «Не вращался или не успел заметить»: вращение не
подтверждено. enc_raw1058 на всех активных выборках, MD+ML слабое поле,
angle/speed invalid. RMS номинально~0,06А, тогда как в предыдущем подтверждённом
FILTER100вращении~0,43А. Поэтому48→0ошибок НЕ доказывает устранение I2C
сбоев при равных условиях вращения/нагрузки. В comparison.json записаны
ограничения, данные/SD/UART/логи сохранены. После STOP2561успешное чтение,
новых ошибок0, faults/masks/transport0; SD HIGH. Питание оставлено как было.

Host tools/run_as5600_bounded_5hz.py исправлен без изменения прошивок:
requestdeadline10с; при первом проверенном новом MCUrun один раз привязывает
backupdeadline к remaining MCU5000мс+1сек, absolute16с. Повторные/замороженные
статусы deadline не продлевают. MCU RUNLIMIT5сек/все аппаратные защиты прежние.
RunWatchdog использует condition/уведомление/cancel для независимого STOP.
5watchdogтестов (включая replay этой задержки) и4start-transitionтеста PASS.
Исправление hostwatchdog на железе ещё НЕ проверялось. Дополнительных пусков
или CLEAR не выполняли и повтор автоматически не планировать.

## 2026-10-26: один CLEAR, POLL100; короткий пуск остановлен ошибкой host-проверки

На «делай» выполнен один штатный CLEAR после сохранения SD/UART. Все faults/
masks/transport/badcnt обнулились, SD HIGH/BIE1, восемь ready ответов. Uno
переключена ENC BUS POLL100 (mode4), опрос в покое исправен; перепрошивок0.
Один START5Гц/MCUlimit5000 отправлен. Host увидел localPWM1/run_elapsed12мс
при peer bp_status1 (ещё OFF) и ошибочно применил steady-RUN predicate.
Сработал обычный STOP: elapsed1865/reason2, SAFE/PWM0/ARM0 подтверждены.
Аварий привода/SD/UART нет, AS5600 ошибок0; START response в631мс уже
показывал bp_status99 (remote RUN). Это НЕ полный5сек тест и НЕ доказанный
успех AS5600 при длительном ШИМ. Архив poll100_powered_5hz_r1/test_incomplete.

tools/run_as5600_bounded_5hz.py исправлен на host: до300мс нового MCUrun
при peer статусе строго1 разрешён начальный переход localSTART→remoteRUN,
все проверки voltage/temp/fault/UART/zero/SD/BIE/epoch сохранены. После первого
remoteRUN переход больше не разрешается. Положительный replay реальных12мс
и отрицательные варианты (fault/SD/UART/stale/runid/deadline/etc) прошли4теста
tests/test_as5600_bounded_start_transition.py. Firmware/пороги не менялись.
Пользователю задан вопрос о ровно одном полном повторе5Гц/5сек без CLEAR и
без смены питания. Ответ пока ожидается: автоматически повторно не запускать.

## 2026-10-26: повторное включение, только чтение; до Пуска защёлкнут UART reject

Пользователь сообщил включение, затем явно подтвердил повербанки/15В/J1 ON.
Первый статус0В сменился322–325В после заряда; НЕ утверждать, что J1 не включён.
2518/2510 SAFE/PWM0/ARM0/run_id0; автоноль готов, AS5600 FILTER100 в покое
без ошибок. При включении сохранены SDtick116386 (MOEoff/outsideSTART,
PA6 LOW2,0мкс и1,2мкс; TP23 LOW1,8/1,0/0,8мкс) и UARTtick116387:
неполный кандидат aa55030000,5байт, reason4, uart_flags8, last_seq106.
CRC полного пакета недоступен: не выдавать это за доказанную CRC-ошибку.
SD сейчас HIGH, но BIE0, transport4/fault3; MCSDKмаски4/4 (ранееUV).
bad_cnt31 стабилен на повторных чтениях, новых ошибок AS5600 нет.
Весь этап ТОЛЬКО чтение: CLEAR0/START0/flash0/mode changes0. Снимки в
artifacts/live_bench_20261026/as5600_followup_r1. Причина физически не установлена;
совпадение событий на1мс по MCU не является осциллограммой. Для следующего
пуска сначала нужен штатный CLEAR с проверкой полного восстановления защит/
UART и сохранением записей; не запускать при текущем transport4/BIE0.

## 2026-10-25:2518 силовой тест выполнен; привод PASS, AS5600 при ШИМ FAIL

Пользователь подтвердил обе платы на повербанках, USB ПК/Saleae отключены,
15 В/J1 через soft-start включены; разрешил один CLEAR и один пуск5Гц/5сек.
Выполнены ровно один штатный CLEAR и один START, без записи прошивок/RESET.
2518/2510, шина322–323В, автоноль/UART исправны. До CLEAR сохранён SD:
PA6 LOW61,6мкс/TP23 LOW61,4мкс, tick16136, MOEoff, вне START, run_id0;
cached context отсутствовал (context_valid0), его значения не выдумывались.
Для этого точного события использована привязка по raw/event/хешу waveform,
при неизменных активных проверках. После CLEAR первый ответ ещё содержал
старые fault5 при masks0/0; следующий свежий ответ fault0. Повторного CLEAR
не было; восемь свежих ready-статусов подтвердили SD HIGH/BIE1 и защиты.
Снимок сохранён, слот первой waveform занят; второй полный импульс этим
слотом уже не записать, но аппаратный Break остаётся включённым.

Архив as5600_recovery_r1/powered_5hz_r1: MCUstart253273/stop258273,
elapsed5000/reason1. Один START, два различных валидных окна5Гц, покрытие
100%, RMS по номинальному масштабу около0,43А. Пользователь подтвердил
ровное физическое вращение до автостопа. SAFE/PWM0/ARM0/ESTOP0, faults/masks/
transport0 подтверждены. START HTTP занял5,277с; резервный host STOP также
отправился через10с от HTTP-запроса, первый ответ с MCUcompletion пришёл
через10,344с. Длительность подтверждена локальной записью MCU, а не вебом
или осциллограммой фронтов. Нельзя утверждать, что host backup не сработал.

AS5600: ошибок0→48: NACK23, ARLO21, BUSY3, deadline1. Отдельно14 событий
одиночного BERR обработаны без немедленного abort; это не ещё14 ошибок.
Controller resets4, graceful cleanup44, post-reset BUSY0; GPIOcfg неизменна.
Первые4 события — ARLO в ADDRESS_WRITE/ADDRESS_READ, первое через47мс после
MCU START; rawISR0x201, линии в момент снимка HIGH. Это не доказательство
отсутствия электрических импульсов. После STOP за10с4071 успешное чтение,
0 новых ошибок. В2517 было45ошибок/45reset; теперь48ошибок/4reset: обработка
восстановления уменьшила reset, устойчивость связи при ШИМ НЕ доказана.
Слабое магнитное поле MD+ML сохраняется, angle/speed invalid, FOC не готов.
report.json явно разделяет drive_pass=true и sensor_bus_pass=false.
Питание осталось включённым по указанию пользователя, ШИМ выключен. Новые
пуски/CLEAR не выполнять автоматически; следующий отдельный опыт — сравнить
POLL100/FILTER100 в том же образе либо получить электрические измерения.

## 2026-10-25:2518 установлена, FILTER100 idle PASS; ожидается автономный силовой тест

Пользователь подтвердил J1OFF/DMM<20В/UnoUSBPC, NucleoPB/15Вunchanged.
install_as5600_recovery installation_r1 PASS: ровно1Uno flash+readback PASSED,
Nucleo writes0, calSHA до/после одинаковая. В этот раз RPC восстановилась
автоматически: НЕ просили холодный USBrestart, не выполняли HMIrestart/MCUreset.
Реально2518/2510, defaultFILTER100mode5/init0, kernel160000000Гц,
TIMINGR0xF0E23131,CR10x0F01=PE1/ANFON/DNF15, GPIOcfgmatch1.
Это реальные прочитанные настройки, не электрическое измерение частотыSCL.

idle_filtered_web_stress_r1 PASS:22005успешных чтений без новых ошибок,
тайм-аутов/NACK/BERR/ARLO/BUSY/reset, включая3параллельных клиента полного
веб-статуса. MaxHTTP2,219с, maxprotected-transfer626мкс. Автоноль по
полной истории готов, SD HIGH/configOK/BIE1/captureRUNNING/слот свободен.
После записи остаётся ожидаемая latch2/transport7/reason13/last_bad13,
masks0/0/ESTOP0 —CLEAR не делали. Истории/ADCpeak UI2518 декодируются,
активного старого HMIoverlay нет: новыйserver уже включает whitelistфиксы.
Manifest installed/readback/runtime=true, idleverified=true, PWMproven=false.

После готового пакета, установки и idleпроверки пользователю через async
передана конкретная подготовка: обе платы на повербанки, USBПК/Saleaeснять,
15Воставить,J1soft-startON,безSTART/RESET; после подтверждения —один
штатный CLEAR остаточного тайм-аута и один5Гц/5сек START с записью. Ответа
на эту последнюю подготовку пока нет. До него не запускать двигатель.
Для прогона использовать tools/run_as5600_bounded_5hz.py
--uno-build2026102518 --sensor-modeFILTER100, свежий каталогpowered_5hz_r1.
Проверить firstevents/counts/errorISR/CR2/lines, а не толькоenc_errors:
одиночный BERR теперь advisory по errata. Нельзя объявлять отсутствие
IOошибок доказательством отсутствия всех импульсов или валидностиугла.
Датчик всё ещё сигнализирует слабое магнитное поле, angle/speed invalid.

## 2026-10-25: подготовлено errata-aware исправление2518; запись начата после подтверждения

Пользователь попросил устранить NACK/BERR/ARLO при ШИМ, питание сначала
оставлял как есть. Без новых пусков изучены ES0499 Rev12/June2026 §2.20.2
для именно STM32U585 revU0x3007 и AS5600. Подтверждён программный дефект:
2517 немедленно abort/PEreset при одиночном BERR. ST требует только
clear BERR и продолжение controller-transfer; такой abort способен породить
вторичный BUSY, но его доля в нашем силовом сбое ещё не доказана.

as5600_recovery_r1 Uno2518/Nucleo2510 собран/LLEXT PASS,185host-тестов:
одиночный BERR очищается/считается и полный кадр продолжается; NACK/ARLO/OVR/
deadline остаются ошибками, данные отбрасываются. После NACK даётся до120мкс
на аппаратный STOP внутри3мс общего бюджета; после ARLO не генерируется STOP,
только ожидание освобождения до120мкс, затем при необходимости PEreset.
PEreset с readback и2мкс задержкой; нет внешних bus-clear clocks или retry
того же отсчёта. Режим4 POLL100 сохраняется для сравнения; default5 FILTER100
добавляет ANF/DNF с пересчитанным conservative standard timing. Mux должен
быть PCLK, kernel rate реально считывается20..160МГц; неподдерживаемая
конфигурация делает сенсор init-invalid, не меняет общий RCC/мотор.

Добавлены счётчики BERR advisory/ARLO/BUSY/cleanup/resetBUSY, CR1/TIMINGR/
kernelHz и первые4события ISR/CR2/линиями ДО cleanup/ISRпосле. BERR-only
с завершённым кадром отдельно помечен mode|256, не выдаётся за NACK-error.
ТаймерMCU5с/моторный код/UART/ADC/SD/пороги/магнитная валидность прежние.
Worker stack увеличен2048→4096 для расширенных диагностических структур.
Сигнальные rise/fall не измерены; предполагаются standard≤1000/300нс.
Физическая причина и устранение всех исходных NACK при ШИМ НЕ доказаны.

Образ SHA b79b4ca221d1c7b254e29a94e6a6466d8db30674013efbfd24c33d203850a241.
После готового пакета пользователь явно подтвердил J1OFF/DMM<20В/UnoUSBPC,
NucleoPB/15Вunchanged. ADBdevice3880458060 и исходные2517/2510
SAFE/PWM0/Vbus10В/fault0/transport0 реально подтверждены. Один вызов
tools/install_as5600_recovery.py начат, installation_r1; не вызывать повторно
для исправления одного runtime timeout. Проверить его результат/verify_uno.log,
затем только реальные2518/mode5/kernel/filter/idle stress. Новых моторных
START/CLEAR в этом этапе0. Силового теста2518 ещё не было.

## 2026-10-25: один силовой5Гц/5000мс прогон2517; AS5600 при ШИМ ошибается

Пользователь явно подтвердил повербанки, отсутствие USBПК/Saleae,15В/J1через
soft-start ON и разрешил один штатный CLEAR+один5Гц START. Начальный503
сменился нормальной загрузкой самостоятельно, без переключений/RESET/Flash.
2517/2510,322В,49°C,SD HIGH/BIE1/free, автоноль иUART исправны, исходные
fault/transport уже0 после автономной загрузки. По явному запросу выполнен
ОДИН обычный CLEAR даже при чистом исходном состоянии; затем8readyстатусов.
Архив powered_5hz_preflight_r1 содержит до/после и исходные свободные SDслоты.

tools/run_as5600_bounded_5hz.py --uno-build2026102517 выполнен ОДИН раз,
powered_5hz_r1/report.json drive PASS: один START, MCUlimit5000мс,
run_id1/start88623/stop93623/elapsed5000/reason1. Host backup STOP не сработал;
SAFE/PWM0/ARM0 подтверждены, ESTOP0, fault/transport0, MCSDKmasks0/0.
Достигнут референс5Гц,2различных валидных окна, RMS по номинальному масштабу
около0,424–0,432А, покрытие100%. Это не независимая калибровка ампер или
измерение ротора. Пользователь после завершения явно подтвердил: двигатель
физически вращался ровно до автостопа; report/cause_assessment обновлены,
новых моторных команд не отправляли. Запись контроллера подтверждает5000мс между
локальными командами Uno, а не осциллографически точные фронты IGBT.

AS5600 bus FAIL: до пуска errors0, после45; NACKF10, тайм-аут1. В5активных
снимках и start-response зафиксированы причины NACK2/BERR8/ARLO9/BUSY11.
ADDRESS_WRITE NACK ISR0x8011 (81/87мкс), ADDRESS_READ BERR0x8101 (199мкс),
STOP ARLO0x8201 (494мкс), BUSY0x8001 между транзакциями (2–3мкс), при BUSY
оба GPIO после PEreset наблюдались HIGH. Нельзя объявлять BUSY доказанным
внешним удержанием провода, а аппаратный NACK —доказательством брака датчика.
Cfgдо/после совпадают, максимум участка3003мкс на одном реальном deadline.
Точных суммарных BERR/ARLO/BUSY счётчиков нет, остаток45 не распределять
произвольно. Дельта reads от preflight включает подготовку при PWM0, поэтому
не выдавать её за число успешных чтений исключительно при ШИМ.

После STOP8снимков:3615успешных чтений, новых ошибок0; lifetime45,
шина322В,49°C, SD HIGH/BIE1/captureRUNNING/слот свободен. Нового SD/Break
при этом пуске не зарегистрировано. Магнитный статус0x37=MD+ML, угол/скорость
невалидны, AS5600 не участвует в скалярной обратной связи. Сохранены
after_bkin_trace/after_break_snapshot/logs/post_stop_recovery/cause_assessment.
Это отделяет исправленный idle/web scheduling от сохраняющегося сбоя
при ШИМ; физический источник и влияние алгоритма PEreset пока не доказаны.
Никаких повторных START/CLEAR/перепрошивок в этом этапе, подключения/питание
оставлены как подтвердил пользователь. Повторный пуск требует нового запроса.

## 2026-10-25: планирование AS5600 исправлено и проверено без силового,2517 установлена

Пользователь попросил исправить опрос и проверить без J1, подтвердил прежние
питание/USB. Исправлена собственная ошибка2516: PollIo вызывал k_yield каждые
32ожидания внутри общего3мс deadline, позволяя веб/контрольным потокам
занимать CPU дольше срока обмена. Приоритеты/квант ядра не менялись.
Убран yield из wait_step; только poll.read обёрнут в RAII k_sched_lock/unlock.
Глобальные IRQ не маскируются; нет mutex/sleep/RPC внутри участка,3мс
deadline/ошибки/проверки свежести и магнитной валидности сохранены. Между
успешными чтениями остаётся k_msleep2мс. Код управления мотором и5с STOP
побайтно прежний за исключением buildID и двух пассивных полей диагностики.
Бюджет блокирования потоков —номинально0,55мс, при зависании3мс+ISR/учёт;
произвольно долгий ISR не ограничен этим механизмом. Nucleo/его защиты независимы.

Пакет as5600_poll_schedule_r1:44старых+16новых fault/scheduling тестов PASS,
старый код воспроизводит записанные интервалы3772/3959/4132/4810мкс и20мс,
исправленный проходит, ошибки NACK/BERR/ARLO/OVR и настоящая остановка
по3мс по-прежнему отклоняются, scope освобождается, IRQ моделируются.
Сборка/LLEXT PASS. Uno2517 записана ОДИН раз и сверена чтением обратно;
Nucleo2510 не записывалась, калибровка SHA не изменилась:
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
Образ SHA65696de563d8827f5041f2b3847c43407a18f15b2404e6b0a4b65f4d2f160978.

После записи RPC снова требовала холодного USB старта: один owned HMIrestart
не помог, пользователь сам переподключил только Uno. BootID
19b6fd6f-00da-4656-ac39-3f29be0003d5,2517/2510/POLL100 подтверждены.
Исторический installation_r1/passfalse сохранён; readback/runtime отдельно PASS.
Никаких START/CLEAR за этот этап. J1 OFF,15В ON, USB как подтверждено.

Реальный idle_web_stress_r1 PASS:61,312с,65HTTPснимков,23514успешных
чтений,0ошибок/тайм-аутов/NACK/reset, в том числе33с с3параллельными
клиентами полного веб-статуса. Новых UART bad/drop0, ответы Nucleo свежие.
Максимум HTTP2,141с, максимальное время защищённого обмена552мкс.
К финальной проверке72239чтений за загрузку и0ошибок/тайм-аутов.
Это подтверждение исправления web/idle scheduling, НЕ доказательство
устранения прежних электрических NACK при ШИМ. Силового пуска не было.

Обнаружен и исправлен HMI-only пропуск2517 в двух whitelist: zero-history
и ADCpeak. Веб-исправление —отдельный as5600_poll_schedule_hmi_r1,
без повторной записи MCU; parent manifest указывает active_hmi_overlay.
SHA активного server74aa1838b6d3eba6e3ec0913419421cf952ab7c75637e510ea1c8fee8b4898a3.
Проверки реальных D9/ADCpeak данных, повреждённого CRC и неизвестной пары PASS;
8последующих настоящих статусов: zero/history ready PASS, AS errors0.
Первоначальные sealed источники/верификации2517 не переписаны.

Финал SAFE/PWM0/ARM0,DC10В, SD HIGH/configOK/BIE1/captureRUNNING/recordready0.
Остаётся ожидаемая после перезапуска Uno защёлка Nucleo fault2/transport7,
reason13/last_bad13, masks0/0,ESTOP0. CLEAR НЕ отправляли. Перед будущим
пуском нужен один отдельно согласованный штатный ACK после проверки,
не RESET/повторная перепрошивка. AS5600 статус0x73: MD+ML, поле слабое,
angle/speed невалидны. Магнит/проводку при поданном силовом не трогать.
Будущий MCU5с helper поддерживает --uno-build2026102517 (обязательно явно);
zero quality whitelist2517 добавлен без изменения порогов. Пока продолжаем
только в рамках новых указаний пользователя, J1 не включаем автоматически.

## 2026-10-25: холодный старт восстановил2516; выявлены idle deadlines AS5600

Пользователь переподключил только USB Uno, J1 OFF, Nucleo/15В не трогал.
Дождались нормальной загрузки самостоятельно: ADB появился, forwards восстановлены,
несколько503 сменились настоящими статусами2516/2510. Linux bootID
57623778-8be7-46c7-932a-a16c6e94506a. START/CLEAR/Flash/MCUreset/HMIrestart0
за эту проверку. Manifest runtime_pair_verified=true, idle_runtime_verified=true,
полная hardware/PWM validation=false. Исторический installation_r1/passfalse
не изменён; успешная загрузка отдельно cold_boot_verify_r1/report.json.

SAFE/PWM0/ARM0/ESTOP0, шина10В, transport/bad/integrity/sequence/UARTflags0,
fault/masks0. Автоноль3/3, три блока истории корректны, offsets2068/2068/2067/2069.
SD HIGH/configOK/BIE1/captureRUNNING/recordready0: полный захват свободен.
Калибровка по реальному /home/arduino/.config/mic-ai/vbus_calibration.json
SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17 не изменилась.

AS5600 действительно работает в POLL100/mode4/priority4, cfg совпадает,
init0/current_io_error0, возраст2–5мс, тысячи успешных чтений. Но накоплено
8тайм-аутов БЕЗ ШИМ к финальному чтению, NACKcount0, resets8; первый3772мкс/stage9, один из поздних
4810мкс/stage10/ISR0x25=TXE|RXNE|STOPF. Ранее ISR0x8005=BUSY|RXNE|TXE.
Это не сохранённый NACK: когда проверялся общий deadline, байт уже был готов.
При7с паузы запросов нашего коллектора reads+2861/errors+0; затем8запросов
статуса reads+2467/errors+2. Другие клиенты не контролировались, поэтому
исключительная причинность не доказана. Вероятна проблема расписания/общего
deadline нового polling-reader; в PollIo wait_step есть k_yield каждые32ожидания,
приоритет равен control4. Это нужно исправлять/проверять программно, не
объявлять исходные NACK при ШИМ устранёнными и не увеличивать пороги защит.
Магнитный статус0x73 (ранее0x33) имеет MD+ML: поле слабое, angle/speed невалидны.
Питание/подключения оставлены, силовой пуск в этом этапе не выполнялся.

## 2026-10-25: Uno2516 записана/сверена, RPC пока недоступна

Пользователь подтвердил J1 OFF, независимый DMM<20В, Uno USB к ПК,
Nucleo на повербанке,15В ON. Во время начальной загрузки USB ещё не было,
затем самостоятельно появились3880458060/COM10/ADBdevice; повторного
переподключения не просили. Windows также видит STLink/COM13, несмотря
на сообщение о повербанке; Nucleo не опрашивали по SWD и не записывали.

tools/install_as5600_bounded_io.py выполнен ОДИН раз, installation_r1:
HMI обновлён, Uno flash1, readback PASSED, Nucleo flash0, actuation0/CLEAR0.
SHA образа6df3fa7553952e9e68cbe404d4a0519f9d12f55114d69b9ae6490d16e096f4ab;
калибровка до/после одинаковаяa89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
Перед записью статус2515/2510 SAFE/PWM0/ARM0/Vbus10В прошёл programming gate.
Report passed=false ТОЛЬКО из-за runtime verification timed out; историю
не подменять успешным отчётом и не запускать установщик повторно.
Manifest installed/readback=true, runtime_pair_verified=false/hardware=false.

ADB доступен, forwards18080→8080/12222→2222 есть. Linux bootID
e51011f9-a3b1-4079-931b-5bd35ad521c0, обе службыactive. Выполнен один
владелец-проверенный программный restart только unoq-hmi.service через
SIGTERM PID992/Restart=always, без MCUreset; owned_hmi_reconnect.json.
После него оба запроса/api/status по8с снова timed out.
Прошивка и её readback завершены; нужен холодный USB-перезапуск только
Uno на5секунд. Nucleo,15В,проводку не трогать,J1 OFF. Повторной прошивки
не будет. После подтверждения дождаться загрузки, заново выставить ADBforward,
проверить2516/2510/POLL100mode4/priority4 и реальные счётчики/автоноль/SD
только чтением; START/CLEAR не согласованы в текущем этапе установки.

## 2026-10-25: подготовлена Uno2516, ещё НЕ записана

По запросу исправить программу AS5600 и автостоп подготовлен пакет
artifacts/live_bench_20261025/as5600_bounded_io_r1, Uno2516/Nucleo2510.
Сборка154200байт, LLEXT PASS,44сценария poll-reader/таймера PASS,
исполнена реальная новая ветка MCU deadline на ПК с wrap/непродлением,
реальный HMI start проверен на позднем ответе о завершении. Новый host
runner исполнен с fake HTTP-ответом через6,2с: MCU-событие5000мс принято,
второго START/CLEAR/ожидания5с после ответа нет. Это программные проверки,
не измерение реального аппаратного отключения. verify-package-only PASS.
SHA образа6df3fa7553952e9e68cbe404d4a0519f9d12f55114d69b9ae6490d16e096f4ab.

POLL100/mode4 теперь default: тот же аппаратный I2C2/100кГц/0x36/0x0B+3байта,
но sole-owner polling вместо непрозрачного native interrupt transfer.
Ожидание проверяет общий deadline3мс, фиксирует ISR NACK/BERR/ARLO/OVR
ДО локального PE-reset; повторной попытки того же отсчёта нет, ошибочный
отсчёт невалиден. Нет отключения глобальных IRQ, внешних bus-clear clocks,
OTP/config-записей. CPU ожидает с короткими yield; при произвольном
вытеснении3мс не являются жёсткой wall-clock гарантией —это проверено
отрицательным тестом с задержкой500мс. Прежние режимы сохранены для сравнения.
Нативные553мс согласуются с upstream Zephyr4.2 ожиданием500мс, но это не
доказательство конкретного исходного электрического события. Устранение
самих ошибок при ШИМ пока НЕ доказано. Магнитная валидность не ослаблена.

Для короткого теста runner задаёт MCU RUNLIMIT5с; отсчёт в MCU от локальной
выдачи пуска, не от HTTP-ответа. Нормальное завершение теперь STOP, без
ESTOP; прежние аварийные ветки сохранены. run_id/start_ms/stop_ms/elapsed_ms/
limit_ms/reason доступны в API. Это отметки Uno, не прямое измерение фронтов
Nucleo/IGBT; задержку UART и фактический OFF нужно проверить на стенде.
HMI распознаёт уже завершённый единственный прогон при позднем ответе,
START/CLEAR больше не повторяются RPC автоматически. Пороги защит,
UART-протокол, ADC/SD Nucleo и калибровка не менялись.

Инсталлятор tools/install_as5600_bounded_io.py готов; нужен только USB Uno
при J1 OFF и подтверждённом мультиметром DC<20В. Nucleo остаётся на повербанке,
15В можно оставить, двигатель/проводку не менять. Новых моторных команд,
CLEAR, записей или перезапусков за эту подготовку0. Последний read-only статус:
всё ещё2515/2510, SAFE/PWM0/ARM0,ESTOP1,transport0, шина20В по контроллеру;
положение J1 и показание DMM в этот момент не подтверждены.

## 2026-10-25: LEGACY2515 проверен при ШИМ; ошибки AS5600 повторились

Обе платы на повербанках, USB ПК/Saleae сняты,15В и J1 через soft-start
подтверждены пользователем. После загрузки Uno выбран LEGACY/mode3/priority14.
При включении J1 до первого START записаны SD: PA6 LOW18391,0мкс,
TP23→PA4 LOW18387,6мкс, несовпадение3,4мкс; полный захват, без DMA/overrun.
Контекст MOE0, reference0, вне START. В тот же этап защёлкнут отказ
UARTtransport4; общий bad_cnt25, не доказанные25ошибок CRC. Сохранённый
фатальный UART-кандидат9байт, reason4; предыдущие UART flags в статусе0.
Сырые записи/логи/волна сохранены в legacy_powered_preflight_r1;
SHA волны390af98cc0f6bc51249b05a45d11f47a706fd529083d7182d1c7e256145715bf.

После стабильных SAFE/PWM0/ARM0,SD HIGH,готового автонуля и отсутствия
роста bad_cnt выполнен один согласованный штатный CLEAR. Восемь свежих
снимков подтвердили ready, BIE включён, transport/bad/masks0, волна сохранена.
Затем ОДИН START5Гц, новых CLEAR/повторных START нет. Артефакт:
artifacts/live_bench_20261025/as5600_software_regression_r1/legacy_powered_5hz_r1.
Получены4различных валидных токовых окна5Гц, покрытие100%, номинальные
RMS около0,43–0,44А; независимая проверка масштаба ампер не выполнена.
Физическое вращение именно этого прогона пользователь ещё не подтверждал.

AS5600 за активные снимки: errors0→5, успешные reads+163, generic native
driver error(stage2/cause1), максимальная длительность553464мкс.
cfg до/после всех наблюдавшихся операций1114490, включая сохранённую
ошибку; изменения GPIO не обнаружено в этих точках. Возврат старого
приоритета14 НЕ устранил сбой. В отличие от прежнего SW100, между
ошибками были успешные чтения. Причинное сравнение ограничено разной
нагрузкой/экспозицией. Магнитный статус0x33/0x37 всё ещё слабый; angle/RPM
не квалифицированы. Нативный generic EIO нельзя объявлять NACK.

Остановка подтверждена SAFE/PWM0/ARM0. После STOP ESTOP1/mc_fault1,
reason4, transport0/masks0/0: установленный MCU при достижении runlimit
защёлкивает ESTOP. START HTTP занял5,167с, host STOP был запрошен через5с
после ответа; резервный MCUlimit7с достигнут раньше. Ровно5с работы от
фактического включения ШИМ этим helper не доказаны; отчёт PASS означает
получение целевых окон и подтверждённый OFF, не чистый обычный STOP.
Нового first_start_window SD не записано; исходная волна сохранена.
Причина ошибок датчика пока не доказана; прошивки/пороги не меняли.

## 2026-10-25: Uno2515 установлена и проверена; ожидание прогона новой диагностики

Пользователь подтвердил J1 OFF/DMM<20В/USB для записи. Uno обнаружена
после загрузки, live2513/2510 SAFE/PWM0/ARM0/Vbus10В. Выполнен
install_as5600_software_regression.py, installation_r1/report.json PASS:
одна записьUno, проверка чтением обратно PASSED, Nucleo не записывали,
SHA калибровки до/после совпадает. RPC восстановилась автоматически;
дополнительного USB-переподключения и перезапуска HMI не потребовалось.

На2515 при J1 OFF выполнен idle_modes_r1: HW100/priority4 —1948чтений,
LEGACY/priority14 —68, SW100/priority4 —1459; ошибки0 во всех окнах.
В native/LEGACY cfg1114490, GPIO modeAF/OD; в SW100 cfg1114485,
GPIO output/OD; до/после совпадают с эталоном. В SW100 переданный
read-address byte0x6D прочитан обратно как0x6D,8бит. Это проверка
уровня на MCU, не измерение линии на конце датчика. Слабое поле0x33
сохраняется, двигатель при этой проверке не запускали.

Значимое программное наблюдение: старый priority14 резко замедляет
опрос под частыми запросами полного статуса —68чтений за5,09с,
приpriority4 —1948за5,09с. При паузе запросов от нашего коллектора
1359чтений за7,52с, ошибок0; другие клиенты не контролировались.
Это ограничение планирования/нагрузки, не доказанная причина NACK.
Основной цикл действительно имеет k_msleep(1) после owner.release(),
бесконечного занятого цикла не обнаружено. Простое возвращениеpriority14
нельзя объявлять исправлением. Количественная запись legacy_polling_gap.json.

В конце выбран LEGACY/mode3/priority14, подтверждены SAFE/PWM0/ARM0,
готовая история автонуля и совпадение cfg; J1 OFF, USB ПК пока подключены.
После записи/перезапуска Uno осталась защёлка тайм-аута Nucleo:
mc_fault=bp_fault=2,transport7,reason13,last_bad13,seq234; UART flags0,
MCSDK current/occurred0/0,ESTOP0. В before установки её не было,
в первом after она уже есть. CLEAR не отправляли; перед новым пуском
нужно штатное подтверждённое снятие после проверки защиты. SD сейчас HIGH,
BIE включён, конфигурация исправна, полный захват свободен.
После перевода Uno на повербанк её загрузка вернёт mode0/HW100;
перед любым пуском нужный режим выбирается заново при OFF и проверяется.
Новых START/CLEAR в этом этапе0. Для следующего силового этапа —обе
платы на повербанки, USB ПК/Saleae отключены,15В как есть, J1 через
soft-start; после подтверждения пользователя и проверки состояния можно
выполнить только новый согласованный ограниченный пуск с автостопом.

## 2026-10-25: программный разбор по просьбе пользователя, подготовлен Uno2515

Пользователь сообщил: AS5600 питается от3,3В Uno, провода примерно20см,
проходят далеко от силовых; модуль раньше работал, просит искать причину
в программе. Аппаратные переделки отложены, фото/перемычки не требуем.

Проверено без запуска двигателя: команда DISPLAY TEST на установленной2513,
17последующих статусов SAFE/PWM0/ARM0; ещё11430чтений AS5600 без новых
ошибок. Дисплейный тест не воспроизвёл отказ. Артефакт:
as5600_i2c_diag_r1/software_display_isolation_r1/report.json.

Сравнение раннего UNOQ_MOTOR/as5600_teacher.cpp и установленного до2513
нативного драйвера показало только замену приоритета с последнего
вытесняемого (14 на этом ядре) на4 и комментарий. Адрес0x36, регистр0x0B,
100кГц, три байта и периоды2/100мс в том diff не менялись. Найденный
архивный check_r1 подтверждает работу датчика без ШИМ; причинность
изменения приоритета для NACK пока не доказана.

Подготовлена НЕ УСТАНОВЛЕННАЯ версия2515, Nucleo остаётся2510:
artifacts/live_bench_20261025/as5600_software_regression_r1.
Добавлен режим ENC BUS LEGACY: нативные100кГц с прежним приоритетом14.
HW100/priority4, SW100 и SW25 остаются для сравнений одной прошивкой.
Настройки только PB10/PB11 (MODER/OTYPER/PUPDR/OSPEEDR/AFR) сохраняются
перед/после обмена и при ошибке. Программный мастер дополнительно читает
SDA во время каждого передаваемого бита: intended byte/echo/number of bits.
Это наблюдение на стороне MCU, не осциллограмма на выводах датчика.

Сборка/LLEXT проверка пройдены,14проверок reader включая искажённый адрес,
функция упаковки регистров проверена на синтетическом GPIO, HMI проверен
на реальных записанных токовых/SD-пакетах; исходный motor sketch за
исключением sensor selector/диагностики/buildID побайтно сохранён.
Пороги, UART/Nucleo, V/f, калибровка и фильтры валидности AS5600 не менялись.
Host helper поддерживает --mode LEGACY --uno-build2026102515, проверяет
реальный приоритет14; автоматических CLEAR/повторных START нет.

Для установки необходимы J1 OFF, DMM<20В, USB только Uno Q к ПК.
Nucleo можно оставить на повербанке,15В сохранять. Пока на стенде2513/2510,
SW100, мотор остановлен; снятие HV пользователем не подтверждено,
последнее чтение перед новым разбором322В. Новых START/CLEAR не отправляли.

## 2026-10-25: короткий SW100-пуск выполнен; пойман NACK адреса AS5600 при ШИМ

После включения J1 до первого Пуска зафиксирован новый SD на обоих входах:
TP23→PA4 и PA6 LOW 61,4 мкс, несовпадений0, полные фронты, без ошибок DMA.
tick897813; MOE0, вне START, cached context18мс/референс0/состояние0/
температура50°C/шина10В (последние18мс, не напряжение на электрическом фронте).
AS5600 при этом ошибок не имел. Архив sw100_power_on_sd_event_r1 содержит
полную wave.bin, оба API-снимка и пять проверок устойчивого OFF/SD HIGH.
SHA256: 1a80672982a2cc8bdefc2a6b17756ca6501106e1377db48de312e98896ee2060.

Пользователь явно разрешил один CLEAR и один короткий пуск. Отдельный
single_authorized_ack/report.json PASS: ровно1CLEAR, восемь готовых статусов,
SD HIGH/BIE включён, аварии0, волна не изменена. Повторных CLEAR не было.

run_as5600_i2c_diagnostic_5hz.py --mode SW100 выполнен один раз:
sw100_powered_5hz_r1/report.json PASS. Один START, в runner CLEAR0,
автостоп выполнен, SAFE/PWM0/ARM0 подтверждены, current/occurred0/0,
UART transport0. Контроллер достиг5Гц; пять различных валидных токовых
окон при5Гц, покрытие100%, номинальный RMS около0,43А; абсолютный масштаб
не квалифицирован. Физическое вращение пользователь в этом запуске ещё
не подтверждал. Температура по телеметрии50→51°C. J1 остаётся включённым,
по последнему чтению шина323В; платы на повербанках, ПК/Saleae отключены.

AS5600: за попытку enc_errors0→68. Во всех8активных HTTP-срезах mode1,
cause2=NACK, stage4=ADDRESS_WRITE: мастер не увидел LOW ACK после адреса
0x36 (write byte0x6c). Длительность записанных неуспешных транзакций
272–290мкс, SCL ожидание2–3мкс, тайм-аут SCL в этих срезах не наблюдался.
Счётчик успешных чтений неизменен между первым и последним активными
срезами. После STOP обмен восстановился: ещё1268 успешных чтений,
0новыхошибок. Слабое поле0x33 остаётся отдельной проблемой.

Сбой воспроизводится программным мастером при отключённом I2C2, поэтому
не сводится к нативному контроллеру/драйверу Zephyr. Сам NACK на стороне
MCU не различает отсутствие ответа у датчика и порчу ACK в линии.
Питание датчика/общая земля/подтяжки/помехи ещё не измерены, брак и
конкретная электрическая причина не доказаны. Полный cause_assessment.json
сохраняет эти ограничения. Новых запусков после этой попытки не было.

## 2026-10-25: платы на повербанках, J1 OFF; выбран SW100 перед коротким пуском

Пользователь подтвердил переход на повербанки и отключение ПК/Saleae.
ADB устройств не видит; после загрузки Uno получен прямой Wi-Fi статус
2513/2510, SAFE/PWM0/ARM0, шина 10 В, температура IPM 51 °C.
Автоноль готов: три блока, полная история. SD HIGH, Break IRQ включён,
конфигурация исправна, захват свободен; аварии и транспортные ошибки 0.

При выключенном J1 отправлена одна команда ENC BUS SW100; epoch2.
Шесть последующих статусов подтвердили стабильный обмен без новых ошибок
и рост счётчика чтений, неизменное состояние OFF/SD HIGH/готовый автоноль.
Результат: as5600_i2c_diag_r1/autonomous_sw100_preflight_r1/report.json.
Магнитный статус остаётся0x33/ML, AS5600 не используется для управления.

Подготовлен tools/run_as5600_i2c_diagnostic_5hz.py: один ограниченный
пуск 5 Гц, штатный host STOP через 5 с после подтверждения START,
резерв MCU 7 с и жёсткий host deadline10с от запроса. Повторного START,
CLEAR, RESET, перепрошивки и переключения I²C при ШИМ нет. Ошибки обмена
AS5600 записываются как диагностируемая величина; прежние проверки
привода, SD, тока, температуры, UART и связи сохраняются. Порогов не меняли.
Поддержка пары2513/2510 добавлена в host-проверку автонуля с теми же
критериями; отрицательные проверки готовности/возраста/флагов пройдены.

Следующее физическое действие: включить J1 через soft-start, не нажимая
START/RESET. После подтверждения пользователя и проверки HV-состояния
можно выполнить только один короткий SW100-пуск с записью и автостопом.
До этого момента START не отправляли. После любого перезапуска Uno режим
вернётся в HW100; helper отклонит несовпадение, автоматически не исправляет.

## 2026-10-25: Uno2513 установлена; три режима AS5600 проверены без ШИМ

Пользователь подтвердил J1 OFF/шина <20 В/USB. Установлен пакет
as5600_i2c_diag_r1: только Uno2513 и HMI; Nucleo остаётся2510.
Ровно1записьUno,0записейNucleo,чтениеобратно OpenOCD PASSED.
SHA калибровки до/после совпадает a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
После записи RPC не восстановилась от одного перезапуска HMI; пользователь
переподключил только USB Uno, после загрузки получена живая пара2513/2510.
installation_r1/report.json дополнен результатом восстановления; исходный
тайм-аут сохранён в pre_cold_boot_error. Повторной записи не было.

При J1 OFF/PWM0/телеметрии10 В выполнен idle_modes_r1: HW1001967чтений,
SW1001714,SW25953; во всех окнах0новыхошибок,init_error0.
Номинальные программные режимы не гарантируют фактическую частоту SCL:
полная транзакция наблюдалась до565/1355/3196 мкс соответственно.
Возвращён HW100,epoch4,SAFE/PWM0/ARM0; CLEAR/START не отправлялись.
Магнитный статус0x33: MD есть,MLслабое поле,угол/RPMневалидны.
Физическая причина PWM-зависимых сбоев ещё не доказана; следующий этап —
сравнение режимов при коротком ШИМ после перехода плат на повербанки.

Обе платы наблюдались по USB ПК (COM10/COM13). До следующего включения J1
ПК и Saleae должны быть отключены. J1 остаётся выключенным,15 В включены;
двигатель и проводку не меняли. Подробности: пакет manifest.json,
installation_r1/report.json, idle_modes_r1/report.json и status.jsonl.

## 2026-10-25: r3 завершён, ШИМ выключен; подготовлена диагностика I²C AS5600

Удержание r3/session40959 остановилось после ~619,6 с: в abort_status
телеметрия mc_temp_c достигла 80 °C, что нарушает прежний host-допуск <80 °C.
MC/UART-маски на этом снимке нулевые. final_status подтверждает SAFE/PWM0;
новых CLEAR/START после остановки не отправляли. Снятие силового питания
пользователем в этом этапе не подтверждено: остановка ШИМ не означает
снятие напряжения. Поздняя телеметрия шины снизилась с 65 до 59 В;
это не замена измерения мультиметром перед подключением ПК.

На активном участке 619,38 с счётчик ошибок AS5600 вырос на 4971,
успешных чтений — на 10887; максимальный опубликованный возраст 584 мс.
После остановки получено ещё 4130 успешных чтений без новых ошибок.
Успешные чтения также сообщают 0x37/MD+ML: слабое магнитное поле — отдельная
проблема, не установленная причина ошибок I²C. Физическая причина EIO ещё
не доказана; приоритетная версия — связь со включением ШИМ, возможны
электрические помехи/питание/GND либо поведение аппаратного контроллера.

Новый, пока НЕ УСТАНОВЛЕННЫЙ пакет:
artifacts/live_bench_20261025/as5600_i2c_diag_r1, Uno2026102513/Nucleo2510.
Только Uno и совместимый HMI: HW100 по умолчанию, SW100/SW25 на тех же
PB10/D21 SCL и PB11/D20 SDA. Команды ENC BUS HW100/SW100/SW25 допускаются
только при свежем подтверждённом OFF и снятом HMI ARM; START блокируется
на время передачи владения контактами. AS5600 остаётся наблюдателем.
Диагностика сохраняет стадию/причину/длительность ошибки; аппаратный EIO
не объявляется NACK без доказательства. Nucleo, калибровка, снимки SD,
пороги и токовая логика не меняются. Сборка и offline-checks см. пакет.

Для установки требуется выключенный J1, подтверждённые мультиметром
<20 В и USB к ПК только Uno Q. Nucleo можно оставить на повербанке,
15 В и двигатель/проводку не менять. Пока установленная пара2509/2510.

## 2026-10-25: ВНИМАНИЕ — активно удержание 5 Гц r3 после отдельного разрешённого ACK

На новый runningBreak/E-stop пользователь явно разрешил «Да, один CLEAR
и повторный пуск». as5600_r2_drive_trip/single_authorized_ack/report.json
PASS: передкомандой3GETexactseq19/mask0x400/estop1/SDHIGH/датчикнаблюдение,
сверены сохранённый rawfirst_starttick2234201 и стараяwaveSHA. Writeaheadintent,
ровно1CLEAR безретрая; затем8ready,estop0/masks0/SDHIGH/BIEon,всеархивынеизменны.

Hosthelper получил явное разрешение допускать ТОЛЬКО этот сохранённый
и ужеACK runningBreak через --acknowledged-running-break-report; это
допуск занятой диагностической памяти, а не ослабление SD/Break/аварий.
Проверены негативные случаи новогоtick/активнойаварии/E-stop/SDLOW/
maskedBreak/UARTfault — все отвергаются. Исправлено также распознавание
SAFE/PWM0 с аварией как faultSTOP, а не внешний нормальныйSTOP.

Запущен r3: tools/hold_as5600_scalar_5hz.py --confirm-fixed-sensor-hands-away
--confirm-continuous-5hz-no-clear --acknowledged-running-break-report
artifacts/live_bench_20261025/as5600_r2_drive_trip/single_authorized_ack/report.json
--outdir artifacts/live_bench_20261025/as5600_manual_hold_r3.
EXEC session_id=40959. Ровно1START,дополнительныхCLEARвrunner0.
Подтверждён RUNNING/VF_RUN/PWM1/field5,0; AS5600сноваI2C−5/angleinvalid,
не используется в управлении и не останавливает мотор. До командыSTOP
или отказа привода сохраняется ручное удержание безтайм-лимита.

Для немедленного STOP: создать файл as5600_manual_hold_r3/STOP,
отправить WifiHmi.fail_safe_stop,дождаться session40959 и свежимGET
подтвердитьSAFE/PWM0/ARM0. WebSTOPтакжезавершает. Старыеr1/r2/session
69334/99923 уже завершены — не использовать их вместоr3. Снимки SD и
калибровка сохранены; прошивки2509/2510 неизменны. НовыеSTART/CLEAR
после самостоятельного faultSTOP не делать безновогозапроса.
J1/15ВON,платыповербанки,USBПК/SaleaeOFF,датчикзакреплён/тольконаблюдение.


## 2026-10-25: r2 остановлено новым Break на 5 Гц; повторный START не отправлен

Пользователь «а сейчас еще раз запускай». READONLY обнаружил r2 STOPPED,
elapsed107,17с; старый helper дал stop_reason external_web_or_controller_STOP
без error, потому что проверил SAFE/PWM0/ARM0 до проверки fault. Это НЕ
доказательство команды пользователя STOP. Свежие8GET:SAFE/PWM0/ARM0,estop1,
mc/bp_fault1,MCSDKreason8,maskSnapshotcurrent/occurred0x400,SDHIGH/BIEoff,
UARTclean,Vbus321..323В. Шина под напряжением! Все процессы удержания закончены.

Новый first_start_window snapshot:tick2234201,BIFtrue,PA6LOWatIRQ,BKEtrue,
MOEfalse (аппаратный Break уже мог снять MOE до IRQ, это не доказательство
предварительного OFF). Кэш31мс: motorstate6/RUN,reference50speedunits=5Гц,
Vbus321В,temp65C,masks0,seq19. start_windowraw1 — устаревший флаг послеRUN,
декодер правильно не считает событие стартовым. Первая fullSDwave по-прежнему
старая526448, не длительность нового импульса. Все статус/diag/logs/contexts/
analysis сохранены artifacts/live_bench_20261025/as5600_r2_drive_trip/.

AS5600 без ШИМ busOK/ошибкинерастут,ноstatus55(ML1/MD1/MH0),angleinvalid,
RPM0невалидно — слабое поле. ПовторныйSTART/CLEAR/RESET=0 в этом запросе;
прежний однократныйCLEAR уже израсходован. Новый E-stop/Break нельзя
молча сбросить или обходить. Перед восстановлением нужно отдельное
подтверждение штатногоCLEAR; гарантии исправления причины не заявлять.


## 2026-10-25: активное удержание AS5600 r2; r1 остановилось на наблюдаемом SD LOW

Пользователь сообщил «я поправил датчик еще раз пробуем» — новый пуск разрешён,
прежнее подтверждение фиксированного датчика/только наблюдения сохраняется.
Проверка показала r1 уже STOPPED. Его последний активный status на181,28с
от START-request действительно SDlevelLOW при age45мс/BIEtrue/configOK;
MCSDK current/occurred/transport0,GPIOLOW мог быть короче аппаратного фильтра,
точная длительность не записана. Host корректно STOP. Не называть причиной
таймер180с, ошибкуAS5600, просрочкуSD или защёлкнутую новую MCSDKаварию.

ПослеSTOPI2C:3465новыхчтений/0ошибок,ноstatus55(0x37,MD1/ML1/MH0) —
слабое поле, угол/скоростьinvalid. Независимый мотор/SD preflight5подрядHIGH
и masks0. Предупреждение получено: даже послеSTOP сенсор HOT при J1ON,
никаких касаний/перестановок до отключения и разряда. Вектор не включался.

В tools/hold_as5600_scalar_5hz.py добавлена отдельная mutually-exclusive
ветка --confirm-continuous-5hz-no-clear: только ужеREADY, никакихCLEAR.
Гейты защиты не менялись; abort_status теперь сохраняется с точнымSDLOW.
Запущен r2 с этим флагом и --confirm-fixed-sensor-hands-away,
outdir artifacts/live_bench_20261025/as5600_manual_hold_r2,
exec session_id=99923. 8 READY передSTART,ровно1START/CLEAR0. Последний
срезRUNNING/VF_RUN/PWM1/field5,0,ноAS5600сноваI2C−5,угол/RPMinvalid.

СЕЙЧАС продолжительное ручное вращение r2 активно до команды пользователя
или защиты. При «Стоп» создать as5600_manual_hold_r2/STOP и отправить
штатный fail_safe_stop, дождаться session99923, подтвердитьSAFE/PWM0/ARM0
свежимGET. WebSTOP также завершает. Не ориентироваться на старый69334/r1
для остановки: он уже завершён. AS5600 только наблюдение, его ошибки неSTOP;
SD/UART/связь/токи и watchdog3с сохранены. J1/15ВON,повербанки,ПК/SaleaeOFF.


## 2026-10-25: ВНИМАНИЕ — активное ручное удержание 5 Гц до команды пользователя

Пользователь попросил не останавливать при ошибках AS5600 и подтвердил:
датчик уже закреплён, руками не трогает, только наблюдает. Затем явно разрешил
«Да, один CLEAR и удерживать 5 Гц». Новое событие SD после предыдущего STOP
архивировано as5600_manual_request/: MC_DPoccurred0x400,current0,sequence99,
SDHIGH/BIEoff, по Linux-журналу событие наблюдалось в SAFE/PWM0 после прошлого
пуска. Полная wave всё ещё первая, новых фронтов не содержит.

Запущен tools/hold_as5600_scalar_5hz.py с двумя explicit confirm flags,
outdir artifacts/live_bench_20261025/as5600_manual_hold_r1,
exec session_id=69334. Перед START 3 проверки и write-ahead intent,
ровно1CLEAR и8ready-проверок, затем ровно1START(manual=true). На последнем
срезе VF_RUN/PWM1/field5,0Гц,Vbus322В,SDHIGH/BIEon/config,masks0,
UARTclean,RMSноминально[.441,.444,.440]A,coverage100%. AS5600 I2C−5 продолжается,
enc_ok0,errors419 на последнем срезе; датчик только наблюдение, его ошибки
НЕ вызывают STOP. Защиты SD/MCSDK/UART/токовых окон/связи сохранены.

Режим БЕЗ тайм-лимита по явному желанию пользователя. Python host отправляет
operator heartbeat для штатного watchdog3с и пишет status.jsonl/latest/report.
Не завершать его и не обрывать наблюдение молча. При сообщении «Стоп»,
«хватит», «нашёл положение»/завершении поиска — немедленно создать файл
as5600_manual_hold_r1/STOP и отправить штатный /api/stop-sequence через
WifiHmi.fail_safe_stop, затем дождаться завершения session69334 и свежим
GET подтвердить SAFE/PWM0/ARM0. Web STOP тоже завершает hold. Если связь
или защита меняется, скрипт сам STOP без повтора. Не делать CLEAR/START снова.

J1/15ВON,обеплатынаповербанках,USBPC/SaleaeOFF,моторJ3/магнитнавалу.
До любой регулировки руками или переподключения — STOP и отключение/
разряд силового; датчик относится к HOT-домену. Оператор это предупреждение
получил и подтвердил только наблюдение.


## 2026-10-25: один CLEAR и один пуск AS5600 выполнены; I2C пропадает при ШИМ, STOP подтверждён

Пользователь явно разрешил «Да, один CLEAR и пуск 5 Гц». Ровно1 CLEAR,
без ретрая, записан write-ahead intent и before/after в
as5600_low_speed_preparation/single_sd_ack/report.json PASS. Перед ним
3 GET проверили exact SHA00ca7877.../tick526448,MOEoff/неSTART/SDHIGH,
нулевую активную маску и единственную произошедшую0x400,чистыйUART/датчик/
автоноль/шину. После8подряд READY,SDHIGH/BIEon,masks0,старыйSDSHAсохранён.

Затем tools/run_as5600_low_speed.py --confirm-powered-ready --outdir
artifacts/live_bench_20261025/as5600_low_speed_run_r1: ровно1 START,
CLEAR/RESET/flash в прогоне0. Предварительно AS5600 anglevalid/readsprogress/
errors0. При PWM1 уже на1,4Гц появилась I2Cerror−5,enc_errors4;
на2,1Гц errors5,age308мс,скоростьinvalid; следующий collector3,7Гц/errors12.
Первый monitor обнаружил потерю датчика и запросил STOP, без повтора.
3 активных status, ни одного с достоверным RPM. 5Гц не достигнуты.
НовыеSD/MCSDKfault/current/occurred/UART CRC/sequence/transport0;
токовые окна valid/coverage100%. Не называть это аварией инвертора/UART
или повторным SD: причина hostSTOP — потеря пригодности AS5600.

Конец: 3 независимых GET подтвердили SAFE/PWM0/ARM0,SDHIGH/BIEon/config,
masks0. Счётчик AS5600 за попытку0→17 (не все17локализованы точно внутри
PWM из-за редких HTTPнаблюдений/хвоста). ПослеSTOP bus/angle/speedvalid
восстановились,errors17стабилен,RPM0,raw2001/175,9°. Было изменение raw,
но физическое вращение оператором ещё не подтверждено и достоверная
скорость при PWM не получена. Снимок SD точногоSHAсохранён. Анализ/статусы/
logs/report/encoder_result/independent_final_status в каталоге прогона.
Причина I2C−5 не установлена: помехи, питание и ПО/тайминг не различены.
При успешных чтениях MDвнорме, нельзя утверждать слабый магнит.

Силовое и15В по последнему подтверждению остаются ON,платынаповербанках,
USBPC/SaleaeOFF,моторJ3/датчик на валу. Не подключать ПК/щупы по инерции,
не считать шину разряженной. Разрешённый одиночный пуск израсходован;
нового START/CLEAR/RESET не было и не делать без нового запроса.


## 2026-10-25: J1 включён для проверки AS5600, пуск заблокирован новым SD до ШИМ

Пользователь подтвердил «готово» на включение J1 через soft-start для одного
5-Гц скалярного пуска с AS5600. Powered preflight 3 GET: SAFE/PWM0,Vdc320В,
2509/2510,AS5600 valid/MD/enc_errors0 неизменно,автоноль3/3. Но новое SD
до START: mc_fault5/reason8,currentmask0,occurredmask0x400,SDсейчасHIGH,
BIEfalse,полныйрегистрFROZEN. START/ARM/CLEAR/RESET не отправлялись.

Полный архив as5600_low_speed_preparation/prestart_sd_event/ содержит
sd_wave.bin/status/decoded_wave/bkin_trace/break_snapshot/report.json.
SHA00ca7877e135c1b51f7fbcb922354e3740e450b3135ded17fe5377b31b81554d,
tick526448,PA6LOW61,6мкс/TP23→PA4LOW61,4мкс,несовпадение1отсчёт,
оба фронта полные, DMA/timeout ошибок нет. SnapshotMOEoff/неSTART,
cached reference0/motorstate0/masks0,кэшшины10В за30мс доIRQ.
Это событие включения до вращения, не доказанный дефект IPM/перегрузка.
Питание оставлено как есть по явному подтверждению:15В/J1ON,повербанки,
USBPC/SaleaeOFF,двигательJ3 и датчик на валу.

Через async задан ровно один вопрос: разрешить один штатный CLEAR,
проверку защит и уже согласованный 5Гц пуск; альтернатива без сброса/пуска.
Ответа на CLEAR пока нет. Не запускать и не сбрасывать до ответа.
При положительном ответе перед CLEAR заново проверить точный SHA/tick,
MOEoff,SDHIGH/config,нулевую активную маску,известную произошедшую0x400,
датчик/связь/автоноль; ровно1 CLEAR без авторетрая, сохранить ряд постACK
SAFE/SDHIGH/BIEon/masks0 и неизменный SDархив. При успехе можно выполнить
уже разрешённый tools/run_as5600_low_speed.py --confirm-powered-ready
--outdir artifacts/live_bench_20261025/as5600_low_speed_run_r1.
Этот runner не сбрасывает аварии сам, допускает сохранённый предSTART
архив, проверяет его неизменность, не требует свободного ADCpeak для
обычной телеметрии AS5600. ОдинSTART,host5с/MCU7с/hard10с/STOPприошибке.


## 2026-10-25: подготовлен один 5-Гц пуск с AS5600, ожидается включение J1

Пользователь явно попросил проверить AS5600 на малых оборотах и подтвердил:
мотор возвращён на J3, магнит закреплён на валу, обе платы на повербанках,
USB ПК/Saleae отключены, 15В включены, J1 выключен. После смены питания
Wi-Fi временно пропал; ADB сначала был доступен, затем USB исчез. READONLY
ADB показал временное отсутствие WLAN IP; настроек сети не меняли. Wi-Fi
восстановился самостоятельно, силового пуска не было.

as5600_low_speed_preparation/idle_preflight.json PASS: 3 свежих GET,
SAFE/PWM0,2509/2510,Vdc10В,автоноль3/3/историяvalid,SDHIGH/BIE/configOK,
пустой SD-регистратор, fault/current/occurred0, AS5600 valid, reads+683,
новых sensor errors0. Подготовлен tools/run_as5600_low_speed.py на базе
проверенного bounded5Hz runner: hostSTOP5с после подтверждения START,
host hard deadline10с, MCUrunlimit7с, operator watchdog3с, ровно1START,
CLEAR/RESET/flash0. Дополнительно датчик должен быть свеж/valid,
без роста I2C ошибок, с правдоподобным RPM и движением за2,5с; потеря
датчика вызывает STOP без повтора. Существующие токовые/SD/UART/силовые
гейты сохранены, старый SD архив не стирается. 4 теста политики PASS.

Через async запрошен только J1 через soft-start при закрытом стенде,
оставить15В/повербанки/датчик, Пуск/RESET не нажимать. Подтверждения J1 ON
ещё нет. До него не выполнять --confirm-powered-ready. После подтверждения
сначала свежий powered GET: шина/SD/автоноль/датчик/ошибки; не делать
автоматический CLEAR при любом новом SD. Если чисто — одна команда
python tools/run_as5600_low_speed.py --confirm-powered-ready --outdir
artifacts/live_bench_20261025/as5600_low_speed_run_r1. Это только скалярный
пуск для проверки датчика, не FOC и не режим аппаратной идентификации.


## 2026-10-25: повторная проверка AS5600 — связь и неподвижный угол восстановились

По просьбе пользователя выполнено 8 GET /api/status, аппаратных команд/пуска 0.
Все ответы SAFE/PWM0, Uno2509/Nucleo2510, Vdc10В по телеметрии. enc_bus_ok=1,
enc_ok=1, enc_status103(0x67; MD=1, ML=MH=0), enc_io_error/init_error=0,
enc_age2..3мс на первом/последнем ответах. Успешные чтения55278→58059 (+2781),
ошибки14476→14476 (исторический счётчик сохранён, новых ошибок нет).
Угол3130/4096=275,1°, RPM0, enc_speed_ok1, rawspan0: подтверждён только
неподвижный датчик, полный оборот/направление/скорость/монтаж на валу не проверены.
Причина восстановления не установлена; не приписывать его программному исправлению
или изменению питания без сообщения пользователя. Артефакт:
artifacts/live_bench_20261025/as5600_readonly_recheck/report_001.json.


## 2026-10-25: проверка подключённого AS5600 — I2C чтение не работает

Пользователь попросил немедленно проверить AS5600 и подтвердил подключение
к Uno Q «как последний раз». Силового/тестового воздействия не выполняли.
GET /api/status: Uno2509/Nucleo2510 SAFE/PWM0, Vdc10В (телеметрия, не DMM).
В 16 ответах enc_reads=0 неизменно, enc_errors13756→13906, enc_io_error=-5,
enc_init_error=0, SCL/SDA оба HIGH, enc_bus_ok/enc_ok=0. UART свежий.
После повторного чтения успешных чтений всё ещё 0, errors14466. АDB доступен
3880458060. Linux /dev/i2c-* — не доказательство доступа к I2C2 STM32;
сканирование этих шин не выполнялось и его нельзя выдавать за проверку датчика.

Архив as5600_readonly_r1 содержит samples/report/source_comparison.json.
Датчик ищется на Uno D20/PB11 SDA и D21/PB10 SCL, 100кГц, 0x36, чтение
0x0B..0x0D. Исторический check_r1 от 07.10 доказывает успешные чтения на
этой схеме; header драйвера совпадает, cpp отличается только комментарием
и приоритетом потока (последний→4). Адрес/контакты/транзакция прежние.
Растущие счётчики ошибок доказывают попытки чтения; причину -5
нельзя объявлять установленной неисправностью магнита, отсутствием ACK
определённого типа или браком датчика без дальнейшей диагностики.
Следующий конкретный внешний шаг — измерить VCC–GND прямо на модуле,
при выключенных J1 и 15В и включённом Uno. Ожидается ~3,3В при прежней
схеме. Не просить заново все четыре провода: пользователь подтвердил прежнее
подключение. FOC/аппаратный ID-пилот ещё не собраны; последнее действие
по ID было чтение исходников, никаких кандидатных PWM изменений не сделано.


## 2026-10-25: LCR недоступен, добавлен офлайн-расчёт электрической идентификации

Пользователь сообщил отсутствие режима индуктивности/LCR; название прибора
не распознано и модель не установлена. Никаких новых физических подтверждений
по питанию, USB или подключению мотора это сообщение не содержит.

motor_identification/standstill.py оценивает входной импеданс неподвижного
асинхронного двигателя по многочастотным синхронным RMS-фазорам. Известный
Rs=12,23 Ω берётся из измерения. Определяются наблюдаемые L_transient,
K=Lm²/Lr и tau_r, затем эквивалентная T-модель с явно заявленным допущением
LLS=LLR и LMS=LM/1,5 для Workbench. Это НЕ независимое измерение двух
физических индуктивностей рассеяния. J/B и ток намагничивания не определяются.

Добавлена команда tools/motor_parameter_identification.py standstill.
21 тест расчёта + 9 существующих тестов моста модели PASS, проверен CLI на
синтетических независимых fit/validation данных. Реальный профиль не заполнен
синтетическими параметрами. Не принимаются несинхронные данные, coverage<95%,
мало циклов/отсчётов, NaN/Inf, повтор run_id между fit и validation,
неподтверждённое напряжение и недостаточный многочастотный захват. Даже принятый
электрический fit имеет eligible_for_foc_start=false. Номинальный масштаб
шунтов разрешён для предварительного анализа и явно не считается калиброванным.

Артефакты lso_foc_preparation_r1/standstill_offline/ содержат исключительно
синтетический fixture/result и verification.json. Исходные сырые захваты пиков
имеют лишь 12 кадров, ими автоидентификацию не подменять. Аппаратный режим
автотюна пока НЕ реализован/не собран/не установлен: ещё нужны длительный
синхронный захват, компенсация ошибки напряжения/deadtime, ограниченное
воздействие вдоль неподвижной оси и STOP при ошибке. Нельзя сообщать, что
«прошивка автоидентификации готова», включать FOC или обещать найденный Rr/Lm.
HTTP/аппаратные команды/пуски/прошивки в этом этапе = 0.


## 2026-10-25: сопротивление щупов учтено, Rs = 12,23 Ω

Пользователь сообщил замкнутые щупы 0,24 Ω после трёх одинаковых
межлинейных 24,7 Ω. Исправленные межлинейные U–V/V–W/W–U = 24,46 Ω;
сбалансированный звёздный эквивалент Rs = 24,46/2 = 12,23 Ω. Расчёт
проверен Decimal. Физическое сопротивление отдельной обмотки при Delta
и эквивалентное Rs — разные величины; не записывать 24,46 в фазное Rs.
Температура/точность мультиметра не квалифицированы, температурной поправки нет.
Наблюдение и частичный профиль сохранены в lso_foc_preparation_r1:
motor_line_resistance.json, motor_profile_partial.json. Профиль явно частичный,
Rr/Lls/Llr/Lms/J/Im/B неизвестны, eligible_for_foc_start=false. Установленные
прошивки/пороговые защиты не изменены, аппаратных команд/пуска не было.


## 2026-10-25: получено предварительное сопротивление двигателя

Ответы пользователя «24.7 ома» и «везде все одинаковое» трактованы как три
межлинейных значения U–V/V–W/W–U по 24,7 Ω. Сохранены в
artifacts/live_bench_20261025/lso_foc_preparation_r1/motor_line_resistance.json.
Предварительный эквивалентный звёздный Rs = 12,35 Ω до коррекции проводов.
Сопротивление замкнутых щупов ещё неизвестно; температура и точность прибора
не установлены. Не подменять этим наблюдением готовый измеренный профиль FOC,
не переносить 0,35 Ω из старого примера. Текущее физическое питание отдельно
не подтверждено. Никаких команд платам/прошивки/пуска не выполнялось.


## 2026-10-25: начата подготовка LSO-FOC; силовой векторный пуск НЕ выполнялся

Пользователь попросил доработать векторный способ и тестировать пуск; номинальный
масштаб шунтов согласован по документации: 0,04 Ом, усиление 2,1. Только работа
на ПК, без HTTP-команд, прошивки, RESET/CLEAR/START и изменений калибровки.
Установленная пара Uno 2509 / Nucleo 2510 остаётся скалярной.

Исправлен prepare_air56_lso_profile.py: ACIM_NOMINAL_CURRENT — пиковые цифровые
единицы, не амперы RMS; Id требует magnetizing_current_rms_a; пересчитываются
LM/LS/LR/tau/sigma; WB_UI_INERTIA и WB_UI_FRICTION получают микро-SI из SI.
mcsdk_release_preflight нормализует инерцию обратно в SI. В шаблон добавлены ток
намагничивания и вязкое трение. Подготовщик проверяет профиль до копирования
проекта, --validate-only не изменяет файлов. Проверки конвертера и release gate
пройдены, 36 сравнений с настоящим кодом установленного Workbench прошли,
9 тестов моста идентифицированной модели прошли. Артефакты:
artifacts/live_bench_20261025/lso_foc_preparation_r1/.

Модель реального двигателя отсутствует: Rs/Rr/Lls/Llr/Lms/J/Im/B не измерены.
Rs=0,35 в текущем V/f заголовке не считать измеренным. Каталожный профиль
отклоняется подготовщиком FOC. Новая FOC-прошивка не собрана/не установлена;
оставшаяся работа включает параметры/настройку наблюдателя и регуляторов,
интеграцию ADC R3_2 вместо скалярного владельца JSQR/TIM1 CH4, актуальные UART/SD
и ограниченный тест. Не обещать FOC после одного измерения Rs.

Через async запрошен первый физический шаг: выключить J1 и 15 В, дождаться
по мультиметру практически 0 В шины, отсоединить три провода двигателя от J3,
сохранив перемычки двигателя, измерить замкнутые щупы и U–V/V–W/W–U в Ω.
Ответа пока нет; не предполагать выполненное отключение. Для симметричного
двигателя эквивалентный звёздный Rs = половина среднего межлинейного
сопротивления после вычитания сопротивления щупов (и при физическом Delta).


## 2026-10-25:2509/2510 строгий30→35→40→45→50Гц нажелезе — PASS, покрытие100%, RMSVALID, SDархивсохранён

Пользователь явно разрешил1прогон/ADCпики/автостоп/проверкупокрытияRMS,сохранитьSDснимок/неослаблятьзащиты,питаниеиподключениябезизменений. ПередзапускомподготовленТОЛЬКОhostwrapper tools/run_current_adc_apex_retained_sd_trial.py:требуется --confirm-retained-prestart-sd;принимаеттолькоранееархивированноеMOEoff/неSTARTсобытиеточногоSHA/tick300427снулевымконтекстомскорости/faults,first_start_windowсвободен. Сохраняетвсеphysical/SDHIGH/BKEconfig/BIE/MCfault0/UART/zeroгейтыистрогийRMSvalid1≥95%. Во времяACTIVEдополнительнонеизменностьSHAстаройволны;автоматическогоCLEAR/RESET/прошивкинет. tools/current_adc_apex_retained_sd_selftest.py34негативных/позитивныхпроверкиPASS:SDLOW/BIEoff/activefault/плохаяпамять/coverage94/NaNRMSне допускаются.

Команда --confirm-powered-ready --profile30-to-50 --outdircurrent_adc_apex_fix_r1/peak_trial_30_to_50_r1выполненаPASS. Ровно1START,все5ступенейпрошли,автоSTOPчерез34.75сотзапроса(<60);операторскийwatchdog3с/независимыйhostSTOPсохранены. CLEAR/RESET/flash0. Физическоеровноевращение/ускорениедоавтостопапользовательподтвердил. НовыхMC/BPfault/current/occurred/CRC/sequence/UARTошибокнебыло,collectionerrors0,шина317..321В. ФинальныйGETSAFE/PWM0/ARM0,SDHIGH/BIEtrue/configok,faultmasks0. Силовое/15Восталисьвключены,платынаповербанках,ПК/Saleaeотключены,проводкане менялась.

Результат coverage_rms_result_r1/report.json PASS, rms_coverage.csv содержитвсе5ступеней. Наустановившихся30/35/40/45/50Гц coverage100%,rejected0,CMflags11(ZERO|VALID|ACTIVE),RMSvalid1. По2+разных200мсокна/ступень. RMSU/V/W(номинальныймасштабшунтов):30=[.743,.750,.745];35=[.798,.801,.799];40=[.759,.765,.759];45=[.796,.803,.799];50=[.619,.635,.628]A. Доисправления2508на45/50coverage89/88/RMSNone;теперьизмерительноепокрытиевэтомиспытанииустранено/соответствуетпрежним95%/12samplespermsкритериям. Масштабампер/полярность/полосанезависимымэталономещёНЕквалифицированы,необъявлятьметрологическуюкалибровкузавершённой. Скоростьроторанеизмерена;подтвержденочастотаполя50и визуальноеразгон/вращение.

ADCпассивновыгруженtools/collect_current_peak.py --candidatecurrent_adc_apex_fix_r1 --outdirpeak_capture_30_to_50_r1:PASSCRC,1024Б/12кадров,NO_PEAKtrue,post_shortfalse,порог626counts≈6.0056Aне сработалнарегистрируемыхeligibleвыборках,всего488303samples. МаксимальныйпиквполученныхVALIDокнах1.976A(номинально);невсеокнапередаются,неназыватьегофизическимнепрерывныммаксимумом. Финишные50Гцкадрыдействительнодоказываютновуюпозднююточку:CCR45184,IRQDIRdown1,CNT~5102..5109,11активныхпринятыхкадров(12йMOEoff/STOP),всеepochconsistent,нетpendingepoch/JSQRnonempty/queueoverflow,геометриябезопасна. maxqueuepublishDWT5.112мкснаблюдавшийся,неполныйWCET. RecordSHA cf1cc9f3f710032b1a6e9217e9041f47ac7190fda51adec1a7e8025279cc2c67.

СохранённыйSDснимок61.4мксНЕстирался;воВСЕХstatusпрогонаифинальномGETSHA09ab8d06b01b4a514abc397f89c11d307c3215f0c19f710e7057fdea65fa7c0eсовпал. Не былоновогосрабатываниявэтомпрогоне;причинаисходногоSDприJ1ONдоПускаостаетсянеустановленной. ПолныйSDcaptureпо-прежнемуFROZENстарый,ADCcaptureтеперьFROZENNO_PEAKновый. НельзяобъявлятьэтизахватысвободнымипослеуспешногоSTOP. Дляновойrawзаписи—явнаяподготовка/разрешениенарестартпослеархивирования,неавторесет.

Manifestphysical_high_frequency_coverage_verified/full_current_rms_coverage_verified/physical_window_fix_verifiedtrueдляЭТОГОодиночногоиспытания;physical_current_scale_qualifiedfalse. coverage_rms_result_r1включаетfinal_status,hostrunnerSHA,34checkpolicyselftest. Installed2509/2510/calunchanged. Текущийзапросполностьювыполнен,дополнительныхпусков/перепрошивки/сбросовне делатьбезновогозапроса.

## 2026-10-25: пользователь разрешил один ACK SD, CLEAR1 выполнен, SD/защиты PASS, START0

Пользователь явно разрешил:«сбросьавариюодинразштатнойкомандойипроверьSDизащиты,беззапускадвигателя»,питание/подключенияне менял. ТекущаяподготовкаJ1ON/15ВON/повербанки,ПК/Saleaeотключены. prestart_sd_ack_r1/report.jsonPASS,summary.json. ПередACK3GETподтвердили2509/2510 SAFE/PWM0/ARM0/ESTOP0,250≤Vbus≤350,свежиеMC,SDHIGH/configok,currentmask0/occurredmask0x400,известныйfault5/reason8иSHAточнотойжеархивированнойполнойSDволны61.4мкс(eventtick300427,MOEoff/неSTART).

Отправленровно1HTTP/APIcmdCLEAR черезштатныйавторизованныйWi-Fiинтерфейс. Попытказаписанадоотправки,авторетрая нет. НикакогоSTART/HVARM/RESET/flash/измененияпорогов. ПослеACKвыжданачистаястадия,затем16дополнительныхGETпроверилиSAFE/PWM0/ARM0,SDHIGH,SDconfigoktrue,BIEtrue,MC/BPfault/current/occurredmask0,чистыйtransport/CRC/UART,готовыйавтоноль. Внаблюдавшемсяинтерваленовыхсрабатыванийнеобнаружено. Защитынефорсировалитестовымаварийнымсигналом;подтвержденыихтекущаяконфигурацияиразрешениеIRQ,неэлектрическаяквалификациявсехзащит.

ИсходнаяSDволнаimmutableсохраненаипроверенаSHAнавсехпостACKответах. first_since_bootrecordreadytrue/capture_runningfalse — ПОЛНЫЙSDзахватзанятстарымсобытием,необъявлятьсвободным. first_start_windowснимоксвободен. НезависимыйADCpeakзахватсвободен(hex«-»/good0/complete0). ПричинапервоначальногодвойногоLOW61.4мксвсёещёнеустановлена;одинACKине повторениевэтомкороткоминтервалене доказываютустранениеэлектрическойпричины. ПрогонRMSновыхоконещёНЕвыполнялся.

ЗапрошенныйACK/проверказавершены,дополнительногопускавэтомзапросеНЕразрешали. Стендоставленподсиловым,ШИМOFF,проводкуне меняли. Приследующемявноразрешённомпускенеиспользоватьстарыйstrictready,которыйтребуетСВОБОДНОЙSDwave:послеCLEARпамятьне очищалась. МожнооформитьявнуюhostполитикуархивированногособытиядоSTART(старыйarchive_before_startпроверяетMOEoff/неSTART/нулевуюзаданнуюскорость),сохранивреальныеSDHIGH/BKE/BIE/currentfault0/95%RMS/watchdog3с/STOP≤60с;объяснить,чтоfullwaveследующегоSDнеперезапишется,ноfirst_start_windowиADCсамостоятельны. НикакогоCLEARпослеошибкисиловогопрогонаиавтоповтора.

## 2026-10-25: poweredpreflight2509/2510 НЕпройден — доSTART SD LOW61.4мкс одновременнонаTP23/PA4иPA6

Пользователь подтвердилJ1ONчерезsoft-start,15ВON,платынаповербанках,ПК/Saleaeотключены,Пуск/RESETненажимал,попросилТОЛЬКОпрепусковуюпроверку30→35→40→45→50/RMS. ВыполненыGET,START/ARM/CLEAR/RESET/flash0. current_adc_apex_fix_r1/powered_preflight_r1/report.jsonpassedfalse:12свежихответовза13.366с,шина320..323В,HTTPошибок0,MCage≤44мс,новаяпараSAFE/VF/PWM0/ARM0,UART/CRCчистые,автонольready/stable/attempts3,историянеизменна,разгон5/снижение1. Ноstrictreadyfalseиз-зааппаратногособытияSD;двигательне запускали.

prestart_sd_event_r1 архивируетstatus/latest_status,аутентифицированныеREADONLY GET/bkin_traceиbreak_snapshot,sd_wave.bin,decoded_wave/report.json. ПерваяпопыткачерезWifiHmi.requestGETвернулаотказ,т.к.этотклиентпоумолчаниюнедобавляетtokenдляGET;послеиспользованстандартныйRequestссобственнымX-UNOQ-Control-Tokenкаквreaders,никакогообходавалидации. Независимыйдекодеризsealedcandidateсовпалсbackendпоeventtick/runs/channels/flags/samples.

Полныйсовместныйschema5захват:tick300427мс,период0.2мкс,2669отсчётов,2041состояние3HIGH/HIGH,307состояние0LOW/LOW,321состояние3HIGH/HIGH. PA6/BKINиTP23→1кОм→PA4 LOW61.4мкс,расхождение0,пульсзаписанполностью,flags513,timeout/DMA/overrunfalse. Snapshotтотжеtick:MOEfalse,неSTARTwindow,reference0,motorstate0,current/occurredfaults0в5мсстаромконтексте,Vbus10Впередзарядом. СобытиепроизошлопослепрошлойчистойпроверкиипривключениисиловогоДОШИМ. ЭтонаблюдаемыйLOWсдвухлогическихточек,неоднозначныйдиагнозвнутреннегобракаIPM;общиепомехиопорнойземли/питаниянеисключены.

СейчасSAFE/PWM0/ARM0,Vbus320В,SDHIGH/configoktrue,BIEfalse(IRQзамаскированпослезафиксированногоBreak),capture_runningfalse/first_record_readytrue. MC/BPfault5,reason8(MCSDK),currentmask0,occurredmask0x400. Не называтьUVfaultтолькопокоду5илиreason8:0x400драйвернаяBreakзащита. UARTошибокнет,ADCpeakhex«-»/good0—ADCcaptureсвободен. SDполнаяволнаimmutableиужезанята,first_start_windowпуст.

НикакогоCLEARнаэтойсиловойавариинеотправляли,никакихсбросов/перепрошивки/силовогопрогона/измененияпорогов. Текущийзапрос-проверказавершёнсреальнойблокировкой,необъявлятьготовностькSTART. Питание/проводкуоставилибезновыхпереключений. Конкретноеследующеедействиедлярассмотренияпользователем—однократныйштатныйACKсохранённогодопусковогособытияприSDHIGHиPWM0с проверкойBIEиактивныхfaultмасок,отдельноотSTART;подтверждениенапускещёнет. ПередлюбымACKсохранитьэтотархив(ужесохранён),непрятатьсуществованиеSDимпульса.

ЕслипользовательразрешитACK:действоватьштатнымCLEARодинразтолькоеслиSDустойчивоHIGH/MCSDKcurrentmask0/SAFE/PWM0/ARM0/первыйснимокстрогоMOEoff/неSTART,затемчитатьнеповторилсялиLOWиBIEtrue. Строгийtools/run_current_adc_apex_trial.pyсейчастребуетСВОБОДНЫЙSDcapture;послеCLEARпамятьSDостанетсязанятой,незаявлятьобратное. ДлябудущегоRMSиспытанияможноявноподдержатьАРХИВИРОВАННОЕсобытиедоSTARTпопрежнейпроверкеarchive_before_start(каквlegacy),сохранивSDHIGH/BKE/BIE/всеза шиты/95%RMSгейт;первыйSTARTsnapshotиADCcaptureнезависимы,полнаяSDволнаследующегособытиянеперезапишется. Этоограничениедиагностики,незащиты;политикунеподменятьмолча. Не требоватьновогоциклаHVразрядки/USBлишьрадиочисткиснимкабезоценкинеобходимости.

## 2026-10-25:2509/2510 на повербанках перед силовым — Wi-Fi/автоноль/SD/ADC PASS

Пользователь подтвердилобеплатынаповербанках,ПК/Saleaeотключены,15ВON,J1OFF,Пуск/RESETненажимал. Только прямой Wi-Fi GET:current_adc_apex_fix_r1/powerbank_idle_r1/report.jsonPASS. При загрузке были timeout/разрывHTTP/503,промежуточныеошибкисохраненысphasewarmup;затембезпостороннихдействийполучены16стабильныхответовза19.894сбезHTTPошибок. Новаяпара2509/2510 SAFE/VF/PWM0/ARM0,Vbus10В,MCage≤50мс(final21),current/MCpacketsprogress;transportcleantrue,CRC/sequence/UART/MC/BPfault/masks/ESTOP0. ВэтомзапросеSTART/ARM/CLEAR/RESET/flash0.

Автонольready1/stable3/attempts3,offsets[2068,2068,2066,2069],последниесырыеразмахи[27,31,31,26]. Историяиз3блоковполная/неизменная:stable1→2→3,reject/pathmask0. Means[2068,2068,2066,2068]/[2068,2068,2066,2068]/[2068,2068,2066,2069];spans[28,34,29,27]/[29,32,29,26]/[27,31,31,26];estimated3sigma1.093/1.523/1.378counts. ВотличиеотUSBпослепрошивки,наэтомхолодномстарте3успешныхблокаиз3попыток. Дополнительнойкалибровки/ACKне было.

SDHIGH/configok/BIE/capture_runningtrue/first_record_readyfalse,обеbreaksnapshotsпусты,breakwavehex«-»;ADCpeakhex«-»/good0/complete0—захватысвободны. ПроверкаRMS45/50подновымиокнамиНАЖЕЛЕЗЕещёнепроводилась,модель100%непереноситькакфакт.

Следующийфизическийшаг:включитьтолькоJ1черезsoft-startпризакрытомстенде;повербанки/15В/проводкуоставить,ПК/Saleaeотключены,Пуск/RESETненажимать. После подтверждения свежийpoweredpreflight. Разрешённыйбудущий30→35→40→45→50проводитьтолькоtools/run_current_adc_apex_trial.py(строгийvalidRMSбез75%исключения),одинSTART/STOP≤60с/watchdog3с/безCLEARвсиловомэтапе/безавтоповтора;послеSTOPвыгрузитьtools/collect_current_peak.py --candidatecurrent_adc_apex_fix_r1. Текущийзапростолькопроверка,двигательнезапускали.

## 2026-10-25:2509/2510 установлены/readbackPASS, RPC и автоноль проверены наUSB — PASS

Пользователь подтвердилJ1OFF/мультиметр<20В/обеUSBкПК/15ВON и разрешил2509/2510/readback. NucleoST-LinkCOM13определилась,Uno3880458060подняласьпослеожиданиябезновыхфизическихпереподключений. До записи SAFE/PWM0/10В/2507-2508. PackageverifyPASS. tools/install_current_adc_apex_fix.py --confirm-j1-off-meter-below-20v-both-usb --outdircurrent_adc_apex_fix_r1/installation_r1:1flashUno2509/1flashNuc2510,обеreadbackverifiedtrue. DownloadverifiedsuccessfullyиUNOQverificationPASSED. HMIserver/app.jsобновлены,calhashдо/послепрежнийa89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. START/ARM0.

Отличиеотпрошлыхзаписей:RPCсейчассамаответилановымиID,ноinstallerзавершилсяpassedfalseиззаmc_uart_error_flags2. Этобылнакопленныйfirst_uart_errorsFE,а неRPCtimeout. Снимокruntime_after_install.json:SAFE/PWM0/10В,mc_fault/bp_fault2,reason12,transport4,firstUART2,lastUART0,lastbad13,mc_badcnt2,CRC/seq0,MCSDKcurrent/occurredmasks0. Исходныйinstaller/report.jsonнепереписывали.

ДиагностикапередоднимштатнымACKархивирована:uart_before_ack_samples.json8ответов,g_goodпрогрессирует,bad2стабилен,новыхошибокнет. HOTPLUGUSART1ISRпо0x4001381c=0x631090,errorbits0. uart_latch_evidence.jsonпроверилSAFE/PWM0/ARM0/ESTOP0,bus≤20,SDHIGH,точноизвестнуюмаску4/2/last13. Послеобъявленияпользователюсделанровно1CLEARчерезштатныйавторизованныйWi-FiAPI:single_uart_ack_report.jsonPASS,безSTART/ARM/сервисныхвыходов/прошивки/дополнительногосброса. Ошибкаисчезла,неповторилась. Необходилиgate,несбрасывалипоциклу,неослаблялиникакихзащит. ПерваяпопыткасоздатьWifiHmiналокальномADBURLбылаотклоненаконструкторомДОлюбогоHTTP/команды;послеэтогоиспользованобычныйпрямойWi-Fi192.168.1.138:8080,валидациянеотключалась.

verify_current_shunt_idle.py --candidatecurrent_adc_apex_fix_r1 --outdirruntime_idle_usb_r1 --duration8 --require-sd-armedPASS:свежаяпара2509/2510,SAFE/PWM0/ARM0,Vbus10В,current/MCпакетыпрогрессируют,воВСЕХвыборкахfault/transport/CRC/sequence/UARTmasks0. HMI/calхешисовпали,данныеD7согласованыспрямымRAMчтениемstate0x20000860. Автонольready1/stable3/attempts7,offsets[2068,2067,2067,2069],последниесырыеразмахи[30,35,34,29]. История7блоковHMIсовпалавсемиполямисRAM0x200007e4;блоки2и4отклонялисьпооценкешума(varQ7=81/80),сохраненывидимыми;последние5,6,7стабильность1→2→3/reject0. Не говорить,что3успешныхиз3попыток. SDHIGH/configok/BIE/capture_runningtrue/first_record_readyfalse,ADCpeakhex«-»/good0 — захватысвободны.

TIM1HOTPLUGподтвердилOC4PEtrue,TRGOOC4REFtrue,BKEtrue,BKF9,MОEfalse,PSC0/ARR5312/RCR1/idleCCR44928,BDTR0x02393c72. Никакихизмененийсиловыхзащитнеобнаружено. installation_completion_r1.jsonPASSобъединяетreadbackиruntime;manifestinstalled/runtimepairtrue,rpc_pendingfalse. НенуженещёодинхолодныйUSBцикл—RPCработает. НовыйRMS45/50нажелезеещёНЕпроверен.

Следующийфизическийшагдляиспытания:перевестиобеплатынаповербанки,USBПКиSaleaeотключить,15ВоставитьON,J1остаётсяOFF,Пуск/RESETненажимать. После подтверждения читатьновыйавтоноль/историю/свободныезахватыпоWi-Fi;потомотдельноJ1ONпризакрытомстенде,свежийpoweredpreflight. Дляследующегоразрешённого30→35→40→45→50использоватьtools/run_current_adc_apex_trial.py(строгийVALIDRMS≥95%,без75%исключения),одинSTART/hostSTOP≤60с/watchdog3с/никакогоCLEARвсиловомтесте/автоповтора. ТекущееположениеобеплатыUSBПК,J1OFF,15ВON,двигатель/TP23→1кОм→PA4/шлейфбезизменений.

## 2026-10-25: покрытие45–50Гц доработано,2509/2510 собраны/проверены, НЕ установлены

Пользователь попросил достаточное покрытие/RMS на45–50Гц, проверку по записям и готовую прошивку без ослабления защит. В текущем запросе толькоhostсборки/тесты и финальныйGET. Стендпо-прежнему2507/2508 SAFE/PWM0. Последнее физическое подтверждение пользователя: повербанки/15В/J1ON,ПК/Saleaeотключены; финальныйGETэтогоэтапаужеVbus10В. Самопоказаниене доказываетположениеJ1;передзаписьюнужноподтверждениесостоянияпользователем. НиSTART/CLEAR/RESET/flash/удалённыхрестартов,ниперезаписикалибровки. СтарыйADCcaptureFROZEN NO_PEAKпослепрошлогопрогона,не свободен.

Новыйкандидат current_adc_apex_fix_r1,параUno2026102509/Nucleo2026102510. tools/prepare_current_adc_apex_fix.py,current_adc_apex_fix/{deadline.h,update.py},current_adc_apex_fix_selftest.py,seal_current_adc_apex_fix.py,install_current_adc_apex_fix.py. Причинапотерь: верхняяточкаADCбылаARR−384=4928иIRQдопускалсятольконавосходящейсчитательнойполовине,хотяRCR1UEVунасвнизу. ВновойпрошивкеактивнаяпоздняяточкаARR−128=5184,апертура112заканчиваетсяещё16tickдоапекса;высокийOC4REFимпульсне короче256tick≈1.506мкс. JEOSможнопослеапекса,покаосталось>2048tick≈12.047мксдоследующегоbottomUEV. ОтступыотВСЕХ3фронтов771/112tickНЕуменьшены,95%coverage/12samplespermsиRMSарифметикаcurrent_core.hбайт-в-байтпрежние. CCR1..3/Break/Vf/ADCsample24.5/клоки/защитыне менялись.

Текущийraw привязанкfull32bitpending_epochплюсзащёлкеCCR4иbottomupdate. Частные5флаговупакованыводинбайт,чтобывыделить4БstampбезростаRAM. pending_epochпроверяетсядоиспользованияraw,nextstampepoch+1публикуетсясочередью. ПослеJEOSобеJSQRдолжныбытьпусты(JQM1);непустаяочередь/ADC2missing/JQoverflow=>lost_sync. Уевапекс/позднийpublish/несовпадениеepoch=>явныйотказвыборки. В80Бtraceдобавленысмыслыflag2048(deadline),4096(epoch),8192(nonemptyJSQR);HMIдекодирует. АвтонольприMOEOFFработаетидажекогдаMCSDKнаSTOPмаскируетUPDATEIRQ:свежаяоднаинъекция/пустаяJSQR/низкаяшина/!active,coreс500мс+3блоками/оценкойшуманеизменён. ВысокаяшинаНЕстановитсянулём. IdleCCR4прежнийARR−384.

Офлайнаккуратность: adc_coverage_analysis_r1/variants.csvнанастоящемPWMкодепоказалпереход89%→100%геометрическихугловдля45/50Гцпри318/320/324В. Новыйwindow_sweep_r2PASS:5410800из5410800плановбезопасны,0nosafe/0geometryerrors,0..50Гцшаг0.1/3600углов/318,320,323В. Это геометрическаяпроверка,неаналоговаясимуляциядвигателя.

apex_selftest_r1PASS853161наНАСТОЯЩЕМIRQ:воспроизведены24rawкадраиздвухреальныхпредыдущихзахватов. Старые12геометрическиплохихraw2506всёещёнепринимаются,rawпик750countsсохранён. Старые2508последние12воспроизведеныпопрежнимвременнымточкам:10приняты,2отвергнутыкакраньше;дляэтих2впланировщикенайденыдругиебезопасные5184точки. ВнихновыеrawНЕизмерены,неиспользоватьстарыеrawкакбудтоониизновоговремени. saved_window_plans.csv, saved2508_replayed.bin содержатсравнение. ЧистаямодельactualPWM/Vf+центровойtimer+JSQR+реальныйIRQпри40/45/50Гцдаёт15999/16000принятыхпослеодногостартовогопропуска;каждыезавершённые200мсRMSwindowsвалидныпоНЕИЗМЕНЁННЫМгейтам. Синтетическийsinамп120countsдаётRMS84.856..84.880countsприэталоне84.853. ПровереныpostapexJEOS,full-epoch/wrap,ошибочныйапексUEV,очередьnonempty/overflow,IRQпрерываетсяUEVмеждуCH4иJSQR,zeroприUIE0иотказzeroпри320В. Модельтоковсинтетическая,physicalRMSfalse.

zero9071/display94539/UI22PASS,productionRPC/parser/zero_history/manual/calidentityPASS. Обесборкиуспешны,Nucleo0errors/0warnings,UnoLLEXTpass. RAMmargin4096Бне снижен,ADCIRQstack376≤384,publiccm_corelayoutи80Бcapturewireсохранены. ИсточникST: RM0440repetitioncounter/UEVpreload, RCR1beforeCENдаетunderflowUEV;вреальныхзаписяхupdateCNT~109/DIR0. HardwareWCETновойверсии/полнотатоков/масштабещёнепроверены.

Сealedmanifestиverification/report.jsonPASS. python tools/install_current_adc_apex_fix.py --verify-package-onlyPASS:Uno715ff879da097d2c66d6d078eba42ddc2fcabdbf038ff4828bbd53e6106a692f,NucHEX1adec4b8616b4d2cf29ddcdb698a023a9408743bd5b90e11e84e42a2cac0cadf. ДлябудущегострогогоRMSпрогонаtools/run_current_adc_apex_trial.pyставит2509/2510+zerohelperиОБЯЗАТЕЛЬНЫЙvalidRMS;частичныйdiagnosticрежим75%НЕприменятькэтойквалификации.

Следующийфизическийшагдлязаписи:выключитьJ1штатнымвыключателем;показаниемультиметра<20В;обеплатыперевестинаUSBПК. 15Вможнооставить,двигатель/TP23→1кОм→PA4/шлейфнетрогать,Saleaeне нужен. Послеподтвержденияпользователяtools/install_current_adc_apex_fix.py --confirm-j1-off-meter-below-20v-both-usb --outdir.../installation_r1,readbackобоихобразов/calSHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. RPCчастоне возвращаетсяпослеMCUflash,несчитатьreadbackнеуспешным;послеподтверждённыхобразовсочетатьхолодныйстартспереносомобеихплатнаповербанки/15ВON/J1OFFдляWiFiпроверкибезлишнихUSBциклов/повторныхflash. Не начинатьновуюсиловуюпробубезсвежегосостояния/разрешениянапрогон.

## 2026-10-25:2507/2508 повторный30→35→40→45→50Гц — PASS, старый≥6Aпик не повторился, RMS45/50невалиден

Пользователь явно разрешил один прогон с записью/автостопом и сравнением; питание/подключения безсмены. Нужен был отдельныйHOSTдиагностическийрежим: tools/run_current_adc_window_diagnostic.py использует существующий stagedrunner с новойпарой/zerohelper. В tools/run_current_shunt_5_10_5.py добавленперехватываемыйmeasurement_healthy и явноеимяполитики; defaultlegacyпо-прежнему требуетvalidRMS. Для2507/2508диагностическийрежим допускаетсвежиеокна≥75%покрытия(исходнаяплотность12/16samples/ms), НЕ выставляетCM_VALIDине меняет95%gateилиNoneвHMI. Сохраняютсяжелезные/связные/SD/zero/транспортныегейты, отсечениеADCclippingиstale, минимум2разных200мсокон/1снастуащейступени; watchdog3с,independenthostSTOP60с. Доактивации37чистыхhostnegativechecksPASS. Ниfirmware, ниcal, нипорогизащитне менялись.

Один запускtools/run_current_adc_window_diagnostic.py --confirm-powered-ready --profile30-to-50 --outdircurrent_adc_window_fix_r1/peak_trial_30_to_50_r1: PASS, ровно1START, все5ступеней пройдены, STOPчерез46.469сотзапроса(<60), SAFE/PWM0/ARM0, collectionerrors0, fault/current/occurred/CRC/sequence/UART0. Пользовательподтвердил ровноефизическоевращение иускорение. Шины318..324В(старыйпрогон317..321), физическоечислооборотовнезависимонеизмерено. Никаких CLEAR/RESET/flash/повторовпослеошибки. J1/15Востаютсявключены,платынаповербанках,ПК/Saleaeотключены,проводкане менялась.

Пассивный tools/collect_current_peak.py --candidatecurrent_adc_window_fix_r1 — PASS, traceCRCвалидный,1024Б/12кадров. peak_seenfalse, NO_PEAKtrue,post_shortfalse,626counts≈6.00558Aпорогне сработалнарегистрируемыхeligibleотсчётахдоSTOP, total_samples634556. Сохранены последние12кадровпри50Гц/STOP, это НЕmatched39.6Гцосциллограмма. Сырыемакс|counts|вних93, первыйстарыйtrigger750countsпри39.6Гц. Вnewфинальномкольце10safeпринятыхкадрови2небезопасныхотклонённых(одинужесMOEOFF), unsafeaccepted0, epochconsistent12/12, queueoverflowfalse. CCR4реальнодвигается4207..4275перед3мфронтом;приотсутствииокнапереходит4928сrejectflag1024. maxqueuepublish4.729мкс, прежнийзахват2.4мкс(разныепродолжительностинаблюдения,неназыватьуниверсальнымWCET).

Сравнение `peak_comparison_30_to_50_r1/comparison.json`, stage_comparison.csv: максимумноминальныхпиковсредиПОЛУЧЕННЫХD5оконпринятыхотсчётов7.195A→2.024A; это НЕсертифицированныйнепрерывныйфизическийпик. Поэтапам(rampincluded)30:1.468→1.727;35:1.631→1.362;40:7.195→1.650;45:6.524→1.832;50:5.411→2.024A. Встаромraw12/12геометрическинебезопасныипринимались,вновомunsafeaccepted0. Наблюдениеподдерживаетпричинупомехиизмерениявозлефронтов,ноодноиспытаниенеисключаетреальныекраткиетокии неметрологическаяквалификация.

Наустановившихсяступеняхnew30/35/40coverage99/99/95%,RMSvalid1;45/50coverage89/88%,CM_VALID0,RMS/peakвHMINone. Неполноепокрытиеявноотображено,никакойподменывалидности. Программаодноразовогодигностическогопрогоназавершиласьуспешно,полнаядостоверностьRMS0..50ещёНЕдостигнута. Следующийтехническийвопросприотдельномзапросе—полнотабезопасныхизмерений45..50Гц,неавтопрошиватьи неуменьшать771tickguardили95%gateдлявида. ADCcaptureтеперьFROZEN NO_PEAK, не свободен; SDзахватосталсясвободен. Дляповторнойrawзаписипотребуетсяосознанныйresetприбезопаснойподготовке,неавтосброс.

ФинальныйGETпослесравнениявpeak_comparison_30_to_50_r1/final_status.json:SAFE/PWM0/ARM0,свежийMC,всеfaultmasks0. Артефактывключаютhostrunnerhashи37checkselftest. Текущийзапросвыполнен;не включать/не запускатьничегоещёавтоматически.

## 2026-10-25:2507/2508 powered preflight после J1ON — PASS, START0

Пользователь подтвердил J1ONчерезsoft-start,15ВON,платынаповербанках,ПК/Saleaeотключены,Пуск/RESETне нажимал; запрос только проверить перед прогоном с пиками. Прямой Wi-Fi GET12ответовза15.542с: `current_adc_window_fix_r1/powered_preflight_r1/report.json` PASS. Пара2507/2508, SAFE/VF/PWM0/ARM0, шина320..322В(final322), MCage≤47мс(final31), softstartready1. HTTPошибок0,transportclean,пакетыprogress,всеMC/BPfault/current/occurredmasks0,ESTOP0. Автонольready/stable/attempts3,историяvalid/неизменна. SDHIGH/configok/BIE/capture_runningtrue/first_record_readyfalse; обеbreaksnapshotsсвободны, ADCpeakhex«-»/good0/complete0. Разгон5Гц/с,снижение1Гц/с,downmodecoast0. START/ARM/CLEAR/RESET/flash0. Питание/подключениянепереключали; шинаподсиловым.

Готовностьизмерений/захватапередоднимпрогоном подтверждена, но сампрогонвэтомзапросене разрешали/не выполняли. Следующийзапроснапрогонпотребуетhostдиагностическогоrunnerдля2507/2508: использоватьcurrent_zero_quality.ready напрямую, не legacyzero_okтолько2505/2506. Не запускать старыйrun_current_zero_noise_trial.py(онвыставляет2505/2506) и не подменятьегоRMSvalidгейты молча. All3geometry при50Гцдаёт~89%покрытия,исходный95%gateсохранён: непрерывнуюдостоверностьRMS на всехступеняхне обещать. Длядиагностическогозахвата нужно явноразделитьполнотуизмеренияRMSиаппаратнуюготовность/аварии;сохранятьNoneдляневалидныхRMS,проверятьrawстраницы/расписание/контекст иостановприошибкесвязи/SD/защит/тайм-аута. MCUоператорскийwatchdog3си независимыйhostSTOP≤60с сохранить. Никакойновойпрошивки/переходавFOC/снижениязащит/автоповтора.

## 2026-10-25: новая пара2507/2508 после холодного запуска на повербанках — RPC/автоноль/захваты PASS

Пользователь перенёс обе платы на повербанки с паузой5с,ПК/Saleaeотключены,15ВON,J1OFF,Пуск/RESETненажимал. Прямой Wi-Fi GET по192.168.1.138:8080: новаяпара2026102507/2026102508, SAFE/VF/PWM0/ARM0, Vbus10В, finalage17мс. Никаких ошибокHTTP;16стабильныхответовза21.037с,пакетыcurrent/MCпрогрессируют,transport_cleantrue,всеfault/current/occurredmasks0,ESTOP0. START/ARM/CLEAR/RESET/flash0вэтомэтапе. ПрежняяRPCpendingпослепрограммирования разрешилась холоднымстартом безповторнойпрошивки.

Автонольready1/stable3/attempts3,offsets[2067,2067,2067,2069],последниесырыеразмахи[37,32,28,26]. ИсторияD9valid1,неизменнаявовсех16ответах: стабильность1→2→3,reject/pathmasks0. Means[2067,2067,2067,2069]/[2067,2067,2066,2069]/[2067,2066,2067,2069]; rawspans[28,32,31,28]/[34,34,44,25]/[37,32,28,26];estimated3σ1.569/1.186/1.569counts. Сырой44не скрыт; старыйspan40неgate,новаяоценкасреднего+межблочнаястабильность проходят. SDHIGH/configok/BIE/capture_runningtrue/first_record_readyfalse;обеbreaksnapshotsпусты,breakwavehex«-». ADCpeakhex«-»/good0/complete0 — свободен.

Артефакты current_adc_window_fix_r1/powerbank_idle_r1/{report.json,status.jsonl};completion_after_powerbank_r1.jsonPASS объединяетраньшеподтверждённыйreadbackс текущейruntimeпарой. Manifestinstallation_runtime_pair_verifiedtrue/rpc_pendingfalse/adc_idle_zero_verifiedtrue. Историческийinstallation_r1/report.jsonpassedfalseне переписан:тамреальныйtimeoutвмоментустановки. Calhashпроверендо/послезаписи,неперезаписывался. Проверкаоконподнагрузкой и масштaба токовещёНЕ выполнена.

Следующийшаг — включитьтолькоJ1черезsoft-startпризакрытомстенде,повербанки/15В/проводкуоставить,ПК/Saleaeотключены,Пуск/RESETненажимать;затемpoweredpreflight. Вэтомзапросемоторнезапускался. Длябудущегодиагностическогопрогонасновымall3ADCplannerзаранееподготовитьявнуюполитикунеполногоRMSпокрытия:при50Гцгеометриядаёт~89%окон,95%gateнеослаблять,старыйrunnerсобязательнымcurrentvalidможетSTOP. Сырыепикисохраняютсядажедлягеометрическиплохихкадров,ноневходятвRMS. Необъявлятьреальноепадениепиковдоновогозахвата.

## 2026-10-25:2507/2508 записаны и проверены чтением, калибровка сохранена; RPC pending

Пользователь повторно подключил обеUSBпрямокПК, подтвердил J1OFF/мультиметр<20В/15ВON и разрешил запись/readback. Теперь ST-Link003A002C3335510933383531/COM13 определяется; Uno3880458060 появиласьпослезагрузкибезновыхпросьб. До записи ADBHTTPGET:2505/2506 SAFE/PWM0/Vbus10В/age49мс. Package verifyPASS. tools/install_current_adc_window_fix.py --confirm-j1-off-meter-below-20v-both-usb --outdircurrent_adc_window_fix_r1/installation_r1 выполнен: ровно1flashNucleo2508и1flashUno2507. Nucleo Downloadverifiedsuccessfully, Uno verificationPASSED с verify_restartконфигурацией. Это штатная верификация после единственной записи, повторной перепрошивки не было. HMIserver/app.jsустановлены, SHAсовпали; calibrationSHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17 до/послепрежний. START/ARM/CLEAR0.

installer/report.json passedfalse толькоизза Runtimeverificationpending:timedout; обаreadbackverifiedtrue. После60с иодногодополнительногоGETRPC всёещёtimeout. ПоSSH rootarduino-router.service активенPID554, unoq-hmi.service активенPID1062; хеши правильные. Никакихповторныхreset/restartслужб/flash/обходасudoне делали. imageswritten/installedtrue относятся к образам, runtimepairverifiedfalse/rpcpendingtrue сохранены вmanifestиinstallation_readback_result.json. Не заявлятьвебавтоноль/свежуюсвязьуже проверенными.

НезависимаяNucleoпроверкачтениемHOTPLUG (безreset/halt): state0x20000860, zero_ready1,zero_bad0,attempts3,stable3,lastreject0,offsets[2067,2068,2067,2070],rawspans[32,49,33,49]. TIM1регистры72Бпо0x40012c00:OC4PEtrue,TRGOOC4REFtrue,BKEtrue,BIEtrue,MOEfalse,PSC0,ARR5312,CCR44928. Доказательствавinstallation_r1/{zero_state_hotplug.json,tim1_checks.json,*log}. Дополнительногоизмененияfirmwareнет.

Следующийфизическийшаг объединитьснормальнымпереносомдляиспытания: обе платысUSBПКнаповербанки,15ВоставитьON,J1остаётсяOFF,Saleaeнеподключать,Пуск/RESETненажимать. ЭтоодновременнохолодностартуетLinuxUnoдляRPCиNucleo,безлишнегокругаUnoUSBкПК. После подтверждения ждатьзагрузкуи читатьновуюпару/zerohistory/SD/ADCпоWi-Fi; не объявлятьшум/пикиустранёнными. Не включатьJ1ипускдопроверки. При будущей диагностике50Гц учитывать no-safe~11% и исходный95%RMSgate, не подменятьvalid и не запускатьстарыйrunnerсожиданиемполногоRMSбезизмененияявнойполитикидиагностическоготеста.

## 2026-10-25: запись2507/2508 разрешена, но USB обеих плат не определяется; Flash0

Пользователь подтвердил J1OFF, мультиметр<20В, обеUSBкПК,15ВON, разрешил запись/readback. Package verify-only PASS (Uno SHA26ebc2b2c0335306218595cbbdef1d218e0534e5495aaf4505a25d735e003e15, Nuc HEX598c4dc2f9dddb31580011dec7506a36b765165919772aa344d8da9333cf1466). Ни MCU, ни HMI ещё НЕ обновлены. Полный installer не запускали, так как перед ним отсутствуют USBустройства.

Проверки: adbdevices пуст; adb -s3880458060 get-state после45с ожидания device not found; ArduinoCLIвидиттолькоCOM3/COM4сдругимиserial, целевых нет; WindowsPresentOnly не содержит3880458060/003A002C3335510933383531; CubeProgrammer-lstlink: NoST-Linkdetected. Одна PnPscan попытка отклонена Windows Accessisdenied, без обхода админправ/сбросаUSBконтроллеров. Это не RPCпадение: прямойWiFiGET подтвердил старуюпару2505/2506 SAFE/PWM0/Vbus10В/age30мс. Не заявлять, что прошивки записаны, и не запускатьповторно старый моторныйпрогон.

Артефакты current_adc_window_fix_r1/installation_usb_check_r1/{report.json,adb_devices.log,board_list.json,stlink_list.log}. FlashUno0,FlashNuc0,START/CLEAR/RESET0;калибровкуне трогали. Нужен физическийUSBдоступ: приобщемхабе/переключателе выбратьэтотПК, либо подключитьобеплаты напрямуютемижекабелямисданными (Nucleo черезST-Link). J1остаётсяOFF,15Вможнооставить,проводку/двигательнетрогать. Не запрашивать повторное подтверждение разрядки без новогоJ1ON. После USBпоявления продолжить уже разрешённуюзапись штатным tools/install_current_adc_window_fix.py --confirm-j1-off-meter-below-20v-both-usb --outdir .../installation_r1; readback/calhash/runtimeidle.

## 2026-10-25: all-three-leg ADC window исправлен, новая пара2507/2508 собрана и проверена, НЕ установлена

Пользователь попросил исправить окно, проверить на реальном захвате и подготовить прошивки/инструкцию записи. Текущий стенд по-прежнему на2505/2506, повербанки/15В/J1ON, USBПК/Saleae отключены. В ходе подготовки только хостовые сборки/тесты и один финальный GET (SAFE/PWM0); START/ARM/CLEAR/RESET/flash0. Никакого нового пуска не было.

Кандидат `current_adc_window_fix_r1`, пара Uno2026102507/Nucleo2026102508. tools/prepare_current_adc_window_fix.py, tools/current_adc_window_fix/window_irq.c, tools/current_adc_window_plan.h. Планировщик сохраняет старуюточку4928, когда безопасна; иначе выбирает интервал между всеми3фронтами с771tick до и112tick после триггера. CH4 preload включён явно; только его shadow обновляется для следующего UEV вместе с очередью JSQR. Текущий отсчёт проверяется по отдельной защёлке CCR текущего updateepoch и старому trigger; поля latch теперь volatile. Отслеживание epoch продолжается после freeze peak. JQOVF/нетADC2 даёт lost_sync; геометрия/контекст/план безsafewindow отклоняются явно. Следующий контекст публикуется до статистики. CCR1..3/Break/защиты/Vf/автоноль/масштаб/арифметикаRMS/критерии95% и12samples/ms не изменены.

Сыройпик продолжает запускать диагностический capture даже при плохой геометрии, но не включается в RMS/peakмониторинга. В80Бtrace новыйflag1024 означает отказ all3geometry, acceptedflag64 остаётся независимым; HMIдекодер его показывает. Rawкольцоimmutable/CRC/wireсхема не изменены. HMI явно пишет о недостаточном покрытии/фронтах/рассинхронизации/насыщении; недостоверныйRMS остаётсяNone. Unoлогика полностью прежняя, меняются только identity/peerконстанты для согласованной пары.

`window_selftest_r2/report.json` PASS358413: настоящийIRQ иplanner; 12реальных кадров сraw/CCRиз предыдущего захвата проиграны без подмены времени данных. Все12старыхточек отклонены, длявсех12естьбезопасныеальтернативныеCCR4. Для triggerновыйCCR4=3963 вместо4928; это расчётнаядругаяточка, новыйток там НЕизмерен. Raw1719/1665 и восстановленныеcounts348/402/−750 сохранены и прошлиwire→HMI. Проверены8kцикловдинамическогостобра+10kсменывсех3CCR/пар и10kOFFIRQавтонуля, отсутствующийADC2/overflow/epochrace/contextmismatch/nosafewindow/freeze, реальный1162-countсигнал вsafeокне не обрезается, CRCnegative. `window_replay.csv` — old/newвремена.

`window_sweep_r1` PASS на настоящем PWM/Vfкоде0..50Гц,3600углов,шины318/320/323: 5296554safe,114246nosafe,geometryfailures0. ВАЖНО: при50Гц только3204из3600угловsafe (~89%). Не ослаблять95%gateи не объявлятьполныйRMSдостоверным; старыйrunner30-to-50 останавливается, еслиcurrentvalid0. Для будущего чистодиагностического прогона потребуется явно учитыватьнеполноепокрытие и сыройзахват, сохранивфизическиезащиты, анеподменятьvalid. В этой итерациинеизменятьPWMдлясозданиядополнительныхокон.

`zero_selftest_r1` PASS9071,автоноль/history/RPC/CRC; display94539,UI22; productionRPC/calibrationidentity/manualcompatroundtrip PASS. Обеbuilds успешны,Nucleo0errors/0warnings,UnoLLEXTpass. RAMmargin4096Бпрежний,IRQstack368Б≤384. РеальныйWCET/пикинажелезе ещё не проверены. tools/seal_current_adc_window_fix.py запечаталhash иverification/report.json; инструментыhostonly. `python tools/install_current_adc_window_fix.py --verify-package-only` PASS, flash0. Non-gatingmcsdkpreflightexit2—не новый аппаратный отказ, сборка успешна.

Следующий шаг — ровно подготовка USBдля записи: выключитьJ1 штатнымвыключателем; после показаниязаранееподключённогомультиметра<20В перевестиОБЕплатысповербанковнаПКUSB. 15Вможнооставитьвключёнными; двигатель,TP23→1кОм→PA4,шлейф оставить;Saleaeненужен. После подтверждения пользователя применять tools/install_current_adc_window_fix.py --confirm-j1-off-meter-below-20v-both-usb --outdir .../installation_r1. Сохранитьcalhash a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17, readbackобоихобразов. ХолодныйUSBUnoзапрашиватьтолькопослеобоснованногоподтвержденияRPCпроблемы, датьLinuxзагрузиться. Никакой записи покаJ1ON.

## 2026-10-25: один диагностический прогон30→35→40→45→50Гц выполнен — PASS, пик записан

Пользователь явно разрешил профиль с захватом и автостопом, питание/подключения без изменений. Выполнен tools/run_current_zero_noise_trial.py --confirm-powered-ready --profile30-to-50, каталог peak_trial_30_to_50_r1. Ровно1START, без CLEAR/RESET/flash, все5ступеней установились, STOP подтверждён через37.843с от запроса, раньше hostdeadline60с. SAFE/PWM0/ARM0, fault/current/occurred/CRC/sequence/UART/transport0, collection_errors пуст. Bus317..321В. Пользователь подтвердил ровное физическое вращение и заметное ускорение до автостопа. Питание менять не просили, J1 и15В остаются включены, ПК/Saleae отключены, платы на повербанках.

Пассивно выгружен tools/collect_current_peak.py --candidatecurrent_zero_noise_r1: peak_capture_30_to_50_r1, CRCPASS,1024Б, все12кадров (5до+trigger+6после), peak_seentrue,post_shortfalse, trigger39.6Гц. analysis.json хранит факты/ограничения. Первый пик750counts/номинально7.195A на восстановленнойW: pair0=U1/V2, raw1719/1665 при offsets2067/2067, countsU348,V402,W−750. Соседние raw до2419/2209, после2153/1965; оба измеренных канала меняются одновременно. Все12epochсогласованы, queueoverflowfalse, очередьmax2.4мкс. На trigger CCR[699,2511,4757,4928], исключённаяW переключается за171tick≈1.006мкс доADCstrobe, меньше существующего771tick≈4.535мксsettlingguard, который проверяется только по выбраннойпаре. Во всех12кадрах excluded_compare_inside_assumed_acquisition=false: это НЕ доказательство буквального попадания фронта внутрь112tickапертуры, а наблюдение слишком близкого предшествующего фронта. CCRсофтзащёлка, не прямойactive readback.

Максимумы среди полученных окон RMS[0.929,0.885,0.898]A, peak[6.572,4.509,7.195]A; масштаб не квалифицирован, не объявлять эти числа независимым измерением реального тока. Сильный признак загрязнения измерения переключением, но реальные короткие токи и прежние11A не исключены. Следующая доработка при разрешении пользователя: окноADC с отступами от фронтов ВСЕХ3плеч и честной маркировкой непригодных отсчётов, сохранив сырые данные, CCR1..3/защиты/Vf. Никакую новую прошивку и повторный пуск в этом запросе не делать.

## 2026-10-25: после включения J1 перед диагностическим прогоном — PASS, START не отправляли

Пользователь подтвердил J1 через soft-start, 15 В ON, обе платы на повербанках, ПК/Saleae отключены, Пуск/RESET не нажимал. Запрос только проверить перед прогоном. `current_zero_noise_r1/powered_preflight_r1/report.json` passed=true, 12 последовательных ответов прямого Wi-Fi GET, HTTP ошибок0. Пара2505/2506, SAFE/VF/PWM0/ARM0, Vbus321В (оба поля), свежая связь28мс, пакеты прогрессируют, CRC/sequence/UART/transport/fault/current/occurred masks0. Softstart ready1, автоноль3/3 с полной неизменной историей, отклонений0. SD HIGH/config_ok/BIE/capture_runningtrue, first_record_readyfalse; обе break snapshot пусты; ADCpeak пуст. Никакой RESET/CLEAR/ARM/START/flash не выполнялся.

Настройки разгона5Гц/с, снижения1Гц/с, downmode_coast0 соответствуют существующему stagedrunner. Испытание с пиками ещё не выполнялось: не расходовать immutable ADC capture лишним коротким5Гц STOP. Для следующего единственного профиля30→35→40→45→50Гц применять tools/run_current_zero_noise_trial.py --profile30-to-50 с независимым STOP≤60с и штатным операторским watchdog3с, только по разрешению пользователя на прогон. Свежий preflight обязателен внутри runner; никакого CLEAR/повтора после ошибки. После STOP выгрузить collect_current_peak.py --candidate новыйкаталог. Проводку и питание сейчас менять не требуется; J1 включён, USB кПК/Saleae не подключать.

## 2026-10-25: обе платы на повербанках, автоноль и история PASS по прямому Wi-Fi

Пользователь подтвердил обе платы на повербанках, USB ПК и Saleae отключены, 15 В ON, J1 OFF, RESET не нажимал. Только GET /api/status по 192.168.1.138:8080; START/ARM/CLEAR/RESET/flash 0. Артефакты: current_zero_noise_r1/powerbank_idle_r1/report.json и status.jsonl. При загрузке были разрывы HTTP и 503, затем связь восстановилась без действий с питанием или RPC. HTTP-переходные ошибки сохранены отдельно от нулевых UART/CRC-счётчиков.

Пара 2505/2506, SAFE/PWM0/ARM0, Vbus10В, mc_fault/bp_fault0, свежая связь, пакеты прогрессируют. В последнем окне21 ответов автоноль ready1/stable3/attempts3 и история неизменна: 1→2→3, reject0/failed_paths0. offsets [2067,2067,2067,2069], последний rawspan [47,38,40,64]. Оценка3σ среднего блоков1.546/1.378/1.186 ADCcounts; сырые размахи остаются видимы и не скрыты. Новая проверка среднего проходит на реальной конфигурации повербанков; физическая причина сырых выбросов и масштаб токов ещё не установлены. SD HIGH, config_ok/BIE/capture_runningtrue/first_record_readyfalse, ADC peak пуст — захваты свободны. По Wi-Fi RAM напрямую не читали, совпадение RAM было отдельно проверено на предыдущем этапе ПК.

Следующий физический этап для ранее согласованного диагностического прогона: включить только J1 через soft-start при закрытом стенде, оставить повербанки/15 В/проводку, ПК/Saleae отключены; Пуск и RESET не нажимать. После явного подтверждения проверить свежий SD/шину/zero и сохранить захват для одного согласованного прогона. Текущий запрос — проверка без силового, двигатель не запускался.

## 2026-10-25: после USB-переподключения связь 2505/2506 и автоноль проверены на ПК — PASS

Пользователь подтвердил: переподключил только USB Uno Q, Nucleo и 15 В не трогал, J1 выключен. После загрузки RPC восстановилась. Новых команд Flash/RESET/CLEAR/START/ARM не отправляли; выполнены GET, проверка хешей HMI/калибровки и ST-Link HOTPLUG чтение.

Окончательная проверка: `current_zero_noise_r1/runtime_idle_r2/report.json`, passed=true. Пара 2026102505/2026102506, SAFE/PWM0/ARM0, Vbus 10 В, автоноль ready1/stable3/attempts3, offsets [2069,2069,2067,2070], последние raw spans [27,48,41,35]. UART/current packets прогрессируют, проверяемые счётчики ошибок не растут. Масштаб токов не квалифицирован; idle не является измерением RMS двигателя. SD HIGH/config_ok/BIE, захват свободен; ADC peak ожидает событие. HMI хеши совпадают, калибровка сохранена.

История трёх блоков подтверждена на проводе и напрямую в RAM: `runtime_idle_r1/history_comparison_r2.json` и `zero_history_direct_r2.log`. Адрес zero_history из точного link map: **0x200007e4**, размер 120 Б. Первое ручное чтение по 0x200007e8 было смещено на 4 Б, не использовать его как доказательство совпадения. Все means/spans/stable/reject/path masks и квантованная оценка совпали при правильном чтении, затем с финальным runtime_idle_r2. Блоки: means [2068,2068,2067,2069]/[2069,2069,2067,2070]/[2069,2068,2067,2069]; spans [33,35,32,28]/[40,34,52,34]/[27,48,41,35]; stable 1→2→3, reject0, оценки 3σ 1.677/1.523/1.272. В более раннем runtime_idle_r1 была иная история; непрерывность MCU между этими проверками не доказана, причину изменения не утверждать. Текущие RAM и веб-история согласованы.

`completion_after_usb_r1.json` PASS, manifest runtime/RPC flags обновлены. Факт проверки относится к USB ПК/15 В ON/J1 OFF. Шумовой случай обеих плат на повербанках ещё не проверен. Следующий шаг: обе платы с ПК на повербанки, USB ПК/Saleae отключены, 15 В оставить, J1 пока выключен, RESET не нажимать; затем проверить Wi-Fi, автоноль и свежую историю перед силовым этапом. Двигатель в текущем запросе не запускался.

## 2026-10-25:2505/2506 установлены/readbackPASS; автоноль Nucleo3/3 подтверждён напрямую, RPC Uno пока pending

Пользователь подтвердил обеUSBкПК,J1OFF,15ВON,двигатель/проводку безсмены и явно разрешил запись/проверку. Uno появился вADB после загрузки без просьбы повторно менятьUSB. `current_zero_noise_r1/installation_r1/report.json` сохранён: первыйpreflightHMI503, flash0. Затем GET восстановился сам и штатный installer выполнен в `installation_r2`: ровно1FlashNucleo и1FlashUno, оба образа проверены чтениемобратно. HMIserver/app.js обновлены. Calhashдо/после a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. START/ARM/CLEAR0, J1не включался.

После записи RPC/get не отвечает (timeout), поэтому installation_r2/report.json passedfalse, runtimepairverificationpending; readbackPASS от этого не отменяется. Выполнен один дополнительный verify_restart НОВОГО образа2505 без erase/writeflash (`post_verify_restart.log`), RPC не вернулся. Затем диагностическое halt/read/resumeUno (`uno_rpc_snapshot.log`, SCB CFSR/HFSR0, coreidle/mainспит, не доказанHardFault) и один scoped restart принадлежащегоarduino процессаHMI с проверкойhash/owner/cwd/Restartalways/cal; PID1057→1220, `hmi_restart.log`. Всё ещёtimeout. Root arduino-router PID578 принадлежитroot, системныйrestartнедоступенбезадминправ; не пытаться обходить права и не перепрошивать вслепую. Физическую причинуRPCне установили; гипотезуOOM не выдавать за факт: corekernelheap32768, libc mallocarena=-1 (всядоступная), UPDATE_THREAD_STACK_SIZE500, faultрегистры0. Никаких новыхsourceправок/сборок послеустановки не делали.

Независимо отUno проверена Nucleo черезST-LinkHOTPLUG безreset: точнаяmap state0x20000860,size0x128; zero_history0x200007e8,size0x78. `installation_r2/zero_state_direct.log`, `zero_history_direct.log`, `autonull_direct_report.json` PASS. Автонольready1/bad0, attempts3/stable3, offsets2067/2068/2067/2070. Блок1:mean2067/2067/2067/2069,rawspans30/35/34/30,stable1/reject0,estimated3σmax~1.930. Блок2:2067/2068/2067/2070,spans30/35/40/28,stable2/reject0,estimate~1.569. Блок3:2068/2068/2068/2070,spans36/38/36/30,stable3/reject0,estimate~1.299. Это реальныеRAMданные наUSBПК; шумовойслучайповербанка ещё не повторён, токовыймасштаб/аппаратнаясинхронность не квалифицированы.

`installation_state.json` и manifest отмечают installed/imageswritten/readbackverified/calunchangedtrue, adc_idle_zero_direct_memory_verifiedtrue, rpc_pendingtrue/installation_runtime_pair_verifiedfalse. Исходныйнеуспешныйreportне переписывать. Следующий конкретный шаг пользователя: вынуть ТОЛЬКОUSBUnoQна5сек и подключитьобратно кПК для холодногоLinuxстарта; NucleoUSB,15В,проводку оставить,J1OFF. После подтверждения только чтением проверить новуюпару2505/2506,SAFE/PWM0/ARM0,Vbus<20,historyD9 complete3/3, zero3/3, SDHIGH/freecapture иADCpeakempty, hashes/calibration. Не делать повторныйFlash, не сбрасыватьNucleo/историю, не запускатьдвигатель. ЕслиRPC снова не заработает, диагностироватьпакет/bridge/память, а не бесконечно проситьcoldcycle.

## 2026-10-25: исправление проверки автонуля/история блоков2505/2506 готовы, НЕ установлены

Пользователь явно запросил разобраться с U1/W2 и исправить автоноль для прогона. В этом этапе только локальный код/архивы/официальные материалы ST; hardware commands0, START/ARM/CLEAR/RESET/Flash0. Физически последняя конфигурация: обе платы повербанки, ПК/SaleaeOFF,15ВON,J1OFF,последнийVbus10В. На платах остаётся2503/2502 с отклонённым автонулём; действующие образы/исходники не изменены.

Подготовлен и запечатан `artifacts/live_bench_20261024/current_zero_noise_r1`, новая пара Uno2026102505/Nucleo2026102506, источники Nucleo=current_peak_capture_r1/Uno+HMI=uno_display_order_r2. Immutable vendor деревья скопированы hardlink без правок; mutable Inc/Src/Uno/HMI — отдельные файлы. `tools/install_current_zero_noise.py --verify-package-only` PASS; запись ещё не выполнялась.

Выявлен недостаток старой программной отбраковки: смещение уже оценивалось средним256отсчётов, но допуск зависел от одиночных extrema(max-min<=40). По одним сохранённым min/max49/46 и округлённым средним нельзя восстановить временную последовательность или доказать физическую причину шума. Настоящей записи всех исходных256отсчётов нет. На синтетической последовательности с ТОЧНО теми же min/max U1=2054..2103/W2=2056..2102 старый настоящийcore воспроизводит attempts8/stable0/zero_bad; редкие выбросы почти не смещают среднее. Широкий постоянный шум с теми же extrema — другая совместимая последовательность, которую новый критерий продолжает отклонять. Не выдавать это за replay отсутствующей реальной временной серии или доказательство аппаратного дефекта.

Новый критерий явно меняет метод проверки, а не увеличивает40: для256сырьевыхотсчётов считается большая из оценок дисперсии среднего по отдельным отсчётам и по четырём неперекрывающимся группам64. Требуется оценка3σ_среднего<=2ADCcounts и прежние3последовательныхсредних в пределах2counts, максимум8попыток и mean1600..2500 сохранены. Любой сырой код<16/>4079 отклоняет блок. Raw40 теперь справочная величина, D7contract byte34=0/bytes36:38=3,2; UI не называет40 допускающим порогом. Это инженерная оценка, а не метрологическая гарантия независимости/нормальности; эмпирические группы и межблочная проверка ограничивают коррелированные и медленные изменения. Шумовая первопричина АЦП ещё не идентифицирована.

Изменён порядок IRQ: следующая пара/JSQR публикуется ДО расчёта статистики, после этого выполняютсяcm_sample и диагностическая запись. Аппаратный strobe/clock/sampletime не изменены. Сбор80Бpeakкадра при полностью неактивном приводе больше не выполняется. Active cm_sample/cm_window_valid/cm_publish/choose_pair/pair_window и все силовые/Vf/vendor/защиты/командныйUART/калибровка сохранены. Пик1162ADCcounts при active остаётся в настоящемcore без усреднения/обрезки.

История всех завершённых3..8блоков сохраняется вNucleo:120Б (8×15). В каждом блоке четыре средних, четыре сырых размаха, stable/reject, маска каналов и квантованная максимальная оценка дисперсии среднего. Размах>255 хранится как нижняя граница255 с отдельной маской, последнийD7 по-прежнему содержит точные16битныеmin/max. Меток времени отдельного блока в15Бистории нет; порядок фиксирован индексом. D9 уникален, кадр43БCRC32C, страницы отправляются толькоMOEoff вместо одного существующего слотаD5, без роста5ppsмониторного потока. АктивныеD5/D6/D7 имеют прежнее расписание. Uno собирает immutableисторию, очищает её при паденииD7HALtick/resetpeer; подPWM вRPC передаётся уже сохранённая история, D9 UART подPWM запрещён. HMI показывает все причины блоков, а не только последнюю очищеннуюмаску. Peer/CRC/контракт проверяются.

`zero_noise_selftest_r6/report.json` PASS9071: настоящийcore/encoder/wire/HMI;3000рандомизированных четырёхканальных случаев сравнивают целочисленную дисперсию с независимым longdouble двухпроходным эталоном; проверены rail0/4095/overflow. Новая проверка отклоняет постоянный24-countшум (старыйпорог40его допускал), коррелированный6-countсигнал, дрейф, смещение, насыщение и одиночный1162выброс при автонуле; sparse49/46 проходит при устойчивом среднем. История успешных3 и неуспешных8блоков проходитencode→CRC→Uno→Python. `peak_selftest_r2` PASS42624, `display_selftest_r2` PASS94539, `collector_selftest_r1` PASS, UI22 и настоящийRpcBridgeparser PASS. ДисплейX+Y2503 сохранён; физическая сверка10/01 всё ещё не сообщена пользователем.

Обе целевые сборки успешны, Nucleo0errors/0warnings, UnoLLEXTpass. _end0x20006a00, запас сверхminheap/stack4096Б (не снижать этот gate), ADCIRQstack320Б/currentpacket376Б. Аппаратный WCET ещё не измерен. Негейтящийbuildpreflight exit2 не являетсяHVразрешением. `verification/report.json` и source/build/testSHA запечатаны. Установленные predecessorhash проверены и не изменены.

Инструменты: prepare_current_zero_noise.py/install_current_zero_noise.py/seal_current_zero_noise.py; current_zero_quality.py для новой готовности; verify_current_shunt_idle.py поддерживает новый критерий и boundedwait истории, а не maxspan40; collect_current_peak.py --candidate новыйпуть; run_current_zero_noise_trial.py использует прежнийbounded stagedrunner на новойпаре (не запускался). Приготовление ПО завершено, следующий физический шаг только для записи: J1 остаётсяOFF, подключить ОБЕ платы кПКUSB вместо повербанков,15В можно оставить, двигатель/TP23→1кОм→PA4 не менять, Saleae не нужен. Подтверждённая низкая шина сохраняется, нового включенияJ1 не было. После подтверждения пользователя штатный installer с gate J1OFF/метр<20В/обеUSB, readback/calhash; затем реальная проверка автонуля безсилового. Не объявлять проблему физически устранённой до этой проверки и не запускать мотор автоматически.

## 2026-10-25: после переноса Uno на повербанк связь восстановилась, latch7 отсутствует; отказ автонуля измерен на U1/W2

Пользователь подтвердил: Uno на повербанке, обеUSBПК/Saleae отключены,15ВON,J1OFF,RESET не нажимал. Первичная коллекция `uno_display_order_r2/wifi_before_trial_r1` сохранена с RemoteDisconnected/0статусов; по SSH службыLinux/HMI/router были запущены. Позднее статусы появились без перезапуска/перепрошивки. `wifi_before_trial_r2/summary.json` PASS:10с/9свежихстатусов, пара2503/2502,SAFE/PWM0/ARM0,Vbus10В,UART CRC/sequence/flags0, transport0/fault0/masks0. Сохранённой программнойблокировки7 больше нет, CLEAR не понадобился и не отправлялся. START/ARM/CLEAR/RESET/Flash от агента0.

`wifi_before_trial_r2/preflight_report.json` passedfalse по автонулю:ready0/CM_ZERO_BAD16,attempts8/stable0,lastreject1 (разброс блока). Последние offsets2068/2068/2067/2069 в обычной области; пакетD7 передаёт живые min/max последнего блока: U1low2054/high2103/span49>40; V1 2052/2085/span33; V2 2052/2082/span30; W2 2056/2102/span46>40. Теперь конкретная причина отбраковки последнего блока установлена по самим отсчётам; первопричина разброса (аналоговый тракт/питание/выборка/помехи) пока не доказана. Это не измерение прежних11А и не доказательство их физического происхождения.

SDHIGH/BIEtrue/configok/capture_runningtrue/firstrecordfalse; ADCpeak«-» — захваты свободны. Силовое/мотор не включались. Критерии40counts/3blocks/8attempts/2countdrift не изменялись. ПовторныеRESET вслепую не назначать и не сбрасывать отсутствующий transportlatch. Пользователю сохранить текущую конфигурацию,J1OFF. Следующая содержательная работа — диагностировать нулевыеADC/историюблоков до нового силовогоцикла; новая прошивка для этого ещё не подготовлена/не записана. Последняя визуальная сверка10/01 пользователем также пока не сообщена.

## 2026-10-25: на вопрос «что дальше» прочитан свежий статус; следующий шаг — только перенос Uno на повербанк

`uno_display_order_r2/after_display_next_step_r1/status.json`: свежая2503/2502, SAFE/PWM0/ARM0,Vbus10В, age14мс. Автоноль теперьready1/stable3/attempts3, spans36/37/32/26. SDHIGH/BIEtrue/freecapture; ADCpeak«-». Watchdoglatchtransport7/fault2/reason13 после программирования Uno сохранён, masks0/0/UARTflags0. В этом этапе только GET, CLEAR/START/RESET/Flash0. Не утверждать готовность к моторному START, пока latch не обработан на свежей автономной связи.

Последняя подтверждённая физическая конфигурация: UnoUSBПК, Nucleoповербанк,15ВON,J1OFF,SaleaeOFF. Следующий операторский шаг — перевести только UnoQ сПК на повербанк, Nucleo/15В не трогать, J1 пока OFF. После подтверждения проверить свежуюWi-Fi связь и автоноль/SD/ADC, сохранить watchdogснимок и обработать только известный programmingtimeout отдельным контролируемым действием приJ1OFF; не назначать RESETпоинерции и не сниматьреальныеBKIN/MCSDKошибки. Затем физическое включениеJ1 и согласованный одиндиагностическийпрогон сADCзахватом/STOP. Сейчас силовое не включалось и двигатель не запускался. Визуальная сверка10/01 от пользователя пока не получена.

## 2026-10-25: Uno-only исправление дисплея2503 установлено; связь/буфер проверены, ждём визуальную сверку

Пользователь подключил только Uno Q к ПК; Nucleo оставил на повербанке,15ВON,J1OFF. `uno_display_order_r2/installation_r1/report.json` сохранён passedfalse безFlash: HMI503, router отвечал methodgetnotavailable. Для восстановления выполнена проверка и перезапуск прежнего точного образа2501 через verify_restart_unoq_sketch.cfg (без erase/writeflash); лог installation_r1/predecessor_verify_restart.log. После этого свежая2501/2502 SAFE/PWM0,Vdc10В успешно прошла штатный programmingprecheck; recovered_before_update.json сохранён. Nucleo не сбрасывали.

`tools/install_unoq_display_order_r2.py --confirm-j1-off-meter-below-20v-uno-usb --outdir .../uno_display_order_r2/installation_r2` PASS: ровно1flashUno/0flashNucleo, readbackUnoPASS, HMI обновлён. Калибровка до/после a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. Новая свежаяпара2503/2502,SAFE/PWM0/ARM0,10В,UARTflags0. В последнем статусе transport7 — сохранённый watchdog при перезапуске Uno для программирования; штатный programmingprecheck распознаёт этот latch и не требует CLEAR. Это НЕ готовность к START. START/CLEAR0.

`tools/verify_current_peak_display.py --display-order-r2 --outdir .../uno_display_order_r2/display_runtime_r1` PASS: пассивное чтение framebuffer соответствует10В с X+Yкомпенсацией, scan работает, после чтения связьсвежая. Ни reset/halt/flash этим чтением не выполнялись. Физический порядок разрядов глазами ещё не подтверждён — не выдавать совпадениебуфера за исправление реального наблюдения. `completion_r1.json` и manifest отмечают installed/runtimeverifiedtrue,rpcpendingfalse,physical_display_observation_pendingtrue.

Следующий шаг пользователя — только посмотреть, читается ли теперь10, и сообщить10/01 (при неизменной ориентации платы). USB/15В/повербанк пока не менять, J1OFF. В последнем свежем статусе автоноль ужеready1/stable3; причина смены результата относительно прежнего stable1 здесь не установлена, команды RESET Nucleo от агента не было. Не переносить старый отказ1/3 на новый статус и не объявлять его устранение дисплейным исправлением: исходники Nucleo прежние. При возобновлении моторной диагностики сохранить/проверить текущий watchdoglatch7 перед любым START. История8блоков всё ещё полезна для причины нестабильного автонуля, но новый отказ сейчас не утверждать. Силовое/мотор в этом этапе не включались.

## 2026-10-25: пользователь подтвердил физическую ошибку «10→01»; готова отдельная правка только Uno, НЕ записана

На установленной Uno2026102501 пользователь всё ещё видит01 при10В. Прежний host/framebuffer PASS подтверждал цифровой буфер, но использовал неверифицированную модель физической ориентации; он не доказывал правильную читаемость платы. В manifest установленного current_peak_capture_r1 отмечен display_user_report_failedtrue/display_inverted_mount_fixedfalse, исходники/образы не изменены. Не объявлять физический дефект исправленным без нового наблюдения пользователя.

Подготовлен `artifacts/live_bench_20261024/uno_display_order_r2`, Uno2026102503/Nucleo2026102502. Только Uno/HMI, Nucleo НЕ копируется и НЕ прошивается. В matrix_set_pixel сохранён Yflip и добавлен Xflip для всей картинки/глифов/маркеров. Вне отображения sketch отличается только buildID; UART, моторный код, ADCpeak/zero приёмники побайтно прежние. HMI лишь добавляет новую пару в существующие decoder/calibration/manual allowlists, старую2501/2502 принимает для этапа установки.

`tools/prepare_unoq_display_order_r2.py`, `tools/seal_unoq_display_order_r2.py`, `tools/install_unoq_display_order_r2.py`. Сборка Uno успешна, LLEXT PASS. Host renderer/core packing:94539 проверок/1000напряжений/1000частот; новая модель обеих осей основана на текущем сообщении пользователя, физическая проверка по-прежнему pending. Отрицательный контроль ловит прежний Y-only mapping. HMI проверен на обеих парах: виден реальный zero-failure8/stable1, декодируется peaktrace, unknownidentity отклонена, стараяVbusкалибровка принимается. UI20 проверок PASS. Пакет запечатан; `--verify-package-only` PASS безжелеза. Flash/START/RESET/CLEAR в этом этапе0.

Стенд остаётся по последнему подтверждению: обе платы на повербанках,15ВON,J1OFF,ПК/SaleaeOFF, шина по контроллеру10В и пользователь указывает10В. Для этой установки нужен USBПК только Uno Q; Nucleo и15В можно оставить как есть, J1OFF сохраняется. После подтверждения подключения выполнить Uno-only installer с существующим gate J1OFF/метр<20В и чтением нового live статуса, затем readback и визуальная сверка пользователем10/01. Не просить NucleoUSB и не перепрошиватьNucleo ради дисплея. Автоноль остаётся реально отклонённым (см. wifi_after_b2_reset_r1), силовойпрогон не готов. История8блоков ещё не добавлена.

## 2026-10-25: B2 RESET подтверждён, новый автоноль действительно отклонён; силовое не включалось

После явного подтверждения B2 RESET прочитан `current_peak_capture_r1/wifi_after_b2_reset_r1`: 10с/9свежихответов по Wi-Fi, summary PASS по связи. В D7 HALtick теперь9819→20047мс вместо прежних196160мс: настоящий перезапуск основногоSTM32 подтверждён. START/ARM/CLEAR/RESET/Flash от агента0; пользовательские15ВON/J1OFF/повербанки/отключённыеПК+Saleae сохранены.

`preflight_report.json` passedfalse по автонулю: ready0, CM_ZERO_BAD16, attempts8/stable1, lastreject0. Последний блок spans28/33/32/25, offsets2069/2068/2067/2069. Связь чистая: CRC/sequence/UARTflags/transport0, masks0/0, SAFE/PWM0/ARM0,Vbus10В. SD HIGH, BIEtrue, capture_runningtrue, first_record_readyfalse; ADCpeak«-»/good0 — оба захвата свободны.

Прочитан точный current_core.h: last_bad очищается в начале каждого блока, а D7 передаёт только последний low/high/reject. Поэтому последний хороший блок скрывает причины прежних отказов. Логический вывод из attempts8/stable1/lastreject0: перед последним блоком stable был0; седьмой блок обнулил последовательность из-за span>40 либо mean вне1600..2500. Точный канал/величина и остальные блоки не записаны. Это вывод из алгоритма, не измерение причины помех и не доказательство аппаратного дефекта. Дрейф средних сам по себе оставляет stable1/lastbad4 на своём блоке и не даёт такой переход для седьмого блока.

Новые RESET по кругу не назначать; прогон пока не готов из-за реального отказа автонуля. Следующая содержательная диагностика — история всех8блоков с mean/span/reject и таймингом до изменения критериев. В текущем этапе никакие критерии/прошивки не менялись; новая прошивка пока не подготовлена и не записана. Пользователю оставить текущие подключения, J1OFF. Не путать этот результат с предыдущим нажатием, когда перезапуск по uptime не наблюдался.

## 2026-10-25: после сообщения о RESET счётчик Nucleo продолжился; повторный автоноль не подтверждён

Пользователь сообщил RESET Nucleo при15ВON/J1OFF/повербанках. В этом этапе только чтениеWi-Fi, никаких START/ARM/CLEAR/RESET/Flash от агента. `current_peak_capture_r1/wifi_after_nucleo_reset_r1/summary.json` PASS по связи: 10с/9свежихответов, пара2501/2502, SAFE/PWM0/ARM0,Vbus10В, CRC/sequence/UARTflags/transport0. SDHIGH/BIEtrue/freecapture, ADCpeak «-». Автоноль осталсяready0/stable2/attempts8, offsets иspans побитно прежние.

Дополнительная проверка не дала принять это за второй неудачный автоноль: timestamp в D7 — настоящий HAL_GetTick() Nucleo (current_shunt.c:140). До сообщенияRESET последнийD7tick82304мс при host09:29:49.155UTC; после сообщения последнийD7tick196160мс при host09:31:42.832UTC. Разность MCU113856мс при host113677мс: непрерывное время, не новый отсчёт после reset. D7age<1с, последовательность идёт, приёмник хранит реально обновляемые пакеты; это не устаревшая страница интерфейса. Причину отсутствия наблюдаемого reset пока не утверждать и пользователя не обвинять.

`wifi_after_nucleo_reset_r1/preflight_report.json` passedfalse, controller_restart_observedfalse; исходные данные сохранены. Официальный UM2505 Rev7, раздел7.6.2/page23, https://www.st.com/resource/en/user_manual/dm00556337-stm32g4-nucleo64-boards-mb1367-stmicroelectronics.pdf: чёрная B2 RESET подключена кNRST целевогоSTM32G4, синяяB1USER — PC13/PA0. Следующий конкретный шаг — попросить один раз нажать именно чёрнуюB2RESET и подтвердить, не меняя15В/повербанки/J1OFF. После этого проверить сначала обнуление HALtick и новый D7, затем3/3 и свободныеSD/ADCзахваты. Без наблюдаемогоreset не диагностировать повторный провал автонуля и не назначать новые прошивки/силовойпуск.

## 2026-10-25: после переноса на повербанки Wi-Fi исправна, автоноль отклонён — J1 остаётся OFF

Пользователь подтвердил: обе платы на повербанках, USB ПК/Saleae сняты, 15 В ON, J1 OFF, RESET не нажимал. В этом этапе только HTTP GET и чтение состояния служб по SSH; START/ARM/CLEAR/RESET/Flash0. `current_peak_capture_r1/wifi_preflight_j1off_r1` сохранён: в начале загрузки HMI отвечала503. Позже без перезапуска/перепрошивки статусы появились; `wifi_preflight_j1off_r2/summary.json` PASS: 10с/9свежихответов по прямойWi-Fi, пара2501/2502, SAFE/PWM0/ARM0, Vbus10В, good691→880, badCRC/sequence/flags/transport0. В служебном журнале router были boot-сообщения invalidpacket/int8; это не ошибка CRC транспорта Nucleo и не доказанная причина отказа автонуля.

Моторный preflight НЕ пройден: `wifi_preflight_j1off_r2/preflight_report.json` passedfalse. Автонольready0, attempts8/stable2 вместо3; последние offsets2066/2066/2067/2070, spans31/32/40/24, последнийreject0. Последний блок в допуске, но история ранних отклонений по D7 полностью не передаётся. Не объявлять конкретную физическую причину и не ослаблять40counts/2counts/3blocks. SD HIGH, BIEtrue, capture_runningtrue/first_record_readyfalse; ADCpeak «-» и свободен. Перепрошивок, очистки защиты и моторного запуска не было.

Следующее действие: сохранить эту запись (сделано) и попросить пользователя однократно нажать RESET Nucleo при неизменных устойчивых15В и повербанках, J1OFF. После подтверждения заново читать автоноль и свободные захваты. Силовое до результата не включать; кабели/питание не переключать. Текущий запрос разрешает проверку связи перед прогоном, START в этом этапе не выполнять.

## 2026-10-25: связь восстановилась; пара 2501/2502, автоноль, SD и дисплей проверены

Пользователь подтвердил индикацию питания Uno Q и USB к ПК. В ходе повторного чтения устройство появилось в Windows PnP, затем в ADB как 3880458060 и COM10. Подключения менять повторно не просили. Через USB проверена свежая пара Uno2026102501/Nucleo2026102502. Никаких дополнительных Flash/RESET/START/ARM/CLEAR не выполняли; J1 выключен, 15 В и обе USB к ПК сохранены.

`current_peak_capture_r1/runtime_idle_r1/report.json` PASS: 16+ свежих статусов, SAFE/PWM0/ARM0, Vbus10 В, UART/CRC/sequence/current diagnostic без новых ошибок, transport0, MCSDK masks0/0. Автоноль готов, attempts3/stable3, offsets2067/2067/2066/2069, диапазоны36/40/37/33 отсчёта при пределе40. D7 и прямое чтение памяти согласованы. Idle не выдаётся за измерение RMS двигателя. Живые HMIserver/app.js совпали с пакетом, калибровка SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17 сохранена. SD HIGH, BIE включён, capture_running true, first_record_ready false — захват SD свободен. ADC peak ожидает первого прогона, hex «-».

`tools/verify_current_peak_display.py` выполнен без reset/halt/write/flash: адреса framebuffer и scan сверены с точным ELF ядра, затем пассивное чтение памяти Uno. `display_runtime_r1/report.json` PASS: framebuffer совпадает с 10 В и новым преобразованием ориентации, scan меняется. Это проверка цифрового буфера и сканирования, не визуальное наблюдение светодиодов пользователем.

`completion_after_usb_r1.json` PASS объединяет результаты; manifest установленной пары обновлён: installation_runtime_pair_verified true, rpc_pending false. Первый installation_r1/report.json с таймаутом сохранён без переписывания. Ранний runtime_after_usb_r1/partial report также сохранён; его ноль относится к более раннему чтению, не заменяет последнюю свежую проверку.

Следующий этап — согласованный пользователем диагностический прогон для захвата сырого ADC пика. До силового пуска сначала перевести обе платы с USB ПК на повербанки, ПК/Saleae отключены, J1 пока OFF, 15 В можно оставить. После подтверждения проверить свежие состояния по Wi-Fi; заранее не отправлять START и не включать J1 при USB к ПК. Силовой прогон в этом этапе не выполнялся. Реальная величина пиков до11А по-прежнему не квалифицирована.

## 2026-10-25: после подтверждения USB-переподключения Uno не видна; Nucleo проверена напрямую без сброса

Пользователь сообщил: USBUnoQпереподключил, Nucleo/15Внетронуты,J1OFF. В текущем чтении ПК видит ST-Link003A002C3335510933383531/COM13, но Uno3880458060 отсутствует в adb devices, arduino-cli inventory и WindowsPnP. По192.168.1.138:8080 первыйGETtimedout, далее TCPпортдоступен, ноHTTP RemoteDisconnected; SSH2222 также Connectionclosed. Это отсутствие подтверждённого доступакUno, не доказательство новойошибкиUART междуMCU. Новаяliveпара/Веб/RPCещёнепроверены; manifest rpc_pending остаётсяtrue. Задан один вопрос о фактической индикации питанияUno и USBкПК, ответ пока ожидается. Повторныхперепрошивок/RESET/START/ARM/CLEAR0.

`current_peak_capture_r1/runtime_after_usb_r1/report.json`: частичная проверкаNucleo черезST-LinkHOTPLUG, адресcm_core0x200007e8 източнойmap. Автонольready1/bad0, attempts3/stable3/lastbad0, offsets2067/2067/2067/2069, разброс35/35/36/28<=40. TIM1BDTR0x02393c72, MOE0. GPIOAIDR0x0000c054: PA6HIGH иPA4HIGH (последнийпроводTP23через1кОм). ЗахватADCtotal0/running0/triggered0/frozen0 — свободен. Это чтение уровнейSDсейчас, не проверка свободногоDMAзахватаSDилиегоистории. Результатpassedfalseотражает незавершённуюполнуюпроверку, partial_nucleo_checks_passedtrue. ДанныхоVbus/свежестиUARTсо стороныUnoпока нет. Питание/проводку не меняли; J1не включать до завершения текущейпроверки.

## 2026-10-25: новые образы2501/2502 записаны и проверены, RPC ждёт холодного запуска Uno

Пользователь подтвердил J1OFF, мультиметр<20В, обеUSBкПК,15ВоставленыON и разрешил запись. `tools/install_current_peak_capture.py --confirm-j1-off-meter-below-20v-both-usb --outdir artifacts/live_bench_20261024/current_peak_capture_r1/installation_r1` выполнил ровно1flashNucleo и1flashUno; оба образа проверены чтениемобратно. HMIserver/app.js установлены. Calhashдо/после одинаков a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. START/ARM/CLEAR0. До записи свежая стараяпара2411/2412,SAFE/PWM0,шина10В,SDHIGH/free/armed. После записи новой телеметрии пока нет, не переносить эти показания на новуюпару.

`installation_r1/report.json` сохранён passedfalse: Runtime verification pending:timedout. Это не ошибкаreadback. `flash_verify_nucleo.log` Downloadverifiedsuccessfully, `verify_uno.log` UNOQverificationPASSED. Разовый перезапуск только принадлежащегоarduino процессаHMI с проверкой пути/hash/owner/Restartalways выполнен, PID1759→1871, калибровканеизменна; `hmi_restart.log`. RPC не восстановился. Административный restart arduino-router отклонён ОС: sudo passwordrequired. Повторных прошивок/моторныхкоманд/MCUreset не выполняли. `installation_state.json` и manifest отражают imageswritten/readbackverifiedtrue, runtimepairverifiedfalse,rpcpendingtrue.

Следующее действие пользователя: вынуть толькоUSBUnoQ на5с и подключить обратно кПК. Nucleo,15В и проводку оставить, J1OFF. Это холодныйLinuxстарт дляRPC, не новаяперепрошивка. После подтверждения продолжить только чтением: новаяпара2501/2502, SAFE/PWM0/ARM0, свежиеVbus<20В иcurrentD5/D6/D7, автоноль3/3, SDlevel/armed/capture и отсутствие ADCpeakдоSTART. Проверить framebuffer/ориентациюдисплея. Калибровкуснова не писать. Силовое и мотор до этой проверки не включать.

## 2026-10-25: пакет захвата ADC-пика и разворота дисплея готов, НЕ установлен

Новый пакет `artifacts/live_bench_20261024/current_peak_capture_r1`, пара Uno2026102501/Nucleo2026102502, собран и запечатан. На платах остаётся установленная 2026102411/2026102412. В этом этапе hardware commands0: никаких START, RESET, CLEAR, прошивки, SWD/USB или смены питания. Последняя известная конфигурация: повербанки, J1 и15В ON, ПК/Saleae OFF, двигательJ3, TP23→1кОм→PA4; последний прогон остановлен, SAFE/PWM0/ARM0, Vbus324В. Не подключать ПК по инерции на этой конфигурации.

Добавлен пассивный одноразовый захват12 сырых парADC: при заполненной предыстории5 до первого допустимого превышения626 отсчётов (~6А в ещё не квалифицированном масштабе), триггер и6 после. В записи ISR/JEOS/JQOVF, JSQR, выбор пары, четыреoffset, CNT/DIR/ARR, CCR1..4preload, программный latchCCR наupdate и эпохи, DWTcycles и частота. STOP до порога сохраняет последние отсчёты с явным NO_PEAK; короткий хвост помечен. Запись не перевооружается до reboot, неизменна после freeze; UARTD8(35страниц) передаёт её только приMOEoff, сCRC32C страницы ивсегоrecord. Uno/RPC/HMIдекодируют; `tools/collect_current_peak.py` читает GET и сохраняет binary/JSON/CSV, не посылает моторных команд. Порог не является новой токовой защитой. Текущее окноADC, измерительныйфильтр, V/f, CCR1..3, deadtime, BKIN, watchdog и калибровка сохранены. Программный latchCCR не является прямым чтением аппаратного active-регистра; epoch races явные. Фактический ISRтайминг и реальные амперы ещё не проверены.

По сообщению пользователя19В отображалось91, плата перевёрнута. В этом же Unoобразе убран прежнийXmirror и добавленYflip длявсейкартинки, включая точки/маркеры: поворот180° относительно прежнего вывода. `display_selftest_r1/report.json`:94539 проверок на настоящем renderer/packing Arduino core, 1000 напряжений и1000 значений частоты, независимыйglyphoracle; отрицательные проверки ловят старую ориентацию/неверныйпорядок/пропущенныйYflip/испорченныйglyph/staleVbus. `preview.txt` показывает19и91раздельно. Физическийдисплей ещёнепроверен — образнеустановлен.

`verification/report.json` PASS: captureIRQ42624проверки, currentcore649655, UI20, автоноль/encoder/HMI PASS, настоящий RPCstringparser сохраняет1024Бtrace. Обе сборки успешны, Nucleo0errors/0warnings; UnoLLEXTcompatPASS. ADCIRQstack296Б, RAMзапас сверхминимальныхheap/stack4280Б. Проверены1420hash установленного predecessor, оннеизменён. Негейтящийbuildpreflight exit2 не является разрешениемсиловогоэтапа. `tools/install_current_peak_capture.py --verify-package-only` проверяет запечатанныеhash безжелеза; установка предусматриваетreadbackобоихобразов и сохранениеcalhash.

Следующее физическое действие для установки: J1выключить; после показания независимогомультиметра<20В подключить ОБЕплатыкПКUSB. Двигатель иTP23→1кОм→PA4оставить, Saleaeненужен,15Вможнооставить. Дождаться подтверждения пользователя этого состояния; пока его нет, не прошивать. Послеустановки проверитьсвязь/автоноль/SD и фактическуюориентациюдисплея, затем отдельно согласованныйпрогон с записью и STOP; повторные пуски автоматическиневыполнять. Причинареальных11А пока не доказана.

## 2026-10-25: разбор пиков АЦП — найдена воспроизводимая дыра допуска окна, физическая причина ещё не доказана

Пользователь запросил проверку окон/синхронизации пиков до11А. В этом этапе только ПК/архивы, новых START/ARM/CLEAR/RESET/Flash/SWD/USB/live motor команд0. Питание физически не меняли: последняя известная конфигурация повербанки,J1/15ВON,ПК/SaleaeOFF,J3motorconnected,TP23→1кОм→PA4,последнийVdc324В. Рабочая пара2411/2412 сохранена. Никаких просьб повторно включить уже включённое силовое или подключить ПК на заряженной шине.

Точный установленный кодV/f+sine+PWM и current_core проверены tools/audit_current_adc_windows.py. Итог artifacts/live_bench_20261024/current_adc_peak_audit_r5/{report.json,diagnosis.json,diagnosis_ru.md,window_sweep.csv}. Старыеr1..r4 сохранены: r1 отсутствовал cstring в harness, r2 воспроизведение старой дырки PASS, r3/r4 диагностировали отсутствие безопасных окон в части углов вместо ошибочного требования100%охвата. r5 корректно трактует отсутствие окна как reject, не ослабляет допуски.

Подтверждённый пробел: cm_pair_window проверяет лишь две измеряемые фазы, не отсекает сравнение третьего плеча внутри ADC aperture. ПриTIM1=170МГц,ADC42,5МГц,sampling24,5,принятой latency3,5циклов,CCR4=4928,ADC aperture заканчивается примерночерез112таймерныхтиков. На точном коде пересечение начинается при37,9/38,2/38,5Гц дляшин318/320/323В — совпадает с появлением больших пиков на40Гц. Пример318В/37,9Гц/88,3°:CCR4928/1463/1584,измеряетсяV/W,pair2,старыйpredicateпринимаетхотясравнениеU совпалосADCtrigger. Это сильная гипотеза измерительной коммутационной помехи, не доказательство фактической аналоговой формы/величины.

На настоящемcm_core синтетическая вставка6несатурированныхошибочныхADCсреди3201даёт validtrue,bad0,peak11,147741А,RMS0,889854А приисходноммодельномU0,748299А. Это демонстрация недостаточности qualityflag, НЕ восстановление реального тока. Current_irq host regression42324checksPASS (current_adc_peak_audit_r2/actual_irq_regression), но периферияfake: фактическую аппаратнуюсинхронность не доказывает. Каналы/четыреoffsets/JSQR1rank/TIM1TRGO rising/clock/sampling согласованы; JQM1fixedsource/length и JEOSADC2/lost_sync latch. Фактическийtimer updateepoch иJQOVFвозлепика не записаны. RawADCпакеты медленные и не показывают отсчёты maxima.

Проверена официальная ES0431Rev9: архивCubeProgrammer этойплаты показываетRevX. Y-onlyканал0 иZ-onlymuxDNL не применятькней; wrongJDR требуетAHB/ADC>10 (здесь4); JQM0contextissues не соответствуютJQM1. Они не установлены причиной. PrimaryURLs вdiagnosis.json/diagnosis_ru.md (RM0440,AN5346,ES0431).

Подготовлен tools/current_adc_window_plan.h как отдельный host-onlyproposal, НЕ подключённыйкпрошивке: выбираетокносучётомвсех3фронтов,selectedshuntsettling иlatesttrigger4928; еслиокнанетvalid0. В5,410,800cases5296554safe,114246reject,geometryfail0. Приhighmod до11%угловбезокна — это превышает существующий5%reject допуск. НЕЛЬЗЯ просто интегрировать и ослабитьвалидностьдо89% радиPASS. Нужныпроработкаcoverage/таймингпереносаCCR4/контекстJSQRиrawpeaktrace. Никакой фильтрации пиков, измененияCCR1–3/deadtime/защит/прошивки в этом этапе.

Следующий технический шаг: диагностический захват rawADC1/2 до/после максимума,channel/pair/sequenceid,active/plannedCCR1–4,CNT/DIR,updateepoch,ADCISR(JEOS/JQOVF),edge margins; сравнить выборкивдалиоткоммутации, затем при необходимости независимыйдатчиктока. Комплект новой firmware сзахватом пока НЕ собран и НЕ установлен; не утверждать аппаратнуюпричинудоказанной. Поимеющейсязаписи реальные короткие токовыеимпульсы окончательно не исключены. ПерейтикFOC покаоснованийнет.

## 2026-10-25: достигнуты 50 Гц ступенями, ровное вращение подтверждено; высокие пики токовой телеметрии пока не квалифицированы

Пользователь разрешил разгон до50Гц по шагам. Свежий preflight SAFE/PWM0,Vdc322В,zero3/3,SDHIGH/BIEtrue,masks0/0,CRC/sequence0,температурныйканал51C. Добавлен профиль30-to-50 в tools/run_current_shunt_5_10_5.py:30/35/40/45/50Гц, по крайней мере1с и2monitor-окна на каждой ступени, независимый hostSTOP60с отSTART с учётом5ступеней и веб-задержек; operator watchdog3с и стандартные аппаратные защиты сохранены. STARTHTTP timeout12с. Проведён один START, CLEAR/Flash/CAL0, без смены прошивок/проводки/калибровки. Report artifacts/live_bench_20261024/current_shunt_30_to_50_motor_run_r1/report.json passedtrue; все пять ступеней установились, scheduledSTOP успешен, backupSTOP не сработал. Финальный свежий SAFE/PWM0/ARM0 и выходыOFF подтверждены.

Пользователь подтвердил «Ровно до автостопа, ускорение заметно». Скорость ротора прибором не измерялась: подтверждены частота поля50Гц и физическое вращение, не точныеобороты. С collector разных валидных200-мс окон4/4/3/3/4 по ступеням. Последние RMS U/V/W:30Гц0,777/0,786/0,777А;35Гц0,768/0,773/0,767А;40Гц0,931/0,893/0,887А;45Гц0,881/0,883/0,895А;50Гц0,734/0,781/0,742А. ВСЕ амперы номинальные, масштабы/полярность/фазы не квалифицированы. На40–50Гц обнаружены большие принятые пики: максимум по сохранённым plateau-окнам40Гц7,915/5,046/5,459А;45Гц11,148/9,450/9,056А;50Гц9,315/8,308/9,344А. Их реальность не доказана. RMS на этих ступенях может включать вклад выбросов; не объявлять измерение токов исправным/готовымдляFOC и не диагнозировать перегрузку/IPM толькопоэтимчислам.

Код публикует RMS/max за200мс и отдельные более редкие rawADC; rawADC снимки НЕ являются отсчётами соответствующих пиков. Нужны данные возле пиков и проверка фактических окон/синхронизацииADC, чтобы отличить реальные краткие токи от коммутационных помех, окна выборки или ошибки реконструкции. Пока физическая причина не установлена. Никакие фильтры/пороги не меняли и пики не вырезали. Coverage99–100%, максимум1отвергнутыйADCотсчёт; CM_VALID не является метрологическим доказательством.

MCSDK masks0/0 также после ожидания diagnostics, новых защитных отключений нет. CRC/sequence/dropped/current diagnostic/shortwrite deltas0, transport0, heartbeat/collector errors[]. Но НЕ писать «все UART ошибки0»: Uno hardware noise counter+1, flags32(NOISE-only), bp_ne_observed+14 и bp_ne_accepted+14 по действующей политике CRC-проверенных кадров. Эти предупреждения сохранены в analysis.json; не установлена причинная связь с пиками ADC. Активная шина318–323В, канал температуры51–58C, абсолютная точность канала не квалифицирована.

Артефакты current_shunt_30_to_50_motor_run_r1/{report.json,analysis.json,status.jsonl,valid_current_windows.csv,logs.txt}. Первый SD full-wave архив прежний и занят до reboot, BIE включён, SDHIGH, новыхfault/first_start_window нет. Платы повербанки,J1/15ВON,ПК/SaleaeOFF,моторJ3 иTP23→1кОм→PA4 сохранены. ПоследнийVdc324В; силовое не выключали, ПК не подключать. Согласованный разгон завершён; дополнительных пусков/RESET/перепрошивки не выполнять по инерции. Следующая техническая задача — квалификация высокочастотных токовых пиков; переходFOC не разрешён и не выполнен.

## 2026-10-25: полный прогон 25→30→25 Гц с токами — PASS после исправления host HTTP ожидания

Пользователь разрешил прогон25→30→25 Гц при неизменных питании и подключениях. Свежий preflight SAFE/PWM0, Vdc325 В, zero3/3, SD HIGH/BIEtrue, masks0/0, UART CRC/sequence0, канал температуры49 C. Добавлен явный профиль --profile25-30-25 в tools/run_current_shunt_5_10_5.py. accel5/decel1 Гц/с, downmode_coast0, operator watchdog3с и независимый hostSTOP40с сохранены. MCU/HMI прошивки, калибровка и защиты не менялись.

Первая попытка current_shunt_25_30_25_motor_run_r1/report.json passedfalse/error timed out: ожидание HTTP START8с истекло; контроллер по журналу START принял, но host отправил STOP до выхода на25Гц. В записи максимум частоты поля10,6Гц, ни одна ступень не установилась, MCSDK masks0/0, UARTошибки0, SAFE/PWM0/ARM0 подтверждены после STOP. Исходный отчёт сохранён без правки. Это таймаут веб-подтверждения, не установленная авария двигателя или UART.

На ПК исправлен WifiHmi: request/post поддерживают отдельный timeout_s, обычные GET/STOP остаются8с, staged START ждёт12с. Офлайн fake-opener проверка12/8/8 PASS без команд железу. После чистого OFF выполнена вторая попытка того же запрошенного профиля: current_shunt_25_30_25_motor_run_r2/report.json passedtrue. Всего в этом запросе START2, CLEAR/Flash/CAL0, один прерванный начальный разгон и один полный профиль. Питание/подключения не менялись. Нового запуска после успешного полного профиля не было.

Полный профиль дал по2 monitor-окна, вместе с collector разных полных валидных200-мс окон3/3/4. Последние RMS U/V/W:25Гц0,716/0,722/0,719А;30Гц0,746/0,756/0,748А;обратно25Гц0,754/0,761/0,755А. Номинальный масштаб, независимой квалификации ампер/полярности/фаз нет, FOC не проверялся. Coverage99–100%, максимум один отвергнутый ADC отсчёт в обратной25Гц ступени, выбранные окна валидны. Активная DC-шина318–323В, канал температуры49–54C (абсолютная точность не квалифицирована). Новые UART CRC/sequence/hw/drop/shortwrite/current diagnostic ошибки0, heartbeat/collector errors[], MCSDK masks0/0 также после diagnostics. Пользователь подтвердил «Да, ровно, оба изменения заметны». Скорость ротора прибором не измерялась.

Scheduled STOP успешен, резервный timer не сработал, финальный свежий SAFE/PWM0/ARM0 и выходы OFF подтверждены. analysis.json сохраняет оба исхода, ссылку наr1 и подтверждение физического вращения; valid_current_windows.csv/status.jsonl/logs.txt содержат измерения. SD HIGH/BIEtrue, прежний full-wave архив занят до reboot; новой полной волны не записать, новых fault/first_start_window нет. Платы на повербанках, J1/15ВON, ПК/SaleaeOFF, моторJ3 и TP23→1кОм→PA4 сохранены. Последний Vdc324В, силовое не выключали, ПК не подключать. Следующий возможный прогон30→35→30Гц пока НЕ запускался; текущая задача завершена, нужен новый запрос пользователя.

## 2026-10-25: прогон 20→25→20 Гц с токами — PASS, штатный автостоп

Пользователь разрешил один прогон при неизменных питании и подключениях. Свежий preflight SAFE/PWM0, Vdc324 В, zero3/3, SD HIGH/BIEtrue, masks0/0, UART CRC/sequence0, температура канала52 C. В tools/run_current_shunt_5_10_5.py добавлен профиль --profile 20-25-20, проведён ровно один запуск. Report artifacts/live_bench_20261024/current_shunt_20_25_20_motor_run_r1/report.json passedtrue; START1/CLEAR0/Flash0/CAL0. accel5/decel1 Гц/с, downmode_coast0 и manual operator watchdog3с сохранены. Для этого более высокого начального задания независимый host STOP40с (вместо35с младших профилей) включает дополнительное время начального разгона и веб-ответов. Защиты и firmware не менялись.

Все ступени установились и дали минимум два monitor-окна, вместе с collector разных полных валидных 200-мс окон3/3/4. Последние RMS U/V/W:20 Гц0,722/0,729/0,723 А;25 Гц0,718/0,728/0,721 А;обратно20 Гц0,707/0,715/0,709 А. Масштаб номинальный, независимой квалификации ампер/полярности/фаз нет, FOC не проверялся. Coverage99–100%, максимум один отвергнутый ADC отсчёт в одном из окон25 Гц; выбранные окна валидны. Активная шина318–320 В; температурный канал52–56 C (абсолютная точность не квалифицирована). Новые UART CRC/sequence/hw/drop/shortwrite/current diagnostic ошибки0, heartbeat/collector errors[], MCSDK current/occurred masks0/0 и после ожидания diagnostics. Прежняя остановка около25 Гц в этом прогоне не повторилась; это не доказывает устранение всех возможных причин старых SD событий.

Scheduled STOP успешен, raw power OFF подтверждён, резервный timer отменён и НЕ сработал. Финально свежий SAFE/PWM0/ARM0, выходы OFF подтверждены. Пользователь подтвердил ровное физическое вращение и оба изменения скорости: «Да, ровно, оба изменения заметны». Скорость ротора прибором не измерялась.

Артефакты current_shunt_20_25_20_motor_run_r1/{report.json,analysis.json,status.jsonl,valid_current_windows.csv,logs.txt}. SD HIGH/BIEtrue, первый full-wave архив прежний и занят до reboot, новая полная волна не записывается, новых fault/first_start_window нет. Платы всё ещё на повербанках, J1/15В ON, ПК/Saleae OFF, двигатель J3 и TP23→1кОм→PA4 сохранены. Последний Vdc322 В; силовое не выключали, ПК не подключать. RESET/перепрошивка/переключение питания для следующей ступени не нужны. Следующий возможный прогон25→30→25 Гц пока НЕ запускался; текущий разрешённый прогон завершён, нужен новый запрос пользователя.

## 2026-10-25: прогон 15→20→15 Гц с токами — PASS, штатный автостоп

Пользователь явно разрешил один прогон при неизменных питании и подключениях. Свежий preflight SAFE/PWM0, Vdc323 В, zero3/3, SD HIGH/BIEtrue, masks0/0, UART CRC/sequence0. В tools/run_current_shunt_5_10_5.py добавлен профиль --profile 15-20-15, проведён один запуск. Report artifacts/live_bench_20261024/current_shunt_15_20_15_motor_run_r1/report.json passedtrue; START1/CLEAR0/Flash0/CAL0. Текущие accel5/decel1 Гц/с, downmode_coast0, manual operator watchdog3с и независимый hostSTOP35с сохранены. Защиты не отключались.

Все ступени установились и дали минимум два monitor-окна; вместе с collector разных полных валидных 200-мс окон3/3/4. Последние RMS U/V/W:15 Гц0,652/0,659/0,653 А;20 Гц0,707/0,715/0,708 А;обратно15 Гц0,666/0,675/0,668 А. Масштаб номинальный, амперы/полярность/фазы независимо не квалифицированы, FOC не проверялся. Coverage99–100%, максимум один отвергнутый ADC отсчёт в отдельных окнах, все выбранные окна валидны. Активная шина319–324 В, канал температуры51–55 C (абсолютная точность не квалифицирована). Новые UART CRC/sequence/hw/drop/shortwrite/current diagnostic ошибки0, heartbeat/collector errors[], MCSDK current/occurred masks0/0 также после ожидания diagnostics.

Scheduled STOP подтвердил power OFF в raw ответе; timer отменён вовремя, резервный STOP НЕ сработал. Предыдущая ошибка учёта STOP исправлена и подтверждена этим реальным прогоном. Финальный свежий GET SAFE/PWM0/ARM0, выходы OFF подтверждены. Все три ступени выполнены без аварии. Пользователь подтвердил физическое ровное вращение и оба изменения скорости: «Да, ровно, оба изменения заметны». Скорость ротора прибором не измерялась.

Артефакты current_shunt_15_20_15_motor_run_r1/{report.json,analysis.json,status.jsonl,valid_current_windows.csv,logs.txt}. SD HIGH/BIEtrue; первый full-wave архив прежний и занят до reboot, поэтому вторую полную SD волну здесь не записать; новой защиты не было. Обе платы всё ещё на повербанках, J1/15В ON, ПК/Saleae OFF, двигатель J3 и TP23→1кОм→PA4 сохранены. Последний Vdc323 В, силовое не выключали. Не просить повторно включать питание, RESET, перепрошивку или подключать ПК. Следующий возможный этап20→25→20 Гц пока НЕ запускался; нужен новый запрос пользователя, текущий разрешённый прогон завершён.

## 2026-10-25: прогон 10→15→10 Гц с токами завершён, STOP подтверждён

Пользователь прямо разрешил один прогон, питание и подключения не менял. Свежий preflight SAFE/PWM0, Vdc324 В, zero3/3, SD HIGH/BIEtrue, masks0/0, CRC/sequence0. tools/run_current_shunt_5_10_5.py теперь имеет явный профиль --profile 10-15-10; проведён только этот новый профиль один раз, START1/CLEAR0/Flash0/CAL0. Текущие accel5/decel1 Гц/с, downmode_coast0, штатный manual operator watchdog3с, независимый hostSTOP35с от START-запроса сохранены.

Все три ступени установились: минимум два monitor-окна на каждой, с collector полных валидных окон4/3/4. Последние RMS U/V/W:10 Гц0,565/0,572/0,566 А;15 Гц0,670/0,679/0,671 А;обратно10 Гц0,561/0,569/0,563 А. Номинальный масштаб, независимой квалификации ампер нет, FOC не проверялся. Coverage99–100%, максимум один отвергнутый ADC отсчёт в некоторых окнах, все выбранные окна валидны. Активная шина319–324 В; температурный канал49–53 C, абсолютная точность не квалифицирована. Новые UART CRC/sequence/hw/drop/shortwrite/current diagnostic ошибки0, MCSDK masks0/0. Новой защиты не было. Пользователь подтвердил физическое ровное вращение и оба изменения скорости: «Да, ровно, оба изменения заметны». Скорость ротора прибором не измерена.

Все ступени закончены, scheduled STOP успешно выполнен, MCU OFF наблюдался уже на34,297с от запроса START. Резервный STOP отправился на35с во время дополнительного final STOP. Сырой report.json сохранён passedfalse: предыдущая правка timer ожидала hmi_hv_armed в raw response STOP, но это поле там отсутствует, поэтому timer не отменился. Это harness-ошибка учёта подтверждения, не авария двигателя. В коде исправлено различение raw power OFF (SAFE/PWM0/statusbitsOFF/fresh) и полной annotated GET-проверки с hmi_hv_armed0. Реальный raw ответ и негативные проверки PWM1/VF_RUN/statusbitsON/stale/arm1/unknown проверены офлайн, без команд железу. Финальный свежий GET подтвердил полное SAFE/PWM0/ARM0. После исправления нового моторного запуска не было.

Артефакты artifacts/live_bench_20261024/current_shunt_10_15_10_motor_run_r1/: report.json, analysis.json, status.jsonl, valid_current_windows.csv, logs.txt. Старый pre-START SD архив остаётся занятым, полная вторая волна не записывается до reboot; аппаратный Break включён, SD HIGH, новых fault/first_start_window нет. Обе платы на повербанках, J1/15В ON, ПК/Saleae OFF, двигатель J3 и TP23→1кОм→PA4 сохранены. Последний Vdc322 В; силовое НЕ выключали, ПК не подключать. Перепрошивка/RESET/переключение питания для следующей ступени не нужны. Прогон15→20→15 Гц ещё не запускался и требует нового запроса пользователя.

## 2026-10-25: моторный прогон 5→10→5 Гц с токами завершён, обе смены скорости подтверждены

Пользователь разрешил один прогон с неизменными питанием и подключениями. Свежий preflight SAFE/PWM0, шина324 В, zero ready3/3, SD HIGH/BIEtrue, masks0/0, UART CRC/sequence0. Запущен tools/run_current_shunt_5_10_5.py, один START в штатном online manual mode с действующим 3-с operator watchdog и независимым host STOP35с; CLEAR/Flash/CAL0. Сохранены текущие accel5/decel1 Гц/с, downmode_coast0. Силовые защиты не менялись.

Все ступени установились и дали по два monitor-окна, с отдельным collector всего валидных разных полных 200-мс окон4/3/4. Последние RMS U/V/W: 5 Гц0,430/0,437/0,431 А; 10 Гц0,568/0,574/0,567 А; обратные5 Гц0,428/0,432/0,428 А. Масштаб номинальный, не независимо квалифицирован. Coverage99–100%, максимум один отвергнутый ADC отсчёт в отдельных окнах; токовые окна валидны. Активная DC-шина320–324 В, канал температуры49–52 C (абсолютная квалификация не заявляется). UART CRC/sequence/hw/dropped/current diagnostic новыеошибки0, MCSDK masks0/0. Пользователь подтвердил «Да, ровно, оба изменения заметны». Фактическая скорость ротора прибором не измерялась, это VF, не FOC.

Scheduled STOP выполнен успешно; SAFE/PWM0/ARM0 и свежий OFF подтверждены. Все ступени завершены к30,109с от START-запроса; OFF уже наблюдался на32,625с, до host deadline35с. Исходный report.json оставлен passedfalse: резервный timer не отменялся после успешного scheduled STOP и успел отправить второй STOP во время дополнительного final STOP. Это ошибка учёта завершения в harness, не авария привода. tools/run_current_shunt_5_10_5.py исправлен: отмена таймера сразу после подтверждённого OFF в ответе scheduled STOP и отметки времени. Синтаксис проверен; повторного моторного запуска после исправления не было. Реальный завершённый тест и отдельная ошибка harness отражены в analysis.json, сырые отчёты сохранены без правки.

Артефакты: artifacts/live_bench_20261024/current_shunt_5_10_5_motor_run_r1/{report.json,analysis.json,status.jsonl,valid_current_windows.csv,logs.txt}. Первичный SD архив прежний, full-wave capture занят, BIE включён, нового first_start_window/защиты не зафиксировано. Обе платы всё ещё повербанки, J1 и15В ON, J3motorconnected, TP23→1кОм→PA4 сохранён, ПК/Saleae OFF. Последняя шина326 В после остановки; не подключать ПК, не просить повторно включить уже включённое питание. Перепрошивка/RESET/переподключение для следующей ступени не нужны. Следующий предлагаемый прогон10→15→10 Гц пока НЕ запускался и требует нового запроса пользователя.

## 2026-10-25: повторный моторный пуск 5 Гц — токи записаны, ровное вращение подтверждено

Пользователь разрешил один повтор короткого пуска, питание и подключения сохранены: J1 и 15 В ON, обе платы на повербанках, ПК/Saleae OFF, двигатель J3 подключён, TP23 через 1 кОм на PA4. Выполнен tools/run_current_shunt_5hz.py, отчёт artifacts/live_bench_20261024/current_shunt_5hz_motor_run_r2/report.json PASS, START1/CLEAR0/Flash0/CAL0. Пользователь подтвердил: «Да, вращался ровно». Итоги и подтверждение сохранены отдельно в analysis.json, сырые автоматические отчёты не изменены.

Три разных валидных окна по 200 мс при частоте поля контроллера 5 Гц, coverage100%, rejected0. Последнее активное окно: RMS U/V/W 0,430/0,433/0,428 А; максимальные наблюдённые пики среди этих окон 0,931/1,103/1,209 А. Масштаб номинальный Rshunt/Gain, независимая квалификация ампер/знака/фаз пока не выполнена, FOC не проверен. Новые ошибки CRC/sequence/current diagnostic/dropped0, heartbeat errors[], MCSDK masks0/0. Активная шина и температура канала сохранены в analysis.json. ШИМ выключен, финально SAFE/PWM0/ARM0, выходы OFF подтверждены. Физическое силовое НЕ выключали, последнее Vdc322 В: не просить снова включить уже включённый J1 и не подключать ПК.

Ограничение времени: веб START ответил через 6,875 с; резервный host STOP отправлен через 10 с от запроса раньше основного STOP через 5 с от ответа. Поэтому ровно пять секунд установившейся полки не доказаны; достаточные три 200-мс окна получены. Нового автоматического повтора не было. Первый r1 сохранён как недостаточная запись установившихся 5 Гц из-за раннего отсчёта host таймера; новых защит в нём не было.

До первого пуска после J1 был записан SD LOW 61,8 мкс на обоих входах при MOE OFF вне START; файл current_shunt_5hz_preflight_r1/bkin_trace.json. Единственный штатный CLEAR в r1 признал только архив UV current0/occurred4 при SD HIGH и выходах OFF, BIE восстановлен. Никакие защиты не отключали. Первичная полная волна остаётся неизменяемым архивом до reboot, поэтому новая полная волна в этих пусках не могла быть записана; BIE и SD HIGH проверялись, новых MCSDK faults не было. Следующая ступень частоты ещё не запускалась; RESET/перепрошивка/переподключение для текущего результата не нужны.

## 2026-10-25: после RESET на повербанках автоноль и свободный SD подтверждены

Пользователь подтвердил RESET Nucleo,15ВON,J1OFF,обеплатыповербанки,безсменыпроводки; J3motorconnected,ПК/SaleaeOFF. Пассивная проверка current_shunt_r4_after_reset_prestart_r1/report.json PASS:10свежихснимков точнойпары2411/2412,SAFE/PWM0/ARM0,Vbus10В; offsets2068/2067/2066/2068, spans31/34/30/26<=40, stable3/3,attempts3/8. SDHIGH/configtrue/BIEtrue/capture_runningtrue/first_record_readyfalse.54новыхcurrentpackets,новыеcurrent/UARTошибки0,transport0,currentmask0/occurred4 (известнаяUVисторияприJ1OFF). START/ARM/CLEAR/RESET/Flashотагента0.

ПовторноRESET/USB/перепрошивку не просить: подготовка на устойчивых15В успешно завершена. Следующийфизическийшаг—включитьтолькоJ1 черезштатныйsoft-start при закрытомстенде, платы и15Воставитькакесть, ПК/Saleaeостаютсяотключёнными, Пуск/RESETне нажимать. После подтвержденияJ1ON читатьсвежуюшину/SD/currentzero; затем одинкороткийскалярныйпуск5Гц с записьюD5/D6/D7 иавтоSTOP. ПокаJ1не включён, никакихARM/START. Масштабтокаещёноминальный, реальныхтоковмотораещёнет; не идтидо50Гц безпервоговалидногонизкочастотногоокна.

## 2026-10-25: R4 на повербанках — автоноль сразу3/3, SD-захват занят ранним импульсом

Пользователь подтвердил обе платы на повербанках, ПК/Saleae отключены,15В ON,J1 OFF,J3motorconnected. Первая current_shunt_r4_powerbank_prestart_r1/report.json застала стартLinux и первый потокD5/D7 ещёдоD6 (detail_age999999); не считать это постояннойошибкойприёма. После загрузки current_shunt_r4_powerbank_prestart_r2/report.json: autonull_passedtrue, offsets2068/2066/2065/2068, spans23/35/30/25, stable3/3,attempts3/8. 10свежихснимков,73новыхcurrentpackets, новыеcurrent/UARTошибки0,transport0. SAFE/PWM0/ARM0,Vbus9В.

Общаяготовностьпокаfalse ТОЛЬКО из-за занятогоSD-захвата: SDHIGH/configtrue, BIEfalse/capture_runningfalse/first_record_readytrue, currentUV4/history0x404. bkin_decode.json содержит полный раннийLOW доSTART: PA6 18285.0мкс иTP23→PA4 18282.2мкс. Не приписыватьтолькоэтомуимпульсу неисправностьIPM/мотор/помехи; физическаяпричинанеустановлена. Архивсохранён; CLEARнеочищаетimmutablefirstcapture.

Следующий единственныйфизическийшаг: один RESET Nucleo приустойчивых15ВON,J1OFF,обеплатыповербанки,безсменыпроводки. Затем читатьсвежийавтонольD7 и SDHIGH/BIEtrue/capture_runningtrue/first_record_readyfalse. Это теперь толькоосвобождениеSDпередсиловымпуском; автонольR4 уже надёжнопрошёл3блока сразу. Не просить сноваUSBПК/перепрошивку/перезапускUno. После успешногоповторногочтения готовитьодинкороткий5Гцпрогонсновойпаройиcurrentвалидностью; J1покаещёнеподан. В этомэтапе START/ARM/CLEAR/RESET/Flashотагента0.

## 2026-10-25: R4 связь и веб-статусы после холодной загрузки восстановлены, runtime PASS

Пользователь переподключил только USB Uno, Nucleo и15В не трогал,J1OFF. Linux действительно перезагрузилась: bootID e96e6e92-af28-433c-8bef-969dea34850a. Сначала ADB отсутствовал и HMI возвращал503 при старте; cold_boot_connection_wait_r1.json сохранил эту нормальную последовательность, затем новаяпара2411/2412+D7 появилась. Дополнительных Flash, MCUreset, HMIrestart, START/ARM/CLEAR в этом этапе0. НЕ повторять уже закрытую инструкцию холодного USBперезапуска ниже.

Read-only tools/verify_current_shunt_idle.py --candidate artifacts/live_bench_20261024/current_shunt_monitor_r4 --outdir .../runtime_after_cold_boot_r1 --require-sd-armed PASS. Три стабильныхблока/проверено5, offsets2069/2067/2067/2069, spans26/37/34/31 <=40. D7 WiFi/RPC совпал с прямой RAMпроверкой Nucleo. Все16+ свежиестатусы SAFE/PWM0/ARM0,Vbus10В; UARTnormal/current counters не растут, SD HIGH/BIEtrue/capture_runningtrue/first_record_readyfalse. Хэши live server/app.js и калибровка совпали, калибровкаSHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

На HMI открыта/оставлена новаястраница с панелью «Токи двигателя U/V/W» и раскрытым прогрессом3/3,5/8,разбросом. Screenshot current_shunt_monitor_r4/current_panel_after_cold_boot.png. В баннере остаётся сохранённый watchdog timeouttransport7/bad1/lastreason13 от отсутствияUno; это НЕ новая CRCошибка и не текущий разрыв: ответ свежий, integrity0/sequence0/hw0, новыеbad0. CLEAR ради удалениябаннера не посылали. Перед реальнымпуском штатно признать толькоизвестнуюисторию при проверенномsafeOFF иотпущенныхзащитах, не подменятьнакопленныйтаймаут утверждением текущейнеисправностиUART.

ManifestR4 installed/runtime/SD/zero/browsertrue,rpc_pendingfalse; completion_summary.json сохранён. Исторические installer report passedfalse и pending_runtime_summary.json оставлены какпротокол до восстановления, не перезаписывать их. Реальные токи работающего двигателя и масштаб ампер ещё не проверены; FOC OFF. Сейчас обе платы USBПК,15ВON,J1OFF,J3motor connected,SaleaeOFF. Следующий физическийэтап перед моторнымпрогоном: обе платы на повербанки и обычныеUSBПК/Saleaeснять,15Воставитьустойчивыми,J1покаOFF, затем читатьновыеzero/SDпослеперевода. Силовое иПуск в этомэтапе не разрешали.

## 2026-10-25: R4 записана и автоноль/SD проверены напрямую; ожидается холодный USB-перезапуск только Uno

Пользователь прямо подтвердил обе платы USB ПК, J1 OFF,15В ON, мотор/J3 и проводка сохранены и разрешил запись автонуля. tools/install_current_shunt_zero_blocks.py записал обе MCU одинраз (Uno2411/Nucleo2412), Flash обеих проверены чтением, HMIserver/app.js установлены, калибровка до/после SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. Исходный artifacts/live_bench_20261024/current_shunt_zero_blocks_install_usb_r1/report.json passedfalse исключительно Runtime verification pending: timed out; не перезапускать installer и не перепрошивать.

Прямой HOTPLUG SWD безhalt/reset/write Nucleo показал реальный новый cm_core: ZERO_READY1/ZERO_BAD0, offsets2069/2067/2067/2069, low2057/2048/2050/2055, high2083/2085/2084/2086, spans26/37/34/31. Три последовательных стабильных блока приняты после5завершённых блоков, lastreject0. post_flash_adc_state.json+log сохранены. Не заявлять пока проверенным D7 через RPC — сетьget ещё не отвечает. Исправление автонуля подтверждено на реальной MCU, диапазон40 не ослаблен.

Прямая SDпроверка post_flash_sd_direct_verification.json PASS: capture_stateRUNNING1, triggered0,record_ready0, PA6HIGH/PA4HIGH, BIEtrue, BKEtrue, MOEfalse. DMAcompleted прогресс1280159744→1281077248 (+917504); захват свободен и реально работает. Никаких START/ARM/CLEAR в этапе.

RPCпосле прошивки Uno не восстановилась. Выполнен один restart_owned_hmi (PID1226; mcu reset0) — не помог. Затем один дополнительный verify_restart_unoq_sketch.cfg безFlashwrites (после обновления RPCклиента); не помог. runtime_after_verified_restart_wait.json содержит4timeout, passedfalse. Matrix read-only показывает framebuffer0/scan0 — не объявлять работающим дисплей. arduino-router.service работает, log содержит историческое invalidpacket от21:04:23; это не доказательство причины текущего автонуля/UART. adb reboot вернулerror:closed; boot_id ebc1a102-0672-486e-ac68-42bcf855f9bf не изменился, Linux не перезапущен. Не повторять Flash/MCUreset/HMIrestart по кругу.

Нужен единственный физический шаг: вынуть ТОЛЬКО USB Uno Q на5секунд и подключить обратно кПК. NucleoUSB,15В и проводку сохранить, J1OFF. После ответа дать Linux загрузиться, вернутьADB forwards18080/12222 и проверить свежий статус точнойпары2411/2412+D7quality/zero3из5+SDfree. Если MCUпослеLinuxcoldboot всёещёsetupstalled, разрешён прежде работающий verify-only restart после стабильногоLinux, не Flash; первыепассивныедиагностики и original reports сохранить. Подключать силовое/переводить на повербанки пока не просили.

ManifestR4 images_written/readback/zero_direct/SDdirect/calibrationtrue, installed/runtimepairfalse,rpc_pendingtrue. pending_runtime_summary.json сохранён. Исторические R3 инструкции ниже устарели. tools/verify_current_shunt_idle.py обновлён для динамического размера cm_core и D7; после восстановления: --candidate artifacts/live_bench_20261024/current_shunt_monitor_r4 --outdir .../runtime_after_cold_boot_r1 --require-sd-armed (поумолчанию8сек read-only), безповторнойзаписи.

## Продолжение после RESET: SD готов, автоноль R3 отклонён; R4 готов к записи

Пользователь подтвердил один RESET Nucleo при15В ON/J1 OFF/обе платы повербанки/ПК иSaleae сняты/J3 мотор подключён. tools read-only сохранил artifacts/live_bench_20261024/current_shunt_after_reset_15v_r1/report.json: общий passedfalse из-за автонуля, но SD HIGH/configoktrue/BIEtrue/capture_runningtrue/first_record_readyfalse — захват послеRESET исправен и свободен. Пара2409/2410,SAFE/PWM0/ARM0,Vbus10В,transport0,integrity0/sequence0/UARThw0. Zero count256×4, offsets2068/2065/2066/2068, flags16/zero_ready0; по коду это отказ из-за span>40, так как всеoffsets в диапазоне. Точный канал/span на R3 WiFi не выдаётся. Это повторяемая программная хрупкость одноблочной калибровки, а не доказанная причина аналогового шума. Повторять RESET наугад или включать J1 не просили, не делали.

Подготовлено исправление current_shunt_monitor_r4, пара Uno2026102411/Nucleo2026102412. Автоноль теперь требует3последовательных принятых блока256/путь, пределы каждого1600..2500/span<=40 сохранены, средние всех3блоков должны совпадать в пределах2отсчётов. Максимум8блоков за загрузку, затем ZERO_BAD; постоянный шум/неверныйbias/дрейф не обходятся. Между блоками нет записиNVM; при unsafe bus/потере временных условий или активномШИМ неполныйноль и streak очищаются. Выдержка500мс приPWMoff/Vbus<=20 сохранена. Готовые offsets после3блоков усредняются по768отсчётам/путь и затемзамораживаются.

Новый отдельный диагностический пакетD7 передаёт min/max каждого пути, количество завершённых/stableблоков, причину последнего отклонения и неизменные пороги. Общий лимитдиагностики5пакетов/с, D5summary3/с,D6raw1/с,D7quality1/с; CTqualityCRC/fw/age/duplicate проверяются какдляостальных. В HMI добавлены размахи4путей, progress3/3 и n/8 и причины span/bias/drift. Это не новая калибровкаDCшины, PWM/VF/deadtime/BKIN/UARTcommands не менялись. НикакогоSTART/ARM/CLEAR/Flash за этот этап ещё не было.

Обе сборкиR4 готовы: Nucleo build0errors/0warnings, RAMmargin5352 сверхminheap/stack; Uno LLEXTPASS. Source/build/verificationSHAsealed вR4/manifest.json. Проверки core649655/IRQ42324/HMI14/UI20/mixedwire62 PASS. Новый zero_blocks_selftest_r2:30 actualcorechecks+5HMIqualitychecks, старый отказ воспроизведён, проверены единичный выброс с последующими3стабильными блоками, постоянныйшум/bias/drift, ограничение8, разрывусловий; настоящий targetpacketencoder D7 прошёлroundtrip через HMI. r1 этого теста — только исправленная ошибка отступов тестовогоC++, сохраненаистория, не firmwarefailure.

Installer tools/install_current_shunt_zero_blocks.py --verify-package-only PASS. R4 НЕ установлен (installedfalse,hardwarecommands0). Нужен следующий физический шаг: J1 оставитьOFF,15ВможнооставитьON, перевести обе платы с повербанков на USB ПК для записи готовойпары. Последнее Vbus10В, пользовательранее разрешил запись<=20В. Проводку,J3,TP23→1кОм→PA4 не менять, Saleae не нужен. После подтверждения/фактического появленияUSB исвежейSAFEтелеметрии запуститьinstaller вновыйкаталог current_shunt_zero_blocks_install_usb_r1. КалибровкаSHA должна остатьсяa89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. Затемпроверить3стабильныхблока, D7spans исвободныйSD приустойчивых15В. Прежде физического пуска —повербанки иПК/Saleaeотключены, отдельное подтверждениеJ1ON.

## 2026-10-24: автоноль на повербанках PASS; до силового нужен свежий захват SD

Пользователь подтвердил обе платы на повербанках, ПК/Saleae отключены,15В ON,J1 OFF,J3 двигатель подключён, Пуск/RESET не нажимал. Read-only report artifacts/live_bench_20261024/current_shunt_powerbank_15v_zero_r1/report.json PASS:10 свежих снимков, пара2409/2410,SAFE/PWM0/ARM0,Vbus10В; offsets2068/2066/2066/2068, четыре count256, ZERO_READY1/ZERO_BAD0, принятые диапазон/span по флагу firmware. Точный span по WiFi не передаётся, не выдавать старые USB-цифры за новый замер.73 новых currentpackets, новыеcurrent_bad/normal integrity/sequence/hw0, transport0. Никаких START/ARM/CLEAR/RESET/Flash.

mc_sd_live HIGH/config_oktrue, но BIEfalse/capture_runningfalse/first_record_readytrue; текущаяUV4 и архив0x404, до первого пуска уже записано событиеSD. Декод сохранён saved_bkin_decode.json. По коду mic_bkin_capture_start() immutable-first-event-per-boot: CLEAR/STOP/START не освобождают эту запись. До включенияJ1 следующий физический шаг — ОДИН RESET Nucleo при устойчивых15В, J1OFF, повербанках и прежней проводке; затем повторно прочитать ноль и убедиться, что SDHIGH/BIEtrue/capture_runningtrue/first_record_readyfalse. Это нужно для свежей диагностической записи следующего пуска; не перепрошивка и не повторная калибровка DC-шины. J1 в этом этапе ещё не включали.

## 2026-10-24: двигатель подключён к J3, следующий шаг — повербанки и только15В

Пользователь подтвердил: силовое J1 и15В OFF, двигатель подключён кJ3, обе платы пока USB ПК. Прежнее указание «J3 отключён» ниже устарело. Пассивное чтение после подключения: точная пара2409/2410, SAFE/PWM0/ARM0, Vdc1В, age2мс, current_zero_ready1, offsets2069/2065/2067/2069, current_bad0, UART hw0. Watchdog transport7 и UV mask4 сохраняются как история; CLEAR/START/ARM/RESET не отправлялись. Следующий физический этап: обе платы на повербанки, USB ПК и Saleae отключены, только15В ON, J1 OFF; дождаться загрузки Uno и после подтверждения прочитать свежий автоноль/связь. Затем можно готовить первый короткий моторный прогон5Гц с записью новых токовых полей, штатным STOP и контролем достоверности; силовое пользователь ещё НЕ включал.

## 2026-10-24: шунтовое измерение и панель токов установлены; автоноль и минутный обмен проверены

Рабочая пара теперь Uno2026102409/Nucleo2026102410, sealed sources/images: artifacts/live_bench_20261024/current_shunt_monitor_r3. Обе Flash записаны и проверены чтением; HMI server+app.js установлены и live SHA совпали. Калибровка DC-шины не менялась, SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. Отчёты: current_shunt_channels_install_usb_r1/report.json, current_shunt_monitor_r3/idle_adc_verification_r1/report.json, current_shunt_monitor_r3/completion_summary.json. Старую2403/2402 больше не ожидать в диагностических wrappers. Предыдущие pending-указания подключения USB закрыты: обе платы реально видны по serial COM10/COM13, пользователь подтвердил «она же подключена».

Текущее физическое состояние: J1 OFF, независимый мультиметр ранее <20В, последняя телеметрия1В; обе платы USB ПК, 15В ON, J3 последнее подтверждённое отключено, TP23→1кОм→PA4 сохранён, Saleae отключён. START/ARM/CLEAR/J1 ON за задачу0. Пользователь ничего нового включать/переподключать ещё не подтверждал. Для будущего моторного измерения физически нужен двигатель на J3: при J1 OFF и измеренной разряженной шине снять15В перед подключением фаз. До силового прогона обычные USB ПК/Saleae снять и перевести платы на повербанки, сначала устойчивые15В и автоноль, затем J1 через soft-start. Не запускать сейчас без подготовки; старые моторные тесты не заменяют проверку новых измерений.

ADC1/2 injected по TIM1_CH4 (ARR−384), один синхронный отсчёт на каждый ADC за PWM-период16кГц; выбираются два длинных интервала нижних ключей, третий фазный ток восстанавливается по сумме. Четыре независимых offsets U/ADC1, V/ADC1, V/ADC2, W/ADC2. Автоноль: ШИМ выключен, шина<=20В, выдержка>=500мс,256отсчётов/путь; диапазон1600..2500 и span<=40 без ослабления. Acquisition24.5ADCтакта. Реальные нули2069/2065/2067/2069, minmax spans24/35/34/29. Это проверка нуля/обмена, НЕ измерение известных токов двигателя и не калибровка масштаба.

Окна200мс: RMS/peak/signed last, flags ZERO/VALID/FROZEN/CLIP/TIMING, coverage/rejects; в IRQ только целочисленное накопление, sqrt/масштаб в foreground. Токовый пакет D5, detail D6, CRC32C; штатные UART-команды и D1/D2/D3 диагностика сохранены. Отдельный static_assert запрещает пересечение версий. V/f-огибающая, CCR1..3, deadtime1350нс, BKIN/SD schema5, watchdog/recoverybudget не менялись, FOC не включён. Rshunt0.04Ω/Gain2.1/Vref3.3В номинальные и физически не квалифицированы; физические sign/phase/scale и активные samplingwindows под ШИМ ещё требуют проверки на двигателе перед FOC. Наличие действующего scalar не означает готовности токовых регуляторов.

Минутная read-only проверка PASS: summary/detail приходят свежими, нормальные ответы прогрессируют, mc_current_bad и normal integrity/sequence/hardware не растут. Сохранена исходная watchdog-история transport7/normal bad1 от смены Uno, CLEAR ради её удаления не выполнялся. В браузере открыта и оставлена страница http://192.168.1.138:8080/ с панелью «Токи двигателя U/V/W», «Автоноль готов», раскрытыми сырыми измерениями. Screenshot current_shunt_monitor_r3/current_panel_idle.png. В idle RMS/peak/instant прочерки, потому что нет окна работающего привода; UV-текст соответствует выключенному J1.

История исправлений прозрачна: r1(2405/2406) отклонила V/ADC1 span49>40; r2(2407/2408) с увеличенным временем выборки прошла автоноль. Причина первой нестабильности по одному сравнению окончательно не установлена. Моя первая версия current packet D3 совпала с UART-reject D3; r2 idle-проверка обнаружила растущий current_bad. r3 выделяет D5/D6 и восстанавливает диагностику. r1/r2 не использовать для моторных испытаний. Всего в задаче три пересобранные/установленные пары, каждая запись и readback сохранены в своих каталогах; никаких повторов Flash для восстановления RPC не было.

Программные проверки actual core649655, ADCIRQ42324, HMI14, renderer16, mixed dispatcher62 PASS; в смешанном потоке восстановлены все320байт/14страниц UART-аварии, возврат коллизии D3 намеренно ломает сборку. Nucleo build0errors/0warnings, RAMmargin5408байт сверх minheap/stack; Uno LLEXT PASS. Verification summaries и source/build SHA sealed в manifest.json. Главный следующий этап — подключить двигатель при снятом питании и проверить низкочастотные реальные токи с номинальным масштабом, затем квалифицировать чувствительность/полярности и только потом готовить ACIM FOC с измеренной моделью.

## 2026-10-24: дисплей напряжения Uno2403 установлен и проверен на работающей плате

Пользователь подтвердил переподключение только USB Uno, Nucleo/15 В не трогал, J1 OFF. После загрузки Linux первая runtime-проверка ещё получила HTTP503 method get not available; runtime_after_cold_boot_r1/report.json с неудачей сохранён. Пассивное чтение boot_state_read.log показало точный новый заголовок Flash, непустой llext_list (программа уже загружена), SCB fault status0/0; пустая матрица сама по себе НЕ доказывала незагруженную программу. Повторного Flash, Nucleo reset, CLEAR/START/ARM не выполняли.

Для восстановления выполнена одна сессия verify_restart_unoq_sketch.cfg: только проверка loader/sketch Flash и штатная последовательность reset/boot release, без erase/write Flash. Лог verify_restart_after_cold_boot.log содержит UNO Q verification PASSED; restarting unchanged images. Последующий tools/verify_unoq_bus_display_runtime.py --outdir artifacts/live_bench_20261024/uno_bus_display_install_usb_r2/runtime_after_cold_boot_r2 завершился PASS.

Реальная пара2403/2402, семь свежих снимков, SAFE/PWM0/ARM0/freq_cmd0, Vbus2В, последний возраст ответа4мс, transport/integrity/sequence/UART hw=0. Прямое чтение реального framebuffer дало [134332416,8390400,83886108,64], точное совпадение с цифрой2 и V-маркером при наблюдённых bp_vdc2/2В. Индексы сканирования [67,4,1,86,40,5,94,56] меняются и находятся в0..103. Работа буфера и сканирования подтверждена; пользователь визуально пиксели ещё не подтверждал (physical_display_verified=false). Не объявлять проведённым тест дисплея при320В: его не выполняли и J1 не включали. Низкое показание — телеметрия контроллера, не новая калибровочная точка и не независимое доказательство отсутствия напряжения.

Живой HMI SHA и калибровка SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17 совпали; Uno записана всего1раз, Nucleo0раз. Summary: artifacts/live_bench_20261024/uno_bus_display_install_usb_r2/completion_summary.json. Оригинальный report.json installer с timeout и pending-файл оставлены как история; финальное состояние manifest installed/runtime/matrix_buffer/matrix_scan=true, rpc_pending=false. Старые инструкции ниже о повторном USB-перезапуске уже закрыты.

В tools/install_unoq_bus_display.py исправлена будущая последовательность: verification/restart через verify_restart_unoq_sketch.cfg, убран лишний последующий bare reset из unoq_reset_run.cfg. После этой правки installer НЕ запускали повторно: актуальный образ не менялся. Для будущих диагностических или моторных сценариев ожидаемая пара теперь Uno2026102403/Nucleo2026102402. Nucleo и кривая U/f — из vf_smooth_start_r1 без изменений. Старые wrappers с жёсткой2401/2402 нельзя запускать, не обновив ожидаемую пару. Текущие физические условия остаются UnoUSBПК/Nucleoповербанк/15ВON/J1OFF, состояние J3 последнее подтверждённое отключено.

## 2026-10-24: дисплей Uno 2403 записан и Flash проверен, требуется холодный USB-перезапуск Uno для RPC

Пользователь прямо подтвердил Uno USB ПК, J1 OFF, мультиметр ниже20В, Nucleo на повербанке, 15В ON и разрешил запись дисплея. Это актуальная подготовка, не спрашивать её заново. Первый installer uno_bus_display_install_usb_r1/ завершился ДО Flash (flash0) из-за раннего boot HTTP503 method get not available; boot_status_wait.json затем подтвердил свежую исходную пару2401/2402 SAFE/PWM0/Vdc3В. Отчёт r1 сохранён.

Второй запуск tools/install_unoq_bus_display.py --confirm-j1-off-meter-below-20v-uno-usb --outdir artifacts/live_bench_20261024/uno_bus_display_install_usb_r2 записал ТОЛЬКО Uno2026102403 один раз. Nucleo2026102402 не перепрошивалась. verify_uno.log содержит UNO Q loader and sketch verification PASSED; resume_uno.log подтверждает CORE_AFTER_RESET_RUN running. HMI server новый allowlist установлен, SHA1fd0cb1f18f67b38402742756a20b7f873175d00fca3faeaad473511440e8e21. Калибровка до/после SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17, не менялась.

Оригинальный r2/report.json passed=false исключительно Runtime verification pending: timed out после прошивки; не переписывать и НЕ запускать installer повторно. Manifest images_written/uno_flash_readback_verified=true, installed/runtime_verified=false, rpc_pending=true. Никаких START/ARM/CLEAR, новых калибровок или лишних MCU reset от агента не делали.

Пассивный remoteocd с tools/read_unoq_matrix.cfg (без halt/reset/write) дал matrix_read_only.log: framebuffer 0/0/0/0, scan index все0 — работа матрицы не подтверждена. Адреса 0x20001228 framebuffer и 0x20001714 i_isr подтверждены nm именно установленного core0.90 ELF. В setup матрица начинается ПОСЛЕ Bridge.begin: зависшая внутренняя RPC может мешать завершению setup. Один перезапуск принадлежащего arduino HMI PID972 выполнен через проверенный restart_owned_hmi, но три GET после него timeout (rpc_after_hmi_restart.json). Повторять MCU reset/HMI рестарты по кругу не нужно.

Следующий единственный физический шаг: вынуть только USB Uno Q на5с и подключить обратно, Nucleo/повербанк/15В/проводку оставить, J1 OFF. Это холодный старт Linux/router после прошивки, повторная запись не нужна. После ответа дать Linux загрузиться (ADB wait-for-device до45с, не начинать installer слишком рано); восстановить forwards18080/12222. Проверять runtime новой пары2403/2402 без перепрошивки: GET /api/status с SAFE/PWM0/ARM0/свежими Vbus/ответами. Известный transport7 от перезапуска Uno не мешает индикации напряжения в idle fault; для задачи дисплея не просить Nucleo RESET/CLEAR только ради снятия этой защёлки.

Дальше read-only архив можно выполнить через read_uart_resync_idle с reader.C=prepare_unoq_bus_display.OUT, reader.PAIR=prepare_unoq_bus_display.NEW и reader.BASE=http://127.0.0.1:18080 (старый read_vf_smooth_start_idle.py жёстко ожидает2401/2402 и не подходит). Сверить живой framebuffer с тремя цифрами округлённого bp_vdc и V-маркером, scan index должен меняться; raw_pixel индекс y*13+(12-x), LSB-bit packing в реальном framebuffer. Значения 0..999/invalid/stale уже проверены host94539checks, это не заменяет проверку работающей платы. Не включать J1 для проверки дисплея; сейчас авторизована только установка. После успешной runtime/матрица-проверки сохранить новый completion report и обновить manifest installed/runtime=true, rpc_pending=false; physical_display_verified оставитьfalse до визуального подтверждения пользователя.

## 2026-10-24: индикатор напряжения Uno собран, ещё не записан; проверен путь к измерению токов/FOC

Пользователь попросил показывать напряжение шины на матрице Uno при нулевой частоте, затем проверить готовность аппаратуры для векторного управления по токам. Текущее питание физически НЕ переподтверждено: последняя шина после no-motor прогона 323 В, платы на повербанках, J3 отключён. Перепрошивку и подключения к ПК в этом состоянии не выполняли; никаких моторных команд в этом этапе не было.

Готов отдельный пакет artifacts/live_bench_20261024/uno_bus_display_r1, новая совместимая пара Uno2026102403/Nucleo2026102402. Изменяется только матрица Uno и её buildID, плюс точечный HMI allowlist новой пары; Nucleo/кривая U/f/UART/калибровка не меняются. В STOP/SAFE показываются принятые свежие g_bp_vdc, целые вольты с маленькой V; при ESTOP/idle fault напряжение также видно. При invalid/stale>500ms/unknown peer/NaN/выходе0..999V — три тире, не ложный ноль. Сохраняются прежняя бегущая индикация Hz/расчётных RPM и краткий boot matrix selftest. MCU voltage — тот же исходный engineering-unit канал Nucleo, что и HMI; сохранённые метрологические точки сервер использует для проверки, не для изменения этой шкалы.

Uno build прошёл, LLEXT pass, flash SHA b82b3b4a5c5a29a15ba31ee1d7ccaf8d065e092300594a15c4d59f059cb0b504. Host renderer selftest_r2/report.json: 94539 проверок настоящего renderer и packing core0.90; 1000 напряжений и 1000 частот при RUN, stale/invalid/rollover/восстановление и 3 отрицательных мутации PASS. selftest/ с первоначальной ошибкой unused-function в host harness сохранён. Контрольный код вне renderer/ID побайтно прежний. 15 синтетических guard-проверок PASS. Manifest built/selftest=true, installed=false, physical_display_verified=false.

Подготовлен tools/install_unoq_bus_display.py; --verify-package-only PASS. Реальный запуск требует --confirm-j1-off-meter-below-20v-uno-usb и --outdir: только UnoUSB, Nucleo можно оставить на повербанке; USB Nucleo не нужен. Installer пишет только Uno один раз с loader/sketch readback verify, обновляет только server allowlist с резервной копией и сохраняет hash калибровки до/после; не шьёт Nucleo, не посылает CLEAR/START/ARM. При обычном после-Flash RPC timeout сохранять отчёт, не перепрошивать повторно. Для установки сначала требуется физически выключенный J1, независимая проверка разряда до<=20В и подключение только USB Uno к ПК; 15 В можно оставить по прежнему разрешению. Пока этого подтверждения нет.

Аппаратный/кодовый разбор FOC в uno_bus_display_r1/vector_current_review.json. STEVAL имеет 3 low-side шунта и внешние TSV994; конфигурация Rshunt0.04/Gain2.1, actual assembly/selector не квалифицированы. Pin definitions: U=PA0 ADC1IN1, V=PC1 ADC1/2IN7, W=PC0 ADC2IN6; PA4 диагностике не мешает. R3_2/ADC injected TIM1_TRGO уже настроены, но HF task выполняет ACIM_VF_Controller, нет достоверной выдачи токов (HMI valid0). Внутренние OPAMP и COMP Nucleo в этом профиле MC_NULL; защита CIN/SD IPM отдельна. Для FOC нужны проверенные токовые окна, offset/scale/sign/phase mapping, RMS/peak/valid telemetry без перегрузки UART, затем измеренная модель ACIM и официальный LSO-FOC. Старый prepare_air56_lso_foc.ps1 использует старую базу и не должен затирать последние UART/SD исправления. По наличию компараторов FOC готовым не считать.

## 2026-10-24: прогон без двигателя 5→50 Гц успешно завершён, штатный STOP подтверждён

Пользователь прямо разрешил чтение и прогон после включения J1 через soft-start: 15 В ON, обе платы на повербанках, ПК/Saleae отключены, J3 отключён, TP23→1 кОм→PA4 сохранён. Перед запуском пассивная запись no_motor_hv_before_run_r1/ показала 321 В, чистую пару 2401/2402 и свободный захват. Единственный CLEAR снял только архивированную UV-историю от выключенного J1 (current0/occurred4); аварий работающего привода не сбрасывали.

Выполнен tools/run_vf_smooth_start_no_motor_to_50.py --confirm-motor-disconnected --confirm-powered-ready --outdir artifacts/live_bench_20261024/no_motor_to_50_run_r1. Report pass=true, START1, CLEAR1, flash/CAL0. Все 10 ступеней 5,10,15,20,25,30,35,40,45,50 Гц установились по заданию частоты контроллера; выдержка минимум 2 с на каждой. Всего 116 снимков, 107 активных, наблюдаемый активный интервал 53.781 с. DC-шина 322–324 В. Канал температуры показывал 48–51 C, без утверждения квалификации абсолютной температуры. Калибровку/таймеры/прошивку не меняли.

На всех активных снимках UART integrity/sequence/hw/transport/dropped/NE observed/NE accepted/recovered drops=0; MCSDK masks0/0. После STOP первые снимки Break по-прежнему пустые, SD HIGH, BIE=true, capture_running=true, first_record_ready=false. Записанной новой SD-аварии нет; отсутствие волны здесь согласуется со свободным вооружённым захватом, а не с его отключением. Физические выходные импульсы и фазные токи внешним прибором не измеряли.

Финальное состояние SAFE/PWM0/ARM0/freq_cmd0; выключение выходов подтверждено. J1 физически пользователь пока не выключал: последнее Vdc 323 В. Подключать J3 в этом состоянии нельзя. Доказан успешный прогон инвертора без двигателя на новой U/f-прошивке, но неисправность двигателя и исправность инвертора под нагрузкой не доказаны. Прежние моторные испытания были с другой огибающей U/f, поэтому для сравнения нужен моторный прогон на этой же паре без перепрошивки.

Итоги: artifacts/live_bench_20261024/no_motor_to_50_run_r1/analysis.json, report.json, samples.json, status.jsonl, after_break_snapshot.json, after_bkin_trace.json, after_uart_reject.json и logs.txt. Следующий физический этап для сравнения: выключить J1 и 15 В, дождаться разряда и проверить его мультиметром, затем подключить двигатель к J3; платы можно оставить на повербанках, USB ПК и перепрошивка не нужны. До подтверждения этой подготовки никаких повторных START.

## 2026-10-24: после RESET при устойчивых 15 В захват свободен, J1 пока выключен

Пользователь подтвердил один RESET Nucleo без изменения подключений: обе платы на повербанках, ПК/Saleae отключены, 15 В ON, J1 OFF, J3 отключён, TP23→1 кОм→PA4 оставлен. Пассивная запись artifacts/live_bench_20261024/no_motor_after_reset_15v_r1/ прошла: точная пара 2401/2402, свежий прогресс UART, transport/integrity/sequence/hw=0, SAFE/PWM0/ARM0, задание 0 Гц, Vdc контроллера 10 В.

SD HIGH, BIE=true, capture_running=true, first_record_ready=false, config_ok=true, оба первых снимка пустые. После RESET нового Break в этом наблюдении не записано. current_mask0/occurred_mask4 — только известная история UV при выключенном J1. Никаких команд START/ARM/CLEAR/RESET от агента не отправляли. Стартовый импульс 18.1 мс из предыдущего boot сохранён отдельно в no_motor_15v_idle_r1/.

Следующий физический шаг: включить J1 через штатный soft-start при закрытом стенде; 15 В/повербанки/отключённый J3 и TP23 оставить, Пуск и RESET не нажимать. После подтверждения включения прочитать свежее состояние и выполнить уже согласованный ограниченный прогон без двигателя tools/run_vf_smooth_start_no_motor_to_50.py до 50 Гц, если готовность сохранилась. Новый вопрос о подключениях или прошивка не нужны. Прогон пока не выполнен.

## 2026-10-24: без двигателя, только 15 В — записан стартовый SD, перед прогоном нужен свободный захват

Пользователь подтвердил обе платы на повербанках, ПК/Saleae отключены, 15 В ON, J1 OFF, J3 отключён, TP23→1 кОм→PA4 сохранён. Выполнено только чтение по Wi-Fi: artifacts/live_bench_20261024/no_motor_15v_idle_r1/. Пара 2401/2402, SAFE/PWM0, Vdc по контроллеру 10 В, UART свежий и чистый, transport/integrity/sequence/hw=0.

На tick 3586 мс после загрузки сохранён полный стартовый импульс: PA6 LOW 18114.8 мкс, TP23/PA4 LOW 18111.4 мкс, несовпадение 17 отсчётов (номинально 3.4 мкс). Оба фронта и окончания в окне, timeout/overflow/DMA errors=false; независимое декодирование совпадает. MOE0, start_window0, context_valid0: это событие до Пуска, не авария разгона на заданной частоте. Само по себе не доказывает UVLO, перегрузку или брак IPM.

Сейчас SD HIGH, но первая запись заняла захват: BIE=false, capture_running=false, first_record_ready=true, mask1028. START/ARM/CLEAR/RESET/перепрошивок не делали. Весь исходный снимок и сырая волна сохранены. Следующий необходимый физический шаг — один RESET Nucleo при уже устойчивых 15 В и J1 OFF, затем повторное чтение готовности захвата. Не просить включить J1 до этой проверки. Возвращать платы на ПК, снимать двигатель ещё раз или ждать разряда повторно не требуется.

## 2026-10-24: подготовлен прогон без двигателя 5→50 Гц, питание выключено

Пользователь подтвердил: двигатель отсоединён от J3, TP23→1 кОм→PA4 оставлен, J1 и 15 В выключены, обе платы на USB ПК. Никаких прошивок, RESET, CLEAR, ARM или START при подготовке не выполняли.

Пассивная запись idle_usb/ подтвердила пару 2401/2402, SAFE/PWM0/ARM0, Vdc около 1 В, чистую свежую связь UART. SD PA6 HIGH, Break IRQ включён, capture_running=true, first_record_ready=false; оба первых снимка пустые. Низкая шина даёт штатный MC_UNDER_VOLT. PA4 отдельно в этом этапе не измеряли; одновременный захват PA4/PA6 уже есть в установленном коде.

Новый tools/run_vf_smooth_start_no_motor_to_50.py использует прежний ограниченный сценарий без изменения прошивок или защит: 5,10,...50 Гц, разгон 5 Гц/с, выдержка 2 с на ступени, host STOP максимум 100 с, операторский watchdog 3 с, STOP при ошибке без повторного пуска. Требует --confirm-motor-disconnected и --confirm-powered-ready. Унаследован единственный ограниченный CLEAR известной пусковой UV после восстановления шины при чистой связи и свободном захвате; прочие аварии не сбрасываются. Selftest 28 проверок реальных readiness-guards на явно синтетических HV-статусах прошёл, аппаратных команд 0.

Артефакты: artifacts/live_bench_20261024/no_motor_to_50_prepare_r1/preparation_report.json, idle_usb/ и runner_selftest/report.json. Прогон ещё НЕ выполнен. Следующий физический шаг: обе платы на повербанки, USB ПК и Saleae отключены, включить только 15 В при J1 OFF. Затем прочитать свежий SD и готовность захвата до включения J1. Если стартовый SD занял захват, сохранить запись до любых действий. Не запускать сейчас: силовое выключено.

## 2026-10-24: установка U/f 2401/2402 завершена, связь и задания без силового проверены

После подтверждённого холодного USB-перезапуска Uno связь восстановилась. Актуальная пара Uno 2026102401 / Nucleo 2026102402, HMI совпадает с пакетом. Nucleo Flash 57888 байт побайтно совпадает с новым BIN; запись Uno ранее проверена loader/sketch verify. Калибровка не изменилась (SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17). Повторной прошивки в этом этапе не было.

При холодном старте Uno у Nucleo оставалась ожидаемая защёлка watchdog transport=7. Снимок сохранён, выполнен один RESET Nucleo через STLink при уже подтверждённых J1 OFF / мультиметр <20 В / USB ПК. После него transport=0, SD PA4/PA6 HIGH, свежие ответы UART. CLEAR/START/ARM не отправлялись. MC_UNDER_VOLT при выключенном J1 сохраняется как штатное состояние; защиты не обходили.

Живой тест SET FREQ 5→9.9→10→15→20→23→25→50→25→10→5→0 прошёл: 26 снимков SAFE/PWM0/ARM0, transport/integrity/sequence/UART hardware errors=0, счётчик ответов Nucleo растёт. Это подтверждает приём настроек HMI/Uno и связь при отключённых выходах; физическую частоту ШИМ и разгон ротора этим тестом не измеряли. Итоговое задание 0 Гц.

Расчёт реального кода MCSDK проверен на ПК для разгонов 0→50 Гц при 1/5/10 Гц/с. Скачок 15.921 В на 10 Гц устранён, новая огибающая непрерывна по значению и наклону; выше 10 Гц CCR совпадают с прежним кодом. Пусковой момент ниже 5 Гц и работу двигателя ещё предстоит проверить физически. Причина прежних физических UART/SD помех этой правкой не доказана.

Итог: artifacts/live_bench_20261024/vf_smooth_start_install_usb_r1/completion_summary.json. Подробности: completion_after_cold_start_r2.json, nucleo_reset_after_cold_start.json, idle_after_install/, idle_frequency/report.json. Оригинальный installer report.json с RPC timeout и слишком ранний completion_after_cold_start_r1.json с отсутствовавшим ещё ADB сохранены; более поздние проверки завершены успешно. Manifest installed/runtime_verified=true, rpc_pending=false; operationally_qualified=false. Пользователь просил текущий этап без силового: J1 не включать и моторный runner не запускать.

Ниже сохранена история предыдущих этапов; указания «ждём переподключения» уже закрыты этой проверкой.


## 2026-10-24: U/f2401/2402 записан и Flashпроверен; требуется холодныйUSBстартUnoдляRPC

Текущийзапроспользователяисправить10Гц/проверить0→50безсилового. Источникготовискомпилирован, тестыплавностиподробнее вразделениже. Физическуюподготовкупользовательподтвердилточно: инвертор **подключён**, J1OFF, мультиметр<20В, обеUSBПКвидны. Не повторятьэтотвопрос. J4состояниенеуточнено, поразрешениюможетоставатьсякакесть; силовоеНЕвключать.

Реально выполнен install_vf_smooth_start_usb_pair.py в vf_smooth_start_install_usb_r1. Оригинальный report.json **pass:false** лишьпо«installed connection not verified: timed out» послезавершённойзаписи: Flashкоманд2, Nucleo-verifyи«UNO Q loader and sketch verification PASSED»true, калибровкадо/послеодинакова. Оригинальныйотчётнепереписывать. НикакихSTART/ARM/CLEAR. ПерезапущентолькопринадлежащийarduinoHMIпроцесс (hmi_rpc_reconnect.log PID1189); RPCневосстановился (rpc_after_hmi_reconnect.json). Одиндополнительныйreset-onlyUnoчерезпроверенныйunoq_reset_run.cfgбеззаписиFlash (uno_reset_rpc_recovery.log)тожеRPCневернул (rpc_after_mcu_reset.json). Повторятьихпокругуненужно.

ОтдельнаяпассивнаяSWDпроверкаNucleoнаподтверждённомJ1OFF/<20В: firmware_register_verification.json passed:true, свежие57888BFlashпобайтносовпадаютновомуBIN, MOE0/BKE1/BKF9/AOE0, PA4input/nopull. НовыйUFкодестьвtargetELFdisassembly selftest/target_vf_controller.asm. Manifest images_written/flash_readback_verifiedtrue, installedfalse/RPCpending. Это**не**причинаповторнойпрошивки.

Черезasyncпользователюданединственныйшаг: **вынутьтолькоUSBUnoQна5сиподключитьобратно; Nucleo/проводкуоставить, J1OFF,15Вкакесть;написать«Unoпереподключена»**. Ответпокане получен. НуженхолодныйLinuxстартдлявнутреннейRPC;непроситьsudoпароль/необходитьправа/неперепрошивать. ПослеответадатьLinuxзагрузиться,проверитьADB3880458060иUSBforward18080/12222,GETстатус. Не считатьпервые5секотсутствияADBновойпроблемойпровода.

Затем python tools/verify_vf_smooth_start_install.py --outdir artifacts/live_bench_20261024/vf_smooth_start_install_usb_r1 --report-name completion_after_cold_start_r1.json. Verifierпринимаеторигинальныйinstallerpassfalseесли2flashverify/calunchangedподтверждены. Еслисвежийtransport7потомуUnoперезапускалась, сохранитьbeforeиодинRESETNucleoчерезSTLinkнаужеавторизованномJ1OFF/<20В;никакихCLEAR/повторнойзаписи. Не сбрасыватьпослепоявлениямоторнойаварии—еёнет,моторнепускали. Затем read_vf_smooth_start_idle.py --usb-transport и test_vf_smooth_start_idle.py (SAFE/PWM0задачи5..50..0, ходитпоWiFi). Завершитьпроверкуреальнойновойпары/калибровкивэтомбезсиловомэтапе, неподменяяhostплавностьфизическимразгоном.

## 2026-10-24: исправление U/f собрано, пользователь подтвердил J1OFF/DMM<20В; установка выполняется

Пользователь явно просит исправить скачок10Гц и проверить0→50Гц безсилового. Подготовлен новый постоянный пакет artifacts/live_bench_20261024/vf_smooth_start_r1, Uno2026102401/Nucleo2026102402; не тестовая прошивка. Прежний sealed2103/2104 не изменён. Curve: выше10Гц прежняяlinearветкабезизменений, ниже10Гц V=k*f +8*max(0,Vanchor-k*F/2)*x*(1-x)^2, x=f/F, F10Гц/Vanchor20Вphasepeak. V0=0, V5=20В, V10=35.921В; значение и производнаястыкуютсясlinearна10Гц. Boostпрофиль, который могбы датьнемонотонность, отвергаетсядозаписиCCR. Калибровка/UART/MCSDKзащиты/таймеры/SDне менялись; измененытолькоV/fконтроллер,комментариипараметровиIDallowlists. Изменениепусковогомоментаниже5Гцещёнеквалифицированонамоторе.

ActualC selftest:6250269checks/541080комбинаций, штатныйREMNG/FluxFreqCalc/CalcAngle/PWMна500Гц/16кГц. Разгоны0→50при1/5/10Гц/с, ретаргетбезскачка, частотныйшаг<=0.100002Гц, наибольшийшагамплитуды0.519122В вместо15.921024В. Левый/правыйнаклонна10Гц3.593445В/Гц, выше10ГцразницаCCR0. Старыйкодпровалилтотжетест. UART7447checks/903NEpairsPASS. ВсёнаПКсрегистровымиstubs/unusedCLPIstub; этонеосциллограмма/вращение. selftest/ramp0_to50.csv содержитразгонпри5Гц/с. Nucleo0errors0warnings/RAMmargin5608B, UnoLLEXTpass. Полныйпакет/USBinstallerverify прошёл; SHAUno2c18858590dfd1ffb8ce8f240a49cd470372c50772c3c012776d4826bd1db067, NucleoHEXc577427d5afd7ce4d0925f2f0d079bb764585395fd86910397895118522eebe6. installedпокаfalse.

ОбеUSBвидны, freshbeforeSAFE/PWM0/ARM0/Vbus1В/transport0. Наодиночноеуточнениепользовательпрямоответил **«Подключён, J1 выключен, по мультиметру ниже20В»**. Этоактуальнаяфизическаяподготовкадлязаписи; большене спрашиватьеёповторно. НикакогоHVстартаэтотответнеразрешает. Выполняется python tools/install_vf_smooth_start_usb_pair.py --confirm-j1-off-usb-bus-below-20v --outdir artifacts/live_bench_20261024/vf_smooth_start_install_usb_r1, session45569. NucleoFlashverifyвлогепрошёл, Unoпокаожидается. Не запускатьinstallerещёраз/неписатьinstalledдоreport. Послеегоокончания tools/verify_vf_smooth_start_install.py --outdir .../vf_smooth_start_install_usb_r1; еслиожидаемыйtransport7послепрошивкиUno, сначалаархивировать, одинRESETNucleoчерезSTLinkнаподтверждённомJ1OFF/<20В, безCLEAR/START/повторнойзаписи.

Затем GET-only tools/read_vf_smooth_start_idle.py --usb-transport --outdir .../idle_after_install и живой tools/test_vf_smooth_start_idle.py --outdir .../idle_frequency (обёрткастарогоSAFE/PWM0тестазаданийдляточной2401/2402пары). Самliveтест ходитпоWiFi, неUSBтуннелю. Никакихактивныхимпульсовприотсутствиисилового: productionUVзащитунеобходить. Результатвыдаватькакплавностьразгонногозадания/расчёта, некакфизическийразгонротора. Новый tools/run_vf_smooth_start_to_50.py подготовленнабудущее; вэтотбезсиловойэтапНЕЗАПУСКАТЬ.

## 2026-10-24: тест без силового завершён в режиме SAFE; реальных импульсов не включали

Пользователь попросил «тестируй пока без силового», затем на138Вконтроллера ответил «я просто пока отключил инвертор поэтому так». Точный объём отключения (толькоJ1 или шлейф/всясиловаяплата) НЕуточнён, независимогоDMMнет. Сеть/силовуючасть НЕвключать наосновеэтойфразы. ОбеUSBплатыфактическивидны: UnoADB3880458060/COM10, NucleoSTLinkCOM13. HTTPпоWiFiработает. Поначалу Vbus138→137В, потом0В; не меняли калибровку и не объявляли остаточныйзаряд/ADCнеисправность доказанными. Никаких SWD/flash/reset/START/CLEAR/ARM не выполнялось.

Результаты в artifacts/live_bench_20261024/no_mains_check_r1/report.json. Новые tools/test_idle_frequency_commands.py и test_current_vf_without_mains.py. Реальная runtimeпара2103/2104. По живому HMI/Uno выполнены SET FREQ5→9.9→10→15→20→23→25→50→25→10→5→0, все подтверждены;26снимковвсёвремяSAFE/PWM0/ARM0, свежиеответыNucleo/UARTprogress, CRC/sequence/UARThw/transport0. SET FREQ0 проходит обычный STOP endpoint; другихпараметровнеписали. Это подтверждаетнастройкиHMI→Uno иOFFсвязь, НЕактивнуючастоту/ШИМNucleo. В концеSAFE/PWM0/freq_cmd0/arm0, UARTgood4096/age20мс.

На ПК с -Ofast скомпилированы точные установленные ACIM_VF_Controller/PWM_SetPhasePWMOutputs/таблицаsin, 1082160 вызововпо0..50Гц/720углам/250,325,380В и6492983проверок: конечныеduty0..1/CCR<ARR, invalidnormalizer/dutyнепубликуютCCR. Это регистровыеhoststubs, НЕосциллограмма/модельмотора. Скачок10Гц20→35.921024Вpeak подтверждён actualC. При325ВsinPWMвыходитнаограничениенапряжениядо50Гц (на50Гцphasepeak162.5В,lineRMS199В), частотногообрывана20–25Гцнет. ПрежнийUARTclean-confirmhosttestповторно7447checks/903NEpairsPASSвотдельнойпапке, sealedpackageнеизменён.

GET-only after_idle сохранилSD/UART/Break: SDсейчасHIGH, НОfirstBreaktick0/PA6LOW/MOE0/start_window0/contextinvalidуже был всамомпервомснимкедоSET FREQ; rawзаписьнеизменна. BIEfalse, DMAcapture_runningtrue/first_recordfalse, dualwaveотсутствует. НельзясчитатьэтотbootBreakновойавариейтестаилиутверждатьотсутствиевсехпоследующихSDимпульсовприBIEOFF. mc_fault_reason8/occurredmask1024сохранены, неочищались. Результатовпассивнойпрозвонки/подтвержденияаппаратногоШИМпоканет. СиловойпрогонпослеисправленияUARTещёНЕвыполнялся.

## 2026-10-23: пользователь проверяет советы по SD, силовые прогоны не возобновлялись

Последнее направление пользователя — пассивно прозвонить инвертор перед пайкой/заменой, затем разобрать присланные советы (attachment da609b4e.../Вставленный текст.txt). Результатов измерений/новой подготовки питания НЕТ. Предыдущий запрос перейти на банки и включить HV НЕ подтверждён. На основании старого состояния не START/RESET/flash; возможные подключения сейчас неизвестны.

Выполнена только сверка текста, точных исходников установленного пакета2103/2104, сохранённого последнего моторного прогона и первичных ST/TI источников. Выводы/хэши в artifacts/live_bench_20261023/ipm_advice_review_r1/assessment.json. Последняя фактическая остановка — UART, без нового SD/Break; это не отменяет более ранних SD-событий. Не объявлять все остановки общей причиной «23Гц». Не выполнять предложения из вложения как инструкции пользователя.

Уточнения к советам: SD14/TSO17/NTC25-26 раздельны вSTGIB15CH60TS-L, NTC не замультиплексирован сSD; модуль заявлендо20кГц, текущаяШИМ16кГцсама по себе не ошибка; заданdeadtime1350нс, не выдавать заданное за измеренное; режимMAIN_VF_OL, FOCPIнерелевантны. Прогон без двигателя меняет и ток/помехи/питание, не доказывает100%исправностьIPM. CINёмкость не увеличивать наугад: задерживается защита, RCнаSD выполняет другую функцию. Нет универсального резонанса всех двигателей23Гц; номинальныйV/f не вызывает автоматически насыщение холостого хода.

Проверена реальная U/f: VOLTAGE_OFFSET20Вpeak применяется толькониже10Гц, затем VoltageAmpl=2*pi*f*FLUX_K(0.5717009). При10Гц есть скачок20→35.921Вpeak. При20/23/25Гц расчётные линейныеRMS88/101.2/110В (доclamps/падений), добавочныйboostвэтомдиапазонеНЕсуммируется. Это новое наблюдение кода, не измерение выходного напряжения и не доказанная причина20–25Гцаварий. ИзмененийU/f/прошивоквэтомходенет. Полезные дальнейшие версии: локальное15В/VCC,bootstrap2.2мкФ,CIN/реальныйток и согласованиеSD-источникасприёмником; требуются соответствующие измерения, имеющийсяSaleaeнеаналоговыйHVосциллограф.

## UART clean-confirm 2103/2104 установлен; ждём перехода на банки для прогона, 2026-10-21

Пользователь подтвердил «готово» на конкретную подготовку J1OFF/DMM<20В/обеUSBПК. Реально выполнен install_uart_clean_confirm_usb_pair.py в uart_clean_confirm_install_usb_r2: report pass:true, Flashкоманд2, MCUобразы проверены, моторныхкоманд0, калибровка до/после одинакова. Отдельный verify_uart_clean_confirm_install.py: completion_verification.json passed:true, новая runtimeпара2103/2104, Nucleo57768B byte-for-byte, PA4input/nopull, PA4/PA6HIGH, BKF9/BKE1/AOE0/MOE0, HMIserver/appSHAсовпадают, калибровкаSHAa89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17 неизменна. Пара installed:true в manifest, но motor qualification false.

После прошивки сохранился ожидаемый транспортный watchdog7 из времени, когда Uno записывалась; все события архивированы до сброса. Через подключённый STLink один раз автоматически RESET Nucleo на подтверждённом J1OFF/12..9В/15В можетON; никаких CLEAR/START/повторнойзаписи. post_programming_nucleo_reset.json passed:true, transport0. GET-only read_uart_clean_confirm_idle.py --usb-transport сохранил idle_after_reset: pass:true, SAFE/PWM0/ARM0/ESTOP0, UARTgood1508/age37мс, CRC/sequence/hardwareUART/transport/drop0, Vbus6В, reported30°C. Низкая DC-шина вызывает только ожидаемый MC_UNDER_VOLT mask4/reason8. SDHIGH/BIEON/capturefree, Breakснимковнет. Нельзя выдавать этот idlepass за моторный тест/отсутствие помех при ШИМ.

Последний запрос пользователю через async: перевести обе платы с ПК на повербанки, SaleaeOFF, двигатель и TP23→1кОм→PA4 оставить; при закрытом стенде15ВON и J1черезsoftstart, Пуск/RESETненажимать. **Ответ на этот новый запрос пока не получен.** До ответа реальное состояние J1OFF/обеПК/15ВдопускаетсяON. Новая перепрошивка не нужна. После ответа сначала GET-only reader поWiFi artifacts/.../uart_clean_confirm_powered_idle_r1; проверить exactpair/свежесть/SD/BIE/свободныйзахват. Затем уже авторизованный один tools/run_uart_clean_confirm_to_50.py --confirm-powered-ready --outdir artifacts/live_bench_20261021/uart_clean_confirm_to_50_r1, без повторов; штатный runner допускает ровно один CLEAR лишь известной стартовой UV4 послеHVready и при свободномзахвате, не UART/SD/DP. Запрос5→10→...→50Гц,2снаступень,100сhostdeadline,3сoperatorwatchdog; STOPприошибке, собратьwave/UARTtrace. Руками не ослаблять защиты ради50Гц.

## UART clean-confirm: собран и проверен, запись новой пары выполняется, 2026-10-21

Пользователь просит устранить UART-срывы для разгона до 50 Гц. По сохранённому fatal кадру из sd_dual_motor_to_25_r1 доказано: полный 43-байтовый пакет с верным CRC, две NE-метки на байтах 6/7, старый приёмник отвергает его при уже занятом бюджете 2/2. Реальные восстановленные CRC-повреждения тоже присутствуют, физический источник помех не установлен. ST ES0431 §2.12.2 описывает возможное повреждение при коротком LOW на второй половине stop bit, но на стенде это не измерено.

Готовый пакет artifacts/live_bench_20261021/uart_clean_confirm_r1, Uno2026102103/Nucleo2026102104. Новая ветка только при уже работающем квалифицированном канале: один полный CRC-верный ENABLE с несколькими NE НЕ выполняется, НЕ меняет previous/last_valid_ms и НЕ расходует/сбрасывает бюджет повреждённых пакетов. Требуется следующая ЧИСТАЯ команда с новым допустимым seq в пределах 100 мс. Повторный шум/тайм-аут — немедленная защёлка OFF; чистый STOP проходит сразу. Бюджет двух настоящих повреждений за 1000 мс, watchdog300 мс, frame15 мс, MCSDK/SD/BKIN/калибровка/ШИМ неизменны. Это исправление обработки ограниченного события, не фильтр электрической помехи и не доказанная работа до50Гц.

Офлайн actual C replay: старый отказ воспроизведён, новый7447 проверок/903 расположения пары NE прошли; 271 прежняя UART-проверка, 1149 SD-сценариев и 65536 GPIO-значений, семь отрицательных контролей. Следующий чистый пакет в replay синтетический, отсутствует в физической записи. Сборки завершены: Nucleo0errors/0warnings, RAMmargin5608B; UnoLLEXTpass. Ша256 Uno elf-zsk7e2cd23f1a26c315fda644ff2b3b8e19f7a031bb13512c54fc0bbec59f0d5b8d, NucleoHEXb17fc61e5d4d3743bc6beb241a3b51d86263dca173bfd22176f90f3dbb1788cb. installer --verify-package-only прошёл; knownNE latch разрешён ТОЛЬКО для программирования на подтверждённом J1OFF/DMM<=20В/USB, без CLEAR. Runner run_uart_clean_confirm_to_50.py подготовлен: 5..50Гц,100с hostdeadline,3сoperatorwatchdog; selftest17checks, НЕ запускался.

На запрос подготовки пользователь ответил «готово»: J1 выключен, DMMниже20В, обе платы на ПК; двигатель и TP23→1кОм→PA4 остаются, J4 может быть15ВON. Новые подтверждения этого же состояния не требовать. Первый USB get-state попал на загрузку Linux и отказал до любых мутаций. uart_clean_confirm_install_usb_r1/report.json pass:false/flash0: HMI503 при загрузке; НЕ переписывать. Спустя несколько секунд ADB/COM10/STLinkCOM13 вернулись сами, freshUSBHTTP показал старую пару2101/2102/SAFE/PWM0/Vbus12В. Никаких HMI/router/MCU reset для восстановления не выполнялось.

Повторная установка уже запущена в uart_clean_confirm_install_usb_r2. По логам Nucleo Flashverify прошёл, Uno загрузка и «UNO Q loader and sketch verification PASSED» прошли. Установщик ещё ожидает итоговую связь/калибровку; НЕ объявлять установленную пару квалифицированной до завершения report и verifier. Контролировать текущую session60004, НЕ запускать установку ещё раз. После успешного report: tools/verify_uart_clean_confirm_install.py --outdir artifacts/live_bench_20261021/uart_clean_confirm_install_usb_r2, затем GET-only read_uart_clean_confirm_idle.py --usb-transport. Если bootRPC не вернулся, сохранить оригинальный неуспешный report, не делать повторный flash. Питание J1OFF/ПК остаётся до верификации. Запуск двигателя/переход обратно на банки ещё НЕ выполнен.

## Фактический прогон 5→10→15→20: остановка UART, SD не срабатывал, 2026-10-21

Это обновление отменяет ниже прежний статус «прогон ещё не запускался». После подтверждённого RESET пассивная проверка sd_dual_after_reset_r1 показала свежие 319 В, чистую пару 2101/2102 и свободный захват. Выполнен один авторизованный tools/run_sd_dual_to_25.py, результаты в artifacts/live_bench_20261021/sd_dual_motor_to_25_r1. START=1, CLEAR/flash/CAL=0. Установились задания поля 5, 10, 15 Гц; переход к 20 Гц завершился защитной остановкой. 25 Гц НЕ задавались. Максимальная активная HTTP-выборка задания поля 18 Гц; фактическая скорость ротора не измерена. Пользователь подтвердил ровное вращение и заметное ускорение.

Причина этой остановки — UART: transport=5 (UV3_NOISE_REJECTED), NE=4, reason=12. MCSDK masks=0/0; SD PA6 HIGH, BIE включён, захват свободен, ни одного Break в этом прогоне не записано. Сохранённый fatal-кадр целый, CRC верен, две NE-метки на байтах 6 и 7 (с нуля), бюджет восстановления уже 2/2. Установленный uv3_noise_allowed принимает только одну NE-метку на проверенном кадре, поэтому этот кадр отвергнут; uv3_drop при исчерпанном бюджете защёлкивает ошибку. Предыдущий сохранённый recovered-reject действительно имеет неверный CRC. Нулевые публичные integrity/sequence counters НЕ означают отсутствия всех восстановленных CRC-ошибок; прежнее «CRC нет» было слишком широким выводом. Физическая причина помех/NE пока не установлена. Не ослаблять проверки и не повторять START/CLEAR автоматически.

После STOP подтверждены SAFE/PWM0/ARM0, UART-ошибка удерживается, ESTOP1. GET-only post_stop_read pass:true означает успешное чтение, не успешный моторный прогон. Последнее физическое состояние: J1 и 15 В включены, обе платы на повербанках, ПК/Saleae отключены, TP23→1кОм→PA4 оставлен. Не выполнять SWD/ADB/прошивку и не просить новое переключение питания ради завершения отчёта.

Пользователь приблизительно видел 0,1 с небольшим Вт на источнике 15 В. Сохранено в operator_confirmation.json как непроверенное показание дисплея; если ровно 0,1 Вт/15 В, это 6,67 мА. Это вспомогательная цепь драйверов, не мощность двигателя и не доказательство отсутствия краткой просадки. analysis.json сохраняет разбор UART и границы выводов. Ранее записанный 18,1986 мс PA6 LOW при PA4 HIGH относится к включению J1 ДО этого RESET, а не к текущей моторной остановке.

## Пользователь просит повторный моторный прогон с TP23→1кОм→PA4; профиль готов, нужен свободный захват, 2026-10-21

Пользователь предложил «попробуй опять погонять двигатель» с сохранённым дополнительнымпроводом; это авторизация повторного диагностическогопуска, не требованиеповторнойпрозвонки. Никакойпрозвонки/снятиярезисторане требоватькакпредусловиеэтогоповтора. GET before_status.json в `sd_dual_retry_preparation_r1`:новаяпара2101/2102, SAFE/PWM0/Vbus320V/age31ms/transport0,UVfirstmask4,PA6HIGH/configOK, **capture_runningfalse/first_record_readytrue/BIEfalse**. Сохранён18.1986мсзахватсJ1-включениядоПуска, первоеокноSTARTещёпустое. Существующаяпрошивкаоднократнаядозагрузки; STOP/CLEAR/START НЕосвобождаютdualwave. Нельзяпускатьпрогонсо старойволнойилипростоCLEARзанятыйзахват.

Подготовлен `tools/run_sd_dual_to_25.py`: адаптер испытанногоrunner кточнойпаре2101/2102, профиль5→10→15→20→25Hz,HOLD2s,hostdeadline60s,операторскийwatchdog3s,одноSTART/STOPприошибке,никакихповторов/flash/CAL. СохраняетсемантикуодногоCLEARлишьизвестнойстартовойUV4 послеHVreadyиТОЛЬКОприсвободномзахвате/SDHIGH/BIEON. Существующий `run_fast_bkin_to_50.py` получил лишь PROFILEconstantс прежнимdefault5-to50,длячестногопрофиляновогоадаптера. `--self-test`offlinePASSED:синтетическиечистыеусловияпринимаются,реальноезанятоесостояниеотклонено иCLEARнедопускается,негативныеSD/CRC/пара/lowVbus/DPотклонены. runner_selftest.json/ preparation.json сохранены,hardwarecommands0. ActualмоторныйпрогонЕЩЁНЕЗАПУСКАЛСЯ,START/CLEAR/RESET/flash0.

Вфиналепользователюединыйфизическийшагбезперепрошивки: выключитьТОЛЬКОJ1,оставить15В/банкиON,приDMM<=20VнажатьRESETNucleoОДИНраз,ждать10sприустойчивых15В,вновьJ1черезsoftstart,Пускненажимать,проводTP23→1кОм→PA4оставить. Это освобождаетодноразовыйрегистратор;следомчитатьfreshHVbaselineперед ужеавторизованнымпрогоном. Подтвержденияэтойподготовкипоканет. ВозможноповторноесобытиенавключенииJ1занимаетзахват—тогданеRUNнастаройволне,сохранитьрезультат;необещатьпускнезависимоотфактическихфлагов.

## Подтверждено TP23→1кОм→PA4; следующий шаг обесточенная прозвонка двух путей, 2026-10-21

Пользователь подтвердил точнуюцепь: **TP23→последовательный1кОм→PA4**, фразаTP22былаошибкойраспознаванияречи. Резисторвдобавленнойдиагностическойветке,нештатномSD→PA6;убиратьегоНЕпросить. Сохранёнoperator_series_resistor_confirmation.json. Подтвержденияобесточивания/реальныхизмеренийсопротивленияЕЩЁНЕТ;последнеефизическоесостояниеJ1ON/J4ON/банки/ПКиSaleaeOFF/PWM0/сохранённыйBreak. Не выдаватьуточнениепроводазаизмереннуюэлектрическуюцелостность.

Следующийтестдляпользователя: выключитьJ1и15В,дождатьсяDCоколо0Впозаранееподключённомумультиметру,отключитьобаповербанка5В,USBнеподключать. ТольконаполностьюобесточенномстендеврежимеОм измерить **TP23→PA4(CN7-32илиA2/CN8-3):ожидаемооколо1кОм** и **TP23→PA6/CN10-13:ожидаемопочтиноль/сопротивлениесоединённыхщупов**. У1кОмпрозвонказуммеромможетнепищать—нуженчисловойΩ,неотсутствиезвукакакпризнакобрыва. Запроситьдвазначения/OL. Неотсоединятьдвигатель,непереставлятьрезистор,неперепрошивать. Диагностическийсмысл:подтвердитьнезависимуюветкуипутьEM_STOP,преждечемобъявлятьисточник18мсLOWнаPA6/приHIGHPA4. ОкончательнаяпричинаSD/25ГцНЕустановлена;START/CLEAR/RESET0вэтомходе.

## Пользователь уточнил резистор1кОм у TP23: скорректировать ожидаемую прозвонку, 2026-10-21

После запросаобесточеннойпрозвонкипользовательсообщил: «какраньшевключилчерезодинкилоомна…23…поэтому…сопротивлениеогромное». **Это НЕподтверждениевыполненияотключения/разрядки/измерений**;читатьJ1ON/J4ON/банки до новогоуточнения. **Непринимать1кОмзаобрыв**. ЕслирезисторстоитпоследовательновНОВОЙветкеTP23→PA4, ожидаемосопротивлениеэтойветки≈1кОм, прежнеетребование«почтиноль»кнейНЕприменимо. ШтатныйпутьTP23→PA6осталсянизкоомнымтолькоеслирезисторнепоставленименнотуда. ТочнаяветкарезисторапокаНЕуточнена: вфиналевопрос, онвдобавленномпроводеTP23→PA4иливштатномSD→PA6. Ничегонеснимать/незамыкатьподпитанием.

PA4фактическипроверенINPUT/NOPULL,поэтомусампосебе1кОмпоследовательносвысокоомнымвходомобычнонеобъясняет18.2мссохраненияHIGHприреальномLOWнаисточнике. Этоинженернаяоценкаприотсутствиидругойнагрузки/ёмкости, не доказательствочтоветканевлияет. Полнаяэлектрическаяцепь/доп.конденсаторы/контактыпоканеизмерены. Запись18.1986мсPA6LOW/PA4HIGHсохранена;источникLOW/дефектIPMНЕустановлен. Непредлагатьубиратьзащитныйрезисторпопервомуупоминанию,поканепонятноегорасположение. Файлoperator_series_resistor_note.jsonсохранёнвhv_idle_r1;hardwarecommands0.

## Настоящий HVbaseline: PA6 LOW18.1986мс при TP23→PA4 HIGH, до Пуска, 2026-10-21

Пользователь явно подтвердил: J1ONчерезsoftstart,J4=15ВON,обеплатынабанках,ПК/Saleaeотключены,TP23→PA4оставлен,Пуск/RESETне нажимал. GET-only `python tools/read_sd_dual_idle.py --outdir artifacts/live_bench_20261021/sd_dual_hv_idle_r1` **pass:true**. Новаяпара2101/2102, freshUART8ms, good6359, integrity/sequence/hardwareUART/transport/drop0,SAFE/PWM0/ARM0. **DC319V**,reportedtemp48°C. Сохранён полноценный первый двухточечный schema5 record320B,14pages/no badpages,independentdecoder совпал сHMI, eventtick324623совпал сfirstBreaksnapshot.

Главнаянаходка: совместныйRLE [state3(HIGH/HIGH),2041samples], [state2(PA6LOW/PA4HIGH),90993samples], [state3,321samples]. **PA6LOWноминально18.1986мс (−1.4us…+18.1972ms отIRQpublication), TP23→PA4 остаётсяHIGH во всёмокне**. ПоследнийHIGHхвост64.2us; flags513/FROZEN+POST_DONE, timeout/DMAerror/overrun/overflow0,необрезанныедвафронтаPA6. IRQGPIOAIDR0xA014самостоятельноподтверждаетPA4HIGH/PA6LOW; BIF1/B2IF0/MOE0/BKF9/BKE1. cachedcontext48msстарый, Vbus0/temp30/state10/UVmask4; НЕвыдавать0VзаVbusвточныймоментсобытия. First_start_windowcapturedfalse: это включениепитанияДОлюбогоПуска, НЕпрежнийрабочийсбой25Гц. ТекущийPA6HIGH, BIEfalse/захватзамороженпервымсобытием; следующийпускнеосуществлятьсо старымзанятымрегистратором.

Это сильнаязацепкавтрактеSD иливцепинезависимогопробника, но НЕдоказательствоисправностимодуля/найденнойокончательнойпричины: **электрическаяцелостностьTP23→PA4ещёнепроверялась**,пользовательподтвердилподключениесловами;могутвлиятьразныепорогивходов/опорнаяземля/захват. ДажеHIGH/HIGHподauxсампосути неотличает плавающийPA4отсоединённого. Первичныйследующийтестбезновойпрошивки—прозвонкаобесточеннойцепи TP23→PA4 и TP23→PA6(CN10-13) черезосновнойкабель/переходник, приJ1OFF/J4OFF/обоихповербанках5VOFF/разряженнойDCшине. Штатный путьожидаемонизкоомный,безпоследовательныхактивныхпреобразователей; IHM09M2R3=0ΩветкаPA6,R1=0ΩPA11. Никакихманипуляций/омметраподHV. Не проситьсниматьдвигатель/новуюпрошивку. Сначалаотключение/разряд,затемконтакты. Необходитьзащиту/BKINи не замыкатьSDна3.3V.

ПриэтойпроверкеJ1/J4/банкиНЕвыключались,hardwarecommands0. На моментзавершенияходасчитать **J1ON,J4ON,банки,PC/SaleaeOFF,PWM0**,новыйсохранённыйBreakнеочищен. Файлыanalysis.json/bkin_wave.bin/decoded_wave.json/break_snapshot.json/status/logsсохраненывhv_idle_r1. Пользователюсообщеноразличиелиний;следующаявозможностьизмерений—двапунктапрозвонкив полностьюобесточенномсостоянии. Причину25Гцещёнеприписыватьэтому18мссобытию.

ЛокальныйUM2014Figure7PNGвизуальноперепроверен: TP23тотжеузелSD/EM_STOPсR28к3.3V/C20, **D6 относитсяTSOclamp,НЕразделяетSD/EM_STOP**. Не строитьдиоднуюверсиюSDнаD6. STсхемапереходника прочитанаweb: https://www.st.com/resource/en/schematic_pack/x-nucleo-ihm09m2_schematic.pdf . СхемаSTEVAL: https://www.st.com/resource/en/schematic_pack/steval-ipm15b_schematic.pdf . Дляокончательнойлокализацииприцелыхобоихпутяхпонадобитсяконтрольвлияния/перестановкавходовилианалоговыйзамер,необъявлятьпа4HIGHдоказательствомвыходамодулябезвалидации.

## Переход на банки прочитан; пользователь уточнил J1 НЕ включал, 2026-10-21

После сообщения «платы на банках,15В и силовоеON» выполнен только WiFiGETreader. r1 (`sd_dual_powered_baseline_r1`) неуспешен из-за запускаLinux/RPC (timeouts/RemoteDisconnected), r2 `sd_dual_powered_baseline_r2` **pass:true** после завершенияboot, безRESET/перезапускаHMI/flash/моторныхкоманд. Linuxuptime69sприSSHread-onlycheck; HMI/router/AppCLIactive; ранниеrouterinvalidpacketstartupошибкисамипрошли, никакихвосстановительныхмутацийвэтомходенеделали.

Новаяпара2101/2102, SAFE/PWM0/ARM0, freshUART21ms,good354→2304наповторномчтении, всеCRC/sequence/hardware/transport/drop0. **NucleoпередаётVbus0V/word0**,mask4/MC_UNDER_VOLT. PA6HIGH, configOK/BIEON, capture_runningtrue/first_recordfalse, всеBreaksnapshotscapturedfalse, wave'-'. TP23отдельнотекущимонлайномнеизмерен(егоуровеньдоступенвдвухточечнойволнепослесобытия);неутверждатьbothHIGHподсиловымпоодномуlivePA6. НикакогоBreakпослепереходанабанкинебыло. 8доп.свежихотсчётовzero_vbus_followup.jsonвсеVbus0. СырыесловаприходятсNucleo,неперекалибровывали; кодMCSDKREAL_SENSOR, regularconversionsизSafetyTask, причина0безэталонаизсофтанеобъявлялась.

Наasyncвопроспоказаниямультиметрапользовательуточнил **«я не включал силовое»**. ЭтоПОСЛЕДНЕЕдостоверноефизическоесостояние, отменяетпредыдущеесловесноеJ1ON. Сохранёнoperator_power_state_correction.json. ПоэтомуVbus0/UV4соответствуютJ1OFF, не считатьновойнеисправностьюADC/питания/SD. На15ВJ4ON,банках,ПКиSaleaeотключены,TP23→PA4оставлен. **НастоящийсиловойbaselineещёНЕвыполнен**, несмотрянаимяпапкиpowered. Дальшепользователюодиншаг:включитьтолькоSTEVALJ1черезsoftstartпри закрытомстенде;15В/банки/проводоставить;Пуск/RESETненажимать;подтвердитьготовность. ПоследующегоподтвержденияJ1ONпоканет. НеSTARTдоfreshHVbaseline/состояниязахвата.

## J4=15В включены при J1OFF: оба SD HIGH, DMA видит обе линии, Break не было, 2026-10-21

Пользователь подтвердил:15ВON,J1OFF,обеUSBПКиTP23→PA4не трогал. Выполнен GET-only `python tools/read_sd_dual_idle.py --usb-transport --outdir artifacts/live_bench_20261021/sd_dual_aux15_r1` **pass:true**. Новаяобёрткаread_sd_dual_idle.py задаёт C/PAIR2101/2102 и USBforward18080; базовыйreader прежний. 7свежихstatus,последнийSAFE/PWM0/ARM0,Vbus0V,temp30°C,age29ms,good9904,CRC/integrity/sequence/hwUART/transport/drop0. MCfault5/reason8/mask4остаютсяожидаемымundervoltageDC приJ1OFF. ОбеBreaksnapshotcapturedfalse; waveavailablefalse/not_received, raw'-', goodpages0/badpages0 — **после подачи15В аппаратногоBreak не записано**, это не подтверждение HVисправности/динамическихимпульсов.

Дополнительно пассивныйSWDHOTPLUGбезreset/write: `hardware_input_readback.json` подтверждаетPA4INPUT/NOPULL,PA4HIGH,PA6HIGH,DMA2channel1EN1/CPAR0x48000010(GPIOAIDR). Восемь реальных отсчётовизRAMring содержат PA6=1,PA4=1. Это подтверждение пути чтения обоихбитов, а не измерение длительности импульсов/квалификация5МГц. START/CLEAR/RESET/flash/CAL0; логизахватаиGPIO/DMA/RAMсохраненывaux15папке. Физическое15ВнеизмерялосьпоADC(нетканалаJ4),включениесо словоператора. Перед первымсиловымпускомзахватпока свободен.

Следующийшагпользователювфинале:перевестиобеплатысUSBПКнаповербанк,15ВможнооставитьON,проводTP23→PA4оставить; послеотключенияПК/SaleaeвключитьJ1черезsoftstartпри закрытомстенде,Пуск/RESETненажимать,подтвердитьсостояние. Это ещё НЕподтверждено. Затем читатьпоWiFiновымdualreaderbaseline,проверитьзахват/состояниедопуска;невыдаватьaux15безсобытиязауспехдо25/50Гц. Старыйrunner2001/2002неиспользоватьбезадаптацииидентичностей/проверокновогосхема5. Новый силовойпрогонещёнезапускался.

## После холодного USB-переподключения связь восстановилась, dual-пара проверена, 2026-10-21

Пользователь подтвердил USB Uno Q переподключён, J1 и15В OFF. В начале проверки Uno ещё загружалась: ADB/COM10 отсутствовали, WiFitimeout. Первый пассивный verifier сохранил **неуспешный completion_verification.json** (ADBforwarddeviceabsent); не удалён/не переписан. Через короткое ожидание ADB3880458060 вернулся сам, без просьбы ещё раз трогать провода. В `tools/verify_sd_dual_capture_install.py` добавлен --report-name с сохранением предыдущих отчётов и отдельных логов по stem.

`python tools/verify_sd_dual_capture_install.py --outdir artifacts/live_bench_20261021/sd_dual_capture_install_usb_r1 --report-name completion_after_cold_start_r2.json` **passed:true**. 10 свежих HTTP samples, фактическая runtimeпара **Uno2026102101/Nucleo2026102102**, UARTgood118→384, age3ms на последнейвыборке, все mc_bad/integrity/sequence/UARThardware/transport=0. SAFE/PWM0/ARM0, Vbus0V. Маска4/MCfault5/reason8 — undervoltage при действительно выключенном J1, не новая аварияSD. PA4input/NOPULL, обаPA4/PA6HIGH, BKF9/BKE1/AOE0/MOE0; capture_runningtrue, first_record_readyfalse, break_wave'-', uart_reject'-'. Никаких START/CLEAR/RESET/flash в этом ходе. Свежий Nucleo readback55672Bbyte-for-byte, liveHMIserver/appSHA совпадаютпакету, калибровка a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17 неизменна/accepted, manualVFavailable. UnoFlashverify at install, а теперьподтверждёнruntimeID. Логиэтойпроверки отдельнопод `completion_after_cold_start_r2/`, предыдущиеfirmware_registerлоги сохранены.

Следующий единичный шаг пользователю в финале: **включитьтолько15ВJ4, оставивJ1OFF, обеплатыUSBПК иTP23→PA4 какесть, RESET/Пуск не нажимать**. После ответа архивировать dualSD и первое включение15В; не требоватьпредварительнопереходанаповербанкдляэтогоaux-onlyэтапа. Подтверждениявключения15Вещёнет. Полный HVпрогон/реальная причинаSDещёнепроверены.

## Двухточечная прошивка записана и проверена; требуется восстановить RPC Uno, 2026-10-21

Пользователь явно подтвердил: PA4 Nucleo соединён с STEVAL TP23, платы на ПК USB, силовое и 15В не подавал. Это ответ на конкретную подготовку после инструкции DMM<20В; повторное подтверждение не запрашивали. ADB3880458060device/UnoCOM10/STLink003A002C3335510933383531COM13 найдены. Запущен `python tools/install_sd_dual_capture_usb_pair.py --confirm-j1-off-usb-bus-below-20v --outdir artifacts/live_bench_20261021/sd_dual_capture_install_usb_r1`. Новый HMI установлен с сохранением резервной копии/калибровки; Nucleo2102 и Uno2101 записаны, оба readback-verify PASSED. Результат оригинального installer `report.json` **pass:false** только из-за end-to-endRPC timeout; НЕ переписывать его в успешный и не повторять flash.

Отдельный `firmware_register_verification.json` **firmware_verified:true, rpc_ready:false**: свежий HOTPLUG readbackNucleo **55672B byte-for-byte** соответствует BIN; PA4=INPUT/NOPULL, PA4HIGH и PA6HIGH, BKF9/BKE1/AOE0/MOE0, AF1=0x201, CKD2, TIM2PSC0/ARR33. Uno readback подтверждён логом `UNO Q loader and sketch verification PASSED`, но runtimeID поRPC ещё НЕ получен. Установленные HMIserver/appSHA совпадают с новым пакетом; калибровкадо/после совпадает a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. Никаких START/CLEAR/ARM/CAL; poweredtest0.

После прошивки один раз перезапущен только принадлежащий arduino HMIпроцесс через корректную проверку PID/cwd/Restart=always (`hmi_rpc_reconnect.log`); HTTP/API всё ещё timeout. Rootarduino-routerPID559active, adbus_uid1000. Штатный `adb reboot` попробован один раз: error:closed/exit1, подтверждения перезагрузки нет; после команды routerPID559 прежний, ADBdevice доступен. Не использовать docker/sysupgrade как обход прав, не проситьsudoпароль. Последний `rpc_after_reconnect.json`:HTTPtimeout4s. Дальнейший практический шаг пользователю — **вынуть только USB Uno Q на5с и подключить обратно**, Nucleo/проводTP23/двигатель оставить, J1/J4оставитьOFF. Запрос этого шага дан в финальном сообщении; подтверждения ещё нет. После ответа — пассивная проверка `python tools/verify_sd_dual_capture_install.py --outdir artifacts/live_bench_20261021/sd_dual_capture_install_usb_r1`; файлcompletion_verification.json ещё отсутствует. Скрипт не сбрасывает/прошивает/очищает защиты и проверяет новую пару,кал,GPIO/регистры/образы. Если сохраняется bootUARTtimeout7, это отдельная сохранённая защёлка, не повод скрывать/автоматически CLEAR/перезапускать без архивирования. Никакого перехода на банки/15В/силовое до восстановления RPC и чтения реального состояния.

## Подготовлен двухточечный SD-захват TP23→PA4 и штатный PA6, 2026-10-21

По запросу пользователя подготовлен, собран и офлайн проверен пакет `artifacts/live_bench_20261021/sd_dual_capture_r1`. **НЕ УСТАНОВЛЕН**, hardware/motor/flash commands=0. На стенде по последней проверке остаётся пара 2026102001/2026102002, текущего физического состояния в этом ходе не спрашивали/не меняли. Новая пара **Uno 2026102101 / Nucleo 2026102102**, record schema5, 320B, 14 прежних UART-страниц. Новые скрипты prepare_sd_dual_capture.py, sd_dual_capture_selftest.py, finalize_sd_dual_capture.py, install_sd_dual_capture_pair.py, install_sd_dual_capture_usb_pair.py. Последний имеет --verify-package-only и не запущен с разрешающим физический этап флагом. Подготовка только после нового подтверждения J1 OFF, DMM <20V, платы USB (не считать этот запрос таким подтверждением).

Синхронное чтение двух битов GPIOA в одном прежнем DMA-слове; PA6=штатный BKIN, PA4=пассивный вход INPUT/NOPULL от STEVAL TP23. DMA ring8192 uint16=16384B, 5MHz requested/200ns, предыстория2048=409.6us, завершение после обеих линий HIGH321samples=64.2us; лимит после IRQ100ms. 32 совместных RLE-интервала состояния двух битов; переполнение/тайм-аут/DMAoverrun явно выводятся, пропавшие фронты не считаются полным импульсом. Сохраняется первый Break после загрузки; STOP/CLEAR не перезаписывают запись. Сам вход не определяет наличие провода; общий GPIOGND не независимая аналоговая опора. Совпадение LOW в двух точках не доказывает внутренний дефект IPM. Заданный шаг DMA не физически квалифицированный timebase.

Новый HMI декодирует по точному ID2102 только schema5, сохраняет decoder старых schema4 записей (реальная запись25Hz прочитана регрессионным тестом), показывает оба набора LOW/их фронты и число несовпавших отсчётов. Калибровка старой пары принимается для новой без записи точек; VF/ручное управление сохранены. Проверены 1635 checks и 1149 C host scenarios, все65536 GPIO слов,2 отрицательных контроля, guard14cases; Nucleo build0errors/0warnings, Uno LLEXT pass. RAMmarginпослеheap/stack5624B. SHA Uno elf-zsk:796152236fb86b90808e1f47a6b2e4f854d0d78fac15b2f77c37152c15e2c92e; NucleoHEX:aac63b72eeaee627e21aa9ab730dbc3d9943104754f915c3636d4a60acbf2e00. Manifest запечатан source/build/test hashes. Не запускать старый 50Hz-runner: он проверяет старые IDs; новый диагностический прогон ещё не подготовлен/не разрешён этой задачей.

Проводка для пользователя: при выключенных STEVAL J1 и J4=15V и DMM<20V добавить **ОДИН короткий провод STEVAL TP23(SD)→Nucleo PA4/CN7-32** (тот же контакт A2/CN8-3, выбрать один). Штатный SD/BKIN→PA6/CN10-13 оставить; не соединять PA4 с PA6 отдельной перемычкой (это обойдёт диагностируемый маршрут). Общая земля уже есть, новую параллельную земляную перемычку не требовать. **IHM09M2 J1(DAC) должен быть БЕЗ перемычек**, иначе возможно соединение PA4 с соседними debug-выводами; это другой J1, не силовой STEVAL J1. UM3030 §hardware settings говорит J1 off и DAC settings указывает PA4 доступным через morpho/J1; ST STM32CubeG4 example OPAMP_PGA/readme подтверждает PA4=CN7pin32. Схема IHM09M2 net C7_32→R18(0Ω)→PA4-DAC/debug header, к motor connector MC не выведен. PDF загрузка локально ST endpoints timeout, device.report403; не заявлять локальный визуальный просмотр этой схемы. Первичные документы читались через web ST. Для записи прошивки после подготовки USB обеих плат к ПК; двигатель оставлять подключённым. Saleae для этого захвата не нужен. Под HV не возвращать PC/Saleae/обычный осциллограф. Сначала flash+проверка новых IDs/образов/PA4 passive/кал; потом отдельный переход на банки и WiFi по реальному состоянию.

Источники распиновки: https://github.com/STMicroelectronics/STM32CubeG4/blob/master/Projects/NUCLEO-G431RB/Examples/OPAMP/OPAMP_PGA/readme.txt ; https://www.st.com/resource/en/user_manual/um3030-getting-started-with-the-xnucleoihm09m2-motor-control-connector-expansion-board-for-stm32-nucleo-stmicroelectronics.pdf ; https://www.st.com/resource/en/schematic_pack/x-nucleo-ihm09m2_schematic.pdf . Полная физическая причина SD не установлена. Защиты BKF9/BKE1/AOE0, UART DMA, CRC/watchdogs/STOP и MCSDK код не менялись (проверено побайтовым/функциональным сравнением).

## Шунты перепроверены по отдельной схеме/DB2731/MCSDK: штатный номинал0,04Ω, ручнойосмотрнеобязателен, 2026-10-20

Пользовательответилнавопросмаркировки«такпосмотриподаташиту»,физическихмаркировок/отключенияпитанияНЕподтверждал. Не повторятьвопросR040/R080кактребуемоедействие. ПроведёндополнительныйпоискпервичныхSTисточников: DataBriefDB2731Rev4(2019),Figure5/page6—R25/R26/R27**0.04Ω**;отдельнаясхемаSTEVAL-IPM15Bсэтижеточныминоминалами. ОтдельныйBOMизкарточкиSTтожепишет0.04Ω,нотакжесодержитнесогласованныеordercodeR1000иU2STGIF5CH60TS-L;неподаватьегоединственнымдоказательством. Ключевоенезависимоеофициальноеподтверждение—локальноустановленный **STMCSDK6.4.2профильплаты** `C:/Program Files (x86)/STMicroelectronics/MC_SDK_6.4.2/Utilities/PC_Software/STMCWB/assets/hardware/board/power/STEVAL-IPM15B.json`:все4hwvariants `shuntResistor:0.04`;штатныйexampleACIM-NUCLEOG431RB-IPM15B-VF_OL.ioc `MotorControl.M1_RSHUNT=0.04`,`M1_AMPLIFICATION_GAIN=2.1`. Нашисходник2002RSHUNT0.04/gain2.1совпадаетспрофилемST. Вывод:документированныйноминал**40мОм**,конфигурацияпрошивкисоответствуетштатнойплате;фактическоепрочтениетвоейPCBнепроизведено,нонетоснованийставитьручнойосмотршунтовобязательнымследующимшагомилименятьRSHUNTпоUMтаблице0.08. Не выдаватьизвестноерасхождениеUMзаустановленнуюпричинуSD.

Сохранён `artifacts/live_bench_20261020/sd_root_cause_investigation_r1/shunt_document_check.json` сSHAофициальноголокальногопрофиля/4вариантами/flagphysical_board_markings_readfalse. findings.jsonрасширенэтимподтверждениемиответомпользователя;hardwarecommands0. Повторныйручнойзапроснепосылали,ничегонепрошивали/незапускали. ДальнейшийнаправленныйшагостаётсяподготовкадвухточечногозахватаSD TP23+PA6вNucleoдлялокализациитракта,аНЕподборшунта/фильтра. Диагностическаяпрошивкаэтогозахватаещёнеподготовлена. ФизическоесостояниепрежнееподтверждённоеJ1ON/J4ON/банки/PWM0/SDзащёлка;не считатьсловапользователяподтверждениемснятияпитания.

## Разбор источника SD: PWM-синхронность, проверка фактических шунтов, план двухточечного захвата, 2026-10-20

Пользователь попросил искать причину и конкретно указатьследующуюпроверку. Никакихпусков/контроля/flash/reset/переподключенийвэтомисследованиине делали. Офлайн `tools/analyze_sd_switching_phase.py`/`artifacts/live_bench_20261020/sd_root_cause_investigation_r1/findings.json`: изactualARR5312/170МГцноминальныйPWMпериод62,4941мкс; **6из9LOWфронтов** ложатсявсеткуэтогопериодасостатком≤0,6мкс, anchor—последнийLOW. Этоописательнаяпривязка, не статистическоедоказательство, и не исключаетPWM-синхроннуюпомехунаCIN. Ведущаягипотеза—переключательныйвыбросSD/опорнойземли/маршрута. STAN4694§5item5описываетLp7driver-ground→controller-groundкаквводпомехвлогику/аналог,дажееслиDCземляподключена. ПоDS10424Rev10Table11OC24мкс/UV70мкс—типичные,не гарантированныеминимумы. Поэтому0,6мксзаписьнаPA6ещёнеклассифицируетфизическийисточник.

**Новая конкретная неучтённая неопределённость:** UM2014Rev3Figure7/page7наR25/R26/R27указывает0,04Ω, аBOMpage25item28—0,08Ω/WSL2816R0800FEH; обе страницыPDFотрендереныивизуальнопроверены. Вфактическиустановленном2002 `Inc/power_stage_parameters.h`RSHUNT0.04/AMPLIFICATION_GAIN2.1. Реальныйноминалплатынеизвестен;нельзяавтоматомменятьпрофильна0.08попротиворечивойдокументации. МасштабтокаинеобходимаяпроверкааппаратногоOCзависятотреальногошунта;самопосеберасхождениепокаНЕобъяснение0,6мксSD.

Черезasyncзапрошентекущийконкретныйручнойшаг: **выключитьJ1иJ4=15В,дождатьсяDMMDC<20В,прочитатьмаркировкиR25/R26/R27наSTEVAL(R040/0R04либоR080/0R08)**. Двигательоставитьподключённым,USBПКне нужен. **Ответаещёнет.** Добывать0.04/0.08обычнымдвухпроводнымомметромнепредлагать—маркировка/квалифицированныйметод. ДоответасчитатьпоследнееподтверждениеJ1ON/J4ON/банки/ПКиSaleaeсняты/ШИМOFF/защёлкаDP. Не проситьповторночтовмаркировке,еслиответпридёт.

Конкретныйследующийрабочийдиагностическийтест—одновременнодветочкиSDсамойNucleoнаповербанке/Wi-Fi:проектируемыйвторойвходотTP23SD→PA4/CN7-32(такжеA2/CN8-3),первыйPA6/CN10-13оставитьврабочейцепиBKIN. UM2505Rev7таблицыподтверждаютPA4pin;вактивныхSrc/IncPA4неиспользован;IHM09M2официальнаясхемамаркируетегоPA4-DAC,фактическуюзагрузкупереходникомещёсверитьпередподключением. PA5невыбирать(потенциальныйLED/другиефункции),PA11наIHMсвязанBKINчерезR1. Новыйдвухканальныйрегистратор **НЕ РЕАЛИЗОВАН/НЕ СОБРАН/НЕ УСТАНОВЛЕН**. Этонаправлениеплана,невыдаватьстаруюпрошивкузаумеющую2точки. ExistingDMAчитаетполный16битGPIOA_IDRв8192uint16ring;можновыделятьPA4+PA6изодногочтениябезновогопотокаDMA,нужныновыйформат/декодер/hostтесты/проверказагрузки/RAM. BKIN/TIM1фильтр9/защитыоставить. Сначалаподготовитьисобратьиофлайнпроверитьдиагностику,потомпроситьподключения/USB,непрогонятьновыесиловыециклыдоэтого.

Интерпретация: PA6LOW при TP23HIGH—проверятьмаршрут/приёмник/опорнуюземлю/влияниепроводов,перестановкойнаблюденийподтвердить;обаLOW—сигналдоходитдообоихмест,это **НЕдоказательствоintrinsicIPMOC**,общийgroundbounceтожеотражаетсявобоихGPIO;BIFбезнезависимогоLOW—проверятьдругиеBreakисточники/регистратор. ЕслиобщийSDостаётсянепонятным—нужнааналоговаязапись **TP23SD,TP17CIN,TP8VCCотносительнолокальнойTP21/22GND**:DS10424VrefCINmin/typ/max0.460/0.510/0.560В,VCCLUVLOoff9.0/10.3/11.0В. CINпередSDпересекаетпорог—различатьреальныйOC/помехуCINпоизмеренномутоку/RC(R23=1k/C19=1n/R53=4.7k)/шунтам;VCCпроваливаетсякUVLO—питаниенамодуле/развязкаC12=4.7uF,C13=100nF/возврат;обааналоговыевходаспокойны—трактSD/R28=10k/C20=330p/опорнаяземля. Компонентытолькопосхеме,фактическиеноминалыфизическинеподтверждены.

Saleaeунасdigital-only24MS/s:непокажет0.5ВCIN/аналог15В;не подключатьнапрямуюсПКпод320В. Предусмотренaux-onlyконтроль2концовCH6PA6/CN10-13,CH7TP23,GND CN7-19/24MS/s/glitchfilteroff, **толькоприфизическиотключённомJ1/DMM<2Впередщупами/J4offпередмонтажом**;отсутствиеимпульсовтамнеоправдывает25Гцсиловойтракт. `tools/capture_sd_endpoints_aux.py`расширенна2001/2002ссохранением1813/1812;selftestPASSвключаяmixedpairreject,никакогозахватане запускали. Дляаналоговподсиловымнужныпригодныеизолированныевходы/диффпробники;непредлагатьземлянойкрокодилобычногоscope/USBизоляторбезпроверки/плавающийноутбуккакдоказаннуюразвязку. Полныйисточнико-связанныйJSONfindingsвпапкеисследования.

## Реальный прогон BKF9:5/10/15/20Гц выдержаны, аппаратныйBreakна25Гц, полнаяSDволна0,6мкс, 2026-10-20

Пользователь ответил«готово»наточныйединыйшаг:J1OFF/DMM<20В/RESETNucleoодинразприустойчивыхJ4=15В+банках/ждать10с/J1черезsoft-startON;PCUSB/Saleaeсняты. Wi-Fi-only `sd_break_filter_powered_after_stable_reset_r1`PASS:2001/2002SAFE/PWM0/ARM0/320…321В/48°C/43…44мс/всеfault/CRC/transport0;SDHIGH/configOK/BIE1/захватRUNNING/пустыеBreak/D3/wave. Свежаяreadypredicate1,startup_ack0,capturefree1. КJ1невозвращалисьдополнительновэтотэтап,неперепрошивали,неCAL/CLEAR.

Выполнен **единственныйреальныйSTART** `python tools/run_sd_break_filter_to_50.py --confirm-powered-ready --outdir artifacts/live_bench_20261020/sd_break_filter_to_50_r1`. ШтатныйmanualVF/accel5/decel1/операторскийwatchdog3с/host100с. Цели5→10→15→20выдержаны≥2с,прицелевой25ГцсработалMC_DP_FAULT0x0400/TIM1Break;30…50НЕкомандовали,25невыдержаны.44активныхHTTPвыборки;максактивнаяHTTPчастотаполя24,8Гц;cachedcontextза13мсдоIRQполе25,0Гц/RUN6/314В/51°C/маски0. Эточастотаполя,НЕизмереннаяскоростьротора. АктивнаяHTTPшина313…317В,температура48…51°C. НаABORT318В/51°C/masks0x400,транспорт0. START1/CLEAR0/flash0/CAL0,STOPбезповтора;финальноSAFE/PWM0/ARM0иOFFstatusподтверждены. `latest_stopped_status.json`—ещёоднотекущееOFFподтверждениепослеанализа. Питаниепользовательнепереключал: **J1ON/J4ON/банки/PCUSB и Saleaeсняты**,приводостановлен/защёлкаSDсохранена. Не просиливыключатьсиловоебезследующейконкретнойпроверки.

Пользователь уже подтвердил«Да, ровно, ускорение заметно». Записаноoperator_confirmation.json,флагиphysical_rotation_confirmed/speed_changes_confirmedtrue; исходныйавтоматическийreportсохранёнкакreport_before_operator_confirmation.json. Анализобновлёнсэтимфактом;датчиковаяскорость/фазныйтоквсёещёнеквалифицированы.

Полная320Bschema4wave:tick74505совпалсобоимиснимками,номинал5МГц/200нс,19RLEruns/9LOW(8по1сэмплу,ближайшийкIRQ3сэмпла). БлижайшийLOW **номинально0,6мкс**,фронты−1,4…−0,8мкс,полныйHIGHхвостдо+64,2мкс;flags519,DMAerror/overrun/overflow/timeout/censor0. BIF1/B2IF0/BKE1/MOE0/PA6HIGHнаIRQ. **BKF9подтверждёнвсамомсобытииBDTR0x02393c72**,а не толькопрежнимreadback. Rawstart_window1припроверенномRUNявляетсястарымфлагом,неошибкойпервоначальногоSTART. Не путатьэтусубмксrunningwaveспрежним18,46мсboot/J4событиемtick6996—старыйзахваточищентолькоразрешённымручнымRESETиархивсохранён.

CRC/integrity/sequence/framing/transport/drops/shortwrites0вовсёмпрогоне. НоUnoZephyrNOISEadvisory0→18,flags32—неподаватькактотальноеотсутствиеUARTуведомлений;этоНЕCRC/НЕпричиназафиксированногоhardwareBreak. D3непоявился. Шагиостановленыпоаппаратномусигналу,нетнуждысновапереписыватьUART. **BKF9неустранилrunningBreak**;нельзяобъявлятьдостижение50илиполныйремонтSD.

Важнаяинтерпретация:три200нсLOWнеявляютсядоказательствомстрого600нсэлектрическойширины. Приидеальномравномерномсемплереправдоподобныйинтервал≈400…800нс,онпересекаетсясBKF9квалификацией≈659…753нс. РеальныйDMAшагещёнеквалифицирован,пересечениеусловномодельное. СледовательноэтотзахватНЕдоказываетсломанныйTIM1фильтр и НЕразрешаетпростообходитьBreak. ИсточникфизическогоSD(помеха/reference/CIN/UVLO/IPM)покаНЕразличён,51°Cкэшнеизмерениетемпературыкристалла/неполноеисключениетермозащиты. Перенос22→25Гцсампосебене доказываетулучшениеиз-зафильтра,условияпрогоновнеидентичны.

Все данные в `artifacts/live_bench_20261020/sd_break_filter_to_50_r1`: report/samples/status.jsonl/before/afterдиагностика/logs,bkin_wave.bin,decoded_wave.json,analysis.json,analyze_run.py,operator_confirmation.json,run_and_sd.png(отрендеренивизуальнопроверен),latest_stopped_status.json. analyze_runреальнонезависимодекодируетчерезновыйHMI,immutablewaveсовпала,ticksсовпали,истинныйBKF9проверенassert. ПослеаварииникакихCLEAR/RESET/повторSTART/новыхпрошивок. Ответоператоравращенияполучен,повторноне спрашивать. Сейчаснуженрезультатэтогопрогона/дальнейшийосмысленныйпланразличенияфизическогосигнала;неубиратьаппаратнуюзащитуидальшенегонятьповторытого жебезновойпроверки. ОбычныйSaleaeпод320В напрямуюнеподключать. Пользовательавторизовалразгонприготовомстенде,неповторчерезэтуSDаварию.

## Перед первым пуском 2001/2002 уже записан SD LOW18,4618мс; разгон НЕ начат, 2026-10-20

Пользователь явно подтвердил: обе платынаповербанках, ПК/Saleaeотключены,15В/J1включены; попросил разгондо50сзаписью. ПроверилиWi-Fi-onlyпередкомандойSTART. Свежая2001/2002SAFE/PWM0/ARM0,320В/47°C/50мс,UARTCRC/sequence/hw/transport0, SDсейчасHIGH/configOK, ноmc_fault5/reason8/currentMask0/occurredMask1028=0x404(UV4+DP0x400),BIE0/capturefrozen/recordready1. Это НЕразрешённыйизолированныйstartupUV4; readyfalse/startup_ackfalse/capture_freefalse. **START/CLEAR/RESET/ARM/STOP/flashкоманд0**, разгоннереализованиз-заужеимеющегосяhardwareBreak,неиз-заCRC. Не вызыватьboundedrunnerсавтоматическимfinallySTOPрадиэтойдиагностики, не ослаблятьегоDPguard.

Сохранён Wi-Fi-only архив `artifacts/live_bench_20261020/sd_break_filter_powered_baseline_r1`:read_only_reportPASS—успешностьчтения/связи,НЕготовностьпуска. Полнаяschema4волна320B, независимыйdecodeсовпал. tick6996мссовпалсоsnapshot, sampleperiodnominal200нс, RLEHIGH2041/LOW92309/HIGH321; **LOW18 461,8мкс**,падающийфронт−1,4мкс/растущий+18 460,4мксотIRQ, полныйхвост64,2мкс. flags519, timeout/DMAerror/overrun/overflow/censor0. BIF1/B2IF0/PA6LOW/MOE0/BKE1/BKF9/BDTR0x02393872,contextinvalid/startwindow0, first-startслотпуст. ЭтоlongSDсобытиепослевключенияпитания/доSTART;несубмикросекундныйвыбросвпрошломразгонедо22Гц. ТочнуюпричинуUVLO/CIN/externalSDнеопределили;Vbus/температуранасобытииНЕизвестны,текущие319В/47°Cнеподставлятькакегоизмерения. НельзяпооднойдлительностипровозглашатьвнутреннееUVLOилиисточникпитаниявиноватым. НынешнийфильтрштатнопропустилдлительныйLOW,егоаппаратноеназначениесохранено,ноустранениесубмксмоторногосбояещёнепроверено.

Архив:final_status/status.jsonl/logs,break_snapshot/bkin_trace/uart_reject_trace,bkin_wave.bin,decoded_wave.json,analysis.json,analyze_startup.py. `startup_sd.png`отрендерен/визуальнопроверен. АнализподтвердилвсеUARTсчётчики0,включаяUnoNOISE0/flags0;rawdecode/eventticksсовпали. Прошивки/калибровкуне меняли.

Черезasyncотправлен **одинобъединённыйручнойследующийшаг**, чтобыисключитьзапускснезавершённымвключениемJ4: выключитьТОЛЬКОJ1,15Виповербанкиневыключать;призаранееподключённомDMMDC<20ВодинRESETNucleo;подождать10с;сновавключитьJ1черезsoft-start;USBПК/Saleaeнесоединять,Пускненажимать. Ответожидается«RESETприустойчивых15Ввыполнен,J1сновавключён». **Покаответане было**, считатьJ1ON/15ВON/банки/ПК и Saleaeсняты/ШИМOFF/старыйDP. Не проситьповторноразрешатьсаммоторныйтест—онявноавторизован. ПослеответанемедленноWi-Fi-onlyновыйbaseline,ничегонеперепрошивать: еслисвежаяпара/SDHIGH/configOK/BIE1/свободныйзахват/noDP/250…350В и UART0,провестиОДИН `tools/run_sd_break_filter_to_50.py --confirm-powered-ready --outdir artifacts/live_bench_20261020/sd_break_filter_to_50_r1`. ЕслисноваSD/DPещёдоSTART—архивироватьсобытие/сравнитьtick/длительность,неCLEARнеперезапускатьчерезSD и не гонятьфизическиециклыбезновойгипотезы. ЭтотRESETпользовательвыполняетсамнапотушенномJ1,неиспользоватьотсутствующийSWDнабанках.

## Повторная проверка по запросу пользователя: корректная запись подтверждена, 2026-10-20

Пользователь попросил «перепроверь все ли правильно прошито», НЕ подтвердил переход на повербанк/включение J1. Выполнен только read-only аудит `artifacts/live_bench_20261020/sd_break_filter_recheck_r1`: verify-package-onlyPASS; новая пассивная телеметрия точной2001/2002/SAFE/PWM0/ARM0/0В/30°C/CRC0/sequence0/hwflags0/transport0; SDHIGH/configOK/BIE/захватсвободен,обаBreakслотапусты/wave-D3'-'. Единственный MCSDKfault—UV4 при выключенномJ1, не аппаратныйDP. Связь свежая/счётчикgoodрастёт. ADB3880458060наПК.

`tools/recheck_sd_break_filter_pair.py`: **свежее полное чтение NucleoFlash HOTPLUG безreset/записи**,56240байт с0x08000000 побайтносовпали сbuild/nucleo BIN. Второе свежееHOTPLUG чтениеTIM1:BKF9/CKD2/BKE1/AOE0/MOE0/AF10x201. ЧерезpinnedSSHпоUSBсвежиеSHAреальныхHMIserver.py/app.jsсовпали сготовымпакетом;калибровкаa896...ea17неизменна/валидна;manualVFподдерживается. UnoFLASHповторноНЕостанавливали/НЕчитали: перечитан успешныйжурналloader+sketchreadbackпризаписи и сейчасподтвержденаRPCruntimeверсия2026102001сpeer2026102002. Не утверждатьсвежеепобайтночтениеUno;ононеповторялось,чтобыизбежатьreset/разрываRPC. Отдельныйverification.jsonpassedtrueчестноразличаетэтипроверки. START/CLEAR/RESET/flashwrites0, послеSWDсвежаясвязьпродолжилась. Отчётофлайн/sd_break_filter_recheck_r1/verification.json.

Предыдущийasyncшагповербанки+15В+J1ещёнеподтверждён; последнеефизическоесостояниеUSBПК/J1OFF. Не включатьмоторпоэтомузапросуперепроверки, не прошивать/не сбрасывать заново. Пользователюсообщить результатпроверки; моторнаяквалификация2001/2002 и50ГцещёНЕвыполнены.

## Установка 2001/2002 завершена: RPC/UART восстановлены, ожидается переход на повербанки и силовое, 2026-10-20

Пользователь ответил «готово» на холодное переподключение ТОЛЬКОUnoQ USB; J1OFF, NucleoUSB/проводкуне трогать. Самостоятельно дождались ADB (8с), нового LinuxbootID97095fca-383e-4267-93bd-e03f9dffff72, сервисов и свежей RPCтелеметрии. Дополнительных ручных действий/перепрошивки/RESET/CLEAR не понадобилось. Начальная попытка читалки до появления ADB ничего не создала; повтор в `sd_break_filter_install_usb_r1/boot_read_after_cold_start` PASS: точная2001/2002, SAFE/PWM0/ARM0/0В,SDHIGH/configOK/BIE1/захватRUNNING, обаBreakслотаявнопусты/wave'-'/D3'-', UARTCRC/sequence/hardwareflags/transport0. ТолькоожидаемыйUV4приJ1OFF, никакогоDP. Startupжурналrouterсодержалinvalidpacketint8прираннейинициализации, но свежиеRPCзатемвосстановились; не выдаватьэто за моторныйUARTCRC или продолжающийсясбой. Wi-Fi192.168.1.138поднялсясам.

`tools/verify_sd_break_filter_install.py` — отдельное пассивное завершение, безисправленияисторическогоreportpassfalse. ПровереныисходныеreadbackобоихMCU/хешпакета/реальныйBKF9изпрошлогоSWD, 16дополнительныхживыхвыборок≈13с, точнаяпара/всеOFF/0…20В/SDHIGH/configOK/BIE/свободныйcapture/CRC0/transport0/manualVFcapability/поддержкаHMI/валиднаяHVкалибровка/отсутствиеBreak и D3. ЧерезpinnedSSHпоUSB проверены фактическиеSHAустановленныхserver.py/app.js и неизменнаякалибровкаa89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. Отдельный `artifacts/live_bench_20261020/sd_break_filter_install_usb_r1/completion_verification.json` **passed:true**,motor/clear/flash/resetcommands0. Установка завершена. Новыхмоторныхпусковобраза2001/2002 ещёНЕТ; устранениефизическойпричиныSD и50Гц не подтверждены.

Черезasyncужеотправлен **единыйследующийфизическийшаг**, не дробитьегонаповторныедопуски: перевестиобеплатысUSBПКнаповербанк; Saleaeостаётсяотключённым; призакрытомстендевключить15ВиJ1черезsoft-start; двигатель/сигнальнуюпроводкунетрогать;Пуск/RESETненажимать. Запрошенныйответ«обеплатынаповербанке,15ВиJ1включены» **ещёнет**. ДоответасчитатьпоследнееподтверждённоеJ1OFF/обеUSBкПК, контроллерыOFF; не запускать. Послеответа проверитьживойWi-Fi-onlystatus/диагностикуточнойпарыиSD,250…350В/мasks0/нетDP/свободныйзахват; затемОДИНужеавторизованный `python tools/run_sd_break_filter_to_50.py --confirm-powered-ready --outdir artifacts/live_bench_20261020/sd_break_filter_to_50_r1`. Runnerиспользуетпрежниебoundedступени5→10→…→50/hold2s/STOPпоошибке/снятиеARM; толькоразрешённыйизолированныйstartupUV4допускаетодноCLEAR, hardwareDPникогданепринимает. ПриstartupDPилиSDLOWнеповторятьпуск; архивироватьсобытие. Приавариивпрогоне—STOP, сохранитьполнуюSDволнуюsnapshot/CRC/температуру/шину, неCLEARнеперезапускать. Пользовательуженеоднократноавторизовалэтотразгон, не спрашиватьснова разрешение на сам START; физическоеподтверждениепитанияещё требуется.

## Образы 2001/2002 записаны и readback проверен; ожидается холодный запуск Uno для RPC, 2026-10-20

Пользователь ответил «готово» на точную подготовку J1OFF/DMM<20В/обеплатыUSBкПК, двигательподключён;15Вможнооставить. Это актуальная авторизация программирования, не просить повторно подтверждать те же подключения. Первая попытка `sd_break_filter_install_r1` остановилась доизменений0flash: Uno ещёзагружалась (ADBсначалапустой/USBнеопределялась, затем3880458060device/COM10). NucleoCOM13точныйserial. Wi-Fiещёнезагрузился; программно подготовлен `tools/install_sd_break_filter_usb_pair.py`, тотжеустановщик/всеguardсохранены, толькоADBforwardHTTP18080→8080/SSH12222→2222. SSHсохраняетpinnedhostkeyчерезHostKeyAlias `[192.168.1.138]:2222`, никакихобходовпроверкиключа. После загрузки Wi-Fi138восстановился сам, сетевые настройки не менялись.

USBархив `artifacts/live_bench_20261020/sd_break_filter_install_usb_r1`: исходныйживойстатус1813/1812SAFE/PWM0/ARM0/0В/2мс/transport0/UV4,SDHIGH/configOK/BIE1/захватсвободен. HMIпоставлен SHAa85e54e3804a9b5fe36f9db0f2a7a5e40ccf0e068a083e0a79a0b2f74762f243,backup `/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/backups/vbus_reuse_20261020_042842`. **ОБА MCUзаписаны**, Nucleo-vPASS, Unoloader/sketchreadbackPASS, U5resetresumeRUNNING. `report.json`:mcu_flash_commands2/nucleo_readback_verified1/uno_readback_verified1/hmi_installed1/calibration_unchanged1; passfalse **толькоиз-за RPCtimedoutпослеобновления**. Не запускать установщик заново и не перепрошивать повторно. Калибровка до/после SHAa89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

SWD **HOTPLUG read-only** регистраTIM1(104B,безRESET) подтвердилреальныйфильтр: `filter_register_verification.json`, BDTR0x02393872/BKF9/BKE1/AOE0/MOE0/BKBID0;CR10x131/CKD2;AF10x201. Полный `tim1_register_readback.log`. Этоreadbackнастройки, не квалификация электрической задержки. МоторныхSTART/CLEAR/ARM0. HMIпослезагрузкиU5пересталотвечать/api/status (RPCrouterrootPID560, повторныесоединения). Один перезапусксобственногоHMIпроцесса по SIGTERM(провереныowner/cwd/Restartalways)1001→1118непомог, `hmi_rpc_reconnect.json`; MCUнеперезапускалиприэтом. Попытки `systemctl --no-ask-password restart arduino-router.service` и `systemctl --no-ask-password reboot` честноотклонены `Interactive authentication required`. Никакихпаролейнеискали/неспрашивали. Первыйпассивный `boot_read` неуспелполучитьниодногостатуса, passfalse/insufficientfreshstatuses; не считатьегоподтверждениемсвязи.

Черезasyncзапрошен **ОДИН** текущийручнойшаг: вынутьТОЛЬКОUSB UnoQна5секунд/подключитьназад; Nucleo/проводкуне трогать, J1OFF,15Вможнооставить. Причина—холодныйLinuxстартвнутреннегоRPC, анеповторнаяпрошивка. **Ответаещёнет.** Послеответаждатьобычнуюзагрузкусамостоятельно, проверитьADB/порты, вновьADBforwardHTTP18080(можетслететьпослехолодногостарта) и при SSH12222. Затем `python tools/read_sd_break_filter_idle.py --usb-transport --outdir artifacts/live_bench_20261020/sd_break_filter_install_usb_r1/boot_read_after_cold_start` (новыйкаталог). ОнвсегоGET, BASE127.0.0.1:18080,точная2001/2002. Историческийreportpassfalseнепереписыватькакбудтоошибкинебыло; добавитьотдельноеfinishverification.

Из-заобновленияU5/холодногостартаNucleoможетсохранитьожидаемыйcommandwatchdogtransport7: это НЕ CRC и НЕ SD. До любогосброса сначалаархивироватьD1/D2/D3 иубеждаться, чтоэтоизолированныйprogrammingtimeout, faultmasksтолько0/UV4,SDHIGH/configOK,обаBreakслотапусты/wave'-',текущие0…20В/OFF/ARM0/свежесть. Можноиспользовать `finish_sd_live_install.isolated_timeout` с `install` переназначеннымнаinstall_sd_break_filter_pair (нестарую2008пару). Еслиэтиусловияподтверждены—одинSWDresetNucleoврамкахзавершенияустановкиужеавторизован,никакихSTART/CLEAR/flash; затемпассивныйархив. ЕслиSD/DPреальноесть—сохранить, не сбрасыватьчерезаппаратнуюаварию. Старый `finish_sd_live_install.main` требуетinitialreportpass1, поэтому НЕподделыватьreportрадиэтогоскрипта, при необходимостиузкийновыйfinishhelperсчестнойпроверкойreadback/calbыстатуса.

## Кандидат BKIN BKF9 собран, запись ожидает подключения USB, 2026-10-20

Пользователь попросил исправить прошивки. Готов пакет `artifacts/live_bench_20261020/sd_break_filter_fix_r1`, Uno **2026102001**, Nucleo **2026102002**. Предшественник MCU1813/1812 + исправленный HMI из `uart_tx_dma_manual_hmi_fix_r1/server.py` SHA1f9393cb777564609a287deab2aece802ddd8480a5ec8151ef2a8fe26bde66f1. Старые пакеты не изменены. В Nucleo TIM1 BreakFilter3→9 (LL FDIV8_N8), CKD2 оставлен: выборка10,625МГц/N8, номинальная цифровая квалификация659…753нс, без учёта входной синхронизации/аналоговых неопределённостей. Это изменение времени внешнего Break, не доказанное устранение физического источника SD. BKE/полярность/входной режим/запретAOE/внутренняя защитаIPM сохранены; V/f/PWM/deadtime/CRC/watchdogs/STOP не менялись. LiveSDconfig_ok теперь также проверяет BKF9/CKD2/AOE0. IOC также BKF9. Uno сменил только свой/ожидаемый peerID; HMI расширил совместимость ручного VF/диагностик/старой калибровки. Время удержания SD24/70мкс из datasheet типовое, не гарантия минимума; физическая причина короткого LOW остаётся неподтверждённой.

Обе сборки готовы; Nucleo0errors/0warnings, запасRAM5624B, UnoLLEXTpass. Повторный UART/DMA/BKIN selftest124группы/2048кадров/271UART/450BKIN/6negativecontrols PASS. Специфический `filter_selftest/report.json`:1272проверки, настоящий MX_TIM1_Init и live-предикат исполнялись с HALspies и штатными CMSIS/HALопределениями;3negativecontrols (BKF3/BKEoff/AOEon) пойманы.22528модельныхфаз/ширин:≤600нс отклоняются,≥800нс принимаются; это не электрическое измерение. Все исходники вне объявленных изменений сравнены, совместимость старой/новой пары и старой калибровки проверена. Установщик14синтетическихguardслучаев PASS; допускает сохранённыйDP для программирования при реальном J1OFF/USB/низкой шине, никаких CLEAR не шлёт. `manifest.json` фиксирует source/build/verificationSHA; verify-package-only PASS. UnoimageSHA64e889c2ff17090e3f6ad818d05849de908d8caf4ec30634f92b46edc0186964; NucleoHEX56820dd75c1cb61ff788feef53bdf31ea63d1f0b3d17e195cc221c23148e780d.

**НЕ УСТАНОВЛЕНО.** MCU/hardware/control/reset/CLEAR/калибровочные записи0. Текущее физическое состояние не подтверждено заново: последнее было J1/J4ON, платы на повербанках, ПК/Saleae сняты, моторSTOP/DP. Один публичныйGETстатуса20октября вернул timeout; свежей телеметрии нет, не объявлять связь восстановленной. Через async уже запрошен конкретный шаг: выключитьJ1 если включён, дождаться DMM DC<20В, подключитьобеплатыUSBкПК; двигательоставитьподключённым, J4можнооставитьON по прежней авторизации, Saleaeне нужен. **Ответа пока нет.** Не ставить physical-confirm флаг и не делатьSWD/ADB до ответа.

После точного ответа выполнить `python tools/install_sd_break_filter_pair.py --confirm-j1-off-usb-bus-below-20v --outdir artifacts/live_bench_20261020/sd_break_filter_install_r1`. Он архивирует before, проверяет калибровку до/после, ставит HMI и оба MCU с readback; никакихSTART/CLEAR/ARM. Если сервис или USB недоступны, разбирать по фактической ошибке, не угадывать sudoпароль. После установки `tools/read_sd_break_filter_idle.py --outdir ...` для новойпары. Для последующего силового прогона подготовлен `tools/run_sd_break_filter_to_50.py`, использует прежний boundedrunner/ready/STOP и допускает только известный startupUV4, никогда hardwareDP. Не запускать пока без USBизоляции и живой проверки готовности. До50Гц этим образом НЕПРОВЕРЕНО; при новом Break сохранить полную волну и STOPбезповтора. Подробности/команды/источники в README_RU пакета.

## Поиск по STмануалам/форумам: BKF3≈47нс; ведущаяверсия—SDпомеха/опорнаяземля, 2026-10-19

Пользовательпопросилчитатьфорумыимануалы. Поисквыполнен,факты/ссылки/неподтверждённыеверсиив `artifacts/live_bench_20261019/sd_literature_audit_r1/{findings.json,local_register_audit.json}`. Источники:STAN4277Rev9,AN4694,DS10424Rev10,UM2014,ES0431Rev9,официальныйSTM32G4LLheader,4первичныхSTCommunityобсуждения. ОбсужденияF1/F303FOC/другихSLLIMMмодулейотмеченыкакдругиеконфигурации,непереносилиськакисправление. Никакихпостов/сообщенийнафорумыотпользователянеотправляли.

Конкретнаяноваянаходка: событиеBDTR0x02333c72даётBKF3/BKBID0/BKE1. ПоофициальномуG4LL/RM0440BKF3=8выборокнаfTIMkernel;принастроенных170МГцэто47,06нс,аодноточечныйDMAсэмпл200нсНЕдоказываетдлительностьLOW200нс. ИстинныйLOW0,4мксможетштатнопропускатьсятакойфильтрацией;14ранниходноточечныхLOWмоглибытьдругойдлительности/положенияотносительновыборки. Этообъясняетвозможныймеханизмсрабатывания,неустанавливаетисточникспада. НикакихувеличенийBKF/RCилиотключенийBKEнеделали. AN4694§5item5отдельноописываетпаразитнуюиндуктивностьмеждуdriverGND/controllerGNDкакпутьпомехвлогике;наличиеобщейDCземли/экранаэтогонеисключает.

ES0431§2.8.5short-pulsebidirectionalошибканесовпадает:унасBKBID0. DMAMUX§2.4.4требуетвключенияSE/сменыrouteсsyncevent;кодрегистратораинициализируетrequestодинразбезsync,нетсовпаденияусловийсустойчивымRUN. GPIOложныеLOWизerrataкакпричинаненайдены,реальноеслужениевсех5МГцDMAещёнеквалифицировано. СохранённыйidleTIM1AF1=0x201выбираетBKINиинверсию,COMPисточникивыключены;eventAF1неснимался. ВкоденетsoftwareTIM1EGR.BG/GenerateEventBRK. CSSвключён,ноNMIизmapвdefaultinfinite0x08000f0c;послеаварииUARTнормальнопродолжался,такчтопостоянныйCSSNMIненапоминаетэтопрогон,приэтомeventRCCflagsнет. BIFсампосебенесертификатвнешнегоSDисточника(AN4277системныеbreakисточники).

SDтипичны24/70мксSTсравнениеостаётся,этоНЕминимумынеуниверсальныйклассификатор. Ведущаяверсия—коммутационнаяпомеха/сдвигопорнойземливтрактеSD,альтернатива—ошибкааппаратногозахвата/реальныйIPMfault/инойBreak. Реальныйсверхтокисостояние15ВуIPMпокаНЕизмерены. Необъявлятьcausefixedи50Гцготовыми. ПланSaleaeостаётсяпассивнымJ1физснят/J4только15,сравнениеTP23/PA6;необещатьвоспроизведение22Гцнаэтомэтапе.

ПодготовкаоператоромещёНЕподтверждена: последнееподтверждениеJ1/J4ON/повербанки/ПКSaleaeсняты/SAFEсDP. Пользовательисследованиемнеподтвердилразряд/снятиеJ1/подключениещупов. Неисполнятьcaptureсфлагомизоляции/непроситьещёразтемжевопросомбезнужды. Вэтомисследовательскомэтапемоторныхкоманд/RESET/CLEAR/flash/измененийпитания0.

## Подготовлена проверка двух концов SD с имеющимсяSaleae, толькоJ1физическиснят, 2026-10-18

Пользовательпопросилподготовитьпроверкуисказатьконкретнораспиновку. ПрямуюSaleaeзаписьприJ1ONНЕразрешали: общаяUSBземляприборaсПК/неизолированныйHOT_GND. Явноисправленапредыдущаянеполнаяформулировка,обещавшаянезависимуюзаписьбезучётаразвязки. НизковольтныйэтапсSaleaeпровериттракт/захват/включение15В,нонеобещаетвоспроизвестиаварию22Гц. РазгонподHVсSaleaeбезпровереннойизмерительнойизоляциизапрещён. Не предлагатьноутбукбеззарядки/плавающуюземлю/непроверенныйUSBизоляторкакобход.

РеальнаяархивнаяmetadataSession8 найдена НЕнаDesktop (тогофайланет),ав artifacts/live_bench_20261012/local_button/pwm_session_r2/manual_run_1791818470131763700/capture_meta.json: физическийLogic deviceid12092652639477301394,8цифровыхканаловalwaysenabled,max24MS/s. ЭтоНЕLogic8Gen2/100MS/s и аналоговыхканаловпометаданнымнет. Сейчасприборнеподключён,невыдаватьархивзамгновенноенаблюдение. Logic2.4.48запущенбезубийствачужихсессийсautomation10430;appAPIработает,devices[]ожидаемо.

НавыкPDFиспользовандлявизуальнойсверкилокальногоUM2014Rev3: рендерPopplerстр7/таблицастр23 подтверждаютTP23=SD/netIPMpin14,TP17=CIN,TP8=15В,TP21/22GND. ПоэтомущупыCH6=PA6/CN10-13,CH7=STEVALTP23,GND=логическаяNucleoCN7-19. СтараяPWMраспиновкаCH0..5неизменяется/необязательнадлясравненияSD. НикакихщуповнаCIN/15В/DC/U/V/W. Никакойдополнительнойперемычки/подтяжкиSDнет. ДвигательдляПАССИВНОГОбезSTARTтестаоставляетсякакесть;требованиеотключатьегоизстарогоIPM_SD_BKIN_HILотносилоськактивнойHILоснастке/инжекции, здесьинжекции/ШИМнет.

Новый `tools/capture_sd_endpoints_aux.py`:толькоSaleaecapture+WiFiGET,никакихSTART/STOP/CLEAR/RESET/flash/переключенийпитания; exactpair1813/1812/freshOFF/PWM0/ARM0/MCSDK12Vbus<20 доcapture,получениефизическогоприборапоexactid,24MS/s/8каналов/glitchfilters[]/30сек,save.sal/строгийCSVпроверяетобаCH6/7,полныеиобрезанныеLOW/совпадения±2отсчёта. Неотмечаетотсутствиесобытиякакдоказательствоисправности, невыдаётфизическуюпричину. Offline --self-test PASS:совпадение0,4мкс/толькоPA6/left&rightcensor/пустаяволна/нетколонки/запретHV/PWM/ARM/stale. Физическогозахватанебыло. Артефакт `sd_endpoints_aux_preparation_r1/{preparation.json,wiring_plan.json}`;ранние8387mockcasesнеповторялись.

Следующийоператорскийшагподготовлен: выключитьJ1иJ4,помультиметруDC<2В,физическиотсоединитьсиловойвходSTEVALJ1отисточника,затемCH6/CH7/GNDкаквышеиUSBтолькоSaleaeкПК;обеплатынаповербанках,15ВпокаOFF,J1снят,RESET/STARTнежать. Запроситьединое«J1снят,шинаразряжена,щупыподключены». ПодтвержденияэтогоновогосостоянияпокаНЕТ;последнееподтверждённоевсёещёJ1/J4ON/платынаповербанке/ПКиSaleaeсняты/SAFEсDPзащёлкой. Послеответапроверитьприбор/состояниеистартовать30секпассивнуюзаписьскриптомсЧЕСТНЫМфлагом,послеCAPTURESTARTEDпопроситьвключитьТОЛЬКО15В,записатьпереходдвухSDканалов. Не выполнятьстарыеHILflashскриптыдля0801/fixture0899 и не сбрасыватьтекущиеснимкидоархива. Текущиепрошивки1813/1812икалибровканеменяются.

## Проверена версия ложныхLOWизрегистратора; приоритет—трактSD/достоверностьаппаратногозахвата, 2026-10-18

На жалобу пользователя о затянувшемся поиске выполнен конкретный офлайнаудит `tools/audit_sd_short_pulses.py`, результаты `artifacts/live_bench_20261018/sd_short_pulse_audit_r1`. Скомпилирован точныйустановленныйCкод регистратора1812 с mockDMA: PA6постоянноHIGH/соседниебитыGPIOменяются,8192положениякольца—ложныхLOWнет;65побайтныхповторовреальной31RLEволныидентичны;130проверокимпульсов24/70мкснесжимаютсяв0,4мкс; negativecontrolсневернымGPIOбитомпадает. Всего8387hostcases, НЕаппаратныезапуски. ПодменаGPIOсловмодельюнепроверяетреальныенаводки/пропущенныезапросыDMA/целостностьGPIOаналоговогосигнала. ОшибкаCлогикирегистратораненайдена; утверждатьчтоDMAреальноисправенполностьюнельзя. СхемаPA6AF6OD/pullup, BKF3/CKDDIV2, BKBID0/BKE1 изкода/архива; нифильтры,ниBKEнеменялись.

ПроверенофициальныйST DS10424Rev10 §4/Table11 https://www.st.com/resource/en/datasheet/stgib15ch60ts-l.pdf: внутреннееOCдержитSDтипично24мкс,UVLOтипично70мкс,RCдобавляетдлительность. ЭтоТИПИЧНЫЕвремена, не гарантированныйminimum и не универсальныйклассификатораварии. Наши14×1+1×2отсчёта(номинально0,2/0,4мкс)наPA6непохожинаэтоттиповойвнутреннийfault-hold. Приоритетнаярабочаяверсия—помеха/контактвтрактеSDилидостоверностьаппаратногоDMAзахвата. Нельзяобъявлятьнипомехудоказанной,ниток/UVLOисключённымипооднойPA6записи. UM3030J7pin1=PA6/PA11DIAG/BKIN;STEVALсхемаотдельноразводитSDpin14иEM_STOP. ДляразличениянужнонезависиморазличатьуровеньуIPMинаPA6,непростоувеличиватьBKFилимаскироватькороткийLOW. ОбычныйSaleaeподHVнеподключать. Анализисточниковвdatasheet_comparison.json.

Заэтотэтапаппаратныхкоманд/перепрошивок/RESET/CLEAR/перезапусковмотора0. ПоследняяфизикаостаётсяJ1/J4ON/повербанки,моторOFF,DPзащёлкнут,полнаяволнасохранена. Новыхдействийпоотключению/перекоммутациипользователюнепредлагали.

## Оператор подтвердил ровное вращение и ускорение до Break около22Гц, 2026-10-18

Ответ пользователя на вопрос о реальном прогоне `uart_tx_dma_to_50_r2`: «Да, ровно, ускорение заметно». Сохранён `operator_confirmation.json`, report.json/analysis.json отмечены physical_rotation_confirmed=true/speed_changes_confirmed=true/smooth_rotation_reported=true. Независимого измерения скорости ротора нет. Контроллерные ступени5/10/15/20Гц прошли, Breakприразгонек25Гц с кэшчастотойполя22Гц;50ГцНЕдостигнуты. После ответа никаких управляющих/RESET/CLEAR/flash/питательных действий не выполняли, пользователь переключений не сообщал. Состояние по последней проверке: SAFE/PWM0/ARM0, J1/J4ON/повербанки/ПК иSaleaeсняты, DPзащёлкнут иполныйSDархивсохранён. Старое указание ниже «ответ ещёнеполучен» теперь историческое.

## Реальный разгон1813/1812: ступени5/10/15/20 выдержаны, Break около22Гц; полная SD-волна получена, 2026-10-18

Последний ответ «готово» подтвердил включениеТОЛЬКОJ1черезsoft-start приустойчивомJ4=15В/повербанках;PCUSB/Saleaeсняты. Wi-Fi baseline `uart_tx_dma_powered_after_bank_reset_r1` показалSAFE/PWM0/ARM0/fault0/маски0,325В/48°C,SDHIGH/BIE1/захватRUNNING/пустыеBreakиD3,CRC/sequence/transport0. Моторный прогон был уже явно авторизован, дополнительных разрешений не запрашивали.

Первый HTTP-запрос ручного START `uart_tx_dma_to_50_r1` был ОТКЛОНЁН HTTP409 ДО включенияШИМ: manual_scalar_supported отсутствовал для1813/1812, несмотря на корректную MCUcapability1. start_commands1 в отчёте означает запрос, реальныхактивныхвыборок0/максчастота0, выходыOFFподтверждены. Это отдельная ошибка HMI совместимости; MCU/UART/SD не виноваты. В текущем пакетеHMI добавили новуюпару в calibration list, но пропустили отдельную manual predicate; предыдущий selftest этого не проверял.

Исправлена только однафункция HMI черезSSH, БЕЗ выключениясилового/перестановок/MCUflash/reset/CLEAR. Артефакты `uart_tx_dma_manual_hmi_fix_r1`: exactsourceBefore совпал со старым установленным пакетом SHA37a406f828ff75244a2caf76dc0a6cd60e4a6cbf6d8a3ff755bbed6d8a9793a9; новый SHA1f9393cb777564609a287deab2aece802ddd8480a5ec8151ef2a8fe26bde66f1. AST вне manual_scalar_supported побайтноэквивалентен; auth/heartbeat/HV/START/защитныефункции неизменны. Проверены текущаяпара/capability/mismatch. Узкоспециализированный `install_uart_manual_hmi_remote.py` требует exactpair/HV250…350/OFF/PWM0/ARM0/SDHIGH/пустойзахват/noerrors; толькоatomicserverreplace иSIGTERMсобственногоавтоперезапускаемогопроцесса. Не подставлялиложныйmains-off в старыйinstallerguard. RuntimePID552→1060,3проверкиSAFE/PWM0/manualsupported1. Калибровка SHAa89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17 неизменна. Backup `/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/backups/manual_pair_20261018_183153`. MCU1813/1812 остаются прежними.

После устранения ДО-пускового HMIотказа выполнен единственный реальный START `uart_tx_dma_to_50_r2`: штатныйmanualVF/accel5/decel1/3соператорскийwatchdog/100сhostSTOP, задания5→10→15→20→25.5/10/15/20Гц достигнутыивыдержаны≥2с; приразгонек25Гц hardwareBreak/DP0x0400, STOPбезповтора, CLEAR0. АктивнаяHTTPчастотамакс21,2Гц; кэшконтекстза23мсдоBreak содержит22,0Гц/RUNstate6/321В/52°C/маски0. ЭтоЧАСТОТАПОЛЯ, не измереннаяскоростьротора. 25Гцневыдержаны,30…50незадавались. 42активныхвыборки, Vbus320…324В, отображаемаяактивнаятемпература48…51°C. Реакцияаварии/STOPподтвердилаSAFE/PWM0/ARM0, свежийUART. Повторныхпусков/сбросовпослеэтойаппаратнойаварииНЕТ.

После9сдоставкиD1/D2/D3получена и независимо декодирована полная320-байтнаяschema4SDволна:tick194566совпалсобоимиснимками. В предыстории15LOWотрезков:14по1отсчёту и1по2, номинальныйшаг200нс. БлижайшийкIRQLOW −0,8…−0,4мкс,0,4мкс, полныйHIGHхвостдо64,2мкс. flags519, timeout/DMAerror/overrun/runoverflow/censor0,31RLEотрезок. SnapshotBIF1/B2IF0/BKE1/MOE0/PA6HIGHнаIRQ, start_windowraw1приRUNявляетсястарымфлагом, неошибкойпервогоSTART. КороткиеLOWнеравныизмереннойаналоговойдлительности; ближайшийкIRQотрезокнеопределяетоднозначнофизическийисточник. Номинальные5МГцнепрошликвалификациюкаждогозапросаDMA;ток/VCC/CIN/внутренняятемператураIPMнеизмерены. НиOC/UVLO/помеха/внутреннийthermalнеразличены. Программныйтемпературныйfaultнеотмечен, но52°Cкэшнеисключаеттемпературукристалла.

ЗаэтотреальныйпрогонCRC/integrity/sequence/frameerrors/transport/dropped/shortwrite0. ОднакоUnoZephyrNOISEadvisory0→17,flags32: не писать«вообще никакихUARTуведомлений», это неCRC/непричинаSTOPпотекущейдиагностике. НовыеUARTD3rejectнеполучены. Ранний UARTTXtimeout текущимпрогономневоспроизведён,50Гцнепроверены.

Все материалы в `artifacts/live_bench_20261018/uart_tx_dma_to_50_r2`: report/samples/status.jsonl/after_bkin_trace/after_break_snapshot/after_diagnostic_status/logs,bkin_wave.bin,decoded_wave.json,analysis.json,analyze_run.py,run_and_sd.png (отрендерен/визуальнопроверен),latest_stopped_status.json. В tools исправлен будущийгенераторmanualpair, добавлены3регрессионныепроверкиselftest (полныйMCUselftest/rebuildнеперезапускали, образыНЕменялись), hostreadyтеперьтакжетребуетhmi_manual_scalar_supported1/capability1. `generator_check.json`PASSдля1811/1810и1813/1812; первоначальныйпакет/егоSHAархивнепереписаны.

ФизикапокаНЕменялась: J1ON/J4ON/повербанки,моторостановлен,ПК/Saleaeсняты. ЧерезasyncпользователюзаданТОЛЬКОвопросо ровномвращениидоостановки, ответещёнеполучен. Не просили выключатьпитание/сбрасывать/сниматьдвигатель. Доосмысленногоследующегоизмерениясохранитьзащёлку/снимок, неCLEAR/RESET/повторSTARTчерезDP. Следующаяпричинаразбирательства—короткиеактивныеSDсигналы/физическийисточник, атакжеограниченияноминальногозахвата, анеCRC. Достижение50Гцнеобъявлять.

## Один ручной RESET при устойчивых15В: SDHIGH/захватсвободен/UART0, ожидается толькоJ1ON, 2026-10-18

Пользователь ответил «готово» на точный запрос: при независимом DMM DC<20В один RESET Nucleo, J1OFF/J4=15ВON/повербанкиON/USB и Saleae сняты. Считан Wi-Fi-only архив `artifacts/live_bench_20261018/uart_tx_dma_bank_reset_j4_only_r1`. Никаких agent RESET/CLEAR/START/flash/calibrationwrites. Точная установленная1813/1812; SAFE/PWM0/ARM0/ESTOP0; 12В,48°C; mc_fault/bp_fault/reason/currentMask/occurredMask0. SDHIGH/valid/configOK/BIE1/captureRUNNING/recordready0 во всех7начальныхнаблюдениях; CRC/sequence/hardwareUART/dropped/transport0, goodрастёт. Оба first-since-boot/first-start слота явно пусты, wave/D3'-'. Старая62мкс boot-волна сохранена в powered_baseline_r1; физическая причина остаётся неизвестной, RESET при устойчивых15В её не воспроизвёл.

`reset_acceptance.json`PASS8проверок, включая ещёодно живое подтверждение11В/good762 и последние5полностьюсобранныхпассивныхснимков. `reset_acceptance_initial.json`сохранёнкакпервоначальный ложныйFAIL hostpredicate: первые2наблюдениябылидоокончанияпассивнойпередачиD1 иимелиnot_received, анеаварию. Итог требуетявноemptyв5поздних+1свежемчтении иниодногосapturedвовсех; прошивки/допускSTART/защиты не меняли, дополнительногоRESETнебыло.

Уже отправлен следующий единственный физический шаг через async: включить ТОЛЬКОJ1черезштатныйsoft-startпризакрытомстенде;15В/повербанкикакесть;USB/Saleaeсняты;RESET/STARTненажимать;ответ«силовое включено». ЭТОГОответаещёНЕТ, пока считатьJ1OFF. Послеответа Wi-Fi-only baseline точной1813/1812 вновыйoutdir; еслисвежаясвязь/250…350В/SDHIGH/BIE1/захватсвободен/noDP, выполнитьОДИНужеавторизованный `python tools/run_uart_tx_dma_to_50.py --confirm-powered-ready --outdir artifacts/live_bench_20261018/uart_tx_dma_to_50_r1`. СкрипттребуетодноSTART/ступени5…50/HOLD2с/STOPпоошибке, умеетодинCLEARТОЛЬКОизвестнойstartupUV4приполностьювосстановленнойHV;hardwareDPникогданепринимает. Не просить повторно разрешать сам пуск, не прошивать. Пусковнаокончательнойпарепока0.

## J1 выключен пользователем; ожидается один ручной RESET после разряда, 2026-10-18

Получено точное подтверждение «J1 выключен». Повербанки/J4=15В сохраняются, USB/Saleae не подключены. Wi-Fi-only архив `artifacts/live_bench_20261018/uart_tx_dma_j1_off_after_boot_break_r1/read_only_report.json`: обмен/архивPASS, UART CRC/sequence/hw/transport/dropped0, свежие ответы растут, SAFE/PWM0/ARM0, SDHIGH/configOK. Vbus278В во время архива, следующее чтение240В; шина ещё НЕ разряжена. Не считать это состоянием для USB/работы с платой. Полная прежняя волна62мкс/tick4963/flags519 совпадает побайтно и независимо декодирована; новых first-start снимков нет. DP0x0400 всё ещё защёлкнут, BIE0/capturefrozen ожидаемы; CLEAR/RESET/START/flash0.

Через async уже запрошен следующий конкретный ручной шаг: КОГДА заранее подключённый мультиметр покажет DC<20В, один раз RESET на Nucleo; J1 остаётсяOFF, J4=15В и повербанкиON, USB не подключать. Требуемый ответ «ниже20В, RESETнаNucleoнажат» ещё НЕ получен. Не посылать reset через отсутствующий ST-Link и не требовать подключенияПК. После ответа прочитать `tools/read_uart_tx_dma_r2_idle.py` в НОВЫЙ outdir; проверить точную1813/1812, OFF/ARM0, свежий UART, SDHIGH/configOK/BIE1/captureRUNNING/recordready0, обаBreakпусты/wave-D3'-', nofault0 либо только ожидаемуюUV4 приJ1OFF. Гонять50Гц приJ1OFF нельзя; J1 возвращать через soft-start только после реальной проверки свободного захвата при устойчивых15В. Старую62мкс запись не терять и не называть причиной старого20Гцотключения.

## После перехода на повербанки: до START записан SD LOW 62 мкс, разгон не начат, 2026-10-18

Пользователь ответил «готово» на точный шаг: обе платы на повербанках, PC USB и Saleae сняты, J4=15 В on, J1 включён через soft-start, мотор подключён, START/RESET не нажимал. Выполнен только Wi-Fi GET архив `artifacts/live_bench_20261018/uart_tx_dma_powered_baseline_r1`, точная установленная пара1813/1812. UART свежий, ответы растут, CRC/sequence/dropped/hardwareUART/transport0. В preflight SAFE/PWM0/ARM0/ESTOP0, Vbus325 В, текущая телеметрия48°C. Read-only report pass означает исправность чтения/обмена, НЕ готовность пуска.

До агентского START уже защёлкнут MCSDK DP: fault5/reason8/current0/occurred1024=0x0400. Это НЕ разрешённая startup UNDERVOLTAGE4, несмотря на общий reason8. Первый since-boot Break tick4963 мс, BIF1/B2IF0/PA6LOW/BKE1/MOE0, start_window0, context_valid0. Первый start-window слот пуст. Схема4: HIGH2045/LOW310/HIGH321 отсчёт, LOW62,0 мкс, оба фронта −0,6…61,4 мкс, полный хвост64,2 мкс; flags519, DMAerror/overrun/overflow/timeout/censor отсутствуют. Сырой320-байтный архив независимо декодирован, tick совпал со снимком. Время/температура/шина именно на событии недоступны (контекст ещё не заполнен); текущие325В/48°C нельзя приписывать событию. Источник SD по одному импульсу не установлен, связь этого boot-event с прежним20Гц отключением не доказана.

Текущий SD HIGH/configOK, но BIE0/captureRUNNING0/firstRecordReady1: штатный Break-обработчик отключил только IRQ, аппаратный BKE сохранён, запись заморожена до reset. Код clean CLEAR может восстановить BIE, но НЕ освобождает первую волну; запускать с занятой диагностикой через этот DP не стали. `boot_break_analysis.json` подтверждает ready=false/startup_ack_allowed=false/transport_clean=true. START/CLEAR/RESET/flash/calibrationwrites0. Установленную прошивку и критерии допуска не меняли.

Следующий операторский запрос уже отправлен через async: выключить ТОЛЬКО J1 штатным выключателем, оставить15В и повербанки, USB не подключать, RESET пока не нажимать; ответ «J1 выключен». Подтверждения этого нового шага ещё НЕТ. До него считать J1 включённым. План после ответа: считать разряд/состояние при стабильных15В, затем подготовить свободный захват контролируемым reset с сохранённой исходной записью; новую перепрошивку/калибровку не требовать. Не посылать скрытые CLEAR/RESET и не повторять START через аппаратную защиту. До50Гц в этом включении не дошли: моторный прогон вообще не начинали.

## UART TX исправлен и установлен: окончательная1813/1812, минутныйidlePASS; ожидается переходнаповербанк/силовое, 2026-10-18

Пользователь поручил исправить timeoutTX/обрезкуCRC для путидо50Гц, питание/подключения не менял: обеUSBнаПК, J4=15Вon, J1off. Использовано сохраняющееся явное разрешение на запись при DC<20В с включённым вспомогательным15В; свежиеOFF/10В/SDHIGH/age<300 дополнительно проверены. Никаких новых требований отключать двигатель/разряжать/переставлять Saleae не было.

Окончательно установлен `artifacts/live_bench_20261018/uart_tx_dma_fix_r2`, Uno2026101813/Nucleo2026101812. `uart_tx_dma_install_r2/installation_acceptance.json`PASS,9проверок: обе MCU flash/readback verified, HMIатомарнообновлён, калибровкапрежняя SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. UnoZSK SHA cd909cd8f7c779e5f0b7ba77de571f5887ac9ae2932870ee9b62d1c5cd7b8a02, NucHEX SHA e10138270e78a952dc88e7d6568358abc3ece8e06546a255af50d141f82ec644. Пусков/ARM/CLEAR/calibrationwrites0. Подробности в README_RU.md нового пакета.

ОтправкаUSART1 больше не блокирующийHAL_UART_Transmit: DMA1channel1/DMAMUXrequest25/byte→byte normal highpriority, очередь4собственных43байткадров. Следующий кадр только после физического USARTTC и CNDTR0, раннийTCнепродвигает очередь. DMA2ch1SD и ch2/ch3MCSDKUSART2 сохранены. CRC-tail не отбрасывается на5-мс timeout: STOP/защёлка сохраняются, текущий кадр допередаётся. DMAhardwareerror сразуMOEoff/безавтоповтора; CLEARнепринимаетсяприactive/harderrorTX. OFFдляD1/D2/D3 публикуется только послеTC. CRC/frame15ms/watchdog300ms/recoverybudget/sequence/BKIN/температура/шинные/VFуправление неослаблены.

Промежуточнаяr1/1811/1810 действительно устанавливалась и сохранена в uart_tx_dma_fix_r1/uart_tx_dma_install_r1, НЕтекущая и НЕполностьюуспешная. CRC послеDMA0, completed2352/head=tail, но физическийidleпоймалtimeouts1/laststatus3 безDMAerrors. Доказанновоспроизводимаягонка: времябралидоlock, TCIRQмогначатьновыйкадрнаследующеймс; unsignedoldnow-newstart давалпереполнение. r2читаетHALtickПОСЛЕмаскированияписателяstarted_ms, регресс TCbeforelock и negativecontrolclockbeforelock это ловят. Нельзя утверждать точно измеренный межпоточный тайминг прежнегореальногособытия; реальныефлаги/счётчикив r1/tx_watchdog_fault_status.json и tx_watchdog_fault_registers.log. R1неCLEARили/неRESETиличерезошибку; послеархиваперепрошилиисправленнуюr2приJ1off/10В ссохранённойзащёлкой. Программировочныйguardпринялтолькоэтот известныйr1pattern(boottransport7/first13/lastTX11/tx3/masks0/SDHIGH/пустыеBreak/D3полный), это не разрешение моторногоSTART.

Офлайнr2:121группа,2048DMAframes,271UART/D3контракт,450настоящихBKINrecorder/receiverсценариев,6негативныхконтролейPASS. 292520assertмакетаНЕколичествопусков. Сборкиуспешны Nuc0errors/0warnings/UnoLLEXTpass, RAMmargin5624. HALоригиналссмоделированнойпаузойmain воспроизводит39байтpayloadбез4CRC; DMAтотжекадрпередаётцеликомпри18мспаузеmain. ПричинаисходногоповышенияCPUlatencyвфизическомJ4eventнеизмерена, ни физическаяпорчапроводов, ни устранениепрежнего20ГцDPпока недоказаны.

Послеflashr2 сохранён ожидаемыйloaderwatchdog `boot_read`: recovered tick2277/reason2/length1/raw2a/marks00,lastseq201,lastvalid2149; fatal tick2450/reason7/length0/301мс, hardwareflags0,14страницbad0 иrawнезависимосовпал. EmptyBreak/SDHIGH/configOK/captureRUNNING. Через общий `finish_sd_live_install` с installmoduleR2 и ЧЕСТНЫМ `--confirm-j1-off-usb-bus-below-20v` выполнен один завершающийreset-onlyNucleo, безCLEAR/flash. `finish_install_verification.json`PASS, D3кэшавтоматическипуст.

Железнаяпроверкаr2: `idle_60s_r2/report.json`PASS60,172с/+1184goodответа, bad/CRC/sequence/hardwareUART/dropped/transport0, SDHIGH/BIE1/configOK/захватRUNNINGсвободен. ПервыйhostidleFAILтребовалfault0приJ1off; поправленТОЛЬКОкритерийровноожидаемойUNDERVOLTAGE4 с5проверками, исходныйFAILвidle_60sсохранён, MCUнеперезаписывались/неперезапускалисьпоэтому. Текущаязащёлкаmc_fault5/reason8/current0/occurred4 при10В — известнаянизкаяшина, неUARTошибка. `tx_runtime_final/report.json`PASS: DMAMUX25/CPARUSART1TDR/bytebyte/normal/highpriority, completed+144 за7наблюдений, финальныеqueued3704/completed3704, timeouts/full/DMAerrors/harderror/earlyTC0. `sd_registers_final/report.json`PASS3GPIO/TIMчтенияHIGH. `final_idle_read`PASS: SAFE/PWM0/ARM0/ESTOP0, pair1813/1812,Vbus10В/47°C, age51мс, всеUART0, обаBreak/SD/D3пусты. Послеидле ещёповторныйHOTPLUGproof, дополнительныхтестовбезновойпричиныненужно.

Hostrunner `tools/run_uart_tx_dma_to_50.py` ужеадаптирован/готовкточнойпаре1813/1812, план5…50шаг5, HOLD2с/ступень, hostSTOP100с, operator3с, abortпоошибке/защите, nopostfaultretry. 18hostready/negativechecksPASS. ПослеSTOP9сдляполногоD1/D2/D3, `/api/uart-reject` исырые320байтсохраняются. НоваяготовностьтакжетребуетfreshSDHIGH/configOK/BIE1/captureRUNNING/пустойпервыйслот. ОтдельныйstartuphookпередSTART можетОДИНразподтвердитьТОЛЬКОизвестнуюJ1offUNDERVOLTAGE4 послевосстановленияHV/softstart, при0UART/SDHIGH/пустомзахвате;14условийhostPASS, DP/CRC/occupiedcaptureнепринимаются. ПокаэтотCLEARНЕисполнялся. ПредшествующийgenericrunnerбезhookпоумолчаниюостаётсябезCLEAR.

Пользователю уже задан следующийфизическийшаг: обеUSBсПКнаповербанк,15Вможнооставить,послеснятияPCUSBизакрытиястендаJ1черезштатныйsoft-start, Saleaeостаётсяснят, двигательподключён, START/RESETненажимать. Требуется ответ «обе платы на повербанке,15Висиловое включены» — ЭТОТответещёНЕполучен. ПослеответаWi-Fiсчитатьbaseline,проверитьточнуюпару/250…350В/свежуюсвязь/SDHIGH/пустойзахват, затемвыполнитьодинавторизованныйразгон5→10→…→50приусловиинормы. Пользовательпускужеразрешилтекущимпоручением,новую«допускподтвердите»ненавязывать. ТекущаяподтверждённаяфизикадоответаВСЁЕЩЁJ1off/J4on/обеUSBнаПК. Моторныйскриптприэтомневызывать.50ГцнаокончательнойпареНЕдостигались/ещёнепроверены. Новаяперепрошивкаилиперекалибровкадляпереносабанки/HVне нужны.

## J4on: SD-пульс18,1238мс записан полностью; RESET при стабильных15В не вызывает LOW, 2026-10-18

Пользователь подтвердил выполнение точного шага: обе платыUSBнаПК, J4=15 Вon, J1off, RESET/START не нажимал. Считаны SD/Break/Wi-Fi,3независимыхSTLinkHOTPLUGGPIO/TIMнабора. `sd_live_j4_on_r2/read_only_report.json`PASS, raw/HMI immutablewave совпадают, tickсовпадаетсоsnapshot. Событиеtick176396: HIGH2038/LOW90619/HIGH321, обафронта, LOW18123,8мкс=18,1238мс по200нссетке, спад−2,0мкс/подъём18121,8мкс, хвост64,2мкс, flags519, DMAerror/overrun/overflow/timeout/censorfalse. SnapshotBIF1/B2IF0/PA6LOW/BKE1/MOE0/startwindow0/contextvalid1, кэшконтекст50мсстарый: freqref0/state10/MCSDK4/4/Vbus1В/30°C. Точный физический VCC/CIN и фронтJ4 не измерены; связь с включениемJ4 пооператорскомуэтапу, UVLO/OCфизически не различены. ТекущийSDHIGH/configOK подтверждён UART и3GPIOчтениями `sd_live_j4_on_registers_r1/report.json`PASS. В устойчивом состоянии шина9В/48°C. Это не зависшийLOW, а уже завершившийся импульс.

Первая попытка `sd_live_j4_on_r1` имела ложныйFAIL host-сравнения: новая вложенная live_sd.age_ms меняется междуGET(24/22мс). Исправлен ТОЛЬКО хост `read_uart_resync_idle.immutable_wave`: из сравнения сохранённого объекта исключены HTTPвозраст/fresh и весь отдельный текущийlive_sd; сами liveнаблюдения сохраняются.3проверки на реальномархиве: изменениевозрастов/currentlevel не меняетimmutablewave, изменениеpulse_width ловится. Повторr2PASS; новыхпрошивок/калибровки поэтомунебыло. Старыйr1FAILсохранён.

При переходеJ4 зарегистрирована отдельная ошибка UART, её НЕЛЬЗЯ скрывать за passidle: Uno replyCRC/integrity1, Nucleo lastbadreason11TX и lastTXstatus3HAL_TIMEOUT, Nucleo badcnt1 доreset; sequence/hwUART/transportfatal/dropped0, recovered0. Во времяпоследующегоустойчивогочтения новыеошибки0, ответырастут/свежие. `sd_live_j4_on_r2/uart_tx_timeout_analysis.json`: сыройuno_rx_rejected_hex43байт содержит полный39-байтныйpayloadответа, в позицииCRC39…42 стоят `55aa0309` — началоСЛЕДУЮЩЕГОответа. НастоящийCRCдляэтогопейлоада `f6e31d40`. Это вместе с HAL_TIMEOUT подтверждает наблюдаемуюобрезкуотправки/потерюокончаниякадра, а не доказаннуюпорчуодногобитавпроводе. Причинапревышениялимитаотправки5мс ещёнеизмерена/неисправлена; текущий main.c всёещёHAL_UART_Transmit(...UNO_REPLY_TIMEOUT_MS=5) дляконтроляиD1/D2/D3. Это новый конкретный путь разбирательства, не объявлять исправленным до реализации и проверки. D3commandreceiverпуст, таккакэтопередачаответовNucleo→Uno, анефатальныйприёмкомандUno→Nucleo.

Послеархивацииполногоимпульса и8стабильныхOFF/HIGH/currentcountersнаблюдений выполнен ОДИН agent-controlled reset-onlyNucleo при неизменных15В/J1off/USBПК. `probe_sd_reset_j4_only.py` строго требует сохранённуюполнуюволну, exactpair/lowbus/MOEoff/SDHIGH/configOK/transport0 и отсутствиерастущихсчётчиков; никакихSTART/CLEAR/flash. За20секпослеRESET: текущийSDHIGH/BIE1/captureRUNNING/recordready0, обаBreak-слотапусты, wave/D3 '-', fault0/masks0/0, Vbus10В/48°C, UARTсчётчикистабильны. Uno cumulative replyintegrity1/aliasmc_bad1 сохраняются, Nucleo mc_bad_cnt послеreset0. Не писать «вообще не было ошибок».

Первый `sd_live_j4_reset_probe_r1/report.json`FAIL был ошибкойhostpostcondition: требовал наличие UVreason8/masks4/4, а настоящийконтроллерпослеRESETвернул здоровыеfault0/masks0. Предикатreadyрасширен ровно здоровымнулевымслучаем, запретDP/CRC/SDLOW/highbus/PWMсохранён. `reset_outcome_verification.json`PASS проверяет7последнихсохранённыхстатусов+новоеживоечтение, extrareset0; исходныйFAIL не стёрт. `register_verification/report.json`PASS ещё3GPIO/TIMчтения послеRESET сJ4on совпадаютсHIGH/правильнымBKIN. Условиебывшего«LOWпослеRESET» наустойчивомJ4 в этомтесте не воспроизвелось; старое100мсцензурированноесобытиенеотменено, егоисточникнеустановлен.

ФизическийстендСЕЙЧАС: ОБЕплатыUSBнаПК, J4=15Вon, J1off, двигательподключён/остановлен, Saleaeне нужен. Пусковновойпары/50Гцнет. Не предлагатьсиловоеилиповербанкдоразбораконкретнойобрезкиTX. Не проситьзановоразряжать/подключатьПК: USBуженаПК, J1off. НовогообновленияUARTTXещёнет; исходникиновойпары1809/1808 иHMI/калибровканеменялись. SDдиагностикаисправлена, текущийуровеньизмеряетсядостоверно, нофизическийисточникстартовогоимпульсанеобъявлятьнайденным.

## SD1809/1808 установлен; текущийSDHIGH послеRESET подтверждён регистрами приJ4off, 2026-10-18

Пользователь ответилготово на точную подготовку: J1/15 Вoff, DMMниже20 В, обеUSBнаПК. Новая пара Uno2026101809/Nucleo2026101808 записана и проверена; `sd_live_install_r2/report.json`PASS, обеreadbackverified, mcu_flash_commands2, motor/START/ARM/CLEAR/calibrationwrites0. Калибровка прежняя SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. HMI тот же новый из sd_live_diagnostics_r1. `installation_acceptance.json`PASS все7проверок. Источники/хеши в пакете неизменны, `install_sd_live_diagnostics_pair.py --verify-package-only` ранееPASS.

Первая попытка `sd_live_install_r1` завершилась до любых записей Wi-Fitimeout; COM10/COM13 по точным serialID присутствовали, ADB сначала отсутствовал, затем появился. HTTP503RPC при загрузке сам восстановился; ни resetUno, ни userUSB-переподключение не потребовались. Доflash read-only STLink GPIOA IDR0x0000c044/PA6HIGH приJ4off; исходныйSD не виселLOW в этом состоянии. Этот ранний ручной вывод не записан отдельным файлом, но послеflash все независимые регистры сохранены в sd_registers_before_reset и sd_registers_after_reset.

ПриflashUno ожидаемо сработал commandwatchdogNucleo. `boot_read` сохранил D3raw320байт/14страницbad0 и независимое декодирование: recovered tick2331/reason2/length1/raw2a/marks00/lastseq62; fatal tick2479/reason7LINK_TIMEOUT/length0/UARTflags0/lastvalid2178 — ровно301 мс. Это программировочная пауза, не моторная неисправность. Первый MCUdiag8/masks4/4 относится к ранее зафиксированной низкой шине, transport7/lastbad13 относится к последующемуtimeout. Обе Break-ячейки пусты, SDHIGH/configOK/BIE1/captureRUNNING, SDwave '-'.

Новый `finish_sd_live_install.py` допускает ТОЛЬКО такой архивированный isolatedprogrammingtimeout плюс ровно известнуюнизкуюшину masks4/4, требует пустыеBreak/SDHIGH/configOK/captureRUNNING и fatalD3timeout301мс. Негативныепробы (PWM/высокаяшина/DP/CRC/SDLOW/неверныйfatal) отклонены. Выполнен один reset-onlyNucleo, неflash/неCLEAR. `finish_install_verification.json`PASS: transport/bad/CRC/sequence/dropped0, SDHIGH, кэшиSD/D3пусты. Не повторятьresetпоэтомуотчёту.

`sd_registers_after_reset/report.json`PASS:3независимыхGPIO/TIMчтенияHOTPLUGбезhalt/reset/registerwrites совпали с SDHIGH поUART. PA6 mode2/OD1/pull1/AF6/lock1; TIM1 BKE1/BKP1/BKBID0/MOE0/AF1BKINE1/BKINP1. Новый `verify_sd_live_registers.py` толькоread. `recorder_runtime/uart_resync_recorder_runtime_verification.json`PASS: общийпроверяющий импортирован с новойinstallmodule, адреса взяты из map1808, TIM2PSC0/ARR33, DMA5МГцRUNNING/untriggered/recordready0/streamerror0/CNDTRиprogressрастут. Это не квалифицирует каждую200-нс выборку поднагрузкой.

Пользователю запрошен следующий физический шаг (ответ ЕЩЁ НЕполучен): ОБЕплаты оставить USBкПК, включить ТОЛЬКО15 ВJ4, J1оставитьOFF, RESET/START пока ненажимать. Записать SDcurrent и новое включениеJ4, затем решать RESET приJ4on. Не отправлять сейчас на повербанки/силовое: это низковольтный диагностический этап. Текущий подтверждённый стенд до ответа J1/J4off/USBобеПК/двигательподключён/Saleaeне нужен. SDHIGH доказан при J4off, почемураньше приJ4on/RESET былLOW>100мс ещё не установлено. Пусков новойпары/50Гц нет.

## SD после RESET: устранена ошибка HMI, пакет текущего SD1809/1808 готов, MCU ещё не прошиты, 2026-10-18

Пользователь поручил разобраться и исправить SD после RESET, питание/подключения не менял: J4=15 В on/J1off, обе платы на повербанках, ПК/Saleae сняты. Сохранено повторное GET-only чтение `sd_reset_investigation_r1/live_read`: та же ранняя запись tick4865, LOW до конца100 мс, текущий SD НЕ измерен, UART CRC/sequence/transport0, SAFE/PWM0/ARM0, controllerVbus1 В/30 °C. Не приписывать текущему PA6 LOW по замороженной записи. Исходники PA6 AF6/open-drain/pull-up, BKIN input-only/BKBID0; snapshotBDTR0x02333C72/BKE1/MOE0. Конкретная физическая причина SD не установлена; VCC/CIN не измерены.

Доказана ошибка веб-обработчика `loadBkinTrace`: старые ключи pa6_low_intervals/valid_sample_count/age_ms и шаг1 мкс разбирали настоящую schema4 с runs/sample_count/age_since_delivery_ms/0,2 мкс. Исправлено отображение и формулировка long-LOW: историческое окно отдельно от текущего уровня. Пакет `sd_live_diagnostics_r1`: новый Nucleo1808 добавляет read-only GPIO/регистровые флаги в резервные биты reply21 (SD_VALID/HIGH/BIE/CAPTURE_RUNNING/RECORD_READY/CONFIG_OK), прежние tempbits0/1 сохраняются. Новых кадров/трафика во времяRUN нет; Uno1809 отличается от1807 только identity/peer headers. HMI mc_sd_live принимает только peer1808 со свежестью<300 мс, иначе явно unknown; HIGH не снимает защёлкнутую аварию. Защиты/IRQ/GPIO-init/управление/CRC/watchdog/бюджет/калибровка/сохранённые записи неизменны. Документация и границы вывода в README_RU.md пакета, официальные ST ссылки там же.

Офлайн291 проверкаPASS, включая настоящий фрагмент формирования reply с макетами регистров и отсутствие registerwrites, неверную конфигурацию, настоящий RPC parser, реальный long-LOW + currentHIGH и frontend. 450 действительных BKIN recorder/receiver сценариев и271 UART/D3 контрактаPASS. Ошибки самих host-fixture при первом запуске (mc_fw_build вместо настоящего bp_fw_build в текстовомRPC, отдельные temp_valid/fault поля) исправлены только в тесте, актуальный код по ним не менялся. Обе MCU собраны, Nucleo итог0 ошибок/0 предупреждений, UnoLLEXTpass, RAMmargin5944. Новый HEX SHA256c8c8f760b1229d9884ababb1e7af3d3763940badd0e7966f507fb32dce14ba94; Uno zsk SHA2568e9866133363b46bb4a4532d646de441d72f4da533f2a908cd9807f7addfeb18. `install_sd_live_diagnostics_pair.py --verify-package-only`PASS; 10 programmingguardchecks. Non-gating HV preflight не выдаётся за аппаратную квалификацию.

Веб-часть УЖЕ установлена атомарно поWi-Fi, без ожидания USB, при подтверждённом J1off и SAFE/1 В; `sd_live_hmi_deploy_r1/report.json`PASS, calibrationSHAдо/после прежний a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17, MCUflash/reset/START/CLEAR/ARM/calibrationwrites0. Резервнаякопия `/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/backups/vbus_reuse_20261018_171505`, live server SHA bb5742aefc0147f9c9e8e0c36c169728ff31c9fa94d91b9fe535904d548700a4. Действующая MCU-пара ВСЁ ЕЩЁ1807/1806, поэтому liveHMI правильно mc_sd_live.available=false/reasonunsupported_peer. Для новых read-only архивов использовать `read_sd_live_idle.py` (по умолчанию1809/1808; `--existing-uart-pair` для нынешней1807/1806 с обновлённымHMI). Старый `read_uart_resync_idle.py` использует старый локальный декодер, сравнение дополнительных полей/нового текста с живымHMI даст ложныйFAIL.

Асинхронно запрошена ТОЛЬКО физическая подготовка для MCU-записи: выключить15 В, оставитьJ1off, DMMниже20 В, обеUSBнаПК; двигатель оставить, Saleaeне нужен. Ответа на ЭТУ подготовку ещё нет. До явного подтверждения не вызывать `install_sd_live_diagnostics_pair.py --confirm-j1-j4-off-meter-below-20v`. Не путать установкуHMI с записьюMCU и не обещать исправленную физическую причину. После подтверждения записать/проверитьобе MCU, сохранить ранние события, сначала прочитать новый текущийSD и независимо GPIOA/TIM1 черезHOTPLUG приUSB. Не повторятьRESET/CLEAR через необъяснённыйSD. Текущий пользовательский стенд до нового ответа J4on/J1off/повербанки. Пуск/50 Гц не выполнялись.

## Чтение новой пары после перехода на повербанки и RESET: UART исправен, первый SD-слот занят, 2026-10-18

Пользователь подтвердил: обе платы на повербанках, ПК/Saleae отключены, J4=15 В включён, J1 выключен, RESET Nucleo нажат. Выполнены только Wi-Fi GET; START/ARM/CLEAR/RESET/flash/calibration writes=0. Артефакты `uart_resync_j4_after_reset_r1` и `uart_resync_j4_after_reset_r2`, в r2 доставлен полный первый Break-снимок. Пара Uno2026101807/Nucleo2026101806, SAFE/PWM0/ARM0/ESTOP0; ответы свежие (финальный age44 мс), good растёт, CRC/sequence/bad/UART hardware/transport/droppedbytes0. UART D3 not_received, ожидаемо без фатального транспортного отказа. Это проверка связи OFF, не проверка исправления под нагрузкой.

Неожиданно первый SD-слот НЕ свободен после подтверждённого пользователем RESET. Реальное событие tick4865, контекст на IRQ ещё невалиден; BIF1/B2IF0/PA6 LOW/BKE1/MOE0, стартовое окно0. Волна совпадает по tick со снимком: HIGH2044, LOW500004, спад −0,8 мкс, LOW до конца окна100 мс; flags11, timeout/right-censored true, rising_edge/pulse_width null. DMA error/overrun/overflow false. Полная длительность и текущий уровень SD из замороженной записи неизвестны. Независимый декодер совпал. Первый START-слот пуст. Current MCSDK0x0004 низкая шина, occurred0x0404 также сохраняет DP. Финальный Vbus5 В/температура30 °C — текущие показания контроллера, не измерения на IRQ. Перекалибровки не было.

`read_only_report.pass=true` означает исправный свежий read-only транспорт, НЕ готовность к пуску; добавлен `baseline_acceptance.json` с ready_for_powered_run=false. Нового J1/START/повторного RESET не запрашивали; пользовательское состояние J4on/J1off сохраняется. Не отправлять моторные команды и не выдавать занятую/обрезанную запись за свободный захват. Не объявлять физическую причину SD или исправление моторного CRC доказанными. Перед дальнейшим прогоном нужно разобраться с ранним занятием SD-слота, не повторять вслепую уже подтверждённый RESET. Старые host-runner всё ещё требуют адаптации пары и 9-секундного ожидания D3.

## UART-исправление1807/1806 установлено и принято без силового, 2026-10-18

Пользователь явно подтвердил: J1/15 В выключены, DMMниже20 В, обе платынаПК, разрешилпрошитьUART. Установлена пара Uno2026101807/Nucleo2026101806 из`artifacts/live_bench_20261018/uart_resync_fix_r1`. Обе MCU записаныипроверенычтением, HMIобновлёнатомарносрезервнойкопией. Калибровкадо/послеодинакова, точкинепереписывались. `uart_resync_fix_install_r2/report.json` PASS, mcu_flash_commands2, motor/START/ARM/CLEAR0. Этоустановка/проверкаOFF, непрогонподнагрузкой и не доказанноерешениепоследнегоCRC.

Передустановкойперваяпопытка`uart_resync_fix_install_r1` завершиласьдо любыхзаписейпоWi-Fitimeout. ADB/COM10 Uno иCOM13/STLink NucleoподтвержденыточнымисерийнымиID. ЛокальныйHTTPпоказалRPCgetnotavailable. TIM1 BDTR=0x02333C72/MOE0прочитанHOTPLUG. Сделанодинreset/runтолькоUnoчерезпроверенный`unoq_reset_run.cfg`, беззаписиflash, нанизкойшине/J1J4off. MCUпродолжилаработать, RPCвернулся, свежаястараяпара1805/1804 SAFE/PWM0/10 В/age24 мс. ОжидаемыйtimeoutNucleoнеCLEARили, установщикпринялдокументированнуюprogrammingtimeoutзащёлку.

НоваядиагностикаD3проверенанаживомобменепослеflash/verify: 14 страницбезbad,320 байтприняты, локальныйдекодерсовпадаетсHMI. Последнийвосстановленныйкандидатприпрограммировании: tick2518,код2,длина1,raw2a/marks00,previousseq246,lastvalid2370,budget1. Фатальныйснимок tick2671,код7LINK_TIMEOUT,длина0,lastvalid2370,301 мсбезкоммитнутойкоманды. Этоотказотвремениперезапуска/записиUno, нерабочийCRC-сбойподШИМ. Данныев`boot_trace_read/{uart_reject_trace.json,uart_reject.bin,decoded_uart_reject.json,read_only_report.json}`. Русскийтекствисточнике/APIкорректенUTF8; одинпромежуточныйвыводчиталJSONWindowsdefaultcp1251, егоmojibakeнеявлялсяошибкойживогоHMI, коддляэтогонеменяли.

Передобнулениемсохраненыfirsttimeout/сырыедиагностическиеданные. Выполненодинзавершающийreset-onlyNucleoприJ1J4off, безCLEAR/дополнительнойпрошивки. `finish_install_verification.json`PASS. ПослеRESET обаслотаснимковBreakпусты, SDwave '-', UARTreject '-', URWpages0/0. КэшD3Unoочистилсяавтоматическипоpeerreset, безвторогосбросаUno.7последнихсвежихстатусовновойпары: SAFE/PWM0/ARM0/ESTOP0, mc_fault0/MCSDKmasks0/0, transport0, CRC/sequence/UARThardware/droppedbytes0; goodрастёт, последнийage5 мс, шина10 В,48 °C. Это текущиеизмерениянизкойшины, независимогоновогоDMMнепросили/калибровкунеменяли.

РегистраторSDпроверенST-LinkHOTPLUGбезhalt/registerwrites: TIM2CEN/UDE1/PSC0/ARR33, DMAword→halfword, источники/адрескольцаверны, CNDTRменяется, полубуферныйсчётчикрастёт, captureRUNNING/trigger0/ready0/stream_error0, MOE0. `uart_resync_recorder_runtime_verification.json`PASS. Итоговый`installation_acceptance.json`PASS, обеreadback/calibration/D3delivery/очисткакэшей/свежийOFFподтверждены. Перепроверкасырыхошибокподнагрузкойивыходна50 Гцещёнепроводились.

Текущийфизическийстенд: J1/J4выключены, обеплатыподключеныкПК, двигательподключён, моторне запускали. Следующийшагпользователя—обеплатынаповербанк, ПК/Saleaeполностьюснять, включитьтолько15 В, пристабильных15 ВодинразRESETNucleo, J1оставитьOFF. ЭтоосвободитпервыйSD-слотпослевключенияJ4; затемсчитатьновуюпарупередJ1. ЭТОТследующийфизическийшагещёНЕподтверждён. До следующегосиловогопрогонаадаптироватьhostrunnerPAIRк1807/1806ипослеSTOPждать≥7,2 сдляполногоD3цикла(лучше9 с); старый`run_fast_bkin_to_50.py`покаожидает1805/1804. Новойпрошивки/калибровкидлясменырежимовненужно.

## UART-парсер исправлен офлайн; новый пакет1807/1806 готов, ещё НЕ установлен, 2026-10-18

Пользователь поручил разобраться вUART иисправитьпричинуCRC дляпродолжениядо50 Гц. Заэтотэтап командыплатам/START/CLEAR/RESET/flash/calibration writes=0; работатолькоофлайн. Последнеефизическоесостояниенеменялось: J1/J4включены, обеплатынаповербанках, ПК/Saleaeотключены, двигательостановлен, transportCRC2/ESTOP1 сохранены после предыдущегопрогона.

Найден воспроизводимыйдефектучётаошибок: `uv3_resync` послеошибочного43-байтногокадрасохраняетвозможныйзаголовок, напримерхвостAA. Есликандидатпротухаетчерез15 мсбезединогонового байта, старыйкод второйразсписываетбюджетзаодиноти жеужеотброшенныйпакет. Проба `tools/uart_resync_probe.cpp` на настоящемустановленномзаголовке:83 968 сценариевпо256seq/битам2…42; дваповреждённыхкадравокне1 сдают16 ложныхзащёлок. Примерseq122/byte42/bit0. Сисправлением0. Последнийреальныйотказимелlastseq196, сырогоотвергнутогопотоканет: нельзяутверждать, чтофизическаяпричина/последнийостановдоказанноименноэтотдефект.

Подготовлен`artifacts/live_bench_20261018/uart_resync_fix_r1`, Uno2026101807/Nucleo2026101806, основаустановленная1805/1804. Новаяметкадлиныповторногоостаткаубираетлишьспекулятивныйтайм-аутбезновыхбайтов, бездополнительногобюджета/sequence-gap/освеженияwatchdog; перекрытиеAAстарогопр суффиксаиAAновогозаголовкатожеучтено. Лимиты2 повреждения/1000 мс, frame15 мс, watchdog300 мс прежние; третьереальноеповреждениепо-прежнемуSTOP. CRC32C/sequence/replay/cleanCLEAR/аппаратныеUART/BKIN/управлениемоторомнеослаблены.

Добавленприёмныйсыройснимок320 байт: последнийвосстановленныйотказ+перваяфатальнаяошибка, bytes/marks/длина/префикс/причина/sequence/бюджет/времена/принятыйираcсчитанныйCRCтолькодляполных43 байт. ДиагностическийD3/14 страниц, дваCRC, передаётсялишьпослефатальногоотказаподтверждённоOFF, нево времяШИМ. Первыефатальныеданныеimmutableдоpeerreset, кэшUnoтакжеочищаетсяегообщимдетектором. HMI`/api/uart-reject` read-only, статус`mc_uart_reject_hex`, ввидимый`mc_fault_detail`добавляетсяполныйкадр/заголовок, совпалCRC/нетибюджет. Циклпассивнойдиагностикитеперь7,2 с: послеSTOP ждать≥одногоцикладляD3; прежниехостраннеры5-секунднойпаузыбудетнужноадаптироватькновойпареипаузе передновымпуском. SD/DMA5МГцсохранён.

Проверки: обеобразасобраны, Nucleo0 ошибок/предупреждений, UnoLLEXTpass; RAMmargin5944 байта послепрежнегоheap/stackрезерва. `tools/uart_resync_selftest.py`:1453 проверки (включаяфайловыесравнения),83 968 сценариевстарый/новый,271 транспортный/диагностическийконтракт,450 прежнихBKINсценариев,6 отрицательныхконтролейобнаружены. C/PythonвалидаторысырыхзаписейиRPC-текстпроверены. ХостовогорегрессаISR/моторныхфункцийизмененийнеобнаружено, калибровкасовместима. `tools/finalize_uart_resync_package.py` обновилхеши; `tools/install_uart_resync_fix_pair.py --verify-package-only` PASS. Installer13 проверокразрешаетсохранённыйизвестныйCRC-latch толькоOFF/lowbus; невызываетCLEARдляотчёта.

СледующийфизическийшагещёНЕподтверждён: выключитьJ1/J4, посленезависимогопоказанияDMMниже20 В подключитьобеплатыкПК, мотороставитьподключённым. ТолькоПОСЛЕэтогоустановить`tools/install_uart_resync_fix_pair.py --confirm-j1-j4-off-meter-below-20v`. Установленнаяпарапока1805/1804, ане1807/1806. УстранениефизическойпричиныCRC, старого20-ГцBreak иработана50 Гц НЕподтверждены; новыеотвергнутыебайтынужны, еслиотказсохранится. Всеисточники/логи/хеши/описаниев`uart_resync_fix_r1/README_RU.md`.

## Прогон к50 Гц остановлен транспортомUART при разгоне к15 Гц, аппаратногоBreak нет, 2026-10-18

Пользователь явно разрешил один прогон5→10→15→20 и дальше до50 еслиисправно, подтвердил неизменные питание/подключения. Подготовлен host-runner `tools/run_fast_bkin_to_50.py` для точной пары2026101805/2026101804: задания5…50 сшагом5, каждаяступень≥2 сивыборки≥3 нацелевойчастоте, первыйtimeout12 с/остальные10 с, общийhostSTOP100 с, прежнийmanual-mode/operatorwatchdog3 с.32 офлайн-проверки host-условийPASS, защитMCU/HMI/калибровки/прошивок не меняли. ОдинSTART, CLEAR/RESET/flash/calibration writes0. Послеотказа повторовSTART нет.

5 и10 Гц достигнуты ивыдержаны; user подтвердилровноевращениеизаметноеускорение. При следующемзадании15 Гц аппарат/контроллер перешёлвSAFE самостоятельно; последняяактивнаявыборка reference11,7 Гц, зафиксированныйreferenceпослеотключения13,0 Гц. До15 Гцвыдержки не было,20…50 НЕ задавались. `pass=false`, продолжениевверх отменено всоответствиисусловиемпользователя «если всё нормально». Активныхвыборок23, охват11,296 с; Vbus319–322 В,48–50 °C, decel_bus_hold0, brake0. Ранееошибкаслишкомкороткого5-секундноготаймера в этомсценарии неиспользовалась.

ПричинаЭТОЙостановкиустановленаналогическомуровнетранспорта: Nucleo-защёлка `UV3_BAD_CRC=2`, firstreasonCRC1, faultsequence196, capturedmotorstateRUN6, mc_bad_cnt1. Направлениеотказа — приёмкоманд Uno→Nucleo; CRC/sequenceошибкиответовNucleo→Uno остаются0. Вначалеfault_code3, затем1; firstCRC/transport2 постоянны. `UV3_BAD_CRC` в настоящемкодеиспользуется также дляотбракованногозаголовка/нарушениясинхронизации (`uart_v3_transport.h`), поэтому НЕЛЬЗЯ утверждать доказанноеповреждениеполногоCRCкадра/потерюбитов/помехукабеля: сырыевходныебайтыNucleoипричиныкаждогосбросапарсеранесохранены. Кодразрешаетограниченноевосстановление, ноизтелеметриинельзя точно восстановитьвременныеметкивсехпотерь. Неувеличиватьбюджетпотерьи не отключатьCRC/watchdog/BKINдляпродолжения.

ОбаBreak-слотапослецикладоставкидоступныипусты, волнаnot_received/hex '-', MCSDKcurrent/occurred0/0. ЭТОТотказнеявляетсязафиксированнымTIM1Break и не воспроизводитпрежнююаппаратнуюостановку20 Гц. Temp_fault0, UART hardwarefirst/lastflags0, droppedbytes0. AdvisoryUnoNOISE0→1; Nucleo observedNE1→13 (+12), recovereddrops1→4 (+3), онисохраненывотчёте. Общениепослеостановаостаётсясвежим, ноtransport2/CRCзащёлкасохранены; mc_bad_integrity0 означаетцелыеответынаUno, НЕотсутствиеошибоквобоихнаправлениях.

STOP ивыключениеподтверждены; финальныеSAFE/PWM0/ARM0, Vbus323 В,49–50 °C, свежийage18–50 мс. ESTOP1 — автоматическаяреакцияHMIпослетранспортногоотказа, CLEARнеотправляли. J1/J4 включены, обе платынаповербанках, ПК/Saleaeсняты, моторостановлен; подключениясохраняются. Сбрасывать/повторятьпускдоразбораотказаненужно. Следующееисследование — приёмкоманд/синхронизация/CRC вNucleoссырымиотвергнутымибайтамиисостояниемпарсера, диагностикапока не подготовлена/не прошита. Никакойновойфизическойподготовки/перепрошивкиещё непредлагалось.

Артефакты `artifacts/live_bench_20261018/fast_capture_to_50_r1`: report/summary/samples/status.jsonl/logs, before/afterBreak/волна, post_fault_status.json, fault_analysis.json, analyze_transport_fault.py, run_summary.png. ГрафикиsummaryпоказываютотдельносчётчикотбраковкикомандNucleoиCRCответовUno, чтобы нулевойпоследнийне скрывалпричину. Анализофлайн: `tools/analyze_bkin_scalar_run.py --outdir artifacts/live_bench_20261018/fast_capture_to_50_r1 --operator-confirms-smooth-speed-changes`; после негоприменёнлокальныйanalyze_transport_fault.py. Полнаяцель50 Гц НЕдостигнута; короткаявыдержка5/10 Гцсновойпаройподтверждена.

## Короткий пуск после быстрого захвата: ровное вращение, STOP; выдержка5 Гц не подтверждена, 2026-10-18

Пользователь ответил «давай» на предложение одного короткого5-Гц пуска с записью иавтоSTOP. Использован новый host-runner `tools/run_fast_bkin_short_scalar.py`, точная установленная пара2026101805/2026101804. Предварительно25 офлайн-проверок условий host-сценария PASS: невернаяпара/шина/устаревшие данные/температура/CRC/sequence/loss/transport/активнаязащита/занятыйслот блокируютSTART. Сохранена прежняя политика допустимого cumulative advisory UnoNOISE, остальныеошибки не ослаблены. Один bounded START5 Гц, MCU RUNLIMIT7 с, операторскийwatchdog3 с, отдельный host STOP-таймер5 с. CLEAR/RESET/flash/calibration writes0, повторногоSTART после этого прогона не было.

Фактический host-таймер вr1 запущен от ОТПРАВКИ запросаSTART; HTTPподтверждениеSTART заняло3,019 с. В активной фоновой записи только3 выборки reference1,4→3,0→4,5 Гц, охват2,063 с, Vbus319 В,48 °C. ШИМ выключился по автоматическомуSTOP; запись5,0 Гц появилась уже сPWM0, поэтому её НЕЛЬЗЯ выдавать за доказанную выдержку5 Гц подШИМ. `report.json pass=false` сохранён: строгая цель≥2 активных отсчёта5 Гц не достигнута по наблюдению; это неполный host-тест выдержки, не аппаратная авария. Пользователь подтвердил «Да, вращался ровно», physical_rotation_confirmed=true.

START иавтоSTOP завершены, outputsoff подтверждены: SAFE/PWM0/ARM0, mc_fault0/MCSDK masks0/0, transport0, CRC/sequence/bad0, аппаратныеUARTflags0, потерянныхбайтов0, UnoNOISE0. При этом на сторонеNucleo mc_ne_observed0→1 и mc_recovered_drops0→1: восстановленное/advisory событие сохранено, НЕЛЬЗЯ писать «вообще никаких UART-событий». Защёлкнутогоотказасвязи/MCSDK/Break нет. После полногоцикладоставки обаBreak-слота доступныипусты, wave not_received, захватсвободен. Непосредственный ток/скоростьротора не квалифицированы; энкодер не используется вскаляре.

Моя ошибка host-сценария признана пользователю: часть короткогоокна ушла на STARTтранзакцию. Для БУДУЩЕГО отдельного разрешённого прогона исправлен ТОЛЬКО host-runner: таймер5 с и мониторинг теперь начинаются после подтвержденияSTART, аппаратныйMCUпредел7 с иwatchdog3 с остаются. Pythonсинтаксиспроверен; исправленный отсчёт ещё не выполнялсянажелезе. Прошивкине менялись. Автоматическийповтор не делался, пользовательещё не давалновойкомандыSTART послеответа оровномвращении.

Артефакты: `artifacts/live_bench_20261018/fast_capture_short_scalar_5hz_r1/{report.json,summary.json,status.jsonl,before_clear.json,before_bkin_trace.json,before_break_snapshot.json,after_bkin_trace.json,after_break_snapshot.json,logs.txt}`. Физическое состояние: J1/J4включены, обе платынаповербанках, ПК/Saleaeотключены, двигательостановлен. Питание/подключения менятьненужно. До квалификациивыдержки5 Гц/прогоноввыше нельзя заявлять устранениепричины20-ГцBreak либо работуна50 Гц.

## J1 включён после RESET: свежая силовая база без Break, 2026-10-18

Пользователь подтвердил включениеJ1 через штатныйsoft-start при стабильных15 В, Пуск не нажимал. Обе платы на повербанках, ПК/Saleae отключены. Выполнены только read-only Wi-Fi GET; START/ARM/CLEAR/RESET/flash/calibration writes=0. `artifacts/live_bench_20261018/fast_capture_j1_before_start_r1/report.json` и `powered_idle_verification.json` PASS.7 свежих статусов пары2026101805/2026101804: SAFE/PWM0/ARM0/ESTOP0, faults0/MCSDK masks0/0. CRC/sequence/bad/аппаратныеUARTflags/transport/droppedbytes0, good растёт; последний age17 мс. ФинальныеVbus322 В,47 °C; valid Vbus/temp, softstart_ready1, калибровка действительна, служебные выходы0. Диапазоны всех выборок сохранены в отдельной проверке.

После включенияJ1 оба Break-слота по-прежнему доступны и пусты, wave not_received/hex '-', wave pages0/0. Новый стартовыйBreak при этом чтении не записан; первое место свободно для следующего события. Это проверка покоя под напряжением, не подтверждение работы5-МГц записи приШИМ или устранения причины останова20 Гц. Мотор не запускался.

Текущее состояние: J1/J4 включены, платы автономны, выходы выключены, подключения оставить какесть. Следующий испытательный шаг — один короткий скалярный пуск5 Гц с записью и автоматическимSTOP, а не немедленное увеличение до20/50 Гц; для него требуется отдельное актуальное указание пользователя наSTART (последняя просьба была только «считывай»). Перед выполнением адаптировать host-runner к новой точной паре1805/1804, сохранив все прежние защиты и пределы. Повторных RESET/flash/calibration не требуется.

## RESET Nucleo при стабильных15 В: слот пуст, старый кэш Uno очистился, 2026-10-18

Пользователь подтвердил один физический RESET Nucleo при включённых15 В/J1off, обе платы на повербанках, ПК/Saleae сняты; попросил считать. Выполнены только Wi-Fi GET: control/START/ARM/CLEAR/reset/flash/calibration writes=0. `artifacts/live_bench_20261018/fast_capture_after_nucleo_reset_r1/report.json` и `baseline_ready.json` PASS.7 свежих статусов точной пары2026101805/2026101804: SAFE/PWM0/ARM0/ESTOP0, faults0/MCSDK masks0/0, CRC/sequence/bad/droppedbytes/UART hardware flags/transport0, good растёт. Последний age33 мс, текущие Vbus10 В,48 °C; калибровка действительна, служебные выходы0.

Оба Break-слота доступны и пусты (`no_recorded_break`); wave not_received, rawhex '-', accepted/badwave pages0/0. Старый реальный импульс18,1522 мс исчез из живого кэша Uno автоматически после RESET только Nucleo: новое исправление кэша подтверждено на железе, дополнительный сброс Uno/прошивка не потребовались. Сохранённая копия исходной волны в `fast_capture_j4_baseline_r2` остаётся. Пустой слот сам по себе не измеряет текущую пропускную способность DMA, но предыдущий реальный захват новым кодом сохранён.

Текущее физическое состояние: обе платы автономно, J4on/J1off, двигатель остановлен. Следующий шаг пользователя — при закрытом стенде включить J1 через штатный soft-start, не нажимая Пуск, затем прочитать первый новый Break/волну и свежую шину. Подтверждения ЭТОГО включенияJ1 ещё нет, силовых/двигательных команд в этом этапе не выполнялось. Перепрошивка и калибровка не нужны.

## Новый 5-МГц захват реально получил полный LOW18,1522 мс при J4-only, 2026-10-18

Пользователь подтвердил: обе платы на повербанках, всеПК/Saleae сняты, J4=15 В включён, J1 выключен; просил считать. Выполнены исключительно Wi-Fi GET, START/CLEAR/RESET/ARM/flash/calibration writes=0. Пара2026101805/2026101804. Семь свежих статусов на втором чтении: SAFE/PWM0/ARM0/ESTOP0, Vbus9 В и47 °C текущие (не данные в момент события), финальный UART age22 мс, good675 и растёт. CRC/sequence/bad/аппаратныеUARTflags/droppedbytes/transport0; 14 страниц волны, bad_pages0.

Реальная волна schema4/320 байт, event_tick1896 мс, период200 нс: HIGH2045 / LOW90761 / HIGH321. LOW90761 отсчёт=18152,2 мкс=18,1522 мс по номинальной сетке. Относительно публикации триггера спад−0,6 мкс, подъём18151,6 мкс, предыстория409,6 мкс, участок после подъёма64,2 мкс. flags519, оба фронта и хвост сохранены; dma_error/overrun/overflow/timeout/censoring=false, dma_flags_raw0. Сырой бинарник независимо декодирован локальным HMI, все неизменяемые поля совпали с живымHMI. Tick1896 совпадает с первым Break-снимком: BIF1/B2IF0/PA6 LOW/BKE1/MOE0, start_window0, context_valid0. Снимок START пуст. Текущий fault5/reason8/MCSDK_current0x0004 (низкая шина), occurred0x0404 сохраняет такжеDP с начала сеанса. Полного контекста/VCC/CIN/фазного тока в момент события нет,47 °C не выдавать за температуру наIRQ.

Это подтверждает способность нового регистратора сохранить реальный длинный импульс с обоими фронтами на отключённом силовом и работоспособность новой передачи/шкалы времени. Нельзя объявлять конкретную физическую причину (OC/UVLO/помеха/температура), доказанное обслуживание каждого200-нс запроса или связь именно этого стартового события с остановом на20 Гц. Событие возникло безJ1/START/UARTошибки, но его точная привязка к переключениюJ4 независимо не измерялась.

Артефакты: `artifacts/live_bench_20261018/fast_capture_j4_baseline_r2/{report.json,status.jsonl,final_status.json,break_snapshot.json,bkin_trace.json,bkin_wave.bin,decoded_wave.json,logs.txt}`. Чтениеr1 тоже сохранило те же данные, но host-report ошибочно сравнивал возраст доставки между разнымиHTTPGET и вышелFAIL. Исправлена только host-нормализация: возраст/свежесть исключены из сравнения неизменяемой записи, остальные поля и сопоставлениеtick проверены; r2 PASS, никаких вмешательств в платы не было.

Первая запись занята стартовым событием, сохранена полностью. Следующий физический шаг пользователя — ОДИН RESET Nucleo при стабильных15 В/J1off, подключения оставить какесть. После него считать и проверить освобождение первого слота и автоматический сброс старого кэша Uno (новое исправление), затем только готовить включениеJ1. Пока этот RESET пользователем ещё НЕ подтверждён. Платы на повербанках, J4on/J1off, двигатель остановлен. Перепрошивка/перекалибровка не требуется.

## Быстрый регистратор установлен, проверен без силового, 2026-10-18

Пользователь явно подтвердил: J1/15 В выключены, независимый мультиметр ниже20 В, обе платы наПК, разрешил запись. Установлена пара Uno2026101805/Nucleo2026101804 из `artifacts/live_bench_20261018/bkin_fast_capture_r1`. HMI обновлён атомарно с резервной копией; обе MCU записаны, Nucleo readback «Download verified successfully», Uno loader/sketch verification PASSED, reset/run выполнен. Калибровка до/после совпала по SHA-256, точки не записывались. START/ARM/CLEAR=0; двигатель не запускали. Пакет и прежняя авария20 Гц сохранены.

Первая попытка `bkin_fast_capture_install_r1` завершилась до записей по сетевому timeout во время загрузки Uno после USB. ADB/обе платы были доступны; затем Wi-Fi и RPC восстановились сами, без перезапуска MCU/HMI и без участия пользователя. `bkin_fast_capture_install_r2/report.json` PASS, flash_commands2. Неверно экранированный диагностический curl с wildcard черезADB исправлен простым localhost curl; на прошивки/конфигурацию это не влияло.

После прошивки сохранена ожидаемая LINK_TIMEOUT защёлка Nucleo от времени, пока Uno была в loader/verify: fault2/reason13/transport7, свежий OFF-обмен, MCSDK masks0/0, UART flags0, Break-снимки пусты. Исходное состояние сохранено в `pre_finish_reset_status.json`. Для завершения установки выполнен ОДИН reset-only Nucleo при J1/J4 off, без повторной записи и безCLEAR. Тайм-аут ушёл; появилась штатная MCSDK UNDERVOLTAGE: fault5/reason8/masks4/4 при низкой шине. Первый host-проверяющий скрипт ошибочно требовал fault0 и завершилсяFAIL; первоначальный `finish_install_verification.json` оставлен. Исправлен только host-критерий выключенного стенда: разрешена ровно известная низкая шина, транспортные и иные защиты по-прежнему не принимаются.6 офлайн-проверок подтвердили запрет DP/высокой шины/ШИМ/stale/transport. `finish_after_reset_verification.json` PASS получен только чтением, новых RESET/CLEAR/flash не было. При первом свежем отсчёте сразу после reset было83 В, затем8 В; независимого подтверждения83 В нет, эту переходную выборку нельзя считать физическим измерением. Калибровку из-за неё не меняли.

`tools/verify_bkin_fast_runtime.py` использует только ST-Link HOTPLUG -r32 и Wi-Fi GET, безhalt/reset/пусков. Сначала исправлена единица размера чтенияCLI (байты, не слова); это влияло только на неполное чтение, записей не было. Финальный `fast_recorder_runtime_verification.json` PASS после reset: TIM2 CEN1/UDE1/PSC0/ARR33, DMA enabled word→halfword, адресGPIOA IDR и16-КиБ кольца верны, CNDTR меняется, счётчик обработанных полубуферов растёт, TE0/stream_error0. Capture RUNNING, trigger0, record_ready0, TIM1 MOE0. Пять свежих статусов пары подтверждены; good растёт, новые CRC/sequence/droppedbytes/UART errors0, transport0. Остаётся только известная UNDERVOLTAGE при отключённом питании. Новая запись свободна; реальный импульс и5-МГц DMA под нагрузкой двигателя ещё не квалифицированы. По одним регистрам/счётчику нельзя доказать обслуживание каждого200-нс запроса.

Физическое состояние сейчас: J1/J4 выключены, обе платы подключены кПК, двигатель подключён, Пуск не выполнялся. Следующий операторский шаг — обе платы на повербанк, соединения сПК иSaleae снять, подать только15 В при J1 выключенном; прочитать новый SD/Break и обмен до силового. Если первая запись занята включениемJ4, сохранить её и подготовить свежий захват одним reset-only Nucleo при стабильномJ4/J1off; новый Uno должен автоматически очистить старый кэш по обычному peer-reset детектору. Без новой перепрошивки/калибровки. Последующие силовые команды в этом этапе не отправлялись. Артефакты установки: `artifacts/live_bench_20261018/bkin_fast_capture_install_r2`.

## Быстрый захват подготовлен офлайн; НЕ установлен, 2026-10-18

Пользователь ответил «да» на предложение увеличить скорость/предысторию после отказа20 Гц. Подготовлен пакет `artifacts/live_bench_20261018/bkin_fast_capture_r1`, Uno2026101805/Nucleo2026101804; установленная пара остаётся1803/1802. Запрошены5 МГц/200 нс (TIM2 PSC0/ARR33 при170 МГц), предыстория2048 отсчётов=409,6 мкс, постхвост64 мкс, предел100 мс; кольцо8192 uint16=16 КиБ, GPIO word→memory halfword. Схема4/320 байт/14 страниц; HMI переводит время с коэффициентом0,2. Обработка одинаковых уровней группами эквивалентна прежней поотсчётной; публикация Break постоянного времени, защита/IRQ/MCSDK и управление двигателем не менялись. Исправлено сохранение старого кэша волны Uno после распознанного перезапуска Nucleo: общий детектор с существующим кэшем снимка, без новых управляющих команд.

Обе прошивки собраны; финальный Nucleo0 errors/0 warnings, Uno LLEXT pass. На настоящем коде регистратора/приёмника450 host-сценариев, включая256 сравнений групповой обработки, импульсы0,2 мкс…90 мс, короткий LOW за360 мкс до IRQ, ошибки/потери, rollover, receiver reset. Полный `selftest/report.json`1620 проверок, включая неизменность файлов, шкалу HMI и калибровочную совместимость; это не аппаратная квалификация. Карта линковки:6576 байт RAM остаются после глобальных данных и прежнего резерва heap/stack. Офлайн-установщик `python tools/install_bkin_fast_capture_pair.py --verify-package-only` PASS; hashes вREADME/manifest. Калибровка не записывалась. Аппаратный прогон5-МГц DMA/нагрузка/латентность ещё не проверены; TE/overrun флаги не обнаруживают любой возможный пропуск запроса таймера. Причина20-Гц Break НЕ установлена; новая сетка не гарантирует захват субсеточного/вышедшего за окно импульса.

В этом этапе hardware/control/reset/flash commands=0. Последнее физическое состояние не менялось: J1/J4 включены, платы на повербанках, ПК/Saleae сняты, мотор остановлен, первая авария/волна сохранены, ESTOP1. После готовности пакета пользователю предложено выключить J1/J4 и при независимом DMM ниже20 В подключить обе платы кПК, двигатель оставить подключённым. Подтверждения ЭТОГО нового физического шага ещё нет; до него установщик не запускать. Следующий инструмент после подтверждения: `tools/install_bkin_fast_capture_pair.py --confirm-j1-j4-off-meter-below-20v`, он не отправляет START/CLEAR/ARM, сохраняет калибровку и проверяет образы. До нового силового теста проверить реально работающий TIM2/DMA и свежую связь при отключённой силовой части. Полное описание: `artifacts/live_bench_20261018/bkin_fast_capture_r1/README_RU.md`.

## 15→20→15 Гц: реальный Break на этапе20 Гц, прогон НЕ завершён, 2026-10-18

Пользователь разрешил следующий прогон и подтвердил неизменные питание/подключения. До старта чистые SAFE/PWM0/ARM0/fault0/transport0, шина324 В,49 °C, оба Break-слота пусты; накопленные NOISE14. Один START, CLEAR/RESET/flash/calibration writes=0, повторного пуска после аварии НЕ было. В host-runner добавлен только профиль15-20-15;29 офлайн-проверок прошли, пределы защиты MCU/HMI не менялись. Платы остаются на повербанках, ПК/Saleae отключены, J1 и15 В включены.

Задания15 и20 Гц достигнуты и выдержаны по валидной частоте поля более1 с. На переходе к запросу снижения20→15 возник настоящий TIM1 Break, MC_DP_FAULT=0x0400. Последний активный reference20 Гц; возврат15 Гц не выполнен, pass=false. Из последовательности команд/HTTP нельзя установить причинную связь с самой командой замедления. В RUN-телеметрии21 активная выборка с охватом10,25 с, Vbus318–322 В, текущая температура49–51 °C; CRC/sequence/transport/droppedbytes0, decel_bus_hold0, brake0. NOISE14→28 (14 новых advisory) сохранены, это не протокольный UART-отказ. Пользователь подтвердил: «Вращался ровно, затем остановился».

Первый since-boot и первый start-window снимки имеют одинаковый event_tick1646467, BIF1/B2IF0/BKE1/MOE0, PA6 HIGH при входе в IRQ. Кэш контекста за23 мс до IRQ: RUN state6, reference20,0 Гц, Vbus318 В,51 °C, fault masks0/0. Флаг start_window остался1 после RUN; это не ошибка начального START. После события записан именно MC_DP_FAULT0x0400, программная температурная/шинная ошибка в первой маске не зафиксирована. Ток фаз и VCC/CIN непосредственно в момент события не измерены; физическая причина OC/UVLO/помеха пока НЕ установлена.

Новая волна schema3/320 байт получена и независимо декодирована офлайн; tick совпал со снимком. DMA/overrun/overflow/timeout ошибок нет, flags769. Все129 отсчётов в окне−64…+65 мкс относительно публикации триггера HIGH; reason=low_not_observed, pulse_width=null. НЕЛЬЗЯ писать «импульс короче1 мкс»: возможен пропуск между отсчётами либо LOW до короткого предысторического окна при задержанном обработчике; иной источник Break тоже не исключён. Данные не различают эти варианты. По ST DS10424 Rev10 §4/4.1 SD общий для CIN и UVLO VCC, RC влияет на длительность; ширина здесь вообще не измерена. Следующее измерение требует большей предыстории и более быстрого/аппаратного захвата фронтов, сохраняя немедленный Break и явные признаки потерь.

STOP подтвердил выходы выключенными, финальные SAFE/PWM0/ARM0,323 В,50 °C, свежий UART age21 мс. ESTOP1 добавлен автоматической реакцией HMI после аварии, первичный аппаратный DP-снимок сохранён; CLEAR не отправлялась. Питание/подключения оставлены как были; не запускать повторно и не сбрасывать платы до сохранения/анализа. Артефакты: `artifacts/live_bench_20261018/full_pulse_scalar_15_20_15_r1/{report.json,samples.json,status.jsonl,summary.json,logs.txt,after_break_snapshot.json,after_bkin_trace.json,bkin_wave.bin,decoded_wave.json,run_summary.png,analyze_fault.py}`. Испытан короткий выход на20 Гц с последующим срабатыванием; стабильная работа на20 Гц и полный цикл15→20→15 НЕ квалифицированы, выше20 Гц не задавалось.

## Прогон 10→15→10 Гц завершён, ровное вращение подтверждено, 2026-10-18

Пользователь явно разрешил следующий прогон и подтвердил неизменные питание/подключения. Одна попытка, один START; CLEAR/RESET/flash/calibration writes=0. Пара Uno2026101803/Nucleo2026101802, платы автономны, ПК/Saleae отключены, J1/J4 включены. Перед стартом чистые SAFE/PWM0/ARM0/fault0/transport0, Vbus324–325 В,48 °C, накопленные NOISE5, CRC/sequence/lostbytes0, оба Break-слота пусты. Исполнитель `tools/run_bkin_scalar_5_10_5.py --profile 10-15-10`; добавлен только профиль host-сценария,30 офлайн-проверок условий прошли. Прошивки и пределы защиты не менялись.

Штатный manual V/f, сохранённые разгон5 Гц/с и замедление1 Гц/с, общий host STOP25 с и действующий operator/MCU watchdog3 с. Задания10→15→10 достигнуты и каждое выдержано по валидной частоте поля более1 с:10 Гц за2,609 с после подтверждения START,15 Гц за3,609 с после нового задания, обратно10 Гц за7,359 с после снижения. При снижении reference14,8→13,8→12,9→11,9→11,0→10,0 Гц. Активная телеметрия33 выборки с охватом15,703 с; шина318–322 В, текущая температура48–51 °C, decel_bus_hold0, brake0/brake_duty0. Полный цикл завершён штатным STOP, ограничитель25 с не понадобился.

В этом прогоне нет аппаратного Break, аварии MCSDK, transport fault, ошибок CRC/sequence и потерянных байтов. NOISE advisory Uno вырос5→14: девять новых предупреждений сохранены, их нельзя выдавать за отсутствие всех UART-событий. После STOP свежие SAFE/PWM0/ARM0/fault0/transport0,324 В,51 °C. После полного цикла доставки оба снимка доступны и пусты, wave not_received. Захват первой новой волны свободен.

Пользователь ответил: «Да, ровно, оба изменения заметны». Физическое ровное вращение, ускорение до15 Гц и снижение до10 Гц подтверждены оператором; скорость ротора и фазный ток не квалифицированы. Испытан диапазон до15 Гц в коротком прогоне; причина прежнего останова при20–25 Гц не установлена, более высокие задания в этом этапе не отправлялись. Мотор остановлен, J1/J4 оставлены включёнными, подключения не менять. Артефакты: `artifacts/live_bench_20261018/full_pulse_scalar_10_15_10_r1/{report.json,samples.json,status.jsonl,summary.json,logs.txt,after_break_snapshot.json,after_bkin_trace.json,run_summary.png}`.

## Прогон 5→10→5 Гц выполнен с записью, STOP подтверждён, 2026-10-18

Пользователь разрешил прогон и подтвердил неизменное питание/подключения. Стенд остаётся автономным, J1 и15 В включены, ПК/Saleae отключены. Пара2026101803/2026101802. До пуска чистые SAFE/PWM0/ARM0/fault0/transport0, Vbus323–325 В,47 °C; оба Break-слота пусты. Новых CLEAR, сбросов MCU, перепрошивок и изменений калибровки не было.

Первый проход (`full_pulse_scalar_5_10_5_r1`) остановлен собственным скриптом на5 Гц, когда на Uno накопился один UART_ERROR_NOISE=32. Контроллер при этом оставался VF_RUN с валидными5 Гц, fault0/CRC0/sequence0/transport0/lostbytes0 и без Break. Это не аппаратное срабатывание IPM: host-проверка ошибочно требовала нулевого накопленного advisory, тогда как ранее использованный manual-runner допускает NOISE при целых свежих кадрах. Свидетельства r1 сохранены полностью, STOP подтверждён. Исправлена только host-проверка с использованием прежней `supervisory_uart_healthy`; framing/overrun/parity/dropped bytes/CRC/sequence/watchdog по-прежнему прекращают прогон. Пороги защит MCU/HMI не менялись;12 проверок host-условий прошли. Об исправлении и повторе сообщено пользователю перед следующим START.

Второй проход (`full_pulse_scalar_5_10_5_r2`) выполнил все задания5→10→5 Гц в штатном manual V/f с сохранёнными разгоном5 Гц/с и замедлением1 Гц/с, контролем DC-шины, без тормозного резистора/служебных выходов. Один START в этом проходе, общий host-STOP предел25 с и действующий operator/MCU watchdog3 с; deadline25 с не потребовался. Каждый target выдержан по валидной частоте поля Nucleo более1 с:5 Гц за2,969 с после подтверждения START,10 Гц за2,656 с после нового задания, обратно5 Гц за6,516 с после снижения. Down-reference:9,7→8,8→7,8→6,8→5,9→5,0 Гц. Активная телеметрия30 выборок с охватом14,453 с; Vbus319–324 В, текущая температура48–49 °C, decel_bus_hold=0. NOISE advisory Uno вырос1→5, без потерянных байтов/кадров, ошибок CRC/sequence, transport faults и аварий MCSDK. Нельзя писать «ошибок UART вообще не было»: четыре новых advisory сохранены. По завершении STOP подтвердил SAFE/PWM0/ARM0/fault0/transport0,325 В,49 °C. После цикла доставки оба Break-слота пусты, wave not_received.

Артефакты r1/r2 в `artifacts/live_bench_20261018/full_pulse_scalar_5_10_5_r{1,2}`; r2 содержит `report.json,samples.json,status.jsonl,before.json,logs.txt,after_break_snapshot.json,after_bkin_trace.json,summary.json,run_summary.png`. Исполнитель `tools/run_bkin_scalar_5_10_5.py`. Подтверждено достижение полевой частоты5→10→5; пользователь ответил: «Да, всё ровно, оба изменения заметны». Ровное физическое вращение, ускорение до10 Гц и снижение обратно до5 Гц подтверждены оператором. Скорость ротора/ток не квалифицированы. Причина прежнего отключения на20–25 Гц всё ещё не установлена, частоты выше10 Гц в этом этапе не задавались. Питание и подключения оставлены как есть, мотор остановлен, захват свободен.

## Короткий скалярный пуск 5 Гц выполнен; ровное вращение подтверждено, 2026-10-18

Пользователь явно разрешил короткий пуск и запись данных, подтвердив неизменные питание/подключения. Пара Uno2026101803/Nucleo2026101802, платы на повербанках, J1/J4 включены, ПК/Saleae отключены. Архивированы предшествующие статусы, снимки и логи. Одна штатная CLEAR сняла документированные после сбросов LINK_TIMEOUT7/bad1 и низковольтную защёлку4/4. После CLEAR свежие SAFE/PWM0/ARM0, fault0/transport0/bad0; оба Break-слота пусты. Защиты не менялись.

Ровно один START на 5 Гц через штатный endpoint, BOUNDED с MCU RUNLIMIT7 с и host STOP примерно через5 с от отправки запроса. Частота поля по ответам Nucleo: 0,9→2,0→3,6→5,0→5,0 Гц, reference_valid=1. Зарегистрированы пять активных HTTP-выборок с охватом3,485 с; это не точная электрическая длительность ШИМ. Во время активных выборок шина318–320 В, текущая телеметрия температуры47 °C. Новых CRC/sequence/hardware/UART transport ошибок нет. После STOP подтверждены SAFE/PWM0/ARM0, fault0/transport0/bad0, шина323 В. Через полный цикл доставки диагностики оба Break-слота по-прежнему пусты, wave not_received. Повторного пуска не было. Firmware/calibration writes=0.

Пользователь ответил: «Да, вращался ровно». Физическое вращение подтверждено оператором; скорость ротора и фазный ток этим тестом не квалифицированы. Успешен только этот короткий прогон5 Гц; причина прежнего отключения при20–25 Гц пока не установлена,50 Гц не проверены. Артефакты: `artifacts/live_bench_20261018/full_pulse_short_scalar_5hz_r1/{report.json,status.jsonl,before_clear.json,after_clear.json,before_logs.txt,logs.txt,after_bkin_trace.json,after_break_snapshot.json,run_summary.png}`. Исполнитель: `tools/run_bkin_short_scalar.py`,16 офлайн-проверок условий до одного реального пуска.

Питание/подключения оставлены как были; двигатель остановлен, силовое и15 В остаются включёнными. Захват первой новой волны свободен. Следующий отдельный прогон —5→10→5 Гц с тем же захватом; не повторять калибровку/перепрошивку и не требовать переключения питания для чтения. В этом этапе большего задания не отправлялось.

## J1 включён после освобождения захвата: нового Break нет, 2026-10-18

Пользователь подтвердил включение J1 через soft-start, J4=15 В включён, Пуск не нажимал. Только read-only Wi-Fi GET: десять свежих статусов без HTTP-ошибок. Пара 2026101803/2026101802, SAFE/PWM=0/ARM=0, Vbus321→322 В, текущая температура46 °C/temp_fault0, последний mc_age8 мс, good3692→3943 (+251). bad1/transport7/last_bad13 сохраняются после ранее выполненного сброса Uno; CRC/sequence/hardware UART flags=0, счётчики ошибок не растут. В записанной диагностике MCSDK остаются маски4/4 с предшествующего низковольтного этапа; это не доказательство провала напряжения на шине322 В сейчас.

Оба snapshot-слота доступны и сообщают `no_recorded_break`, wave endpoint=`not_received`, wave hex="-", pages0/bad_pages0. Поэтому включение J1 в этом этапе НЕ воспроизвело Break, и новой осциллограммы импульса нет. Ранее сохранённая волна18696 мкс остаётся отдельным свидетельством J4-only/cold-start и не выдаётся за силовое срабатывание. Вывод о причине прежнего отключения при разгоне20–25 Гц пока не сделан.

Артефакты: `artifacts/live_bench_20261018/full_pulse_j1_before_start_d716cbe3/{status.jsonl,final_status.json,bkin_trace.json,break_snapshot.json,report.json}`. START/ARM/CLEAR/RESET/flash не выполнялись. Захват первой новой волны не занят. Силовое и15 В остаются включёнными, платы на повербанках, ПК/Saleae отключены, мотор подключён и остановлен. Следующий отдельный этап — подготовленный ограниченный скалярный пуск с записью статуса и первого реального Break; до пуска сначала обработать документированные защёлки после сбросов штатной командой, сохранив всю диагностику. Не просить переключать питание или переподключать платы для чтения.

## После RESET Nucleo: захват свободен для J1, 2026-10-18

Пользователь нажал RESET/NRST Nucleo при включённых стабильных 15 В и выключенном J1, платы остаются на повербанках без ПК/Saleae. Восьмикратное чтение Wi-Fi подтвердило свежие SAFE/PWM=0/ARM=0, Vbus=10 В и отсутствие нового Break: оба snapshot-слота доступны, `no_recorded_break`, произошедшая маска только MC_UNDER_VOLT=4.

Выявлено рассогласование кэша: после отдельного сброса Nucleo приёмник Uno всё ещё отдавал прежнюю полную волну 18696 мкс/tick2387 (её возраст доставки уже около 219 с). Это НЕ повторное событие. Причина в `bkw_receive`: complete блокирует приём любых следующих страниц до сброса Uno; смена загрузки Nucleo не сбрасывает этот приёмник. Постоянное исправление прошивки пока не устанавливалось.

Для текущего измерения выполнен один удалённый сброс только MCU Uno через key-auth SSH и `remoteocd` с точным скриптом `tools/unoq_reset_run.cfg`. В скрипте только reset/run; flash write/erase отсутствуют. Linux, проводка, питание и Nucleo не перезапускались. После этого восемь свежих Wi-Fi статусов: старый wave hex="-", pages=0, endpoint wave=`not_received`, оба snapshot-слота вновь доступны и пусты. Таким образом старый кэш очищен и не мешает приёму следующего события. Новый UART LINK_TIMEOUT=7/bad=1/last_bad=13 возник при сбросе Uno, сохранён без CLEAR; текущие аппаратные UART-флаги=0, обмен свежий (последний age=27 мс), SAFE/PWM=0/ARM=0. Это не результат силового теста.

Артефакты: `artifacts/live_bench_20261018/full_pulse_after_nucleo_reset_ee9a3be4/{report.json,uno_cache_reset_only.log,post_uno_reset_status.jsonl,post_uno_reset_trace.json,post_uno_reset_snapshot.json,baseline_ready.json}`. START/ARM/CLEAR и записей прошивок не было. Готов следующий операторский шаг: при закрытом стенде включить J1 через штатный soft-start, оставить Пуск ненажатым и считать первый новый Break/волну. Не сбрасывать платы до сохранения новой записи. Пользователь ещё НЕ подтверждал включение J1 после этого RESET.

## Полный импульс реально получен при J4-only: LOW 18,696 мс, 2026-10-18

Пользователь подтвердил обе платы на повербанках, ПК/Saleae отключены, J4=15 В включён, J1 выключен. Выполнены только read-only Wi-Fi GET. Первые пять запросов вернули HTTP503, затем RPC восстановился без вмешательства. Пять свежих статусов пары 2026101803/2026101802: SAFE/PWM=0/ARM=0, Vbus=8 В, текущая температура 46 °C, temp_fault=0, bad/CRC/sequence/UART hardware/transport=0, good21→134. Это текущая телеметрия, не значения в момент события.

Реальный Break записан при HAL tick=2387 мс: BIF=1, B2IF=0, PA6 LOW, BKE=1, MOE=0, start_window=0. Контекст в момент IRQ отсутствует (context_valid=0); напряжения VCC на IPM и CIN не измерялись. Схема3, 320 байт, все 14 страниц приняты без ошибок. Трасса HIGH63 / LOW18696 / HIGH65 отсчётов, период 1 мкс. Оба фронта и участок после восстановления записаны, ошибок DMA, пропусков, переполнения, тайм-аута и обрезки нет; flags=519. Сырой бинарник независимо декодирован локально и совпал с HMI. Снимок окна START пуст, запуск не выполнялся.

Подтверждено: этот сигнал Break возникает без включения J1 и ШИМ; ошибки UART для его возникновения не нужны. Связь с прежним остановом при 20–25 Гц не установлена. Согласно официальному DS10424 Rev10 §4/4.1 (https://www.st.com/resource/en/datasheet/stgib15ch60ts-l.pdf), SD общий для CIN и UVLO VCC, а длительные события и внешняя RC-цепь удлиняют LOW. Поэтому 18,696 мс не определяют источник однозначно. UVLO при запуске питания с восстановлением SD через RC — проверяемая гипотеза, не доказанная неисправность блока питания.

Артефакты: `artifacts/live_bench_20261018/full_pulse_j4_baseline_c4077ee1/{report.json,status.jsonl,final_status.json,bkin_trace.json,break_snapshot.json,bkin_wave.bin,decoded_wave.json,bkin_full_pulse.png}`. Защиту не обходили; CLEAR, START, ARM, RESET и запись прошивок в этом этапе не выполнялись. Первая запись уже занята и не будет перезаписана при J1. Для отдельного следующего захвата нужен один RESET/NRST Nucleo при стабильных включённых 15 В и выключенном J1, затем свежая проверка до J1. Повторной прошивки не требуется. Текущее физическое состояние: J1 выключен, J4 включён, платы автономно, ПК/Saleae отключены, двигатель подключён.

## Полный импульс BKIN: установлен и проверен без силового, 2026-10-18

Пользователь явно подтвердил J1/J4 выключены, мультиметром ниже 20 В, обе платы на ПК и разрешил запись. Установлена пара Uno 2026101803 / Nucleo 2026101802 из `artifacts/live_bench_20261018/bkin_full_pulse_r1`. Оба образа записаны и проверены чтением; Uno loader/sketch verification PASSED. HMI server/app.js обновлены атомарно с резервной копией. Калибровка до/после побайтно совпадает по SHA-256; точки не менялись. START, ARM, CLEAR не отправлялись. Рабочее силовое питание не включали.

Первый запуск установщика остановился до любых записей из-за недоступного Wi-Fi/RPC после подключения USB. Обе платы определялись с правильными серийными номерами; TIM1 MOE=0 проверен через ST-Link. Сброс только Uno без записи восстановил RPC, затем появился Wi-Fi. Защёлкнутый LINK_TIMEOUT от отсутствия команд во время сброса сохранён в `bkin_full_pulse_install_r1/pre_recovery_status.json`; для программирования его не сбрасывали. Установщик разрешает только известный случай этой защёлки при свежих OFF-ответах, низкой шине и выключенных выходах; новые аппаратные UART-ошибки не разрешает.

После установки через ST-Link HOTPLUG, без остановки ядра, подтверждены TIM2 CEN=1/UDE=1/PSC=0/ARR=169, DMA включён, CNDTR меняется, TE=0; счётчик обработки полубуферов вырос 51167232→51348992→51524608. Регистратор RUNNING, trigger=0, record_ready=0, stream_error=0: первая запись ещё не занята и готова принять реальный Break. На шести свежих Wi-Fi ответах SAFE/PWM=0/ARM=0, последняя шина 3 В, mc_age=49 мс, аппаратные UART-флаги=0; число good растёт, новые ошибки не появились. Сохранённые bad=1/transport=7 — программировочный тайм-аут, не новый силовой сбой и не результат работы двигателя.

Артефакты: `artifacts/live_bench_20261018/bkin_full_pulse_install_r2/{report.json,recorder_runtime_verification.json,post_install_status.jsonl}`. Силовой импульс новой прошивкой ещё не снимался; физическая причина прежнего отключения не установлена. Последнее подтверждённое физическое состояние: J1/J4 выключены, обе платы на ПК, двигатель подключён. Следующий этап — обе платы на повербанк, все соединения с ПК/Saleae сняты; только 15 В при выключенном J1, свежий базовый статус до включения силового. Пуск для этого измерения не требуется.

## История: подготовка полного захвата до установки, 2026-10-18

По просьбе пользователя подготовлена диагностическая пара Uno 2026101803 / Nucleo 2026101802 в `artifacts/live_bench_20261018/bkin_full_pulse_r1`. Аппаратное отключение Break и MCSDK остаются прежними. Обработчик Break только публикует триггер; 1-МГц DMA продолжает запись. Обработка полубуферов с приоритетом ниже Break сохраняет уровни без потерь в формате длительностей: 64 отсчёта до триггера, LOW до возврата HIGH и 64 отсчёта после него. Окно после триггера ограничено 100 мс, ёмкость — 32 участка уровня. Отсутствующий фронт, тайм-аут, переполнение и потеря отсчётов отмечаются явно, без выдуманной полной длительности. Первая запись сохраняется до перезапуска и не стирается STOP/CLEAR.

Формат записи schema=3, 320 байт, 14 страниц UART с покадровым и общим CRC32C. Обновлены приёмник Uno и HMI; сохранённая запись не скрывается через 5 секунд, её возраст отделён от свежести текущей связи. В карточке снимка показываются измеренная по сетке длительность либо конкретная неполнота. По одному SD причина OC/UVLO/помехи по-прежнему не объявляется установленной.

Обе прошивки собраны; Nucleo — 0 ошибок, 0 предупреждений. Прогнаны 136 сценариев на настоящем C-коде регистратора и приёмника с имитацией DMA: импульсы 1–90000 мкс, границы кольца, переполнение счётчика, незавершённый LOW, отсутствующий фронт, ошибка/останов DMA, повреждённые страницы и метаданные. Декодер HMI проверен на этих же записях. Сравнение подтвердило неизменность остальных файлов управления двигателем; калибровочные точки не переписывались. Отчёт: `selftest/report.json`. Пакет проверяется полностью офлайн командой `python tools/install_bkin_full_pulse_pair.py --verify-package-only`.

В этом этапе никаких команд устройствам, START/CLEAR, сбросов, записей прошивок или переключений питания не выполнялось. Последнее подтверждённое физическое состояние: обе платы на повербанках, J4 и J1 включены, двигатель остановлен. Следующий шаг пользователя для установки: выключить J1 и J4; при независимом показании мультиметра не выше 20 В подключить обе платы к ПК, двигатель оставить подключённым. Порог 20 В ранее явно разрешён пользователем; установщик дополнительно проверяет свежую низкую шину, отключённые выходы и ARM=0, не требует сбрасывать защёлкнутый ESTOP. Установщик сохраняет диагностику и хеш калибровки, обновляет HMI и обе MCU с проверкой записанного образа; запуска двигателя не делает. Аппаратная проверка нового полного импульса ещё впереди.

## J1 включён без START: получен полный DMA-захват первого Break, 2026-10-18

Пользователь подтвердил включение J1 через soft-start, Пуск не нажимал. В этом этапе команд START/CLEAR, записи прошивок и сбросов не было. По Wi-Fi: SAFE, PWM=0, ARM=0, ESTOP=1 (от ранее отправленной мной команды), Vbus=323 В, IPM=48 °C, свежий UART с bad/CRC/sequence/аппаратными флагами/transport fault=0. Финальный свежий ответ: age=48 мс, good=8020.

До J1 оба снимка сообщали no_recorded_break; после включения J1 первый since-boot снимок содержит BIF=1, BKE=1, PA6 LOW в обработчике, MOE=0, задание=0 Гц, start_window=0. Контекст за 15 мс до IRQ содержал Vbus=10 В и IPM=48 °C. Точное положение события относительно фронта DC-шины не измерено; событие произошло между J4-only baseline и чтением после включения J1, до активации ШИМ.

Исправленный регистратор выдал корректный полный буфер: schema=2, valid_count=1024, DMA CNDTR=981, flags=0x17 (TC/HT, без TE). Отсчёты: 1023 HIGH и последний LOW. Запись обрывается на активном фронте; длительность LOW и возврат HIGH не захвачены. ОДИН LOW-отсчёт НЕ означает импульс 1 мкс. Эта запись не определяет источник SD и не доказывает причину прежнего останова на 20–25 Гц. По ST UM2014 §4.3 SD общий для компаратора перегрузки и UVLO питания драйвера; на длительность влияет RC. Следующее измерение должно включать окончание импульса, при возможности — питание драйвера/сигнал компаратора. Защиту не обходить. Пуск пока не выполнялся; платы остаются на повербанках, силовое включено, физические подключения не менять.

Артефакты: artifacts/live_bench_20261018/j1_on_before_start_d1bcbcc9/{status.jsonl,final_status.json,bkin_wave.bin,decoded_wave.json,report.json,bkin_wave.png}. Сохранённая первая запись декодирована офлайн независимо от ошибочного 5-секундного фильтра давности HMI; исходная телеметрия не изменялась.

## Этап J4 завершён: связь вернулась, BKIN не записан, 2026-10-18

Пользователь уточнил, что J1 всё время был выключен; фраза «всё включил» не означала включения силового. Uno и Nucleo на повербанках, J4=15 В включён. После временного RPC get unavailable и отсутствия ответов Nucleo свежий обмен восстановился без сброса или прошивки; причина переходного сбоя не установлена. Отправлен один ESTOP, HMI подтвердил outputs_off=1. ESTOP остаётся защёлкнутым; START и CLEAR не отправлялись.

Пять последующих ответов: SAFE, PWM=0, ARM=0, Vbus=10 В, mc_age=20–30 мс, UART bad/аппаратные флаги/transport fault=0; счётчик принятых кадров вырос 1109→1220. Пара 2026101711/2026101710. Оба диагностических снимка доступны и сообщают no_recorded_break. Это результат только J4; силовой этап и вращение в этом прогоне ещё не выполнялись. Следующий диагностический этап — включение J1 через штатный soft-start с отключённым ШИМ и чтение первого BKIN до любого START. Отчёт: artifacts/live_bench_20261018/j4_only_after_powerbank_r1/linked_report.json.

## После перевода на повербанки и включения J4, 2026-10-18

Пользователь подтвердил: обе платы на повербанках, J4=15 В включён, J1 выключен. После временного RPC get unavailable Uno снова отвечает по Wi-Fi (build 2026101711), но Nucleo не прислала ни одного принятого ответа: mc_fw_build=0, mc_good_cnt=0, mc_age_ms=999999. За шесть последовательных наблюдений Uno TX увеличился 349→572, RX остался 0. Показание Vbus=0 в этом состоянии НЕ является измерением; текущие температура, состояние выхода Nucleo и BKIN также недоступны. START/CLEAR, сбросы и перепрошивка не выполнялись. Силовой этап не начинать. Задан один визуальный вопрос про индикатор LD3/PWR на Nucleo для проверки её питания после смены USB-источника. Причина отсутствия ответа пока не установлена. Артефакты: artifacts/live_bench_20261018/j4_only_after_powerbank_r1/.

## Связь восстановилась без sudo, 2026-10-18

После первого ответа HTTP 503 RPC снова начал отвечать без команд перезапуска, сброса или прошивки. Три свежих запроса по прямому Wi-Fi подтвердили Uno 2026101711 / Nucleo 2026101710, SAFE, PWM=0, ARM=0, Vbus=0 В; счётчик хороших кадров вырос 984→1003, UART bad=0 и аппаратные UART-флаги=0. Калибровка сохранила исходный SHA-256 a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17. Пароль sudo пользователю неизвестен; требовать его повторно не нужно. Причина перемежающейся недоступности RPC пока не установлена.

Пассивное чтение ST-Link в Hot Plug подтвердило работу установленного диагностического исправления: TIM2 CEN=1, PSC=0, ARR=169, UDE=1; DMA2 Channel1 включён, circular, CNDTR меняется (673→97), флаги TC/HT установлены, TE=0. TIM1 MOE=0. Это подтверждает заполнение буфера PA6, но не источник аппаратного Break и не результат силового прогона. В этом этапе START/CLEAR, запись прошивок и сбросы MCU не выполнялись. Доказательства: artifacts/live_bench_20261018/rpc_recovered_no_password_r1/.

## Последняя проверка и запись диагностической Nucleo, 2026-10-17

Пользователь подтвердил, что J1 выключен, DC-шина разряжена до <=10 В и Nucleo подключена к ПК. Записан только диагностический образ Nucleo из bkin_dma_arr_fix_r1; ST-Link успешно выполнил запись и проверку по чтению. SHA-256 HEX: 392f43aa192b57ae752255bc089d84ce13d33d75a7f5fd21df7750af3071b922. Офлайн-проверки: 10/10. Uno, HMI, калибровка, команды START/CLEAR и управление двигателем не менялись.

После записи панель остаётся офлайн. /api/status отвечает 503; RPC сообщает method get not available. Последний сохранённый статус до потери RPC (19:22:13) был SAFE, PWM=0, Vbus=10 В, IPM=48 °C; это не текущая телеметрия. Попытка перезапуска arduino-router отклонена системой из-за требования sudo-пароля. Не включать J1 и не запускать мотор, пока панель не получает свежий SAFE-статус. Отчёт записи: artifacts/live_bench_20261017/bkin_dma_arr_fix_install_manual_r1/flash_report.json.


## После холодного USB-перезапуска Uno Q, 2026-10-17

Связь восстановилась: `/api/status` отвечает, Uno `2026101711` и Nucleo
`2026101710`; состояние SAFE, PWM=0, задание 0 Гц. UART свежий, счётчики
плохих кадров, CRC/sequence и аппаратных ошибок равны 0. По контроллеру DC-шина
около 1 В; активная и сохранённая причина MCSDK — `MC_UNDER_VOLT` (`0x0004`),
ожидаемо при выключенном J1. Температура IPM около 30 °C. Нового события BKIN
нет (`no_recorded_break`); START и CLEAR не отправлялись. Текущая RPC-связь
восстановлена после холодного запуска Uno Q, силовой запуск этим не подтверждён.

После перевода плат на повербанки Uno Q перезапустилась; HMI сначала закрыл
соединение во время загрузки, затем восстановился. Повторный запрос подтвердил
SAFE, PWM=0, сборки `2026101711/2026101710`, UART 91 хороших и 0 плохих кадров;
нового BKIN нет, J1 остаётся выключенным.

## Проверка только J4 15 В, 2026-10-17

При J4=15 В и выключенном J1/DC-шине (контроллер показывает около 9 В)
состояние оставалось SAFE, PWM=0, IPM=34 °C, UART-счётчики и аппаратные
флаги ошибок — 0. Read-only опрос ST-Link без сброса/остановки ядра: 5000
выборок PA6, все HIGH, переходов 0; ядро осталось RUNNING. Защёлка старого
`MC_DP_FAULT` (`occurred=0x0400`) сохраняется, текущая маска неисправностей
нулевая. Стабильное питание только от J4 не воспроизводит активный BKIN;
короткий переходный импульс при включении источника этим опросом исключить
нельзя. Ничего не сбрасывали и не запускали. Лог: `artifacts/live_bench_20261017/bkin_dma_powerup_trip_r1/stlink_pa6_j4_only.log`.

Подготовлена и записана диагностическая пара 2026101711/2026101710 из
`artifacts/live_bench_20261017/bkin_dma_boot_armed_r1`. Nucleo вооружает прежний
1-МГц DMA-захват PA6 после синхронизации MCSDK; обычный STOP его не выключает,
аппаратный Break замораживает трассу. При проверке найдено и исправлено, что
STOP раньше выключал захват до события. V/f, разгон/замедление, ШИМ, UART-формат
и калибровка не менялись. Uno Q прошит и readback-проверен; Nucleo прошит и
readback-проверен повторно с исправлением STOP. Nucleo собирается с 0 ошибками/
предупреждениями, офлайн-проверки 11/11. Калибровка не менялась, CLEAR/START не
отправлялись. После проверки readback Uno Q не отвечает по RPC; прямой reset/run
MCU не восстановил обмен, HMI service и USB доступны. Nucleo сейчас работает,
захват `RUNNING` (RAM state=1), но удалённый статус пары не проверяется. Для
восстановления приложения Uno нужен холодный USB-перезапуск только Uno Q при
выключенном J1 и низкой шине. Релизный допуск для силового пуска закрыт: нет HIL
и аппаратной валидации BKIN.

## Новый BKIN при включении силовой шины, 2026-10-17

После включения J4 и силовой шины, до команды START, Nucleo зафиксировала
первое после загрузки событие TIM1 Break. В свежем снимке `BIF=1`, `BKE=1`,
`MOE=0`, PA6 был LOW при входе в обработчик; контроллер сообщил
`MC_DP_FAULT` (`occurred=0x0400`, `current=0`). Последняя телеметрия:
Vbus 321–323 В, IPM 48 °C, PWM=0, SAFE; UART bad/CRC/sequence и аппаратные
UART-флаги равны нулю. Команд CLEAR/START после события не отправляли.

Это подтверждает активное срабатывание тракта BKIN до запуска двигателя и
исключает потерю UART и перегрев радиатора как причину именно этого события.
Снимок не различает перегрузку IPM, UVLO его 15-В питания или неисправность/
уровень линии SD; PA6 прочитан LOW, но длительность события не измерена.
Кольцевой DMA-захват PA6 вооружается только при принятом START, поэтому для
этого события высокочастотной трассы нет. Не сбрасывать защиту и не запускать
двигатель при этом состоянии. Выключить силовое питание и J4, дождаться
разряда DC-шины; перед следующим допуском проверить стабильность 15-В питания
и уровень SD/BKIN при выключенной силовой шине.

После подключения USB обе платы обнаружены на ПК (Uno Q: COM10/ADB, Nucleo:
ST-Link/COM13); телеметрия показала Vbus 10 В, SAFE, PWM=0. Read-only опрос
GPIOA через ST-Link без сброса/остановки ядра: 5000 выборок, PA6 LOW=0,
переходов PA6=0; ядро осталось в RUNNING. Следовательно, линия BKIN сейчас
не зажата низким уровнем при выключенных J1/J4. Это не определяет причину
предыдущего события; следующий этап — отдельно проверить J4 15 В при
оставленном выключенным J1, без запуска двигателя.

Доказательство и полный разбор: `artifacts/live_bench_20261017/bkin_dma_powerup_trip_r1/RESULT_RU.md`.

## Состояние после установки BKIN DMA-диагностики, 2026-10-17 20:47 МСК

Установлена диагностическая пара Uno Q `2026101703` / Nucleo `2026101702`;
обе записи подтверждены чтением, контрольная сумма калибровки DC-шины совпала.
Алгоритм V/f, ШИМ и протокол управления не менялись. Установщик исправлен:
сначала обновляет Nucleo, затем Uno Q, а переходный запускной `LINK_TIMEOUT`
проверяет отдельно. Проверки: 6/6 сценариев установщика, 17/17 проверок
записи BKIN, сухой и итоговый live-проверочный прогоны прошли.

После перезапуска Uno Q появился ровно один запускной `LINK_TIMEOUT`; свежий
обмен продолжался. Счётчики bad были 1/1 из-за этого события, а integrity,
sequence и аппаратные UART-флаги оставались 0; хорошие кадры шли непрерывно.
При SAFE, PWM=0, снятом разрешении пуска, нулевых масках
MCSDK и свежей телеметрии отправлена одна безопасная команда `CLEAR`. Она
сняла защёлку; транспортные ошибки и bad-счётчики теперь 0/0, хорошие кадры
продолжают расти. Команд START/частоты не было.

Текущее состояние при выключенных J1/J4: SAFE, PWM=0, свежесть телеметрии
14–15 мс, DC-шина по контроллеру 10 В, IPM 48 °C, UART transport=0, bad=0.
Ожидается защита по пониженному Vbus `5` (`MCSDK reason=8`, occurred mask
`0x0004`) при обесточенной силовой части; она не является текущей UART-ошибкой.
Калибровка не менялась: `two-point Vbus verification passed`.
Снимков BKIN после новой прошивки ещё нет (`no_recorded_break`), поэтому
причина прежнего срабатывания около 22,7 Гц пока не установлена. Не повышать
частоту выше этой границы, пока не получим достоверный снимок при следующем
контролируемом прогоне. Полный протокол: `artifacts/live_bench_20261017/bkin_dma_pair_final_verification_r1/RESULT_RU.md`.

## Текущее состояние после обновления диагностики, 2026-10-17

Панель Uno Q и фронтенд обновлены для проверки фактического счётчика DMA;
HMI-деплой подтвердил неизменность калибровки Vbus. При MCU-обновлении Uno Q
2026101703 прошла запись и проверку чтением, затем зафиксировала один
`LINK_TIMEOUT` со старой Nucleo 2026101506. Nucleo 2026101702 тоже прошита и
проверена чтением, но после этого прямые RPC-запросы и `/api/status` перестали
возвращать ответ. Пусков, сбросов защиты и команд двигателю не отправляли.

Обе MCU возвращены на прежнюю пару Uno 2026101507 / Nucleo 2026101506; чтение
обоих образов подтвердило запись. Последняя достоверная телеметрия до потери
RPC была SAFE, PWM=0, Vbus=10 В, EStop=0, UART-флаги=0, температура IPM 49 °C.
После восстановления пары новых данных нет, поэтому эти значения нельзя
считать текущими. Калибровочные точки не переписывались.

Служба `arduino-router` доступна, но не получает ответ от MCU. Перезапуск
системной службы отклонён, потому что SSH требует sudo-пароль; ADB reboot
получил «Interactive authentication required». Нужен холодный перезапуск только
Uno Q: при выключенных J1 и J4 отключить её питание USB на 5 секунд и подключить
снова; Nucleo оставить подключённой к ПК. До появления свежего SAFE-статуса и
нулевого ШИМ силовое питание не включать.

Диагностический кандидат `artifacts/live_bench_20261017/bkin_dma_verified_pair_r1`
собран (17/17 host-проверок) и остаётся вне MCU после возврата пары. Он не
прошёл аппаратную квалификацию и не разрешает запуск. Старый trace нельзя
считать достоверным: раньше Nucleo объявляла 1024 отсчёта полными по времени,
не сверяя фактический DMA CNDTR и флаги. Даже корректный цифровой BKIN trace
сам по себе не различает перегрузку IPM, просадку его питания и помеху.

## Последний силовой прогон, 17 октября 2026 МСК

V/f-пуск дошёл до сохранённого задания 22,7 Гц; при следующем повышении в сторону 25 Гц Nucleo остановила ШИМ по `MC_DP_FAULT` (`0x0400`). UART чистый, температурный флаг выключен; D1-снимок фиксирует `BIF=1`, PA6 HIGH в обработчике, шину 318 В и радиатор 60 °C. Восстановленная 1-МГц запись содержит 1024 LOW-отсчёта до границы события, поэтому длительность/источник активного BKIN пока не установлен. HMI ошибочно прячет сохранённую запись после 5 с (`stale`), а флаг окна запуска не очищается при переходе в RUN. Фазный ток невалиден. Защиту не сбрасывали, повторный пуск не выполняли; до выяснения входа BKIN тест до 50 Гц не продолжать. Подробности: `artifacts/live_bench_20261017/manual_scalar_5hz_to_25_ipm_trip_run1/RESULT_RU.md` и `bkin_trace_readback.json`.

## Упрощённая панель V/f, 2026-10-17 МСК

На Uno Q установлен HMI-only бандл `artifacts/live_bench_20261017/manual_scalar_hmi_simplified_r1` поверх фактически отдававшейся диагностической версии. В рабочем виде оставлены Пуск, Стоп, аварийный стоп и ползунок 0–50 Гц; настройки разгона/снижения свёрнуты. Поле ключа скрыто, пока сохранённый токен действителен; поле и отдельная кнопка ARM скрыты в обычном режиме. Пуск использует прежние серверную авторизацию и кратковременный HV preflight. Диагностика ошибки и BKIN-снимок сохранены.

Изменён и проверен только `app.js` (SHA-256 `ea3c7d6be352ff4c5532ede39b7c8bd221671424dabaacb236348b2a8a14bfb5`). Серверный код и калибровка Vbus сохранены побайтно; прошивки MCU не записывались, команд Пуск/Стоп/ARM приводу не отправлялось. HMI-деплой и проверка после него прошли.

После установки: SAFE, PWM=0, DC-шина 0 В, температура IPM 30 °C, UART bad/sequence/error flags=0. Код 5 — ожидаемая защита по пониженной DC-шине при выключенном силовом питании; Пуск заблокирован. Новая панель открыта во второй вкладке браузера; первая вкладка содержит старую загруженную копию страницы и требует обновления.

## HMI-диагностика, 2026-10-17 МСК

На установленную Uno Q добавлен и по SHA-256 проверен только новый
`web_hmi/static/app.js`. Пара MCU-прошивок осталась `2026101507/2026101506`,
серверный файл и калибровка Vbus совпали до/после; MCU flash-команд и команд
приводу не отправлялось. Обновлённая панель прямо в HMI разделяет причину
MCSDK/IPM и UART, показывает свежесть ответа, счётчики кадров, задание поля и
квалифицированную скорость энкодера. При защёлкнутой ошибке она читает D1 снимок
пассивным GET и указывает ограничения измерения.

При установке API показывал SAFE, PWM=0, ESTOP=0, fault=0, Vbus=10 В и свежую
телеметрию. `mc_bad_integrity=1` сохранён как предупреждение накопленного
счётчика; bad=0, bad_sequence=0 и UART-флаги=0. После установки та же пара
прошивок и рабочее состояние подтвердились повторным GET; калибровка не изменилась.
Это не подтверждает отсутствие напряжения на силовой части мультиметром.

## Текущее состояние после установки BKIN-диагностики, 2026-10-15 МСК

Установлена диагностическая пара Uno Q `2026101507` / Nucleo `2026101506`.
Nucleo записана и совпала с образом при полном чтении памяти
(SHA-256 `EF41FB5DCF3AD65B32631D3DD5FA34A87FDE259C927233CD17DBAC589A5B76B5`);
загрузчик Uno Q подтвердил запись и проверку образа. HMI обновлён на Uno Q,
кнопка «Считать снимок BKIN» доступна; существующий ключ управления сохранён.
Нулевые и высоковольтные точки Vbus остались `0/0 В` и `322.7/325 В`;
перекалибровки не было.

После записи выполнено 10 секунд низковольтного наблюдения: 50/50 ответов,
все `SAFE`, PWM=0, шина `1–2 В`, UART error flags=0. Счётчики
`mc_bad_cnt=1` и `bp_bad_cnt=1` за следующие 3 секунды не изменились;
защёлкнутый код транспорта `7=LINK_TIMEOUT` остался в диагностике, а MCSDK
показывает `MC_UNDER_VOLT` при обесточенной шине. Новых ошибок связи во время
наблюдения не прибавилось.

Авторизованный GET `/api/bkin-trace` отвечает HTTP 200, но пока возвращает
`available=false, reason=not_received`: после установки не было нового события
BKIN. Предыдущий D1-снимок регистров сохранён в
`manual_scalar_bkin_trace_r3/install_run/previous_d1_break_snapshot.json`;
это не высокочастотная осциллограмма PA6. Кандидат всё ещё не прошёл
выпускные проверки внешнего soft-start HIL и
аппаратного BKIN-срабатывания; после записи двигатель и силовая часть не
запускались. Перед следующим открытием страницы обновить HMI по адресу
`http://192.168.1.138:8080/`; если панель попросит ключ, используется прежний
ключ, сохранённый на Uno Q.

Подробный журнал записи: `artifacts/live_bench_20261015/manual_scalar_bkin_trace_r3/install_run`.

## Последний силовой результат ручного V/f до установки диагностики, 2026-10-15 МСК

В этом опыте работала пара Uno2026101505 / Nucleo2026101504.
Реальный прогон5→10→5 Гц ПРОЙДЕН: пользователь подтвердил ровное вращение,
видимое ускорение и снижение скорости. Разгон2 Гц/с, снижение0.5 Гц/с;
51 активный отсчёт, наблюдаемый активный интервал34.531с, от запроса START
до конца наблюдения36.359с. Это разные интервалы, не точное время вращения.
Все три задания достигнуты, сессия пережила прежний30-секундный ARM TTL.
UART fault/bad/CRC/sequence0; шина315..319 В; штатный STOP подтверждён.

Следующая расширенная попытка5→20→50→20→5 НЕ ПРОЙДЕНА: при разгоне к20
возник TIM1 Break / MC_DP_FAULT0x0400. Последний активный отсчёт12.6 Гц,
сохранённый контекст12.7 Гц. До20 и50 Гц не дошли. Причиной останова
не был таймаут UART: критические счётчики/CRC/sequence остались0.
Снимок Break: BIF1/B2IF0/BKE1/MOE0, PA6 уже HIGH при входе в обработчик;
контекст старше события на43мс, шина317 В. Это НЕ измерение длительности SD
и не доказательство конкретной причины: токи фаз/15 В/импульс SD не измерены.

В конце того силового прогона STOP был подтверждён, SAFE/ШИМ0/ARM0, авария зафиксирована.
Состояние на момент того отчёта: повторного START/CLEAR после рабочего Break
не было; силовое и15 В были включены, стенд закрыт, обе платы на повербанке,
USB ПК и ВСЕ щупы/GND Saleae сняты, двигатель подключён.
Пассивное наблюдение после аварии10.969с/+221 ответ: выходы выключены,
связь свежая без критических ошибок, шина318 В. Выключение питания здесь
не выполнялось и не квалифицировано. Пользователь подтвердил, что доступен
только Saleae. Он не изолирован от USB компьютера; UNO Q host не запускает
официальный Saleae Logic на ARM.

Тогда был подготовлен отдельный собранный диагностический кандидат
`artifacts/live_bench_20261015/manual_scalar_bkin_trace_r3`:
Uno2026101507/Nucleo2026101506. Nucleo записывает PA6/BKIN с частотой1 МГц
в кольцо1.024мс, замораживает его при BIF/B2IF и после отключения выходов
передаёт снимок Uno; в HMI добавлена кнопка «Считать снимок BKIN». TIM2
переиспользуется только после штатной синхронизации MCSDK при загрузке,
его TRGO на время записи удерживается в сбросе. Оба бинарника собраны;
Nucleo:0 ошибок/предупреждений. На момент сборки предпусковой gate не был
пройден из-за отсутствия внешнего soft-start HIL и аппаратного подтверждения
BKIN-теста. Пара позже записана и проверена; подробности и оставшиеся ограничения
указаны выше и в `manual_scalar_bkin_trace_r3/BUILD_STATUS_RU.md`.
Для чтения нового снимка Saleae не нужен; после последующей установки
калибровка осталась без изменений. Текущий установленный комплект и результат
его проверки приведены в начале этого файла.

Статический разбор выявил разрыв закона V/f на10 Гц: амплитуда команды
20→35.921 В пиковых. Связь с последующим Break НЕ доказана: базовый прогон
достиг10 Гц успешно, тока/SD в момент аварии нет. Закон/фильтры/защиты
по этой гипотезе не менялись. Настоящая осциллограмма активного ШИМ1505/1504,
измеренная скорость вала и фазные токи пока не квалифицированы.

Доказательства в `artifacts/live_bench_20261015/manual_scalar_working_pair_r3`:
базовый `powered_manual_1792055829149795500/report.json`, расширенный
`powered_manual_1792056019094763800/report.json`, пассивный
`powered_stopped_after_break/report.json`; сводка/график реальной телеметрии
`hardware_review/hardware_verification.json` и `hardware_review/actual_runs.png`.
Общий флаг full-range остаётся false, базовый успех сохранён отдельно.
Следующая запись прошивки для изменения частоты/темпов не нужна.

## Установка текущего комплекта, до силовых прогонов

Установлена постоянная пара Uno2026101505 / Nucleo2026101504 из
`artifacts/live_bench_20261015/manual_scalar_working_pair_r3`.
Обе записи проверены, Nucleo дополнительно сверена полным чтением памяти.
Сохранены исходные точки калибровки и их SHA. Исправлен источник частоты VF_OL:
теперь API читает ramp manager, используемый самим скалярным регулятором.
Следующий сегмент замедления ждёт завершения по MCSDK, а не округлённого равенства.

После подтверждения пользователем OFF/мультиметр<20 В/USB обе платы присутствовали.
Внутренний RPC Uno после холодного запуска не зарегистрировался; проверка
существовавшего образа и сброс MCU восстановили его без переподключения кабелей
и без записи старой прошивки. Затем выполнена проверенная запись нового комплекта.
Запись LINK_TIMEOUT от промежутка программирования архивирована; один STOP/CLEAR
при OFF/разряженной шине. Итог: SAFE/ШИМ0/ARM0, UART0/bad0/CRC0/sequence0,
авария0, частота поля0/valid1, шина10 В. Реальное наблюдение7.703с/+154 ответов,
8 отсчётов; это отдельная проверка покоя, не силовой пуск.
Онлайн-разгон2 Гц/с, замедление0.5 Гц/с и нулевое задание подтверждены новой Uno.

Это состояние после установки, до описанных выше силовых прогонов.
Несущая ШИМ настроена16 кГц; это параметр исходников, не новая осциллограмма.

На предыдущей установленной1503/1502 ползунок0→5→20→50→20→5→0 был проверен
на реальной Uno. Saleae при OFF записал12.063с низкого уровня на шести входах;
это не осциллограмма активного ШИМ новой1505/1504. Предыдущие две силовые попытки
сохранены: первая остановлена ошибочным критерием теста на NE-only Zephyr bit5,
вторая выявила нулевой отсчёт MCSDK VF_OL. Их нельзя считать пройденным ручным
прогоном; обе завершились подтверждённым STOP.

Доказательства установки: `manual_scalar_working_pair_r3/installation/report.json`.
Исходники/образы/программные проверки: `qualification.json`; реальный код MCSDK
ramp/VF_OL/API —140073 утверждения с воспроизведением старого дефекта.
Основные АЦП/фильтры/ШИМ/аппаратные защиты не менялись. Для смены частоты и
темпов перезапись не нужна. Прежние1415/1414 и последующие результаты — история ниже.

## Предыдущая подготовка ручного управления, 2026-10-15 МСК

Пользователь переходит к ручному START/STOP и изменению частоты через
http://192.168.1.138:8080/. Свежая телеметрия: рабочая пара1415/1414,
SAFE/ШИМ0/ARM0/авария0, шина324 В, UART исправен; силовое остаётся включённым.
На установленной прошивке подготовлены MODE VF и SET FREQ5. Пуск и ARM
агентом не отправлялись: следующий START выполняет пользователь в интерфейсе.
Первый ручной диапазон3–5 Гц; текущий автоматический лимит одного пуска15с.
Онлайн-изменение ускорения ещё не реализовано. Калибровка и прошивки сохранены.
Подготовка: `artifacts/live_bench_20261015/manual_hmi_r1/preparation.json`.
Это подготовка ручного управления, а не результат нового силового прогона.

## Текущий силовой результат r2, 2026-10-14

r2, рабочая пара Uno2026101415/Nucleo2026101414, записана и проверена.
Nucleo сверена полным чтением памяти. Калибровка сохранена, интерфейс
восстановился без переподключения USB. После обновления31.157с/+595 корректных
ответов без новых ошибок. Затем обычный силовой пуск5 Гц прошёл до штатного STOP.
Пользователь подтвердил ровное вращение именно на r2. В записи20 активных
отсчётов, наблюдаемый интервал ШИМ8.391с, интервал задания5 Гц7.828с;
это интервалы между отсчётами, а не точное измерение времени вращения.

CRC-корректные свежие пакеты с одиночным NE теперь диагностические и не расходуют
лимит повреждённых пакетов. Защиты двигателя, проверка CRC/команды/номера,
таймаут и ограниченное восстановление повреждённых пакетов сохранены.
Во время пуска8 новых отметок NE,6 принятых проверенных NE-пакетов и4
восстановленных отбрасывания. UART fault/bad/integrity/sequence остались0,
MCSDK first-fault masks0/0; связь не сорвала пуск. Один START, один предварительный
CLEAR известной стартовой UV/DP-записи до START; повторных пусков/сбросов нет.
В этом этапе прошивки и калибровка не записывались.

Сейчас SAFE/ШИМ0/ARM0/ошибка0/шина323 В. По пожеланию пользователя силовое
и15 В оставлены включёнными; обе платы на повербанке, ПК/Saleae отключены.
После STOP связь продолжила работать без новых ошибок. Выключение силового
в этом этапе НЕ выполнено и НЕ квалифицировано. Измеренная скорость и токи
пока не квалифицированы; онлайн-изменение ускорения пока не реализовано.
Доказательства: `artifacts/live_bench_20261014/uart_recovery_working_pair_r2/powered_vf_1792011214155394100/report.json`
и `powered_stopped_idle_report.json` в том же каталоге.

## История: силовой результат r1, 2026-10-14

Пользователь подтвердил вращение двигателя при повторном пуске рабочей пары
1413/1412. START подтверждён, были RUN/ШИМ1 и заданная частота5 Гц. Полный
10-секундный прогон не завершился: UART NE вновь вызвал ранний останов;
MCSDK masks0/0, новое срабатывание силовой защиты этим опытом не установлено.

После выключения силового/15 В связь на повербанке сохранилась:30.719с,
+596 ответов, новых ошибок нет. Ошибка предыдущего пуска сохранена.
Подготовлено постоянное исправление r2,1415/1414: CRC-корректный свежий пакет
с одиночным NE теперь диагностический признак; лимит отбрасываний расходуют
повреждённые пакеты.2106 проверок, серия40 NE-пакетов и обе целевые сборки прошли.
Сейчас r2 ещё не записан: ожидается USB-подключение при подтверждённом остатке<20 В.
Двигатель оставляем подключённым, калибровку сохраняем.

## История установки 2026-10-14, 21:23 МСК

Установлена постоянная рабочая пара Uno2026101413/Nucleo2026101412,
`artifacts/live_bench_20261014/uart_recovery_working_pair_r1`. Запись проверена,
Nucleo сверена полным чтением памяти. Калибровка, ШИМ, АЦП, фильтры и защиты
двигателя сохранены. Интерфейс: http://192.168.1.138:8080/.

Неповреждённый пакет с одним NE проходит CRC и проверку команды одинаково при
START и RUN. Повреждённые пакеты отбрасываются с ограниченным восстановлением
по свежему пакету: два события за секунду. Мусор не продлевает таймаут300 мс;
устойчивые ошибки останавливают привод. Отбрасывания видны отдельным счётчиком.

После записи реальная связь проверена30.828с:41 отсчёт,+589 корректных ответов,
новых ошибок нет. Пользователь выключил всё и независимо проверил остаток<20 В.
Последнее SAFE/PWM0/ARM0/шина2 В, ожидаемая защита по низкому напряжению,
транспортная авария0. Двигатель подключён, USB обеих плат использованы для записи.

2061 проверка настоящего кода обеих плат с моделями аппаратуры прошла, включая
потерю силового. Новый силовой пуск ещё не выполнен. Ожидается перевод на
повербанк и включение питания для проверки5 Гц. Онлайн-ускорение пока не реализовано.

## История: оперативное обновление 2026-10-12

- Свежий силовой опыт: один пуск рабочей пары 1205/1204 с заданием 5 Гц,
  пользователь подтвердил вращение. Прогон **не прошёл**: HMI остановила его
  по `uno_rx_hw_errors=1`, `0x20=UART_ERROR_NOISE`. STOP/ESTOP и выключение ШИМ
  подтверждены; пользователь выключил силовое питание.
- Сейчас SAFE, PWM=0, ARM=0, одноразовый допуск потреблён. Последняя сохранённая
  телеметрия шины — 2 В; перед работой с проводкой нужна независимая проверка
  разряда. Повторный START и CLEAR после события не выполнялись.
- UART CRC/sequence/bad и транспортный fault остались 0; первый fault Nucleo —
  ESTOP с MCSDK masks 0/0. Новый MC_DP этим опытом не установлен. Первичный
  физический источник UART-noise не установлен.
- Текущий HMI SHA256 `88f0764f881b5bbc7cb8e1e0b40954fe7d2e63450edd568cd8b92f83550d2d6b`.
  Калибровка сохранена; MCU не перепрошивались. Отчёт:
  `artifacts/live_bench_20261012/local_button/motor_short_r1/RESULT_RU.md`.

Далее сохранена история предыдущих этапов; актуальные выводы указаны выше.

- Свежий этап: измерительный STOP по B1 при работающих шести ШИМ прошёл
  на изолированной тестовой копии 1298/1299. `Session 8.sal`: 16 кГц,
  перекрытия нет, после останова все шесть LOW ещё 9,645 с. Задержка от
  фронта кнопки не измерена; силовой двигатель не запускался.
- Рабочие образы 1205/1204 восстановлены и проверены, тестовый HMI остановлен.
  RPC после смены образов восстановлена холодным перезапуском Uno; повторный
  перезапуск больше не ожидается (`post_cold_boot_r1/REPORT.md`).
  Калибровка по хешу сохранена. Подробности: `PWM_LOCAL_STOP_REPORT.md`
  в каталоге `artifacts/live_bench_20261012/local_button`.

Ниже — ранее подтверждённые этапы этого дня.

- Установлены и проверены: Uno Q `2026101205`, Nucleo G431RB `2026101204`.
- HMI обновлён; исходная калибровка сохранена без новой нулевой точки.
- 30 секунд Wi-Fi: 601 новое корректное сообщение UART, новых ошибок нет;
  SAFE, PWM=0, ARM=0, шина по телеметрии 0 В.
- Диагностика снова распознаётся. На обесточенной шине сохранён `MC_UNDER_VOLT`;
  это не подтверждение готовности силового пуска.
- STOP B1: активный HIGH, EXTI RISING; защёлка и запрет повторного ENABLE
  реализованы. Пользователь подтвердил нажатие: `bp_status=0x8D`, LOCAL STOP=1,
  текущий fault=ESTOP. Пользователь подтвердил отпускание; следующие 10 секунд
  Wi-Fi (11 снимков) подтверждают удержание защёлки, PWM=0, ARM=0, шина 0 В,
  новых ошибок нет. Останов активного ШИМ на этой паре остаётся непроверенным.
  Доказательство: `b1_released_idle_r1/release_verify.json` в каталоге local_button.
- Исправлен и установлен только HMI: `hmi_local_stop_latched=1` совпадает с
  сырым флагом, отображается `LOCAL_STOP_PC13`, переход записывается в логи.
  Первый fault-снимок `MC_UNDER_VOLT`, маски `0x0004/0x0004` сохранён.
  API-регрессия: 70 проверок; пять существующих guard suites прошли.
  Подробности: `artifacts/live_bench_20261012/local_button/HMI_STOP_FIX_REPORT.md`.
- Срок ожидания принятой подготовки убран; предел пробного пуска 3 секунды,
  watchdog и аппаратные защиты сохранены. Разрешение пуска не создавалось.
- Итог: `artifacts/live_bench_20261012/local_button/DEPLOY_REPORT.md`;
  установка: `install_r4/report.json`; связь: `installed_idle_r1/summary.json`.
- Промежуточные образы `1201`, `1202`, `1203` и старые HMI не использовать.

## Архивный блок

Ниже сохранён автоматически сформированный статус августа; текущие версии
и свежие доказательства указаны выше.

- Сформировано: `2026-08-26T01:26:00`
- Проект: `C:\mic_practice`
- Активный motor backend: `nucleo_mcsdk_acim`
- Active PWM разрешен: **НЕТ**
- Build-only preflight свежий и прошел: **ДА**
- Bringup/readiness готов: **НЕТ**

## Решение

Active PWM сейчас **не запускать**. Не подавать `START` и не включать HV/J7 для обхода красного gate.

## Почему gate красный

- `nucleo_mcsdk_runtime_validation`: Аппаратное подтверждение ожидает платы: прошить обе платы при отключённой HV/J7, затем проверить UART и статические уровни PWM.

## Что делать дальше

1. `validate_nucleo_mcsdk_hardware`
   Оставить HV/J7 отключённой, разрядить DC-шину, прошить проверенные артефакты UNO Q и Nucleo, проверить sequence/CRC/тайм-аут 300 мс через USART1 PB6/PB7 и подтвердить Saleae безопасные статические уровни всех шести PWM-входов IPM.

## Последние доказательства

- Nucleo MCSDK build preflight: `C:\mic_practice\mcsdk_reference\AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV\STM32CubeIDE\Debug\mcsdk_release_preflight.json`
- Nucleo MCSDK runtime preflight: `нет`
- Build-only summary: `C:\mic_practice\tools\_preflight_exports\full_system_preflight_20260826_012447_774251\summary.json`
- Readiness summary: `C:\mic_practice\tools\_readiness_exports\research_readiness_20260826_012548_207012\summary.json`

## Запреты до зеленого gate

- Не запускать active PWM без `ready_for_active_pwm=true`.
- Не прошивать и не испытывать Nucleo/IPM с подключенной HV/J7 до статической проверки шести PWM-входов и аварийного останова.
- Не считать предупреждение `nucleo_mcsdk_hv_release_gate` разрешением на подачу высокого напряжения.
- UART loopback делать только при отключенных TX/RX от STM32: коротить TX-RX нужно на стороне USB-UART/изолятора.
- Не держать HMI/serial monitor открытым во время UART loopback на том же COM-порту.
- Если JSON и этот файл расходятся, главным считается свежий `summary.json`; затем нужно заново запустить генератор статуса.
