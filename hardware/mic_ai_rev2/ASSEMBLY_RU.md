# MIC_AI REV 2.1 - схема сборки

> **АРХИВНАЯ РЕВИЗИЯ, НЕ СОБИРАТЬ.** Этот комплект содержит K1/PB4 и не
> соответствует текущей конфигурации без управляемого реле. Актуальные правила:
> `../../POWER_INPUT_NO_RELAY_RU.md`. Перед изготовлением нужна новая ревизия
> схемы, ERC/DRC и повторное аппаратное ревью.

Канонический PDF: `../../output/pdf/MIC_AI_REV2_SCHEMATIC.pdf`.

Редактируемые/производные файлы:

- `MIC_AI_REV2_NETLIST.edif` - импорт netlist в EasyEDA;
- `MIC_AI_REV2_BOM.csv` - перечень элементов;
- `MIC_AI_REV2_CONNECTIONS.csv` - каждая электрическая сеть и вывод;
- `MIC_AI_REV2_PINMAP.csv` - физические выводы критичных корпусов и их сети;
- `svg/page_01.svg` ... `svg/page_06.svg` - векторные листы;
- `manifest.json` - результат автоматической проверки инвариантов.

## Главная архитектура

- `HV_DC_MINUS_HOT_GND` является отрицательной DC-шиной и горячей землей STEVAL/Blue Pill.
- `SAFE_GND` принадлежит UNO Q, ПК, Saleae и изолированному контуру аппаратного запрета PWM.
- Между `SAFE_GND` и `HV_DC_MINUS_HOT_GND` нет прямого соединения.
- UART проходит через `ISO7721DWR`.
- Saleae CH0..CH7 проходит через два `ISO7740FDWR`.
- ST-Link подключается только при отключенной HV/J7 и разряженной шине.

## Обязательные отличия от старой схемы

1. У KBPC5010 четыре отдельные сети: два `AC~`, `PLUS`, `MINUS`.
2. MOV установлен после F1.
3. Внешний precharge K1 управляется `PB4`; `PB1` и STEVAL J2-21 оставлены NC.
4. K1 - TE Mini K HV `2-1904058-5`, а не SRD-12VDC-SL-C.
5. UNO Q питается через `VIN 7-24V` или USB-C. Его 3.3V и 5V не являются входами питания в этой схеме.
6. Blue Pill питается только через внешний `HOT_3V3`; pin 5V не подключен.
7. Все GND-контакты STEVAL J2 подключены к горячей земле.
8. Стандартный 4-pin fan получает постоянные `HOT_12V` и `HOT_GND`; PB3 управляет PWM-входом через открытый коллектор MMBT2222A на 25 кГц.
9. 3-pin fan можно подключить к контактам GND/+12V/TACH, но регулировки скорости тогда нет: он работает постоянно на полной скорости.
10. J4 negative называется `RETURN/HOT_GND`, а не `-15V`.
11. `JP_HOT15_SRC` выбирает ровно один источник: бортовой HLK-20M15 или внешний изолированный 15 В для стендовой проверки без HV.

## Неопределенный параметр

Номинал F1 нельзя корректно выбрать без шильдика двигателя, максимального входного тока и сечения проводов. В BOM он намеренно оставлен `F1_VALUE_BY_LOAD`. Нельзя увеличивать предохранитель, чтобы скрыть ошибку сборки.

## Исходные документы

- ST UM2014, STEVAL-IPM15B: `../../um2014-1500-w-motor-control-power-board-based-on-stgib15ch60tsl-sllimm-2nd-series-ipm-stmicroelectronics.pdf`.
- TE Mini K HV `2-1904058-5`: https://www.te.com/en/product-2-1904058-5.html
- TI ISO7721: https://www.ti.com/product/ISO7721
- TI ISO7740: https://www.ti.com/product/ISO7740
- Arduino UNO Q datasheet: https://docs.arduino.cc/resources/datasheets/ABX00162-datasheet.pdf
- 4-pin fan PWM/RPM interface reference: https://www.noctua.at/cn/support/faqs/microcontroller-guide-pwm-setup-and-rpm-monitoring

## Порядок проверки

1. Не подключая 230VAC, прозвонить разделение SAFE/HOT/PE/AC_N.
2. Выбрать `EXTERNAL` на `JP_HOT15_SRC`, подать изолированные 15 В без J7/HV и проверить аппаратный запрет PWM.
3. Проверить UART через изолятор.
4. Проверить static LOW и PWM через изолированный Saleae.
5. Проверить K1 при отключенной HV.
6. Провести отдельный PCB/layout review по creepage, clearance, ширине дорожек и защитному корпусу.
7. Только после этого рассматривать подачу 230VAC.
