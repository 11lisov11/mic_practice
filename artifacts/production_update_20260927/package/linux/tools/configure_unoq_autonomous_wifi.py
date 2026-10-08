#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from typing import Sequence


def adb_devices() -> list[str]:
    result = subprocess.run(["adb", "devices"], check=False, capture_output=True, text=True)
    devices: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device" and not parts[0].startswith("emulator-"):
            devices.append(parts[0])
    return devices


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def run(adb: Sequence[str], command: str, label: str) -> None:
    print(f"RUN {label}", flush=True)
    subprocess.run([*adb, "shell", command], check=True)


def configure_station(adb: Sequence[str], iface: str, ssid: str, password: str) -> None:
    name = "MIC_AI_STA"
    command = (
        "set -eu; "
        f"nmcli connection delete {shell_quote(name)} >/dev/null 2>&1 || true; "
        "nmcli radio wifi on; "
        f"nmcli --wait 30 device wifi connect {shell_quote(ssid)} password {shell_quote(password)} "
        f"ifname {shell_quote(iface)} name {shell_quote(name)}; "
        f"nmcli connection modify {shell_quote(name)} connection.autoconnect yes "
        "connection.autoconnect-priority 100 ipv4.method auto ipv6.method auto; "
        f"nmcli connection up {shell_quote(name)}"
    )
    run(adb, command, f"configure station profile {name} for SSID {ssid!r}")


def configure_ap(adb: Sequence[str], iface: str, ssid: str, password: str, address: str) -> None:
    name = "MIC_AI_AP"
    command = (
        "set -eu; "
        f"nmcli connection delete {shell_quote(name)} >/dev/null 2>&1 || true; "
        "nmcli radio wifi on; "
        f"nmcli connection add type wifi ifname {shell_quote(iface)} con-name {shell_quote(name)} "
        f"autoconnect yes ssid {shell_quote(ssid)}; "
        f"nmcli connection modify {shell_quote(name)} 802-11-wireless.mode ap "
        "802-11-wireless.band bg 802-11-wireless.channel 6 "
        "wifi-sec.key-mgmt wpa-psk "
        f"wifi-sec.psk {shell_quote(password)} ipv4.method shared "
        f"ipv4.addresses {shell_quote(address)} ipv6.method disabled "
        "connection.autoconnect-priority 50; "
        f"nmcli connection up {shell_quote(name)}"
    )
    run(adb, command, f"configure autonomous AP profile {name} for SSID {ssid!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure persistent UNO Q Wi-Fi for cable-free motor operation.")
    parser.add_argument("--mode", choices=("station", "ap"), required=True)
    parser.add_argument("--ssid", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--device", default="")
    parser.add_argument("--iface", default="wlan0")
    parser.add_argument("--ap-address", default="192.168.77.1/24")
    parser.add_argument(
        "--confirm-service-mode",
        action="store_true",
        help="Confirm that mains, rectifier and STEVAL J7 are physically disconnected and DC-link is discharged",
    )
    args = parser.parse_args()
    if not args.confirm_service_mode:
        raise SystemExit(
            "ERROR: ADB setup is allowed only in service mode; add --confirm-service-mode after physically disconnecting HV"
        )
    if len(args.password) < 12:
        raise SystemExit("ERROR: use a Wi-Fi password of at least 12 characters")
    devices = adb_devices()
    device = args.device.strip() or (devices[0] if len(devices) == 1 else "")
    if not device:
        raise SystemExit("ERROR: specify --device; exactly one physical ADB device was not found")
    if device not in devices:
        raise SystemExit(f"ERROR: ADB device is not online: {device}")
    adb = ["adb", "-s", device]
    if args.mode == "station":
        configure_station(adb, args.iface, args.ssid, args.password)
        print("DONE: station profile is persistent. Open http://<UNO_Q_IP>:8080 after removing USB.")
    else:
        configure_ap(adb, args.iface, args.ssid, args.password, args.ap_address)
        host = args.ap_address.split("/", 1)[0]
        print(f"DONE: AP profile is persistent. Connect the phone to {args.ssid!r} and open http://{host}:8080.")
    print("Before HV: power down, remove USB/ADB and every other external cable, close the enclosure, then power up autonomously.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
