# UNOQ WiFi HMI

This folder hosts a lightweight web UI + HTTP server that runs on the UNOQ Linux side and controls the MCU over the router socket.

## Quick start (on the board)
```
cd /home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python server.py --bind 0.0.0.0 --port 8080 --router /run/arduino-router.sock
```

Open from your phone:
```
http://<board-ip>:8080
```

## Phone via PC LAN bridge with VPN enabled
If the phone/tablet is on a Wi-Fi AP connected to the PC by LAN, and UNO Q is reached from the PC through USB/ADB, run on the PC:
```
py -3 -u tools\ui_access.py --bridge --bridge-port 8080
```

Open the URL printed for the PC Ethernet/LAN adapter, not the VPN adapter. If the VPN blocks `0.0.0.0`, bind the bridge to the LAN IP explicitly:
```
py -3 -u tools\ui_access.py --bridge --bridge-host <PC_LAN_IP> --bridge-port 8080
```

The PC bridge bypasses system proxy/VPN proxy for `127.0.0.1:18080`, so the control path is: Wi-Fi client -> AP -> PC LAN IP -> bridge -> ADB forward -> UNO Q HMI -> MCU RPC.

## Notes
- Commands are sent via RPC `cmd` (START/STOP/MODE/SET FREQ).
- Status is polled via RPC `get` once per second.
- The single emergency button in the UI sends `ESTOP`, and switches to `ESTOP CLEAR` while the latch is active.
- Logs are stored locally (RAM + file) and trimmed by size. Use the Download button for last 24h (or a selected range).
- MIC mode surfaces a real-time savings estimate and id_ref on the Status panel.
- If the router socket is unavailable, the server falls back to direct serial `/dev/ttyHS1`.

## Options
```
--bind 0.0.0.0        HTTP bind address
--port 8080           HTTP port
--router /run/arduino-router.sock  Router endpoint (unix:/path or host:port)
--log-bytes 2097152   Max in-memory log bytes
--log-file ./logs/unoq.log  Log file path (empty to disable)
--log-file-bytes 4194304    Max log file bytes
--status-log-sec 5    Status log interval (seconds)
```
