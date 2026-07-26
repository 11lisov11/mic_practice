#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pc_direct_hmi_service as svc


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


def add_case(cases: list[CaseResult], name: str, ok: bool, detail: str = "", evidence: Any = None) -> None:
    cases.append(CaseResult(name=name, ok=bool(ok), detail=detail, evidence=evidence))


def run_cases() -> list[CaseResult]:
    cases: list[CaseResult] = []
    py_cmd = (
        r"C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe -u "
        r".\tools\unoq_web_server.py --serial COM3 --baud 460800 --host 127.0.0.1 --port 18080 --rx-timeout 0.08"
    )
    py_launcher_cmd = (
        r'"C:\Users\USER\AppData\Local\Programs\Python\Launcher\py.exe" -3 -u '
        r".\tools\unoq_web_server.py --serial COM3 --baud 460800 --host 127.0.0.1 --port 18080"
    )
    other_port_cmd = py_cmd.replace("--port 18080", "--port 18081")
    service_cmd = r"py -3 -u .\tools\pc_direct_hmi_service.py status --port 18080"
    query_cmd = r"powershell Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*unoq_web_server.py*' }"

    add_case(cases, "matches_python_server_command", svc.hmi_commandline_matches(py_cmd, 18080))
    add_case(cases, "matches_py_launcher_server_command", svc.hmi_commandline_matches(py_launcher_cmd, 18080))
    add_case(cases, "rejects_other_port", not svc.hmi_commandline_matches(other_port_cmd, 18080))
    add_case(cases, "rejects_service_manager_command", not svc.hmi_commandline_matches(service_cmd, 18080))
    add_case(cases, "rejects_powershell_query_command", not svc.hmi_commandline_matches(query_cmd, 18080))

    processes = [
        {"pid": 10, "name": "python.exe", "command_line": py_cmd},
        {"pid": 11, "name": "py.exe", "command_line": py_launcher_cmd},
        {"pid": 12, "name": "python.exe", "command_line": other_port_cmd},
        {"pid": 13, "name": "powershell.exe", "command_line": query_cmd},
        {"pid": 10, "name": "python.exe", "command_line": py_cmd},
    ]
    matches = svc.filter_hmi_processes(processes, 18080)
    add_case(
        cases,
        "filters_only_matching_hmi_processes_and_deduplicates",
        [item["pid"] for item in matches] == [10, 11],
        evidence=matches,
    )

    cmd = svc.build_server_cmd(Path(r"C:\mic_practice"), "COM3", 460800, "127.0.0.1", 18080, 0.08)
    add_case(
        cases,
        "start_command_is_pc_direct_safe_server",
        "unoq_web_server.py" in cmd[2].replace("\\", "/")
        and "--serial" in cmd
        and "COM3" in cmd
        and "--baud" in cmd
        and "460800" in cmd
        and "--port" in cmd
        and "18080" in cmd,
        evidence=cmd,
    )

    add_case(cases, "as_list_wraps_single_object", svc.as_list({"pid": 1}) == [{"pid": 1}])
    add_case(cases, "as_list_preserves_lists", svc.as_list([{"pid": 1}]) == [{"pid": 1}])
    add_case(cases, "base_url_defaults_to_host_port", svc.base_url("127.0.0.1", 18080) == "http://127.0.0.1:18080")
    add_case(cases, "base_url_strips_url_slash", svc.base_url("127.0.0.1", 18080, "http://x:1/") == "http://x:1")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        summary = {"tool": svc.TOOL, "action": "status", "pass": True}
        manifest = Path(svc.write_manifest(root, summary))
        loaded = json.loads(manifest.read_text(encoding="utf-8"))
        add_case(cases, "write_manifest_records_latest_summary", loaded == summary and manifest.name == "pc_direct_hmi_latest.json")

    return cases


def main() -> int:
    cases = run_cases()
    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "pc_direct_hmi_service_selftest",
        "pass": len(failed) == 0,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    raise SystemExit(main())
