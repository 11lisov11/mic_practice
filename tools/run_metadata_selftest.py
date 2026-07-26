#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import run_metadata


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


def run_case(name: str, fn) -> CaseResult:
    try:
        evidence = fn()
        return CaseResult(name=name, ok=True, evidence=evidence)
    except Exception as exc:
        return CaseResult(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}")


def write_file(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_repo_fixture(root: Path) -> None:
    write_file(root, "README.md", "safe upload wrapper docs\n")
    write_file(root, "PC_DIRECT_STM32_RU.md", "pc direct safe docs\n")
    write_file(root, "BRINGUP_STEPS_RU.md", "bringup safe docs\n")
    write_file(root, "CONNECTION_MATRIX_RU.md", "connection safe docs\n")
    write_file(root, "PWM_STATIC_BLOCKER_RU.md", "pwm static safe docs\n")
    write_file(root, "UART_LOOPBACK_STEPS_RU.md", "uart loopback safe docs\n")
    write_file(root, "RESEARCH_READINESS_RU.md", "research safe docs\n")
    write_file(root, "tools/a.py", "print('a')\n")
    write_file(root, "tools/b.py", "print('b')\n")
    write_file(root, "web_hmi/server.py", "SERVER = True\n")
    write_file(root, "UNOQ_MOTOR/UNOQ_MOTOR.ino", "void setup() {}\n")
    write_file(root, "bluepill_uart_pwm_pio/platformio.ini", "[env:bluepill]\n")
    write_file(root, "bluepill_uart_pwm_pio/include/config.h", "#define SAFE 1\n")
    write_file(root, "bluepill_uart_pwm_pio/src/main.cpp", "int main() { return 0; }\n")
    write_file(root, "ignored.txt", "not safety critical\n")


def source_fingerprint_is_stable_sorted_and_filtered() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_repo_fixture(root)
        first = run_metadata.collect_source_fingerprint(root)
        second = run_metadata.collect_source_fingerprint(root)
        expected_paths = [
            "BRINGUP_STEPS_RU.md",
            "CONNECTION_MATRIX_RU.md",
            "PC_DIRECT_STM32_RU.md",
            "PWM_STATIC_BLOCKER_RU.md",
            "README.md",
            "RESEARCH_READINESS_RU.md",
            "UART_LOOPBACK_STEPS_RU.md",
            "UNOQ_MOTOR/UNOQ_MOTOR.ino",
            "bluepill_uart_pwm_pio/include/config.h",
            "bluepill_uart_pwm_pio/platformio.ini",
            "bluepill_uart_pwm_pio/src/main.cpp",
            "tools/a.py",
            "tools/b.py",
            "web_hmi/server.py",
        ]
        actual_paths = [item["path"] for item in first["files"]]
        if first["sha256"] != second["sha256"]:
            raise RuntimeError("fingerprint changed without source changes")
        if actual_paths != expected_paths:
            raise RuntimeError(f"unexpected fingerprint file order: {actual_paths}")
        if first["count"] != len(expected_paths):
            raise RuntimeError(f"unexpected source count: {first['count']}")
        return {"count": first["count"], "sha256": first["sha256"], "paths": actual_paths}


def source_fingerprint_changes_only_for_included_sources() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_repo_fixture(root)
        baseline = run_metadata.collect_source_fingerprint(root)
        write_file(root, "ignored.txt", "changed but still not safety critical\n")
        ignored_change = run_metadata.collect_source_fingerprint(root)
        if baseline["sha256"] != ignored_change["sha256"]:
            raise RuntimeError("ignored file changed the safety-critical fingerprint")
        write_file(root, "README.md", "direct upload docs changed\n")
        doc_change = run_metadata.collect_source_fingerprint(root)
        if baseline["sha256"] == doc_change["sha256"]:
            raise RuntimeError("operator doc change did not change fingerprint")
        write_file(root, "bluepill_uart_pwm_pio/src/main.cpp", "int main() { return 1; }\n")
        included_change = run_metadata.collect_source_fingerprint(root)
        if baseline["sha256"] == included_change["sha256"]:
            raise RuntimeError("included source change did not change fingerprint")
        return {
            "baseline": baseline["sha256"],
            "ignored_change": ignored_change["sha256"],
            "doc_change": doc_change["sha256"],
            "included_change": included_change["sha256"],
        }


def source_fingerprint_deduplicates_overlapping_patterns() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_repo_fixture(root)
        fingerprint = run_metadata.collect_source_fingerprint(
            root,
            patterns=("tools/*.py", "tools/a.py", "tools/*.py"),
        )
        paths = [item["path"] for item in fingerprint["files"]]
        expected = ["tools/a.py", "tools/b.py"]
        if paths != expected:
            raise RuntimeError(f"duplicate or missing paths: {paths}")
        return {"paths": paths, "count": fingerprint["count"]}


def run_metadata_reports_git_block() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        metadata = run_metadata.collect_run_metadata(root)
        git = metadata.get("git", {})
        if metadata.get("schema") != "mic_practice.run_metadata.v1":
            raise RuntimeError(f"unexpected schema: {metadata.get('schema')}")
        if not isinstance(git, dict) or "available" not in git or "dirty" not in git:
            raise RuntimeError("git metadata block is incomplete")
        return {"schema": metadata["schema"], "git_available": git["available"], "dirty": git["dirty"]}


def main() -> int:
    cases = [
        run_case("source_fingerprint_is_stable_sorted_and_filtered", source_fingerprint_is_stable_sorted_and_filtered),
        run_case("source_fingerprint_changes_only_for_included_sources", source_fingerprint_changes_only_for_included_sources),
        run_case("source_fingerprint_deduplicates_overlapping_patterns", source_fingerprint_deduplicates_overlapping_patterns),
        run_case("run_metadata_reports_git_block", run_metadata_reports_git_block),
    ]
    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "run_metadata_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
