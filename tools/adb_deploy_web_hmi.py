#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], check: bool = True) -> None:
    log("RUN " + " ".join(cmd))
    subprocess.run(cmd, check=check)


def ok(cmd: list[str]) -> bool:
    log("RUN " + " ".join(cmd))
    return subprocess.run(cmd, check=False).returncode == 0


def adb_device_ids() -> list[str]:
    try:
        out = subprocess.check_output(["adb", "devices"], text=True)
    except Exception:
        return []
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    devices: list[str] = []
    for ln in lines[1:]:
        if ln.endswith("\tdevice"):
            devices.append(ln.split("\t")[0])
    return devices


def detect_device() -> str | None:
    for device in adb_device_ids():
        if device.startswith("emulator-"):
            continue
        return device
    return None


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def server_args(
    firmware_update_token_file: str | None,
    standalone_hv: bool,
    standalone_lv: bool = False,
) -> str:
    args = ""
    if firmware_update_token_file:
        args += " --firmware-update-token-file " + shell_quote(firmware_update_token_file)
    if standalone_hv:
        args += " --standalone-hv"
    if standalone_lv:
        args += " --standalone-lv --start-runlimit-sec 3.0"
    return args


def autostart_script(
    remote: str,
    firmware_update_token_file: str | None,
    standalone_hv: bool,
    standalone_lv: bool = False,
) -> str:
    extra_args = server_args(firmware_update_token_file, standalone_hv, standalone_lv)
    return (
        "#!/bin/sh\n"
        f"cd {shell_quote(remote)} || exit 1\n"
        "mkdir -p logs\n"
        "if command -v flock >/dev/null 2>&1; then\n"
        "  exec 9>/tmp/unoq-hmi.lock\n"
        "  flock -n 9 || exit 0\n"
        "fi\n"
        "while [ ! -S /var/run/arduino-router.sock ]; do\n"
        "  sleep 1\n"
        "done\n"
        "exec ./.venv/bin/python server.py --bind 0.0.0.0 --port 8080 "
        "--router /var/run/arduino-router.sock"
        f"{extra_args} >> logs/server.log 2>&1\n"
    )


def systemd_service() -> str:
    return (
        "[Unit]\n"
        "Description=UNO Q motor control Wi-Fi HMI\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "User=arduino\n"
        "ExecStart=/home/arduino/bin/start_unoq_hmi.sh\n"
        "Restart=always\n"
        "RestartSec=2\n"
        "StartLimitIntervalSec=0\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def privileged_command(command: str) -> str:
    root_cmd = shell_quote(command)
    return (
        "sh -lc "
        + shell_quote(
            "if [ \"$(id -u)\" = 0 ]; then sh -lc "
            + root_cmd
            + "; elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; "
            "then sudo -n sh -lc "
            + root_cmd
            + "; else exit 77; fi"
        )
    )


def ensure_msgpack(adb: list[str], remote: str, local_root: str) -> None:
    check_cmd = f"cd {shell_quote(remote)} && ./.venv/bin/python -c 'import msgpack'"
    if ok(adb + ["shell", check_cmd]):
        return

    pip_cmd = f"cd {shell_quote(remote)} && ./.venv/bin/python -m pip install -r requirements.txt"
    if ok(adb + ["shell", pip_cmd]) and ok(adb + ["shell", check_cmd]):
        return

    cache_dir = Path(local_root).parent / ".cache" / "wheels"
    cache_dir.mkdir(parents=True, exist_ok=True)
    wheels = sorted(cache_dir.glob("msgpack-*-cp313-*-aarch64*.whl"))
    if not wheels:
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--dest",
                str(cache_dir),
                "--only-binary=:all:",
                "--platform",
                "manylinux_2_17_aarch64",
                "--implementation",
                "cp",
                "--python-version",
                "313",
                "--abi",
                "cp313",
                "msgpack",
            ]
        )
        wheels = sorted(cache_dir.glob("msgpack-*-cp313-*-aarch64*.whl"))
    if not wheels:
        raise RuntimeError("msgpack wheel was not downloaded")

    run(adb + ["push", str(wheels[-1]), "/tmp/msgpack.whl"])
    install_cmd = (
        f"cd {shell_quote(remote)} && ./.venv/bin/python - <<'PY'\n"
        "import pathlib\n"
        "import zipfile\n"
        "site = pathlib.Path('./.venv/lib/python3.13/site-packages')\n"
        "site.mkdir(parents=True, exist_ok=True)\n"
        "with zipfile.ZipFile('/tmp/msgpack.whl') as wheel:\n"
        "    wheel.extractall(site)\n"
        "import msgpack\n"
        "print('msgpack', msgpack.__version__)\n"
        "PY"
    )
    run(adb + ["shell", install_cmd])


