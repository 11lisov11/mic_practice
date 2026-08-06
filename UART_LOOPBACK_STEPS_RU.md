# UART loopback: USB-UART -> STM32

Цель: отдельно доказать, что ПК, USB-изолятор, USB-UART, кабель, драйвер и изолированная сторона адаптера реально могут передавать байты. Этот тест выполняется до участия STM32, потому что текущая ошибка `Write timeout` возникает еще на записи в COM-порт.

## Запреты

- Не подавать `START`.
- Не включать HV/J7 и 315 В ради этой проверки.
- Не запускать `unoq_web_server.py` и Serial Monitor на том же COM-порту во время loopback.
- Не коротить TX/RX, пока они подключены к STM32.

## Шаг 1. Разорвать связь со STM32

Отключи только линии UART между USB-UART и STM32:

- USB-UART `TX` от STM32 `PA3 / USART2_RX`.
- USB-UART `RX` от STM32 `PA2 / USART2_TX`.

Питание STM32 можно оставить как для низковольтной диагностики, но в loopback сама STM32 не участвует.

## Шаг 2. Замкнуть adapter TX-RX

На изолированной стороне USB-UART поставь короткую перемычку:

- USB-UART `TX` -> USB-UART `RX`.

Если адаптер или USB-изолятор требует отдельное питание изолированной стороны, оно должно быть подано. Общий GND со STM32 для этого теста не нужен, потому что STM32 отключена от TX/RX.

## Шаг 3. Запустить проверку

Основной безопасный запуск:

```powershell
py -3 -u .\tools\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080
```

Этот wrapper сам:

- отправит HMI `STOP/CLEAR` и остановит `unoq_web_server.py` на `18080`;
- запустит `bluepill_uart_diagnose.py --loopback`;
- снова поднимет PC-direct HMI на `18080`.

Для оператора прямой ручной fallback не нужен: на стенде запускай только wrapper выше. Прямая команда `bluepill_uart_diagnose.py --loopback` остается внутренним шагом wrapper-теста и не должна запускаться вручную при подключенном STM32.

Если wrapper пишет `stop_or_close_pc_direct_hmi_before_uart_loopback`, он специально не открывал COM-порт и не запускал loopback. Сначала закрой HMI/Serial Monitor/любую программу, которая держит COM3, затем повтори wrapper-команду.

## Если PASS

Это значит, что USB-UART/изолятор умеет писать и читать байты. Затем:

- Убери перемычку TX-RX.
- Верни перекрестное подключение: `PC/USB-UART TX -> STM32 PA3`, `PC/USB-UART RX -> STM32 PA2`.
- GND изолированной стороны USB-UART должен быть общим со STM32 logic GND.
- После возврата TX/RX можно снова поднять безопасный HMI:

```powershell
py -3 -u .\tools\pc_direct_hmi_service.py start --serial COM3 --baud 115200 --port 18080
```

- Запусти протокольную диагностику:

```powershell
py -3 -u .\tools\bluepill_uart_diagnose.py --port COM3 --dtr-rts-matrix --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0
```

## Если FAIL или снова Write timeout

Не подключай TX/RX обратно к STM32, пока не исправлено одно из этого:

- выбран не тот COM-порт;
- USB-изолятор не питает изолированную сторону;
- неисправный или неподходящий USB-UART;
- плохой USB-кабель;
- драйвер WCH/CH340/CH341 завис или конфликтует;
- TX-RX перемычка стоит не на стороне USB-UART;
- другой процесс держит COM-порт.

Только после PASS loopback есть смысл искать проблему в STM32, PA2/PA3, прошивке или скорости UART.

## Безопасный инвентарь без записи в COM

Если нужно только посмотреть, какие COM-порты видны Windows/PySerial/PlatformIO, можно выполнить:

```powershell
py -3 -u .\tools\bluepill_uart_diagnose.py --inventory-only --port auto
```

Этот режим не открывает COM-порт и не пишет байты. Он не является доказательством связи со STM32.
