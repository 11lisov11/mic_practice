# NUCLEO-G431RB UART bridge

Это промежуточная безопасная прошивка для проверки связи `UNO Q <-> NUCLEO-G431RB` до генерации официального ACIM-проекта в MCSDK.

Что реализовано:

- `USART1`, `PB6/TX`, `PB7/RX`, `115200 8N1`;
- существующий 32-байтный протокол версии `0x02`;
- CRC, sequence, счётчики good/bad и timeout `300 мс`;
- немедленный stop при E-STOP, timeout или неподдерживаемой команде запуска;
- формат ответа, совместимый с текущей прошивкой UNO Q.

Что намеренно не реализовано:

- TIM1 PWM, ADC, break input и управление STEVAL-IPM15B;
- V/F, FOC и MIC;
- реле, тормоз и вентилятор;
- реальная телеметрия шины, токов и температуры.

`motor_backend_stub.cpp` всегда отклоняет `ENABLE` с `FAULT_INTERNAL` и не конфигурирует ни одного силового вывода. Это не motor-control прошивка и не разрешение подавать J7.

Сборка:

```powershell
py -3 -m platformio run -d C:\mic_practice\nucleo_g431_uart_bridge_pio
```

На стенде без J7 допускается прямой UART для проверки. В итоговой сборке между UNO Q и Nucleo обязателен двухканальный изолятор; земли `SAFE_GND` и `HOT_GND` не соединяются. Полная коммутация описана в `C:\mic_practice\NUCLEO_G431_MIGRATION_RU.md`.

После генерации MCSDK-проекта этот каталог используется как источник модулей `proto`, `uart_link` и `bridge_controller`. Stub заменяется адаптером к публичному API MCSDK; системный clock, TIM1, ADC, fault/break и pin mapping берутся только из MCSDK/CubeMX.
