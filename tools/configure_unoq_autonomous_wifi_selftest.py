#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def load_module(repo: Path) -> Any:
    path = repo / "tools" / "configure_unoq_autonomous_wifi.py"
    spec = importlib.util.spec_from_file_location("configure_unoq_wifi", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    mod = load_module(repo)
    captured: list[tuple[str, str]] = []

    def fake_run(_adb, command: str, label: str) -> None:
        captured.append((command, label))

    mod.run = fake_run
    password = "secret-password-123"
    mod.configure_station(["adb"], "wlan0", "LAB 'A'", password)
    mod.configure_ap(["adb"], "wlan0", "MIC_AI_STAND", password, "192.168.77.1/24")
    station, ap = captured
    cases = {
        "station_is_persistent": "connection.autoconnect yes" in station[0] and "ipv4.method auto" in station[0],
        "station_ssid_is_shell_quoted": "LAB '" in station[0] and "\"'\"" in station[0],
        "ap_uses_wpa_psk": "wifi-sec.key-mgmt wpa-psk" in ap[0] and "wifi-sec.psk" in ap[0],
        "ap_has_static_shared_network": "ipv4.method shared" in ap[0] and "192.168.77.1/24" in ap[0],
        "labels_do_not_leak_password": all(password not in label for _, label in captured),
    }
    failed = [name for name, ok in cases.items() if not ok]
    print(json.dumps({"tool": "configure_unoq_autonomous_wifi_selftest", "pass": not failed, "cases": cases}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
