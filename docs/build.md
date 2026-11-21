# Сборка прошивок и запуск локальных проверок

Команды выполняются из корня репозитория. Сборка не обращается к стенду.

## Nucleo-G431RB

Используйте Python 3.10+ и GNU Tools for STM32 14.3.rel1 из STM32CubeIDE 2.2.0. Если `arm-none-eabi-gcc` доступен через PATH:

```sh
python tools/build_nucleo.py
```

Путь к каталогу `bin` можно передать через `--toolchain`. Файлы `.elf`, `.hex` и `.bin` появятся в `build/nucleo/`. Канонический список компилируемых единиц находится в [`sources.txt`](../firmware/nucleo/sources.txt). Встроенный проект CubeIDE находится в [`firmware/nucleo/STM32CubeIDE/`](../firmware/nucleo/STM32CubeIDE/). Для воспроизведения сборки используйте исходники из Git: повторная генерация CubeMX может перезаписать ручные изменения.

## Arduino Uno Q

Используйте Arduino CLI, ядро `arduino:zephyr` версии `0.90.0` и Python с `pyelftools`.

```powershell
python -m pip install pyelftools
pwsh -NoProfile -File tools/build_unoq_mcsdk_scalar.ps1 -LibrariesDirectory libraries -OutputDirectory build/uno
```

Имя скрипта сохранено для совместимости. Он собирает текущий контроллер Uno Q, подтверждает совместимость расширения Zephyr с загрузчиком и формирует манифест с SHA-256.

## Программные проверки

```sh
python -m pip install pytest
python -m pytest -q tests/test_mcsdk_clear_ack.py
```

Для регрессии MCSDK нужен `g++` с C++17. Тест извлекает обработчики из текущего кода Nucleo и воспроизводит гонку между OFF и подтверждением CLEAR на хосте. Сравнение прошитых байтов и измерение DWT на физическом STM32 относятся к отдельной стендовой проверке. Сверяйте готовые образы с опубликованными SHA-256.
