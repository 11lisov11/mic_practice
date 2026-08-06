#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from run_metadata import SAFETY_CRITICAL_SOURCE_PATTERNS, collect_run_metadata


PWM_CHANNEL_MAP = [
    {"channel": "CH0", "stm32": "PA8", "signal": "PWM-1H", "expected_static": 0},
    {"channel": "CH1", "stm32": "PB13", "signal": "PWM-1L", "expected_static": 0},
    {"channel": "CH2", "stm32": "PA9", "signal": "PWM-2H", "expected_static": 0},
    {"channel": "CH3", "stm32": "PB14", "signal": "PWM-2L", "expected_static": 0},
    {"channel": "CH4", "stm32": "PA10", "signal": "PWM-3H", "expected_static": 0},
    {"channel": "CH5", "stm32": "PB15", "signal": "PWM-3L", "expected_static": 0},
    {"channel": "CH6", "stm32": "PB12", "signal": "EM_STOP/shutdown", "expected_static": 0},
]


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "fail"
    evidence: Any = None


def check_dicts_by_severity(checks: list[Check], severity: str) -> list[dict[str, Any]]:
    return [check.__dict__ for check in checks if not check.ok and check.severity == severity]


def latest_file(root: Path, pattern: str) -> Path | None:
    files = [p for p in root.glob(pattern) if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def latest_build_only_preflight(root: Path) -> Path | None:
    candidates = sorted(
        (p for p in root.glob("full_system_preflight_*/summary.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        summary = load_json(path)
        if not isinstance(summary, dict):
            continue
        sub = summary.get("summary", {}) if isinstance(summary.get("summary"), dict) else {}
        if sub.get("build_only") is True or summary.get("build_only") is True:
            return path
    return None


def uart_loopback_preflight_command(raw_command: str) -> str:
    def opt(name: str, default: str) -> str:
        match = re.search(rf"(?<!\S){re.escape(name)}(?:=|\s+)([^\s]+)", raw_command)
        return match.group(1) if match else default

    port = opt("--port", "COM3")
    bauds = opt("--bauds", "460800,115200,230400,921600")
    timeout = opt("--timeout", "0.5")
    write_timeout = opt("--write-timeout", "2.0")
    return (
        "py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired "
        f"--port {port} --bauds {bauds} --timeout {timeout} --write-timeout {write_timeout} --hmi-port 18080"
    )


ACTION_PRIORITY = {
    "run_full_build_only_preflight": 10,
    "run_uart_loopback": 20,
    "fix_usb_uart_loopback": 21,
    "reconnect_stm32_uart_and_rerun_protocol": 22,
    "check_stm32_uart_wiring_or_firmware": 23,
    "close_com_port_users": 24,
    "restore_hmi_safe_status": 30,
    "run_runtime_static_preflight": 40,
    "run_static_low_isolation_preflight": 50,
    "refresh_saleae_static_probe": 60,
    "fix_pwm_safe_static_levels": 70,
}


def ordered_next_actions(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        action
        for _, action in sorted(
            enumerate(actions),
            key=lambda pair: (ACTION_PRIORITY.get(str(pair[1].get("id", "")), 500), pair[0]),
        )
    ]


def safety_critical_sources(repo: Path) -> list[Path]:
    out: list[Path] = []
    for pattern in SAFETY_CRITICAL_SOURCE_PATTERNS:
        out.extend(p for p in repo.glob(pattern) if p.is_file())
    return sorted(set(out))


def stale_sources(reference: Path | None, sources: list[Path], max_count: int = 20) -> list[str]:
    if reference is None or not reference.exists():
        return []
    ref_mtime = reference.stat().st_mtime
    stale = [p for p in sources if p.exists() and p.stat().st_mtime > ref_mtime + 0.001]
    stale = sorted(stale, key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p) for p in stale[:max_count]]


def latest_saleae_probe(root: Path, required_channels: set[int]) -> Path | None:
    candidates = sorted(
        (p for p in root.rglob("saleae_highlevel_probe_*/summary.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    fallback = candidates[0] if candidates else None
    for path in candidates:
        summary = load_json(path)
        if not isinstance(summary, dict):
            continue
        if summary.get("command_pass") is False:
            continue
        channels = summary.get("channels", [])
        have_channels = {int(ch) for ch in channels if isinstance(ch, int) or str(ch).isdigit()}
        if required_channels.issubset(have_channels):
            return path
    return fallback


def latest_runtime_static_preflight(root: Path) -> Path | None:
    candidates = sorted(
        (p for p in root.glob("bluepill_runtime_static_preflight_*/summary.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def latest_static_low_preflight(root: Path) -> Path | None:
    candidates = sorted(
        (p for p in root.glob("bluepill_static_low_preflight_*/summary.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def latest_uart_diagnose(root: Path, loopback_mode: bool) -> Path | None:
    candidates = sorted(
        (p for p in root.glob("bluepill_uart_diagnose_*/summary.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        summary = load_json(path)
        if isinstance(summary, dict) and summary.get("inventory_only") is True:
            continue
        if isinstance(summary, dict) and bool(summary.get("loopback_mode")) == loopback_mode:
            return path
    return None


def latest_uart_inventory_only(root: Path) -> Path | None:
    candidates = sorted(
        (p for p in root.glob("bluepill_uart_diagnose_*/summary.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        summary = load_json(path)
        if isinstance(summary, dict) and summary.get("inventory_only") is True:
            return path
    return None


def load_json(path: Path | None) -> Any:
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_load_error": f"{type(exc).__name__}: {exc}", "_path": str(path)}


def source_fingerprint_digest(summary: dict[str, Any] | None) -> str | None:
    if not isinstance(summary, dict):
        return None
    fp = summary.get("source_fingerprint")
    if not isinstance(fp, dict):
        return None
    digest = fp.get("sha256")
    return str(digest) if digest else None


def http_status(url: str, timeout_s: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/status", timeout=timeout_s) as resp:
            return {
                "ok": True,
                "http_status": resp.status,
                "data": json.loads(resp.read().decode("utf-8", "replace")),
            }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def digital_static_levels(csv_path: Path, channels: list[int]) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"ok": False, "error": "csv not found", "csv": str(csv_path)}
    with csv_path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        rows = list(reader)
    if not rows:
        return {"ok": False, "error": "no rows", "csv": str(csv_path)}
    first = rows[0]
    last = rows[-1]
    out: dict[str, Any] = {"ok": True, "csv": str(csv_path), "channels": {}}
    for ch in channels:
        col_name = f"Channel {ch}"
        try:
            idx = header.index(col_name)
        except ValueError:
            out["channels"][str(ch)] = {"present": False}
            continue
        out["channels"][str(ch)] = {
            "present": True,
            "initial": int(first[idx]) if idx < len(first) and first[idx] in {"0", "1"} else None,
            "final": int(last[idx]) if idx < len(last) and last[idx] in {"0", "1"} else None,
        }
    return out


def static_levels_from_probe(probe: dict[str, Any], channels: list[int]) -> dict[str, Any]:
    levels = probe.get("levels")
    if isinstance(levels, dict) and levels:
        out: dict[str, Any] = {"ok": True, "csv": probe.get("csv"), "channels": {}}
        for ch in channels:
            rec = levels.get(str(ch), {})
            if isinstance(rec, dict):
                out["channels"][str(ch)] = {
                    "present": True,
                    "initial": rec.get("initial"),
                    "final": rec.get("final"),
                }
            else:
                out["channels"][str(ch)] = {"present": False}
        return out
    return digital_static_levels(Path(str(probe.get("csv", ""))), channels)


def classify_pwm_static_levels(levels: dict[str, Any]) -> str:
    channels = levels.get("channels", {}) if isinstance(levels, dict) else {}
    vals = {
        ch: (
            channels.get(str(ch), {}).get("initial"),
            channels.get(str(ch), {}).get("final"),
        )
        for ch in range(6)
    }
    if all(v == (0, 0) for v in vals.values()):
        return "all_pwm_low_safe"
    if all(v == (1, 1) for v in vals.values()):
        return "all_pwm_high"
    if all(vals[ch] == (0, 0) for ch in (0, 2, 4)) and all(vals[ch] == (1, 1) for ch in (1, 3, 5)):
        return "low_side_static_high"
    if all(vals[ch] == (1, 1) for ch in (0, 2, 4)) and all(vals[ch] == (0, 0) for ch in (1, 3, 5)):
        return "high_side_static_high"
    if any(initial != final for initial, final in vals.values()):
        return "static_capture_has_level_change"
    return "mixed_static_levels"


def pwm_static_remediation(pattern: str) -> dict[str, Any]:
    base_steps = [
        "Keep HV/J7 disconnected, DC bus discharged, and EM_STOP/shutdown asserted while diagnosing static PWM levels.",
        "Confirm Saleae GND is tied to STM32 logic GND and CH0..CH6 are clipped at the STM32/IPM logic input side, not at phase outputs.",
        "Use PWM_STATIC_BLOCKER_RU.md for the step-by-step low-side/high-side static-level isolation checklist.",
        "Run the runtime static preflight so the latest bluepill_uart_pwm firmware is uploaded before the next static capture.",
        "If the latest runtime static preflight still leaves any PWM input HIGH, run bluepill_static_low_preflight.py to isolate firmware/TIM1 from wiring/IPM input bias.",
    ]
    if pattern == "low_side_static_high":
        interpretation = "Complementary low-side inputs CH1/CH3/CH5 are HIGH while high-side inputs CH0/CH2/CH4 are LOW."
        measurement_points = [
            "Measure PB13/PB14/PB15 directly on the Blue Pill pins while the bench is in SAFE/static.",
            "Measure the corresponding IPM logic input pins after the Blue Pill-to-IPM wiring or carrier connector.",
            "Compare both readings with Saleae CH1/CH3/CH5 using the same STM32 logic GND reference.",
        ]
        extra = [
            "Check PB13/PB14/PB15 wiring and Saleae channel order first; this exact pattern can be a TIM1 complementary-output init glitch or an IPM/input pull-up/reference issue.",
            "If the pattern remains after runtime upload, measure directly on PB13/PB14/PB15 at the Blue Pill pins and then at the IPM input pins to separate firmware/GPIO from carrier wiring.",
        ]
    elif pattern == "high_side_static_high":
        interpretation = "High-side inputs CH0/CH2/CH4 are HIGH while low-side inputs CH1/CH3/CH5 are LOW."
        measurement_points = [
            "Measure PA8/PA9/PA10 directly on the Blue Pill pins while the bench is in SAFE/static.",
            "Measure the corresponding IPM logic input pins after the Blue Pill-to-IPM wiring or carrier connector.",
            "Compare both readings with Saleae CH0/CH2/CH4 using the same STM32 logic GND reference.",
        ]
        extra = [
            "Check PA8/PA9/PA10 wiring and confirm no external pull-up or wrong probe reference is forcing the high-side inputs.",
        ]
    elif pattern == "all_pwm_high":
        interpretation = "All six PWM inputs are HIGH in a state that should be fully disabled."
        measurement_points = [
            "Measure PA8/PA9/PA10/PB13/PB14/PB15 directly on the Blue Pill pins.",
            "Measure the same six signals at the IPM logic input pins.",
            "Confirm Saleae GND is tied to STM32 logic GND, not to a floating or HV reference.",
        ]
        extra = [
            "Check common ground/reference and IPM input biasing before suspecting the PWM algorithm.",
        ]
    elif pattern == "static_capture_has_level_change":
        interpretation = "At least one PWM input changed during the static capture; the bench is not in a stable SAFE state."
        measurement_points = [
            "Repeat static capture after reset/upload has settled and no HMI START command is pending.",
            "If changes remain, scope the changing channel at the STM32 pin and at the IPM input pin.",
        ]
        extra = [
            "Repeat the capture after forcing STOP/ESTOP and after any reset/upload has settled.",
        ]
    else:
        interpretation = "PWM inputs are not all LOW in SAFE/static state."
        measurement_points = [
            "Compare Saleae CH0..CH5 against PA8/PB13/PA9/PB14/PA10/PB15 at the STM32 pins.",
            "Then compare the same signals at the IPM logic input pins.",
        ]
        extra = [
            "Compare observed levels against the channel map and isolate whether the wrong channel, wrong node, or wrong firmware is being measured.",
        ]
    return {
        "pattern": pattern,
        "interpretation": interpretation,
        "measurement_points": measurement_points,
        "channel_map": PWM_CHANNEL_MAP,
        "required_command": "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
        "static_low_isolation_command": "py -3 -u .\\tools\\bluepill_static_low_preflight.py --confirm-hv-off",
        "steps": base_steps + extra,
    }


def check_full_preflight(summary_path: Path | None, summary: dict[str, Any] | None, newer_sources: list[str] | None = None) -> list[Check]:
    if summary_path is None or not isinstance(summary, dict):
        return [Check("latest_build_only_preflight_present", False, "no full_system_preflight summary found")]
    sub = summary.get("summary", {})
    build_only_pass = bool(sub.get("build_only_pass") or summary.get("build_only_pass"))
    newer_sources = newer_sources or []
    return [
        Check("latest_build_only_preflight_present", True, evidence=str(summary_path)),
        Check("latest_build_only_preflight_pass", build_only_pass, evidence={"summary": str(summary_path), "build_only_pass": build_only_pass}),
        Check(
            "latest_build_only_preflight_fresh",
            not newer_sources,
            "safety-critical sources changed after latest build-only preflight" if newer_sources else "",
            evidence={"summary": str(summary_path), "newer_sources": newer_sources},
        ),
    ]


def check_runtime_static_preflight(
    runtime_path: Path | None,
    runtime_summary: dict[str, Any] | None,
    build_path: Path | None,
    build_summary: dict[str, Any] | None = None,
) -> list[Check]:
    if runtime_path is None or not isinstance(runtime_summary, dict):
        return [
            Check(
                "latest_runtime_static_preflight_present",
                False,
                "no bluepill_runtime_static_preflight summary found",
            )
        ]

    dry_run = bool(runtime_summary.get("dry_run"))
    runtime_pass = bool(runtime_summary.get("pass")) and not dry_run
    runtime_digest = source_fingerprint_digest(runtime_summary)
    build_digest = source_fingerprint_digest(build_summary)
    fingerprint_known = bool(runtime_digest and build_digest)
    fingerprint_match = bool(fingerprint_known and runtime_digest == build_digest)
    mtime_fresh = bool(build_path is not None and build_path.exists() and runtime_path.stat().st_mtime >= build_path.stat().st_mtime)
    fresh_for_build = bool(not dry_run and (fingerprint_match if fingerprint_known else mtime_fresh))
    pass_detail = "latest runtime firmware uploaded and SAFE/static levels checked"
    if dry_run:
        pass_detail = "latest runtime static preflight is dry-run only; real upload and Saleae capture are still required"
    elif not runtime_pass:
        pass_detail = "runtime static preflight did not pass"
    fresh_detail = ""
    if not fresh_for_build:
        if dry_run:
            fresh_detail = "latest runtime static preflight is dry-run only; real upload and Saleae capture are still required"
        elif fingerprint_known and not fingerprint_match:
            fresh_detail = "runtime static preflight source fingerprint differs from latest build-only preflight"
        else:
            fresh_detail = "runtime static preflight is older than the latest build-only preflight"
    checks = [
        Check("latest_runtime_static_preflight_present", True, evidence=str(runtime_path)),
        Check(
            "latest_runtime_static_preflight_pass",
            runtime_pass,
            detail=pass_detail,
            evidence={
                "summary": str(runtime_path),
                "pass": runtime_summary.get("pass"),
                "dry_run": dry_run,
                "error": runtime_summary.get("error"),
                "static_checks": runtime_summary.get("static_checks"),
            },
        ),
        Check(
            "runtime_static_preflight_fresh_for_build",
            fresh_for_build,
            detail=fresh_detail,
            evidence={
                "runtime_static_preflight": str(runtime_path),
                "full_system_preflight": str(build_path) if build_path else None,
                "runtime_source_fingerprint": runtime_digest,
                "build_source_fingerprint": build_digest,
                "source_fingerprint_match": fingerprint_match,
                "mtime_fresh": mtime_fresh,
            },
        ),
    ]
    static_checks = runtime_summary.get("static_checks", {})
    if isinstance(static_checks, dict):
        checks.append(
            Check(
                "runtime_static_pwm_lines_low",
                bool(static_checks.get("pwm_lines_low")),
                detail=f"runtime static preflight pattern={static_checks.get('pattern')}",
                evidence={"summary": str(runtime_path), "static_checks": static_checks},
            )
        )
    return checks


def check_static_low_preflight(
    static_low_path: Path | None,
    static_low_summary: dict[str, Any] | None,
    build_path: Path | None,
    build_summary: dict[str, Any] | None = None,
    *,
    required: bool = False,
) -> list[Check]:
    if not required:
        return []
    if static_low_path is None or not isinstance(static_low_summary, dict):
        return [
            Check(
                "latest_static_low_preflight_present",
                False,
                "no bluepill_static_low_preflight summary found for the current PWM-static blocker",
            )
        ]

    dry_run = bool(static_low_summary.get("dry_run"))
    restored = static_low_summary.get("restored") is True
    static_low_pass = bool(static_low_summary.get("pass")) and not dry_run and restored
    static_low_digest = source_fingerprint_digest(static_low_summary)
    build_digest = source_fingerprint_digest(build_summary)
    fingerprint_known = bool(static_low_digest and build_digest)
    fingerprint_match = bool(fingerprint_known and static_low_digest == build_digest)
    mtime_fresh = bool(build_path is not None and build_path.exists() and static_low_path.stat().st_mtime >= build_path.stat().st_mtime)
    fresh_for_build = bool(not dry_run and (fingerprint_match if fingerprint_known else mtime_fresh))
    static_checks = static_low_summary.get("static_checks", {}) if isinstance(static_low_summary.get("static_checks"), dict) else {}
    conclusion = static_low_summary.get("diagnostic_conclusion", {}) if isinstance(static_low_summary.get("diagnostic_conclusion"), dict) else {}

    pass_detail = "static-low diagnostic proved all PWM logic inputs can be held LOW"
    if dry_run:
        pass_detail = "static-low preflight is dry-run only; real diagnostic upload and Saleae capture are still required"
    elif not restored:
        pass_detail = "static-low preflight did not restore runtime firmware"
    elif not static_low_pass:
        pass_detail = f"static-low diagnostic failed: pattern={static_checks.get('pattern')}"

    fresh_detail = ""
    if not fresh_for_build:
        if dry_run:
            fresh_detail = "static-low preflight is dry-run only; real upload and Saleae capture are still required"
        elif fingerprint_known and not fingerprint_match:
            fresh_detail = "static-low preflight source fingerprint differs from latest build-only preflight"
        else:
            fresh_detail = "static-low preflight is older than the latest build-only preflight"

    return [
        Check("latest_static_low_preflight_present", True, evidence=str(static_low_path)),
        Check(
            "latest_static_low_preflight_pass",
            static_low_pass,
            detail=pass_detail,
            evidence={
                "summary": str(static_low_path),
                "pass": static_low_summary.get("pass"),
                "dry_run": dry_run,
                "restored": restored,
                "error": static_low_summary.get("error"),
                "static_checks": static_checks,
                "diagnostic_conclusion": conclusion,
            },
        ),
        Check(
            "static_low_preflight_fresh_for_build",
            fresh_for_build,
            detail=fresh_detail,
            evidence={
                "static_low_preflight": str(static_low_path),
                "full_system_preflight": str(build_path) if build_path else None,
                "static_low_source_fingerprint": static_low_digest,
                "build_source_fingerprint": build_digest,
                "source_fingerprint_match": fingerprint_match,
                "mtime_fresh": mtime_fresh,
            },
        ),
        Check(
            "static_low_runtime_restored",
            restored,
            detail="static-low diagnostic must restore runtime firmware before any later runtime test" if not restored else "",
            evidence={"summary": str(static_low_path), "restored": restored},
        ),
        Check(
            "static_low_diagnostic_conclusion_present",
            bool(conclusion.get("result")),
            detail="static-low preflight summary does not include diagnostic_conclusion" if not conclusion.get("result") else str(conclusion.get("meaning", "")),
            evidence={"summary": str(static_low_path), "diagnostic_conclusion": conclusion},
        ),
    ]


def check_uart(
    protocol_path: Path | None,
    protocol_summary: dict[str, Any] | None,
    loopback_path: Path | None,
    loopback_summary: dict[str, Any] | None,
    loopback_fresh: bool,
    inventory_path: Path | None = None,
    inventory_summary: dict[str, Any] | None = None,
    live_status: dict[str, Any] | None = None,
) -> list[Check]:
    checks: list[Check] = []
    live_transport_ok, live_transport_evidence = live_bluepill_transport_proof(live_status)
    if protocol_path is None or not isinstance(protocol_summary, dict):
        checks.append(
            Check(
                "latest_uart_protocol_diagnose_present",
                live_transport_ok,
                "live UNO Q/HMI transport proves the Blue Pill protocol" if live_transport_ok else "no non-loopback bluepill_uart_diagnose summary found",
                evidence=live_transport_evidence if live_transport_ok else None,
            )
        )
        if live_transport_ok:
            checks.append(
                Check(
                    "stm32_uart_protocol_pass",
                    True,
                    detail="fresh valid Blue Pill replies received through UNO Q/HMI",
                    evidence=live_transport_evidence,
                )
            )
    else:
        protocol_pass = bool(protocol_summary.get("protocol_pass")) or live_transport_ok
        next_ids = [a.get("id") for a in protocol_summary.get("next_actions", []) if isinstance(a, dict)]
        checks.extend(
            [
                Check("latest_uart_protocol_diagnose_present", True, evidence=str(protocol_path)),
                Check(
                    "stm32_uart_protocol_pass",
                    protocol_pass,
                    detail=(
                        "fresh valid Blue Pill replies received through UNO Q/HMI"
                        if live_transport_ok and not bool(protocol_summary.get("protocol_pass"))
                        else ("protocol did not pass" if not protocol_pass else "MODE_OFF+CLEAR_FAULT reply received")
                    ),
                    evidence={
                        "summary": str(protocol_path),
                        "next_actions": next_ids,
                        "selected_port": protocol_summary.get("selected_port"),
                        "selected_port_summary": protocol_summary.get("selected_port_summary"),
                        "visible_ports_summary": protocol_summary.get("visible_ports_summary") or protocol_summary.get("visible_ports"),
                        "dtr_rts_matrix": protocol_summary.get("dtr_rts_matrix"),
                        "attempt_counts": protocol_summary.get("attempt_counts"),
                        "attempt_error_digest": protocol_summary.get("attempt_error_digest"),
                        "pc_direct_hmi": protocol_summary.get("pc_direct_hmi"),
                        "port_inventory": protocol_summary.get("port_inventory"),
                        "latest_inventory_only_summary": str(inventory_path) if inventory_path else None,
                        "latest_inventory_only_selected_port": inventory_summary.get("selected_port") if isinstance(inventory_summary, dict) else None,
                        "latest_inventory_only_visible_ports": (
                            inventory_summary.get("visible_ports_summary") or inventory_summary.get("visible_ports")
                            if isinstance(inventory_summary, dict)
                            else None
                        ),
                        "latest_inventory_only_pc_direct_hmi": (
                            inventory_summary.get("pc_direct_hmi") if isinstance(inventory_summary, dict) else None
                        ),
                        "live_transport": live_transport_evidence if live_transport_ok else None,
                    },
                ),
            ]
        )

    if loopback_path is not None and isinstance(loopback_summary, dict):
        checks.append(
            Check(
                "latest_usb_uart_loopback_recorded",
                True,
                severity="warn",
                evidence={"summary": str(loopback_path), "loopback_pass": loopback_summary.get("loopback_pass")},
            )
        )
        checks.append(
            Check(
                "usb_uart_loopback_fresh_for_latest_protocol",
                loopback_fresh,
                "loopback summary is older than the latest protocol diagnosis" if not loopback_fresh else "",
                severity="warn",
                evidence={
                    "loopback_summary": str(loopback_path),
                    "protocol_summary": str(protocol_path) if protocol_path else None,
                },
            )
        )
    elif protocol_summary and any(a.get("id") == "run_loopback" for a in protocol_summary.get("next_actions", []) if isinstance(a, dict)):
        checks.append(
            Check(
                "usb_uart_loopback_evidence_present",
                False,
                "protocol diagnosis requested loopback, but no loopback summary exists yet",
                severity="warn",
            )
        )
    return checks


def live_bluepill_transport_proof(status: dict[str, Any] | None) -> tuple[bool, dict[str, Any]]:
    if not isinstance(status, dict) or not status.get("ok"):
        return False, {"reason": "live status unavailable"}
    data = (status.get("data") or {}).get("data") or status.get("data") or {}

    def as_int(key: str, default: int) -> int:
        try:
            return int(data.get(key, default))
        except Exception:
            return default

    ages = [as_int(key, 999999) for key in ("bp_rsp_age_ms", "bp_age_ms") if key in data]
    age_ms = min(ages) if ages else 999999
    status_flags = as_int("bp_status", 0)
    good_values = [as_int(key, 0) for key in ("bp_good_cnt", "bp_good") if key in data]
    good = max(good_values) if good_values else 0
    bad_values = [as_int(key, 999999) for key in ("bp_bad_cnt", "bp_bad") if key in data]
    bad = max(bad_values) if bad_values else 999999
    explicit_link = data.get("link")
    link_ok = bool(explicit_link) if explicit_link is not None else bool(status_flags & 0x01)
    proven = link_ok and age_ms <= 500 and good > 0 and bad == 0
    return proven, {
        "source": "live_hmi_bluepill_status",
        "link_ok": link_ok,
        "bp_status": status_flags,
        "bp_age_ms": age_ms,
        "bp_good": good,
        "bp_bad": bad,
    }


def uart_next_actions(protocol_summary: dict[str, Any] | None, loopback_summary: dict[str, Any] | None) -> list[dict[str, str]]:
    if isinstance(protocol_summary, dict) and bool(protocol_summary.get("protocol_pass")):
        return []

    protocol_next_ids = []
    protocol_next_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(protocol_summary, dict):
        for action in protocol_summary.get("next_actions", []):
            if isinstance(action, dict):
                action_id = str(action.get("id", ""))
                protocol_next_ids.append(action_id)
                protocol_next_by_id[action_id] = action

    loopback_known = isinstance(loopback_summary, dict)
    loopback_pass = bool(loopback_summary.get("loopback_pass")) if loopback_known else False
    loopback_confirm_missing = False
    raw_loopback_command = str(protocol_next_by_id.get("run_loopback", {}).get("command", "py -3 -u .\\tools\\uart_loopback_preflight.py --confirm-loopback-wired --port COM3 --bauds 460800,115200,230400,921600 --timeout 0.5 --write-timeout 2.0 --hmi-port 18080"))
    run_loopback_command = uart_loopback_preflight_command(raw_loopback_command)
    rerun_protocol_command = str(protocol_next_by_id.get("write_ok_no_bluepill_response", {}).get("command", "py -3 -u .\\tools\\bluepill_uart_diagnose.py --port COM3 --dtr-rts-matrix"))
    if isinstance(loopback_summary, dict):
        loopback_next_by_id = {
            str(action.get("id", "")): action
            for action in loopback_summary.get("next_actions", [])
            if isinstance(action, dict)
        }
        loopback_confirm_missing = bool(
            loopback_summary.get("loopback_confirm_required_missing")
            or "confirm_loopback_wiring" in loopback_next_by_id
        )
        rerun_protocol_command = str(loopback_next_by_id.get("adapter_loopback_ok", {}).get("command", rerun_protocol_command))

    if "host_cannot_write_uart" in protocol_next_ids or "run_loopback" in protocol_next_ids:
        host_detail = str(protocol_next_by_id.get("host_cannot_write_uart", {}).get("detail", "")).strip()
        loopback_detail = (
            "Disconnect USB-UART TX/RX from STM32, short adapter TX to RX on the isolated side, "
            "then run uart_loopback_preflight.py. The wrapper stops PC-direct HMI, runs bluepill_uart_diagnose.py --loopback, "
            "and starts PC-direct HMI again. "
            "Full step-by-step runbook: UART_LOOPBACK_STEPS_RU.md. "
            "Do not run unoq_web_server on that COM port until loopback is complete and STM32 TX/RX is reconnected."
        )
        if host_detail:
            loopback_detail = f"{host_detail} Next: {loopback_detail}"
        if not loopback_known:
            return [
                {
                    "id": "run_uart_loopback",
                    "detail": loopback_detail,
                    "command": run_loopback_command,
                }
            ]
        if not loopback_pass:
            if bool(loopback_summary.get("blocked")) or loopback_confirm_missing:
                return [
                    {
                        "id": "run_uart_loopback",
                        "detail": (
                            "Last loopback diagnostic was blocked before opening the COM port because physical TX/RX "
                            "loopback wiring was not confirmed. "
                            f"{loopback_detail}"
                        ),
                        "command": run_loopback_command,
                    }
                ]
            return [
                {
                    "id": "fix_usb_uart_loopback",
                    "detail": "Adapter loopback failed. Fix USB-UART/isolator power, cable, driver, or TX/RX loopback before reconnecting STM32.",
                }
            ]
        return [
                {
                    "id": "reconnect_stm32_uart_and_rerun_protocol",
                    "detail": "Adapter loopback passed. Remove the TX-RX loopback, reconnect TX/RX cross to STM32 with common isolated GND, close any HMI process holding the COM port, then run bluepill_uart_diagnose.py without --loopback.",
                    "command": rerun_protocol_command,
                }
            ]

    if "write_ok_no_bluepill_response" in protocol_next_ids:
        return [
                {
                    "id": "check_stm32_uart_wiring_or_firmware",
                    "detail": "PC can write, but STM32 does not answer. Check TX/RX cross, isolated GND, USART2 PA2/PA3, STM32 power, and uploaded UART firmware.",
                    "command": rerun_protocol_command,
                }
            ]

    if "port_open_error" in protocol_next_ids:
        return [
            {
                "id": "close_com_port_users",
                "detail": "COM port could not be opened cleanly. Close HMI/serial monitors or replug the adapter.",
            }
        ]

    return [
        {
            "id": "inspect_uart_diagnose_summary",
            "detail": "UART protocol is not proven. Inspect latest bluepill_uart_diagnose summary before active PWM.",
        }
    ]


def check_saleae(
    probe_path: Path | None,
    probe: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    build_path: Path | None = None,
) -> list[Check]:
    if probe_path is None or not isinstance(probe, dict):
        return [Check("latest_saleae_static_probe_present", False, "no saleae_highlevel_probe summary found")]
    check_fresh_for_build = bool(build_path is not None and build_path.exists())
    fresh_for_build = bool(check_fresh_for_build and probe_path.stat().st_mtime >= build_path.stat().st_mtime)
    channels = probe.get("channels", [])
    required_channels = set(range(7))
    have_channels = set(int(ch) for ch in channels if isinstance(ch, int) or str(ch).isdigit())
    edges = probe.get("edges", {})
    all_static = all(int(edges.get(str(ch), -1)) == 0 for ch in required_channels)
    commands = probe.get("commands", [])
    command_pass = probe.get("command_pass")
    command_ok = command_pass is not False
    checks = [
        Check("latest_saleae_static_probe_present", True, evidence=str(probe_path)),
        Check(
            "saleae_probe_commands_passed",
            command_ok,
            detail="saleae_highlevel_probe command failed; do not use this capture as SAFE/static evidence" if not command_ok else "",
            evidence={"summary": str(probe_path), "command_pass": command_pass, "commands": commands},
        ),
        Check("saleae_channels_0_6_present", required_channels.issubset(have_channels), evidence={"channels": channels}),
        Check("saleae_static_no_edges", all_static, evidence={"summary": str(probe_path), "edges": edges}),
    ]
    if check_fresh_for_build:
        checks.insert(
            1,
            Check(
                "saleae_static_probe_fresh_for_build",
                fresh_for_build,
                detail="Saleae static capture is older than the latest build-only preflight" if not fresh_for_build else "",
                evidence={
                    "saleae_summary": str(probe_path),
                    "full_system_preflight": str(build_path),
                },
            ),
        )
    probe_static_checks = probe.get("pwm_static_checks")
    if isinstance(probe_static_checks, dict):
        checks.append(
            Check(
                "saleae_probe_pwm_static_safe_flag",
                bool(probe_static_checks.get("pwm_static_safe_pass")),
                detail=f"saleae_highlevel_probe static flag pattern={probe_static_checks.get('pattern')}",
                evidence={"summary": str(probe_path), "pwm_static_checks": probe_static_checks},
            )
        )
    strict_static_requested = probe.get("require_static_safe") is True or probe.get("require_static_safe_pass") is not None
    if strict_static_requested:
        strict_ok = probe.get("require_static_safe_pass") is True and int(probe.get("exit_code", 1)) == 0
        checks.append(
            Check(
                "saleae_strict_static_safe_exit",
                strict_ok,
                detail=(
                    f"strict Saleae static-safe failed: exit_code={probe.get('exit_code')} "
                    f"pattern={(probe_static_checks or {}).get('pattern') if isinstance(probe_static_checks, dict) else None}"
                ),
                evidence={
                    "summary": str(probe_path),
                    "require_static_safe": probe.get("require_static_safe"),
                    "require_static_safe_pass": probe.get("require_static_safe_pass"),
                    "exit_code": probe.get("exit_code"),
                    "exit_reason": probe.get("exit_reason"),
                    "pwm_static_checks": probe_static_checks if isinstance(probe_static_checks, dict) else None,
                },
            )
        )
    levels = static_levels_from_probe(probe, list(range(7)))
    level_channels = levels.get("channels", {}) if isinstance(levels, dict) else {}
    pwm_level_evidence = {str(ch): level_channels.get(str(ch), {}) for ch in range(6)}
    pwm_static_pattern = classify_pwm_static_levels(levels)
    pwm_lines_low = bool(levels.get("ok")) and all(
        pwm_level_evidence[str(ch)].get("initial") == 0 and pwm_level_evidence[str(ch)].get("final") == 0
        for ch in range(6)
    )
    checks.append(
        Check(
            "saleae_static_pwm_lines_low",
            pwm_lines_low,
            detail=f"PWM inputs CH0..CH5 must be LOW in SAFE/static state; pattern={pwm_static_pattern}",
            evidence={
                "csv": levels.get("csv"),
                "levels": pwm_level_evidence,
                "pattern": pwm_static_pattern,
                "channel_map": PWM_CHANNEL_MAP,
                "remediation": pwm_static_remediation(pwm_static_pattern),
            },
        )
    )
    if isinstance(analysis, dict):
        selected_rate = probe.get("selected_rate")
        requested_rate = probe.get("requested_rate")
        try:
            selected_rate_i = int(selected_rate)
            requested_rate_i = int(requested_rate)
        except Exception:
            selected_rate_i = 0
            requested_rate_i = 0
        if selected_rate_i > 0 and requested_rate_i > 0:
            checks.append(
                Check(
                    "saleae_static_sample_rate_meets_requested",
                    selected_rate_i >= requested_rate_i,
                    detail=(
                        f"Saleae selected {selected_rate_i} Hz while {requested_rate_i} Hz was requested; "
                        "static SAFE levels are still usable, but this capture must not be treated as deadtime proof"
                    ),
                    severity="warn",
                    evidence={
                        "summary": str(probe_path),
                        "selected_rate": selected_rate_i,
                        "requested_rate": requested_rate_i,
                        "selected_sample_period_ns": probe.get("selected_sample_period_ns"),
                    },
                )
            )
        checks.append(
            Check(
                "saleae_static_no_pair_overlap",
                bool(analysis.get("no_overlap_pass")),
                evidence={"analysis": str(probe_path.parent / "pwm_analysis.json"), "no_overlap_pass": analysis.get("no_overlap_pass")},
            )
        )
        ch6 = level_channels.get("6", {}) if isinstance(level_channels, dict) else {}
        checks.append(
            Check(
                "saleae_em_stop_shutdown_asserted",
                ch6.get("initial") == 0 and ch6.get("final") == 0,
                detail="active-low EM_STOP should be 0 while static/safe",
                evidence=ch6,
            )
        )
    else:
        checks.append(Check("saleae_static_no_pair_overlap", False, "pwm_analysis.json missing", evidence=str(probe_path.parent)))
    return checks


def check_live_status(status: dict[str, Any]) -> list[Check]:
    if not status.get("ok"):
        return [Check("live_hmi_status_available", False, status.get("error", ""))]
    data = (status.get("data") or {}).get("data") or status.get("data") or {}

    def as_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def as_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            norm = value.strip().lower()
            if norm in {"1", "true", "yes", "on"}:
                return True
            if norm in {"0", "false", "no", "off"}:
                return False
        return default

    pwm = as_int(data.get("pwm"), 999)
    enable = as_bool(data.get("enable", data.get("pwm", True)), True)
    state = str(data.get("state", ""))
    estop = as_int(data.get("estop"), 999)
    fault = as_int(data.get("bp_fault", data.get("fault")), 255)
    bp_bad_values = [as_int(data.get(key), 999) for key in ("bp_bad_cnt", "bp_bad") if key in data]
    bp_bad = max(bp_bad_values) if bp_bad_values else 999
    live_link_ok, live_link_evidence = live_bluepill_transport_proof(status)
    evidence = {
        "state": state,
        "link": live_link_ok,
        "link_evidence": live_link_evidence,
        "pwm": pwm,
        "enable": enable,
        "estop": estop,
        "bp_fault": fault,
        "bp_bad": bp_bad,
        "miss_count": as_int(data.get("miss_count"), 0),
        "uart_port": data.get("uart_port"),
        "uart_open": as_bool(data.get("uart_open"), False),
        "uart_last_error": data.get("uart_last_error"),
        "uart_error_count": as_int(data.get("uart_error_count"), 0),
    }
    return [
        Check("live_hmi_status_available", True, evidence=evidence),
        Check(
            "live_hmi_safe_state",
            state == "SAFE",
            detail=f"state={state}",
            evidence=evidence,
        ),
        Check(
            "live_hmi_not_running_pwm",
            pwm == 0 and not enable,
            detail="HMI must not show enabled PWM before UART/HIL is proven",
            evidence=evidence,
        ),
        Check(
            "live_hmi_estop_clear",
            estop == 0,
            detail=f"estop={estop}",
            evidence=evidence,
        ),
        Check(
            "live_hmi_bluepill_fault_clear",
            fault == 0,
            detail=f"bp_fault={fault}",
            evidence=evidence,
        ),
        Check(
            "live_hmi_bluepill_bad_count_clear",
            bp_bad == 0,
            detail=f"bp_bad={bp_bad}",
            evidence=evidence,
        ),
    ]


def check_failed(checks: list[Check], names: set[str]) -> bool:
    return any(c.name in names and not c.ok for c in checks)


def command_arg(command: str, name: str, default: str = "") -> str:
    parts = command.split()
    for idx, part in enumerate(parts[:-1]):
        if part == name:
            return parts[idx + 1]
    return default


def operator_action_detail_ru(action: dict[str, Any]) -> str:
    action_id = str(action.get("id", ""))
    command = str(action.get("command", "")).strip()
    port = command_arg(command, "--port", "указанный COM-порт")
    pattern = ""
    raw_detail = str(action.get("detail", ""))
    if "pattern=" in raw_detail:
        pattern = raw_detail.split("pattern=", 1)[1].split(")", 1)[0].split(".", 1)[0].strip()

    if action_id == "run_full_build_only_preflight":
        return (
            "После последнего build-only preflight изменились safety-critical файлы. "
            "Сначала заново запусти build-only проверку, затем снова сформируй bench-gate отчет."
        )
    if action_id == "run_runtime_static_preflight":
        return (
            "Отключи HV/J7, дождись разряда DC-шины и только потом запускай команду ниже. "
            "Проверка прошьет актуальную runtime-прошивку Blue Pill и докажет через Saleae, "
            "что CH0..CH6 находятся в безопасном статическом состоянии. Если любой PWM-вход "
            "останется HIGH, active PWM запрещен до исправления GPIO, проводки или входов IPM."
        )
    if action_id == "run_static_low_isolation_preflight":
        pattern_part = f" Обнаруженный шаблон: {pattern}." if pattern else ""
        return (
            "Это изоляционный тест для текущего PWM-static блокера."
            f"{pattern_part} Запускать только после отключения HV/J7 и разряда DC-шины. "
            "Тест прошивает диагностическую Blue Pill прошивку, которая не запускает TIM1 и не принимает команды, "
            "а только жестко держит PA8/PA9/PA10/PB13/PB14/PB15/PB12 в LOW, снимает Saleae CH0..CH6 "
            "и затем автоматически восстанавливает runtime-прошивку. Если этот тест проходит, а runtime-static нет, "
            "ищем ошибку в TIM1/runtime init. Если этот тест тоже не проходит, ищем физику: проводку, GND Saleae, "
            "перепутанные каналы или подтяжки/опору входов IPM. Для текущего low-side шаблона сначала мерить "
            "PB13/PB14/PB15 прямо на Blue Pill, затем соответствующие входы IPM, затем сверять с Saleae CH1/CH3/CH5."
        )
    if action_id == "run_uart_loopback":
        return (
            f"Отключи TX/RX USB-UART от STM32. На изолированной стороне адаптера {port} "
            "замкни TX на RX. Команду ниже запускать только после этой физической подготовки: "
            "`uart_loopback_preflight.py` сам остановит PC-direct HMI, выполнит loopback и поднимет HMI обратно. "
            "Это проверяет сам USB-UART, изолятор, "
            "питание изолированной стороны, кабель и драйвер до участия STM32. "
            "Не запускай `unoq_web_server.py` на этом COM-порту, пока loopback не завершен и TX/RX не возвращены к STM32."
        )
    if action_id == "restore_hmi_safe_status":
        return (
            "Восстанови live HMI/status до безопасного состояния. `/api/status` должен отвечать и показывать "
            "`SAFE`, `pwm=0`, `enable=false`, `estop=0`, `bp_fault=0`, `bp_bad/bp_bad_cnt=0`. "
            "Если выше есть `run_uart_loopback`, сначала заверши loopback, убери перемычку TX-RX и верни TX/RX к STM32; "
            "HMI и loopback не должны одновременно держать один COM-порт. "
            "Для PC-direct используй команду ниже; она не включает активный PWM и поднимает только safe status/HMI. "
            "Для UNO Q/ADB используй `ui_access.py` или `adb forward`."
        )
    if action_id == "fix_usb_uart_loopback":
        return (
            "Loopback USB-UART не прошел. Не подключай TX/RX обратно к STM32, пока не исправлены "
            "адаптер, USB-изолятор, питание изолированной стороны, кабель, драйвер или перемычка TX-RX."
        )
    if action_id == "reconnect_stm32_uart_and_rerun_protocol":
        return (
            "Loopback адаптера прошел. Теперь верни перекрестное подключение: PC-TX к PA3, "
            "PC-RX к PA2, GND изолированной стороны к GND STM32, затем повтори UART protocol diagnostic."
        )
    if action_id == "check_stm32_uart_wiring_or_firmware":
        return (
            "ПК уже может писать в UART, но STM32 не отвечает. Проверь перекрестные TX/RX, общий GND "
            "на изолированной стороне, питание STM32, USART2 PA2/PA3 и что загружена UART runtime-прошивка."
        )
    if action_id == "close_com_port_users":
        return (
            "COM-порт занят или не открывается. Закрой Serial Monitor, PlatformIO, Logic/скрипты и другие "
            "процессы, которые могут держать порт, затем повтори диагностику."
        )
    if action_id == "inspect_uart_diagnose_summary":
        return "Открой свежий summary UART-диагностики и разбери конкретную ошибку порта, скорости и ответа."
    if action_id == "refresh_saleae_static_probe":
        return (
            "Сними новый статический захват Saleae по CH0..CH6 и пересчитай анализ PWM до любых активных тестов."
        )
    if action_id == "fix_pwm_safe_static_levels":
        pattern_part = f" Обнаруженный шаблон: {pattern}." if pattern else ""
        return (
            "В SAFE/static состоянии хотя бы один PWM-вход CH0..CH5 находится HIGH."
            f"{pattern_part} Проверь соответствие каналов CH0=PA8, CH1=PB13, CH2=PA9, "
            "CH3=PB14, CH4=PA10, CH5=PB15; затем повтори runtime static preflight. "
            "Для low-side HIGH проверяй цепочку PB13/PB14/PB15 на Blue Pill -> входы IPM -> Saleae CH1/CH3/CH5. "
            "HV/J7 и START держать отключенными до устранения."
        )
    return raw_detail.strip() or "Смотри детали этого действия в summary.json."


def render_operator_steps_ru(summary: dict[str, Any]) -> str:
    ready = bool(summary.get("ready_for_active_pwm"))
    next_actions = [a for a in summary.get("next_actions", []) if isinstance(a, dict)]
    lines = [
        "# Следующие действия на стенде",
        "",
        f"- Готовность к active PWM: {'ДА' if ready else 'НЕТ'}",
        f"- Ошибки gate: {summary.get('failed')}",
        f"- Предупреждения: {summary.get('warnings')}",
        "",
    ]
    if ready:
        lines.extend(
            [
                "Bench-gate разрешает active PWM по текущим evidence.",
                "Перед запуском все равно вручную подтвердить E-STOP, ограничение тока и актуальную схему подключения.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Active PWM НЕ запускать, пока этот gate красный.",
                "Не включать HV/J7 и не подавать START для обхода этих шагов.",
                "",
                "## Порядок",
                "",
            ]
        )
        for index, action in enumerate(next_actions, start=1):
            action_id = str(action.get("id", ""))
            detail = operator_action_detail_ru(action)
            command = str(action.get("command", "")).strip()
            lines.append(f"{index}. `{action_id}`")
            if detail:
                lines.append(f"   {detail}")
            if action_id == "run_uart_loopback":
                lines.append("   Подробно: `UART_LOOPBACK_STEPS_RU.md`.")
            if command:
                lines.extend(["", "   ```powershell", f"   {command}", "   ```", ""])
        if not next_actions:
            lines.append("1. Нет next_actions в summary.json; открыть summary.json и смотреть failed checks.")
            lines.append("")
    lines.extend(
        [
            "## Запреты",
            "",
            "- Не запускать active PWM без `ready_for_active_pwm=true`.",
            "- Не выполнять `bluepill_runtime_static_preflight.py --confirm-hv-off`, пока HV/J7 не отключена и DC-шина не разряжена.",
            "- Не выполнять `bluepill_static_low_preflight.py --confirm-hv-off`, пока HV/J7 не отключена и DC-шина не разряжена.",
            "- Loopback UART делать только при отключенных TX/RX от STM32: коротить TX-RX нужно на стороне USB-UART/изолятора.",
            "- Не держать HMI/serial monitor открытым во время UART loopback на том же COM-порту.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize current bench gates from latest build/UART/Saleae/HMI evidence.")
    ap.add_argument("--url", default="http://127.0.0.1:18080")
    ap.add_argument("--offline", action="store_true", help="Do not query live HMI /api/status.")
    ap.add_argument("--out-root", default="tools/_preflight_exports")
    ap.add_argument("--timeout", type=float, default=1.0)
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    exports = (repo / args.out_root).resolve()
    run_dir = exports / ("bench_gate_report_" + time.strftime("%Y%m%d_%H%M%S"))
    run_dir.mkdir(parents=True, exist_ok=True)

    full_path = latest_build_only_preflight(exports)
    newer_build_sources = stale_sources(full_path, safety_critical_sources(repo))
    runtime_static_path = latest_runtime_static_preflight(exports)
    static_low_path = latest_static_low_preflight(exports)
    uart_protocol_path = latest_uart_diagnose(exports, loopback_mode=False)
    uart_loopback_path = latest_uart_diagnose(exports, loopback_mode=True)
    uart_inventory_path = latest_uart_inventory_only(exports)
    saleae_path = latest_saleae_probe(exports, set(range(7)))
    uart_loopback_fresh = bool(
        uart_loopback_path is not None
        and (uart_protocol_path is None or uart_loopback_path.stat().st_mtime >= uart_protocol_path.stat().st_mtime)
    )

    full_summary = load_json(full_path)
    runtime_static_summary = load_json(runtime_static_path)
    static_low_summary = load_json(static_low_path)
    uart_protocol_summary = load_json(uart_protocol_path)
    uart_loopback_summary = load_json(uart_loopback_path)
    uart_inventory_summary = load_json(uart_inventory_path)
    fresh_uart_loopback_summary = uart_loopback_summary if uart_loopback_fresh else None
    saleae_summary = load_json(saleae_path)
    saleae_analysis = load_json(saleae_path.parent / "pwm_analysis.json") if saleae_path else None
    live_status = {"ok": False, "error": "skipped by --offline"} if args.offline else http_status(args.url, args.timeout)

    checks: list[Check] = []
    checks.extend(check_full_preflight(full_path, full_summary, newer_build_sources))
    checks.extend(check_runtime_static_preflight(runtime_static_path, runtime_static_summary, full_path, full_summary))
    checks.extend(
        check_uart(
            uart_protocol_path,
            uart_protocol_summary,
            uart_loopback_path,
            uart_loopback_summary,
            uart_loopback_fresh,
            uart_inventory_path,
            uart_inventory_summary,
            live_status,
        )
    )
    checks.extend(check_saleae(saleae_path, saleae_summary, saleae_analysis, full_path))
    static_level_check = next((c for c in checks if c.name == "saleae_static_pwm_lines_low"), None)
    static_pwm_pattern = ""
    static_pwm_high_now = bool(static_level_check is not None and not static_level_check.ok)
    if static_level_check is not None and isinstance(static_level_check.evidence, dict):
        static_pwm_pattern = str(static_level_check.evidence.get("pattern", ""))
    checks.extend(
        check_static_low_preflight(
            static_low_path,
            static_low_summary,
            full_path,
            full_summary,
            required=static_pwm_high_now,
        )
    )
    checks.extend(check_live_status(live_status))

    failed = [c for c in checks if not c.ok and c.severity == "fail"]
    warnings = [c for c in checks if not c.ok and c.severity == "warn"]
    next_actions: list[dict[str, str]] = []
    static_low_needs_refresh = check_failed(
        checks,
        {
            "latest_static_low_preflight_present",
            "latest_static_low_preflight_pass",
            "static_low_preflight_fresh_for_build",
            "static_low_runtime_restored",
            "static_low_diagnostic_conclusion_present",
        },
    )
    runtime_static_needs_refresh = check_failed(
        checks,
        {
            "latest_runtime_static_preflight_present",
            "latest_runtime_static_preflight_pass",
            "runtime_static_preflight_fresh_for_build",
            "runtime_static_pwm_lines_low",
        },
    )
    if any(c.name == "latest_build_only_preflight_fresh" and not c.ok for c in checks):
        next_actions.append(
            {
                "id": "run_full_build_only_preflight",
                "detail": "Safety-critical source files changed after the latest build-only preflight. Run full_system_preflight.py --build-only again before active PWM.",
            }
        )
    if runtime_static_needs_refresh:
        next_actions.append(
            {
                "id": "run_runtime_static_preflight",
                "command": "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
                "detail": (
                    "Active PWM requires a fresh runtime static preflight: HV/J7 disconnected, DC bus discharged, "
                    "upload latest Blue Pill runtime, then prove CH0..CH6 static SAFE levels with Saleae. "
                    "If this fresh runtime-static run still reports PWM inputs HIGH, run the static-low isolation preflight next."
                ),
            }
        )
    if static_pwm_high_now and static_low_needs_refresh:
        next_actions.append(
            {
                "id": "run_static_low_isolation_preflight",
                "command": "py -3 -u .\\tools\\bluepill_static_low_preflight.py --confirm-hv-off",
                "detail": (
                    f"Observed SAFE/static PWM input HIGH"
                    f"{' (pattern=' + static_pwm_pattern + ')' if static_pwm_pattern else ''}. "
                    "After a fresh runtime static preflight, use this diagnostic firmware to drive PA8/PA9/PA10/PB13/PB14/PB15/PB12 LOW only, "
                    "capture Saleae CH0..CH6, then automatically restore runtime firmware. "
                    "If static-low passes but runtime static fails, the problem is TIM1/runtime initialization. "
                    "If static-low also fails, the problem is wiring, Saleae reference/channel mapping, or IPM input bias/reference."
                ),
            }
        )
    if any(c.name == "stm32_uart_protocol_pass" and not c.ok for c in checks):
        next_actions.extend(uart_next_actions(uart_protocol_summary, fresh_uart_loopback_summary))
    if any(
        c.name
        in {
            "live_hmi_status_available",
            "live_hmi_safe_state",
            "live_hmi_not_running_pwm",
            "live_hmi_estop_clear",
            "live_hmi_bluepill_fault_clear",
            "live_hmi_bluepill_bad_count_clear",
        }
        and not c.ok
        for c in checks
    ):
        next_actions.append(
            {
                "id": "restore_hmi_safe_status",
                "command": "py -3 -u .\\tools\\pc_direct_hmi_service.py start --serial COM3 --baud 115200 --port 18080",
                "detail": (
                    "Restore live HMI/status before active PWM. /api/status must be reachable and show "
                    "SAFE, pwm=0, enable=false, estop=0, bp_fault=0, bp_bad/bp_bad_cnt=0. "
                    "If run_uart_loopback is also listed, finish loopback first, remove the TX-RX short, and reconnect STM32 TX/RX; "
                    "PC-direct HMI and loopback must not use the same COM port at the same time. "
                    "For UNO Q/ADB use ui_access.py/adb forward instead of the PC-direct command."
                ),
            }
        )
    if any(c.name in {"saleae_static_probe_fresh_for_build", "saleae_static_no_pair_overlap"} and not c.ok for c in checks):
        next_actions.append(
            {
                "id": "refresh_saleae_static_probe",
                "detail": "Capture CH0..CH6 and run saleae_pwm_analyze.py before any active PWM test.",
            }
        )
    if static_pwm_high_now and not runtime_static_needs_refresh:
        next_actions.append(
            {
                "id": "fix_pwm_safe_static_levels",
                "command": "py -3 -u .\\tools\\bluepill_runtime_static_preflight.py --confirm-hv-off",
                "detail": (
                    f"SAFE/static capture has HIGH on at least one PWM input CH0..CH5"
                    f"{' (pattern=' + static_pwm_pattern + ')' if static_pwm_pattern else ''}. "
                    "Verify Saleae channel mapping CH0=PA8, CH1=PB13, CH2=PA9, CH3=PB14, CH4=PA10, CH5=PB15; "
                    "flash/run the latest Blue Pill firmware with the runtime static preflight; "
                    "check GPIO force-low path, IPM input pull-ups/reference, and keep EM_STOP/HV disabled until fixed."
                ),
            }
        )

    next_actions = ordered_next_actions(next_actions)

    summary = {
        "tool": "bench_gate_report",
        "ready_for_active_pwm": len(failed) == 0,
        "failed": len(failed),
        "warnings": len(warnings),
        "run_dir": str(run_dir),
        "run_metadata": collect_run_metadata(repo),
        "evidence": {
            "full_system_preflight": str(full_path) if full_path else None,
            "full_system_preflight_newer_sources": newer_build_sources,
            "bluepill_runtime_static_preflight": str(runtime_static_path) if runtime_static_path else None,
            "bluepill_static_low_preflight": str(static_low_path) if static_low_path else None,
            "bluepill_uart_protocol_diagnose": str(uart_protocol_path) if uart_protocol_path else None,
            "bluepill_uart_loopback_diagnose": str(uart_loopback_path) if uart_loopback_path else None,
            "bluepill_uart_inventory_only": str(uart_inventory_path) if uart_inventory_path else None,
            "bluepill_uart_loopback_fresh_for_protocol": uart_loopback_fresh,
            "saleae_highlevel_probe": str(saleae_path) if saleae_path else None,
            "saleae_pwm_analysis": str(saleae_path.parent / "pwm_analysis.json") if saleae_path else None,
        },
        "checks": [c.__dict__ for c in checks],
        "failed_checks": check_dicts_by_severity(checks, "fail"),
        "warning_checks": check_dicts_by_severity(checks, "warn"),
        "next_actions": next_actions,
    }

    operator_steps_path = run_dir / "NEXT_STEPS_RU.md"
    summary["operator_steps_ru"] = str(operator_steps_path)
    operator_steps_path.write_text(render_operator_steps_ru(summary), encoding="utf-8-sig")
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ready_for_active_pwm": summary["ready_for_active_pwm"],
                "failed": len(failed),
                "warnings": len(warnings),
                "failed_checks": [c.name for c in failed],
                "warning_checks": [c.name for c in warnings],
                "summary": str(summary_path),
                "next_actions": [a["id"] for a in next_actions],
            },
            ensure_ascii=False,
        )
    )
    return 0 if summary["ready_for_active_pwm"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
