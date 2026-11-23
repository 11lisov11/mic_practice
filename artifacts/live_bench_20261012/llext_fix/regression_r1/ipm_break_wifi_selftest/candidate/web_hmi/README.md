# UNOQ WiFi HMI

This folder hosts a lightweight web UI + HTTP server that runs on the UNOQ Linux side and controls the MCU over the router socket.

## Автономный запуск на плате
```
cd /home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python server.py --bind 0.0.0.0 --port 8080 --router /run/arduino-router.sock \
  --standalone-hv --control-token-file /home/arduino/.config/mic-ai/control_token
```

Open from your phone:
```
http://<board-ip>:8080
```

Рабочий путь: `телефон <- Wi-Fi -> UNO Q HMI -> MCU RPC -> прямой UART -> Nucleo`. ПК, ADB-мост и любой внешний провод в силовом режиме не используются. UNO Q работает через сохранённый профиль роутера либо поднимает автономную точку доступа; настройка описана в `docs/AUTONOMOUS_WIFI_OPERATION_RU.md`.

## Notes
- Commands are sent via RPC `cmd` (START/STOP/MODE/SET FREQ).
- Status is polled via RPC `get` once per second.
- The single emergency button in the UI sends `ESTOP`, and switches to `ESTOP CLEAR` while the latch is active.
- Logs are stored locally on UNO Q and trimmed at 64 MiB. Download requires the HMI control key.
- START and all setup commands require the control key. STOP/ESTOP remains fail-safe and is accepted without it.
- The browser sends a 1 Hz operator heartbeat. Losing it for 3 s during an armed run triggers STOP and ESTOP.
- MIC mode surfaces a real-time savings estimate and id_ref on the Status panel.
- If the router socket is unavailable, the server falls back to direct serial `/dev/ttyHS1`.

## Options
```
--bind 0.0.0.0        HTTP bind address
--port 8080           HTTP port
--router /run/arduino-router.sock  Router endpoint (unix:/path or host:port)
--log-bytes 2097152   Max in-memory log bytes
--log-file ./logs/unoq.log  Log file path (empty to disable)
--log-file-bytes 67108864   Max persistent log file bytes
--status-log-sec 5    Status log interval (seconds)
--control-token-file /path/token  Protect control and log download
--operator-heartbeat-timeout-sec 3  Stop an armed run on lost browser heartbeat
```
