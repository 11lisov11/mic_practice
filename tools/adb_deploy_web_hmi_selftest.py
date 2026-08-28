#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def load_module(repo: Path) -> Any:
    path = repo / "tools" / "adb_deploy_web_hmi.py"
    spec = importlib.util.spec_from_file_location("adb_deploy_web_hmi", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    mod = load_module(repo)
    cases: list[dict[str, Any]] = []

    def check(name: str, ok: bool, evidence: Any = None) -> None:
        cases.append({"name": name, "ok": bool(ok), "evidence": evidence})

    low = mod.autostart_script("/home/arduino/app", None, False)
    hv = mod.autostart_script(
        "/home/arduino/app",
        "/home/arduino/update-token",
        True,
        False,
        "/home/arduino/control-token",
    )
    lv = mod.autostart_script("/home/arduino/app", None, False, True)
    service = mod.systemd_service()
    privileged = mod.privileged_command("systemctl restart unoq-hmi.service")

    check("autostart_waits_for_router_socket", "while [ ! -S /var/run/arduino-router.sock ]" in low)
    check("autostart_serializes_cron_watchdogs", "flock -n 9 || exit 0" in low)
    check("autostart_binds_wifi_hmi", "--bind 0.0.0.0 --port 8080" in low)
    check("low_voltage_mode_does_not_enable_standalone_hv", "--standalone-hv" not in low)
    check("standalone_hv_mode_is_explicit", "--standalone-hv" in hv)
    check("standalone_lv_mode_is_explicit", "--standalone-lv" in lv and "--standalone-hv" not in lv)
    check("standalone_lv_runlimit_is_three_seconds", "--start-runlimit-sec 3.0" in lv)
    check("autostart_does_not_exit_when_port_is_owned_by_stale_process", "grep -q ':8080'" not in low)
    check("firmware_token_is_explicit", "--firmware-update-token-file" in hv and "/home/arduino/update-token" in hv)
    check("control_token_is_explicit", "--control-token-file" in hv and "/home/arduino/control-token" in hv)
    check("persistent_log_limit_is_64_mib", "--log-file-bytes 67108864" in hv)
    check("systemd_runs_as_arduino", "User=arduino" in service)
    check("systemd_restarts_hmi", "Restart=always" in service and "RestartSec=2" in service)
    check("systemd_starts_on_boot", "WantedBy=multi-user.target" in service)
    source = (repo / "tools" / "adb_deploy_web_hmi.py").read_text(encoding="utf-8")
    check(
        "systemd_install_removes_duplicate_cron_watchdog",
        "duplicate cron watchdog removed" in source
        and "grep -v '/home/arduino/bin/start_unoq_hmi.sh' | crontab -" in source,
    )
    check("privileged_install_supports_root", '"$(id -u)" = 0' in privileged)
    check("privileged_install_supports_passwordless_sudo", "sudo -n" in privileged)
    user_sshd = (repo / "tools" / "unoq_user_sshd_config").read_text(encoding="utf-8")
    user_sshd_start = (repo / "tools" / "start_unoq_user_sshd.sh").read_text(encoding="utf-8")
    check("user_sshd_uses_unprivileged_port", "Port 2222" in user_sshd)
    check(
        "user_sshd_is_key_only",
        "PasswordAuthentication no" in user_sshd
        and "KbdInteractiveAuthentication no" in user_sshd
        and "AuthorizedKeysFile /home/arduino/.ssh/authorized_keys" in user_sshd,
    )
    check("user_sshd_start_is_idempotent", "grep -q ':2222 '" in user_sshd_start)
    check(
        "adb_bootstrap_falls_back_to_user_sshd",
        "User SSH enabled on port 2222" in source
        and "start_unoq_user_sshd.sh') | crontab -" in source,
    )

    failed = [case for case in cases if not case["ok"]]
    summary = {
        "tool": "adb_deploy_web_hmi_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": cases,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
