# Линия NTC Bypass Не Используется

Старая проверка `NTC bypass relay` удалена: контакт `STEVAL-IPM15B J2-21`
на плате не подключен к рабочей цепи.

- `Blue Pill PB1` оставить `NC`; прошивка удерживает его в режиме
  `analog/high-impedance`.
- `STEVAL J2-21` оставить `NC`.
- Команды `NTC ON` и `NTC OFF` не поддерживаются.
- Единственное реле, управляемое Blue Pill, - внешнее реле предзаряда `K1`
  с управляющим выходом `PB4`.

Подключение и проверка `K1`: [PRECHARGE_RELAY_TEST_RU.md](PRECHARGE_RELAY_TEST_RU.md).
