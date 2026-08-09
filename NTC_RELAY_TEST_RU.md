# Линия NTC Bypass Не Используется

Старая проверка `NTC bypass relay` удалена: контакт `STEVAL-IPM15B J2-21`
на плате не подключен к рабочей цепи.

- `Blue Pill PB1` оставить `NC`; прошивка удерживает его в режиме
  `analog/high-impedance`.
- `STEVAL J2-21` оставить `NC`.
- Команды `NTC ON` и `NTC OFF` не поддерживаются.
- Управляемых реле в текущей конфигурации нет. `Blue Pill PB4` также оставить
  `NC`; прошивка удерживает его в `analog/high-impedance` и маскирует бит `0x08`.

Актуальная схема силового ввода: [POWER_INPUT_NO_RELAY_RU.md](POWER_INPUT_NO_RELAY_RU.md).