def ensure_local_ssh_key(key_path: Path) -> str:
    public_path = Path(str(key_path) + ".pub")
    if not key_path.exists() or not public_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)])
    public_key = public_path.read_text(encoding="utf-8").strip()
    if not public_key.startswith("ssh-ed25519 "):
        raise RuntimeError(f"unexpected SSH public key format: {public_path}")
    return public_key


def enable_network_ssh(adb: list[str], key_path: Path) -> None:
    public_key = ensure_local_ssh_key(key_path)
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
            f.write(public_key + "\n")
            tmp_name = f.name
        run(adb + ["push", tmp_name, "/tmp/unoq_codex_key.pub"])
        install_key = (
            "sh -lc "
            + shell_quote(
                "mkdir -p /home/arduino/.ssh && chmod 700 /home/arduino/.ssh && "
                "touch /home/arduino/.ssh/authorized_keys && chmod 600 /home/arduino/.ssh/authorized_keys && "
                "key=\"$(cat /tmp/unoq_codex_key.pub)\"; "
                "grep -qxF \"$key\" /home/arduino/.ssh/authorized_keys || echo \"$key\" >> /home/arduino/.ssh/authorized_keys; "
                "rm -f /tmp/unoq_codex_key.pub"
            )
        )
        run(adb + ["shell", install_key])
    finally:
        if tmp_name:
            try:
                os.remove(tmp_name)
            except OSError:
                pass

    enable_ssh = privileged_command(
        "chown -R arduino:arduino /home/arduino/.ssh; "
        "if systemctl list-unit-files ssh.service >/dev/null 2>&1; then "
        "systemctl enable --now ssh.service; "
        "elif systemctl list-unit-files sshd.service >/dev/null 2>&1; then "
        "systemctl enable --now sshd.service; "
        "else exit 78; fi"
    )
    if ok(adb + ["shell", enable_ssh]):
        log(f"Network SSH enabled on port 22 with key authentication: {key_path}")
        return

    tools_dir = Path(__file__).resolve().parent
    sshd_config = tools_dir / "unoq_user_sshd_config"
    start_script = tools_dir / "start_unoq_user_sshd.sh"
    run(adb + ["push", str(sshd_config), "/home/arduino/.ssh/sshd_config"])
    run(adb + ["push", str(start_script), "/home/arduino/bin/start_unoq_user_sshd.sh"])
    setup_user_sshd = (
        "chmod 700 /home/arduino/bin/start_unoq_user_sshd.sh; "
        "chmod 600 /home/arduino/.ssh/sshd_config /home/arduino/.ssh/authorized_keys; "
        "test -f /home/arduino/.ssh/ssh_host_ed25519_key || "
        "ssh-keygen -q -t ed25519 -N '' -f /home/arduino/.ssh/ssh_host_ed25519_key; "
        "/usr/sbin/sshd -t -f /home/arduino/.ssh/sshd_config; "
        "nohup /home/arduino/bin/start_unoq_user_sshd.sh >/home/arduino/.ssh/sshd-start.log 2>&1 &"
    )
    run(adb + ["shell", setup_user_sshd])
    cron_cmd = (
        "sh -lc "
        + shell_quote(
            "(crontab -l 2>/dev/null | grep -v '/home/arduino/bin/start_unoq_user_sshd.sh'; "
            "echo '@reboot /home/arduino/bin/start_unoq_user_sshd.sh'; "
            "echo '* * * * * /home/arduino/bin/start_unoq_user_sshd.sh') | crontab -"
        )
    )
    run(adb + ["shell", cron_cmd])
    log(f"User SSH enabled on port 2222 with key authentication: {key_path}")


