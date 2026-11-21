# Панель MIC AI на Uno Q/Linux

`server.py` опрашивает MCU Uno Q через локальный сокет Arduino Router. `static/` содержит интерфейс оператора. MCU обменивается командами и телеметрией с Nucleo по UART. Используйте файлы HMI из того же выпуска, что и образы обеих плат. [Текущая версия и статус стенда](../docs/bench-validation.md).

Пример запуска из этого каталога на Uno Q в изолированной сети стенда:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python server.py --bind 0.0.0.0 --port 8080 --router /run/arduino-router.sock \
  --standalone-hv --control-token-file /home/arduino/.config/mic-ai/control_token
```

`GET /api/status` отдаёт телеметрию для диагностики. Снимки АЦП и наблюдателя можно выгрузить по страницам при выключенном ШИМ. Рабочий файл токена хранится на Uno Q, вне Git. Сервис предназначен для локальной сети стенда.
