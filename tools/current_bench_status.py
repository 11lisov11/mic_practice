#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import bench_gate_report


def read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def latest_json(repo: Path, pattern: str) -> Path | None:
    candidates = [p for p in repo.glob(pattern) if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def latest_build_only(repo: Path) -> Path | None:
    candidates = sorted(
        (p for p in repo.glob("tools/_preflight_exports/full_system_preflight_*/summary.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        sub = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
        if data.get("build_only") is True or sub.get("build_only") is True:
            return path
    return None


def bool_ru(value: Any) -> str:
    return "ДА" if bool(value) else "НЕТ"


def path_text(path: Path | None) -> str:
    return str(path.resolve()) if path is not None else "нет"


def command_block(command: str) -> list[str]:
    if not command:
        return []
    return ["", "   ```powershell", f"   {command}", "   ```"]


def render_action(action: dict[str, Any], index: int) -> list[str]:
    action_id = str(action.get("id", "")).strip() or "unknown_action"
    command = str(action.get("command", "")).strip()
    detail = bench_gate_report.operator_action_detail_ru(action)
    lines = [f"{index}. `{action_id}`", f"   {detail}"]
    if action_id == "run_uart_loopback":
        lines.append("   Подробно: `UART_LOOPBACK_STEPS_RU.md`.")
    lines.extend(command_block(command))
    return lines


def next_action_ids(actions: list[dict[str, Any]]) -> list[str]:
    return [str(action.get("id", "")) for action in actions if str(action.get("id", ""))]


def _bench_checks(bench: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    raw_checks = (bench or {}).get("checks", []) if isinstance(bench, dict) else []
    checks: dict[str, dict[str, Any]] = {}
    for check in raw_checks:
        if isinstance(check, dict) and isinstance(check.get("name"), str):
            checks[str(check["name"])] = check
    return checks


def _failed(check: dict[str, Any] | None) -> bool:
    return isinstance(check, dict) and check.get("ok") is False


def _evidence_path(bench: dict[str, Any] | None, key: str) -> Path | None:
    evidence = (bench or {}).get("evidence", {}) if isinstance(bench, dict) else {}
    value = evidence.get(key) if isinstance(evidence, dict) else None
    return Path(str(value)) if value else None


def _pwm_high_channels(evidence: dict[str, Any]) -> list[str]:
    levels = evidence.get("levels", {}) if isinstance(evidence, dict) else {}
    high: list[str] = []
    for item in bench_gate_report.PWM_CHANNEL_MAP:
        channel = str(item.get("channel", ""))
        if not channel.startswith("CH"):
            continue
        try:
            ch_num = int(channel[2:])
        except ValueError:
            continue
        if ch_num > 5:
            continue
        rec = levels.get(str(ch_num), {}) if isinstance(levels, dict) else {}
        if isinstance(rec, dict) and rec.get("initial") == 1 and rec.get("final") == 1:
            high.append(f"{channel}/{item.get('stm32', '')}")
    return high


def _uart_error_digest(summary: dict[str, Any] | None) -> str:
    if not isinstance(summary, dict):
        return "нет читаемого UART summary"
    next_ids = [
        str(action.get("id", ""))
        for action in summary.get("next_actions", [])
        if isinstance(action, dict) and action.get("id")
    ]
    selected_port_summary = str(summary.get("selected_port_summary", "")).strip()
    visible_ports = str(summary.get("visible_ports_summary") or summary.get("visible_ports", "")).strip()
    dtr_rts_matrix = bool(summary.get("dtr_rts_matrix"))
    errors: list[str] = []
    error_digest = summary.get("attempt_error_digest", [])
    if isinstance(error_digest, list):
        for item in error_digest:
            text = str(item).strip()
            if text and text not in errors:
                errors.append(text)
            if len(errors) >= 4:
                break
    attempts = summary.get("protocol_attempts", [])
    if not errors and isinstance(attempts, list):
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            error = str(attempt.get("error", "")).strip()
            if error and error not in errors:
                errors.append(error)
            if len(errors) >= 2:
                break
    counts = summary.get("attempt_counts", {})
    parts: list[str] = []
    if next_ids:
        parts.append("next_actions=" + ",".join(next_ids))
    if selected_port_summary:
        parts.append("port=" + selected_port_summary)
    if visible_ports:
        parts.append("visible_ports=" + visible_ports)
    if dtr_rts_matrix:
        parts.append("DTR/RTS matrix=tried")
    if isinstance(counts, dict) and counts:
        count_items = []
        for key in (
            "protocol",
            "open_ok",
            "write_returned",
            "write_ok",
            "flush_ok",
            "write_timeouts",
            "flush_timeouts",
            "no_response",
            "responses",
        ):
            if key in counts:
                count_items.append(f"{key}={counts.get(key)}")
        if count_items:
            parts.append("counts=" + ",".join(count_items))
    auto_selection = summary.get("auto_port_selection", {})
    if isinstance(auto_selection, dict) and auto_selection:
        auto_parts: list[str] = []
        selected = auto_selection.get("selected_ports", [])
        if selected:
            auto_parts.append("selected=" + ",".join(str(item) for item in selected))
        added = auto_selection.get("added_pnp_ok_devices", [])
        if added:
            auto_parts.append("pnp_ok_added=" + ",".join(str(item) for item in added))
        skipped = auto_selection.get("skipped_pnp_not_ok", [])
        if isinstance(skipped, list) and skipped:
            skipped_text = []
            for item in skipped:
                if not isinstance(item, dict):
                    continue
                device = str(item.get("device") or "?")
                status = str(item.get("status") or "unknown")
                hint = str(item.get("hint") or "").split(";", 1)[0]
                skipped_text.append(f"{device}({status}, {hint})" if hint else f"{device}({status})")
            if skipped_text:
                auto_parts.append("pnp_not_ok_skipped=" + " | ".join(skipped_text))
        if auto_parts:
            parts.append("auto_port_selection=" + "; ".join(auto_parts))
    if errors:
        parts.append("ошибка=" + " | ".join(errors))
    hmi_digest = _uart_hmi_digest(summary)
    if hmi_digest:
        parts.append(hmi_digest)
    return "; ".join(parts) if parts else "протокол не прошел без детализированной ошибки"


def _uart_hmi_digest(summary: dict[str, Any] | None) -> str:
    if not isinstance(summary, dict):
        return ""
    hmi = summary.get("pc_direct_hmi", {})
    if not isinstance(hmi, dict) or not hmi.get("checked"):
        return ""
    selected = str(summary.get("selected_port") or "").upper()
    processes = hmi.get("hmi_processes", [])
    if not isinstance(processes, list) or not processes:
        return "pc_direct_hmi=not_running"
    same: list[str] = []
    other: list[str] = []
    for proc in processes:
        if not isinstance(proc, dict):
            continue
        pid = str(proc.get("pid") or "?")
        serial_name = str(proc.get("serial") or "?").upper()
        item = f"pid={pid}/serial={serial_name}"
        if selected and serial_name == selected:
            same.append(item)
        else:
            other.append(item)
    stop_cmd = str(hmi.get("stop_command") or "py -3 -u .\\tools\\pc_direct_hmi_service.py stop --port 18080")
    if same:
        return f"pc_direct_hmi=holds_selected_port({', '.join(same)}), stop=`{stop_cmd}`"
    return f"pc_direct_hmi=running_other({', '.join(other)})" if other else ""


def failure_digest(bench: dict[str, Any] | None) -> list[str]:
    checks = _bench_checks(bench)
    lines: list[str] = []

    if any(
        _failed(checks.get(name))
        for name in (
            "latest_runtime_static_preflight_pass",
            "runtime_static_preflight_fresh_for_build",
            "runtime_static_pwm_lines_low",
        )
    ):
        runtime_path = _evidence_path(bench, "bluepill_runtime_static_preflight")
        lines.append(
            "Runtime-static: реального upload+Saleae static capture для актуальной прошивки нет "
            f"или он не прошел; последний summary: `{path_text(runtime_path)}`."
        )
        lines.append(
            "Важно: свежий build-only доказывает только сборку firmware/tooling; "
            "Blue Pill считается неподтвержденным, пока `bluepill_runtime_static_preflight.py --confirm-hv-off` "
            "не прошьет актуальную runtime-прошивку и не снимет новый Saleae static capture."
        )

    saleae_check = checks.get("saleae_static_pwm_lines_low")
    if _failed(saleae_check):
        evidence = saleae_check.get("evidence", {}) if isinstance(saleae_check, dict) else {}
        evidence = evidence if isinstance(evidence, dict) else {}
        pattern = str(evidence.get("pattern", "unknown"))
        high_channels = _pwm_high_channels(evidence)
        high_text = ", ".join(high_channels) if high_channels else "не удалось извлечь уровни"
        csv_path = Path(str(evidence.get("csv"))) if evidence.get("csv") else None
        lines.append(
            f"Saleae static: pattern=`{pattern}`, HIGH держатся на `{high_text}`; "
            f"CSV: `{path_text(csv_path)}`."
        )
        if pattern == "low_side_static_high":
            lines.append("PWM static blocker: подробный порядок проверки в `PWM_STATIC_BLOCKER_RU.md`.")

    saleae_fresh_check = checks.get("saleae_static_probe_fresh_for_build")
    if _failed(saleae_fresh_check):
        evidence = saleae_fresh_check.get("evidence", {}) if isinstance(saleae_fresh_check, dict) else {}
        evidence = evidence if isinstance(evidence, dict) else {}
        saleae_summary = Path(str(evidence.get("saleae_summary"))) if evidence.get("saleae_summary") else None
        build_summary = Path(str(evidence.get("full_system_preflight"))) if evidence.get("full_system_preflight") else None
        lines.append(
            "Saleae freshness: статический Saleae capture старше свежей build-only сборки; "
            f"capture: `{path_text(saleae_summary)}`, build: `{path_text(build_summary)}`. "
            "После прошивки нужен новый static capture CH0..CH6."
        )

    if any(
        _failed(checks.get(name))
        for name in (
            "latest_static_low_preflight_present",
            "latest_static_low_preflight_pass",
            "static_low_preflight_fresh_for_build",
            "static_low_runtime_restored",
            "static_low_diagnostic_conclusion_present",
        )
    ):
        static_low_path = _evidence_path(bench, "bluepill_static_low_preflight")
        static_low_check = checks.get("latest_static_low_preflight_pass")
        static_low_evidence = static_low_check.get("evidence", {}) if isinstance(static_low_check, dict) else {}
        static_low_evidence = static_low_evidence if isinstance(static_low_evidence, dict) else {}
        static_checks = static_low_evidence.get("static_checks", {})
        static_checks = static_checks if isinstance(static_checks, dict) else {}
        conclusion = static_low_evidence.get("diagnostic_conclusion", {})
        conclusion = conclusion if isinstance(conclusion, dict) else {}
        lines.append(
            "Static-low isolation: диагностическое доказательство не готово или не прошло; "
            f"summary: `{path_text(static_low_path)}`, "
            f"pattern=`{static_checks.get('pattern')}`, "
            f"conclusion=`{conclusion.get('result')}`."
        )

    strict_saleae_check = checks.get("saleae_strict_static_safe_exit")
    if _failed(strict_saleae_check):
        evidence = strict_saleae_check.get("evidence", {}) if isinstance(strict_saleae_check, dict) else {}
        evidence = evidence if isinstance(evidence, dict) else {}
        lines.append(
            "Saleae strict static-safe: "
            f"`require_static_safe_pass={evidence.get('require_static_safe_pass')}`, "
            f"`exit_code={evidence.get('exit_code')}`, "
            f"`exit_reason={evidence.get('exit_reason')}`; "
            f"summary: `{path_text(Path(str(evidence.get('summary')))) if evidence.get('summary') else 'нет summary'}`."
        )

    uart_check = checks.get("stm32_uart_protocol_pass")
    if _failed(uart_check):
        uart_path = _evidence_path(bench, "bluepill_uart_protocol_diagnose")
        uart_summary = read_json(uart_path)
        uart_evidence = uart_check.get("evidence", {}) if isinstance(uart_check, dict) else {}
        uart_evidence = uart_evidence if isinstance(uart_evidence, dict) else {}
        lines.append(
            f"UART STM32: protocol не подтвержден, {_uart_error_digest(uart_summary)}; "
            f"summary: `{path_text(uart_path)}`."
        )
        inventory_path = uart_evidence.get("latest_inventory_only_summary")
        if inventory_path:
            inventory_summary = read_json(Path(str(inventory_path)))
            selected = str(uart_evidence.get("latest_inventory_only_selected_port") or "").strip()
            visible = str(uart_evidence.get("latest_inventory_only_visible_ports") or "").strip()
            extra = []
            if selected:
                extra.append(f"selected={selected}")
            if visible:
                extra.append(f"visible={visible}")
            hmi_digest = _uart_hmi_digest(inventory_summary)
            if hmi_digest:
                extra.append(hmi_digest)
            details = "; ".join(extra) if extra else "details unavailable"
            lines.append(
                "UART inventory-only: свежий безопасный снимок COM есть, "
                "но это не доказывает protocol/link; "
                f"{details}; summary: `{path_text(Path(str(inventory_path)))}`."
            )

    hmi_check = checks.get("live_hmi_status_available")
    if _failed(hmi_check):
        detail = str(hmi_check.get("detail", "")).strip() if isinstance(hmi_check, dict) else ""
        lines.append(f"HMI /api/status: нет свежего live-status ({detail or 'ошибка не указана'}).")
    else:
        hmi_failed = [
            check
            for name, check in checks.items()
            if name.startswith("live_hmi_") and name != "live_hmi_status_available" and _failed(check)
        ]
        if hmi_failed:
            failed_names = ", ".join(str(check.get("name", "")) for check in hmi_failed)
            evidence = hmi_failed[0].get("evidence", {}) if isinstance(hmi_failed[0], dict) else {}
            if not isinstance(evidence, dict):
                evidence = {}
            compact = ", ".join(
                f"{key}={evidence.get(key)}"
                for key in (
                    "state",
                    "link",
                    "pwm",
                    "enable",
                    "estop",
                    "bp_fault",
                    "bp_bad",
                    "uart_port",
                    "uart_open",
                    "uart_last_error",
                    "uart_error_count",
                )
                if key in evidence
            )
            lines.append(f"HMI /api/status: состояние небезопасно ({failed_names}; {compact}).")

    return lines


def render_status(
    repo: Path,
    *,
    bench_path: Path | None,
    bench: dict[str, Any] | None,
    readiness_path: Path | None,
    readiness: dict[str, Any] | None,
    build_path: Path | None,
    build: dict[str, Any] | None,
) -> str:
    ready = bool(bench.get("ready_for_active_pwm")) if isinstance(bench, dict) else False
    next_actions = [a for a in (bench or {}).get("next_actions", []) if isinstance(a, dict)]
    build_summary = build.get("summary", {}) if isinstance(build, dict) and isinstance(build.get("summary"), dict) else {}
    build_ok = bool((build or {}).get("build_only_pass") or build_summary.get("build_only_pass"))
    build_fresh = "run_full_build_only_preflight" not in next_action_ids(next_actions)
    build_ready = build_ok and build_fresh
    readiness_ok = bool((readiness or {}).get("ready"))
    generated = datetime.now().isoformat(timespec="seconds")
    digest = failure_digest(bench)

    lines = [
        "# Текущий статус стенда",
        "",
        f"- Сформировано: `{generated}`",
        f"- Проект: `{repo.resolve()}`",
        f"- Active PWM разрешен: **{bool_ru(ready)}**",
        f"- Build-only preflight свежий и прошел: **{bool_ru(build_ready)}**",
        f"- Bringup/readiness готов: **{bool_ru(readiness_ok)}**",
        "",
    ]

    if ready:
        lines.extend(
            [
                "## Решение",
                "",
                "Bench-gate сейчас зеленый. Перед активным запуском все равно вручную проверь E-STOP, ограничение тока, схему коммутации и фактическое питание стенда.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Решение",
                "",
                "Active PWM сейчас **не запускать**. Не подавать `START` и не включать HV/J7 для обхода красного gate.",
                "",
                "## Что делать дальше",
                "",
            ]
        )
        if digest:
            action_header = lines[-2:]
            del lines[-2:]
            lines.extend(["## Почему gate красный", ""])
            lines.extend(f"- {item}" for item in digest)
            lines.append("")
            lines.extend(action_header)
        if next_actions:
            for index, action in enumerate(next_actions, start=1):
                lines.extend(render_action(action, index))
                lines.append("")
        else:
            lines.extend(
                [
                    "1. Нет готового списка `next_actions`.",
                    "   Сначала сформируй свежий gate:",
                    "",
                    "   ```powershell",
                    "   py -3 -u .\\tools\\bench_gate_report.py --url http://127.0.0.1:18080",
                    "   ```",
                    "",
                ]
            )

    lines.extend(
        [
            "## Последние доказательства",
            "",
            f"- Bench-gate summary: `{path_text(bench_path)}`",
            f"- Bench-gate operator steps: `{path_text(Path(bench.get('operator_steps_ru')) if isinstance(bench, dict) and bench.get('operator_steps_ru') else None)}`",
            f"- Build-only summary: `{path_text(build_path)}`",
            f"- Readiness summary: `{path_text(readiness_path)}`",
            "",
            "## Запреты до зеленого gate",
            "",
            "- Не запускать active PWM без `ready_for_active_pwm=true`.",
            "- Не выполнять `bluepill_runtime_static_preflight.py --confirm-hv-off`, пока HV/J7 не отключена и DC-шина не разряжена.",
            "- Не выполнять `bluepill_static_low_preflight.py --confirm-hv-off`, пока HV/J7 не отключена и DC-шина не разряжена.",
            "- UART loopback делать только при отключенных TX/RX от STM32: коротить TX-RX нужно на стороне USB-UART/изолятора.",
            "- Не держать HMI/serial monitor открытым во время UART loopback на том же COM-порту.",
            "- Если JSON и этот файл расходятся, главным считается свежий `summary.json`; затем нужно заново запустить генератор статуса.",
            "",
        ]
    )
    return "\n".join(lines)


def repair_operator_text(text: str) -> str:
    repaired: list[str] = []
    for line in text.splitlines():
        if line.startswith("- Saleae freshness:"):
            match = re.search(r"capture: `([^`]*)`, build: `([^`]*)`", line)
            capture = match.group(1) if match else "нет"
            build = match.group(2) if match else "нет"
            line = (
                "- Saleae freshness: статический Saleae capture старше свежей build-only сборки; "
                f"capture: `{capture}`, build: `{build}`. "
                "После прошивки нужен новый static capture CH0..CH6."
            )
        elif line.startswith("- Static-low isolation:"):
            match = re.search(r"summary: `([^`]*)`, pattern=`([^`]*)`, conclusion=`([^`]*)`", line)
            summary = match.group(1) if match else "нет"
            pattern = match.group(2) if match else "None"
            conclusion = match.group(3) if match else "None"
            line = (
                "- Static-low isolation: диагностическое доказательство не готово или не прошло; "
                f"summary: `{summary}`, pattern=`{pattern}`, conclusion=`{conclusion}`."
            )
        repaired.append(line)
    return "\n".join(repaired)


def build_current_status(repo: Path) -> tuple[str, dict[str, Any]]:
    bench_path = latest_json(repo, "tools/_preflight_exports/bench_gate_report_*/summary.json")
    readiness_path = latest_json(repo, "tools/_readiness_exports/research_readiness_*/summary.json")
    build_path = latest_build_only(repo)
    bench = read_json(bench_path)
    readiness = read_json(readiness_path)
    build = read_json(build_path)
    next_actions = [a for a in (bench or {}).get("next_actions", []) if isinstance(a, dict)]
    build_summary = build.get("summary", {}) if isinstance(build, dict) and isinstance(build.get("summary"), dict) else {}
    build_ok = bool((build or {}).get("build_only_pass") or build_summary.get("build_only_pass"))
    build_ready = build_ok and "run_full_build_only_preflight" not in next_action_ids(next_actions)
    text = render_status(
        repo,
        bench_path=bench_path,
        bench=bench,
        readiness_path=readiness_path,
        readiness=readiness,
        build_path=build_path,
        build=build,
    )
    text = repair_operator_text(text)
    status = {
        "ready_for_active_pwm": bool(bench.get("ready_for_active_pwm")) if isinstance(bench, dict) else False,
        "build_only_fresh_and_passed": build_ready,
        "bench_summary": path_text(bench_path),
        "readiness_summary": path_text(readiness_path),
        "build_only_summary": path_text(build_path),
        "next_actions": next_action_ids(next_actions),
    }
    return text, status


def normalize_status_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    return re.sub(
        r"^- Сформировано: `[^`]*`$",
        "- Сформировано: `<normalized>`",
        text,
        flags=re.MULTILINE,
    )


def check_current_status(repo: Path, out_path: Path) -> tuple[bool, dict[str, Any]]:
    expected_text, status = build_current_status(repo)
    if not out_path.exists():
        status.update({"out": str(out_path), "check_pass": False, "error": "status file is missing"})
        return False, status
    actual_text = out_path.read_text(encoding="utf-8-sig")
    expected_norm = normalize_status_text(expected_text)
    actual_norm = normalize_status_text(actual_text)
    ok = expected_norm == actual_norm
    status.update(
        {
            "out": str(out_path),
            "check_pass": ok,
            "error": "" if ok else "CURRENT_BENCH_STATUS_RU.md is stale or was edited manually; regenerate it",
        }
    )
    return ok, status


def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8-sig") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=encoding,
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            tmp_path = Path(fh.name)
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        tmp_path.replace(path)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a root Russian status file from latest bench/readiness evidence.")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--out", default="CURRENT_BENCH_STATUS_RU.md")
    parser.add_argument("--check", action="store_true", help="Do not write; verify that the status file matches latest evidence.")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    out_path = (repo / args.out).resolve()
    if args.check:
        ok, status = check_current_status(repo, out_path)
        print(json.dumps(status, ensure_ascii=False))
        return 0 if ok else 1

    text, status = build_current_status(repo)
    write_text_atomic(out_path, text)
    status["out"] = str(out_path)
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