def install_autostart(
    adb: list[str],
    remote: str,
    firmware_update_token_file: str | None,
    standalone_hv: bool,
    standalone_lv: bool = False,
) -> bool:
    script = autostart_script(remote, firmware_update_token_file, standalone_hv, standalone_lv)
    remote_script = "/home/arduino/bin/start_unoq_hmi.sh"
    run(adb + ["shell", "mkdir -p /home/arduino/bin"])
    run(adb + ["shell", "cat > /tmp/start_unoq_hmi.sh <<'SH'\n" + script + "SH\n"])
    run(adb + ["shell", f"mv /tmp/start_unoq_hmi.sh {remote_script} && chmod 755 {remote_script}"])
    cron_cmd = (
        "sh -lc "
        + shell_quote(
            "(crontab -l 2>/dev/null | grep -v '/home/arduino/bin/start_unoq_hmi.sh'; "
            "echo '@reboot /home/arduino/bin/start_unoq_hmi.sh'; "
            "echo '* * * * * /home/arduino/bin/start_unoq_hmi.sh') | crontab -"
        )
    )
    run(adb + ["shell", cron_cmd])
    service = systemd_service()
    run(adb + ["shell", "cat > /tmp/unoq-hmi.service <<'UNIT'\n" + service + "UNIT\n"])
    install_service = privileged_command(
        "install -m 0644 /tmp/unoq-hmi.service /etc/systemd/system/unoq-hmi.service && "
        "systemctl daemon-reload && systemctl enable unoq-hmi.service"
    )
    installed = ok(adb + ["shell", install_service])
    if installed:
        remove_cron = (
            "sh -lc "
            + shell_quote(
                "crontab -l 2>/dev/null | grep -v '/home/arduino/bin/start_unoq_hmi.sh' | crontab -"
            )
        )
        run(adb + ["shell", remove_cron])
        log("Autostart: systemd service installed; duplicate cron watchdog removed.")
    else:
        log("WARN: systemd install unavailable; using cron fallback only.")
    return installed


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy UNOQ web_hmi to device via ADB.")
    ap.add_argument("--device", default="", help="ADB device id (default: auto-detect)")
    ap.add_argument("--remote", default="/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi")
    ap.add_argument("--restart", action="store_true", help="Restart server after deploy")
    ap.add_argument(
        "--enable-firmware-update",
        action="store_true",
        help="Start HMI with the Wi-Fi firmware update endpoint enabled",
    )
    ap.add_argument(
        "--firmware-update-token",
        default="",
        help="Token to install on the UNO Q for Wi-Fi firmware updates",
    )
    ap.add_argument(
        "--firmware-update-token-local-file",
        default="",
        help="Read the firmware update token from this local file",
    )
    ap.add_argument(
        "--firmware-update-token-file",
        default="/home/arduino/.unoq_firmware_update_token",
        help="Remote token file used by the HMI firmware update endpoint",
    )
    ap.add_argument(
        "--no-autostart",
        action="store_true",
        help="Do not install/update the user crontab HMI watchdog",
    )
    ap.add_argument(
        "--enable-network-ssh",
        action="store_true",
        help="One-time bootstrap of key-authenticated SSH for future Wi-Fi-only deploys",
    )
    ap.add_argument(
        "--ssh-key",
        default=".unoq_ssh/id_ed25519",
        help="Local private key path used by the Wi-Fi deploy tool",
    )
    standalone_group = ap.add_mutually_exclusive_group()
    standalone_group.add_argument(
        "--standalone-hv",
        action="store_true",
        help="Install both Wi-Fi profiles and start fail-closed in HV mode after every restart.",
    )
    standalone_group.add_argument(
        "--standalone-lv",
        action="store_true",
        help="Install both Wi-Fi profiles and start in the HV-disconnected LV test mode.",
    )
    args = ap.parse_args()

    device = args.device or detect_device()
    if not device:
        devices = adb_device_ids()
        if devices:
            log("ERROR: no non-emulator ADB device found. Use --device only if this is intentionally the UNO Q.")
            log("ADB devices: " + ", ".join(devices))
        else:
            log("ERROR: ADB device not found. Use --device.")
        return 2

    local_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web_hmi"))
    if not os.path.isdir(local_root):
        log(f"ERROR: local web_hmi not found: {local_root}")
        return 3

    adb = ["adb", "-s", device]
    run(adb + ["push", os.path.join(local_root, "server.py"), f"{args.remote}/server.py"])
    run(adb + ["push", os.path.join(local_root, "requirements.txt"), f"{args.remote}/requirements.txt"])
    static_dir = os.path.join(local_root, "static")
    for name in ("index.html", "app.js", "style.css"):
        run(adb + ["push", os.path.join(static_dir, name), f"{args.remote}/static/{name}"])

    ensure_msgpack(adb, args.remote, local_root)
    firmware_update_token = args.firmware_update_token.strip()
    if args.firmware_update_token_local_file:
        firmware_update_token = Path(args.firmware_update_token_local_file).read_text(encoding="utf-8").strip()
    firmware_update_enabled = args.enable_firmware_update or bool(firmware_update_token)
    if firmware_update_token:
        tmp_name = ""
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
                f.write(firmware_update_token + "\n")
                tmp_name = f.name
            run(adb + ["push", tmp_name, "/tmp/unoq_firmware_update_token"])
            token_dir = os.path.dirname(args.firmware_update_token_file) or "."
            install_token = (
                "sh -lc "
                + shell_quote(
                    f"mkdir -p {shell_quote(token_dir)} && "
                    f"cp /tmp/unoq_firmware_update_token {shell_quote(args.firmware_update_token_file)} && "
                    f"chmod 600 {shell_quote(args.firmware_update_token_file)} && "
                    "rm -f /tmp/unoq_firmware_update_token"
                )
            )
            run(adb + ["shell", install_token])
        finally:
            if tmp_name:
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

    systemd_installed = False
    if not args.no_autostart:
        systemd_installed = install_autostart(
            adb,
            args.remote,
            args.firmware_update_token_file if firmware_update_enabled else None,
            bool(args.standalone_hv),
            bool(args.standalone_lv),
        )

    if args.restart:
        log("Restarting server...")
        run(adb + ["shell", "mkdir -p " + args.remote + "/logs"])
        if systemd_installed:
            restart_service = privileged_command(
                "systemctl stop unoq-hmi.service || true; "
                "pid=\"$(ss -ltnp 2>/dev/null | sed -n 's/.*:8080 .*pid=\\([0-9]\\+\\).*/\\1/p' | head -n 1)\"; "
                "if [ -n \"$pid\" ]; then kill \"$pid\" || true; fi; "
                "for i in 1 2 3 4 5 6 7 8 9 10; do "
                "ss -ltn 2>/dev/null | grep -q ':8080' || break; sleep 0.2; done; "
                "systemctl start unoq-hmi.service"
            )
            run(adb + ["shell", restart_service])
            wait_for_port = (
                "sh -lc 'for i in $(seq 1 50); do "
                "ss -ltn 2>/dev/null | grep -q \":8080\" && exit 0; sleep 0.2; "
                "done; exit 1'"
            )
            run(adb + ["shell", wait_for_port])
            if args.enable_network_ssh:
                enable_network_ssh(adb, Path(args.ssh_key))
            log("DONE")
            return 0
        extra_args = server_args(
            args.firmware_update_token_file if firmware_update_enabled else None,
            bool(args.standalone_hv),
            bool(args.standalone_lv),
        )
        # Kill by port 8080 first (robust and avoids pkill matching the current shell argv).
        kill_and_start = (
            "sh -lc '"
            "pid=\"$(ss -ltnp 2>/dev/null | sed -n \"s/.*:8080 .*pid=\\([0-9]\\+\\).*/\\1/p\" | head -n 1)\"; "
            "if [ -n \"$pid\" ]; then kill $pid || true; fi; "
            # Wait for the port to be released.
            "for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltnp 2>/dev/null | grep -q \":8080\" || break; sleep 0.2; done; "
            f"cd {args.remote} && nohup ./.venv/bin/python server.py --bind 0.0.0.0 --port 8080 --router /var/run/arduino-router.sock "
            f"{extra_args} "
            "> logs/server.log 2>&1 & "
            # Wait for the new server to bind.
            "for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltnp 2>/dev/null | grep -q \":8080\" && exit 0; sleep 0.2; done; exit 1'"
        )
        run(adb + ["shell", kill_and_start])
    if args.enable_network_ssh:
        enable_network_ssh(adb, Path(args.ssh_key))
    log("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
