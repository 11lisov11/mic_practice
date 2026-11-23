"""RPC failures must not acquire or write the router-owned UART."""
import json
from pathlib import Path
from unittest.mock import patch
from web_hmi_command_guard_selftest import load_server_module


def main():
    mod = load_server_module(Path(__file__).resolve().parents[1])
    cases = 0
    for endpoint in ("/var/run/arduino-router.sock", "unix:/var/run/arduino-router.sock", "127.0.0.1:7500"):
        with patch.object(mod, "TextSerialClient") as text, patch.object(mod, "RouterClient") as router:
            router.return_value.call.return_value = None
            bridge = mod.RpcBridge(endpoint)
            assert bridge._serial_text is None and not text.called; cases += 1
            assert bridge.get() == (False, None, "no response") and not text.called; cases += 1
            assert bridge.cmd("STOP") == (False, "no response") and not text.called; cases += 1
    with patch.object(mod, "TextSerialClient") as text, patch.object(mod, "RouterClient", side_effect=RuntimeError("unavailable")):
        bridge = mod.RpcBridge("/var/run/arduino-router.sock")
        assert bridge.get() == (False, None, "no response") and not text.called; cases += 1
    for endpoint in ("serial:/dev/ttyUSB0", "/dev/ttyUSB0"):
        with patch.object(mod, "TextSerialClient") as text, patch.object(mod, "RouterClient") as router:
            bridge = mod.RpcBridge(endpoint)
            text.assert_called_once_with("/dev/ttyUSB0", baud=115200)
            assert not router.called and bridge._serial_text is not None; cases += 1
    print(json.dumps({"pass": True, "cases": cases, "hardware_commands": 0}))


if __name__ == "__main__":
    main()
