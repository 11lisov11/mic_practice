#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SAFETY_CRITICAL_SOURCE_PATTERNS = (
    "README.md",
    "PC_DIRECT_STM32_RU.md",
    "BRINGUP_STEPS_RU.md",
    "CONNECTION_MATRIX_RU.md",
    "PWM_STATIC_BLOCKER_RU.md",
    "UART_LOOPBACK_STEPS_RU.md",
    "RESEARCH_READINESS_RU.md",
    "tools/*.py",
    "web_hmi/server.py",
    "UNOQ_MOTOR/*.ino",
    "bluepill_uart_pwm_pio/platformio.ini",
    "bluepill_uart_pwm_pio/include/*.h",
    "bluepill_uart_pwm_pio/src/*.cpp",
)


def _repo_root(repo_root: str | Path | None = None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    return Path(__file__).resolve().parents[1]


def _git(repo_root: Path, args: list[str], timeout_s: float = 2.0) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip()


def collect_source_fingerprint(
    repo_root: str | Path | None = None,
    patterns: tuple[str, ...] = SAFETY_CRITICAL_SOURCE_PATTERNS,
) -> dict:
    root = _repo_root(repo_root)
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path for path in root.glob(pattern) if path.is_file())
    unique_files = sorted(set(files), key=lambda path: path.relative_to(root).as_posix())

    digest = hashlib.sha256()
    records = []
    for path in unique_files:
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        file_sha = hashlib.sha256(data).hexdigest()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha.encode("ascii"))
        digest.update(b"\0")
        records.append({"path": rel, "sha256": file_sha, "size": len(data)})

    return {
        "schema": "mic_practice.source_fingerprint.v1",
        "patterns": list(patterns),
        "count": len(records),
        "sha256": digest.hexdigest(),
        "files": records,
    }


def collect_run_metadata(repo_root: str | Path | None = None) -> dict:
    root = _repo_root(repo_root)
    commit = _git(root, ["rev-parse", "HEAD"])
    branch = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    status_short = _git(root, ["status", "--short"])
    remote = _git(root, ["remote", "get-url", "origin"])
    return {
        "schema": "mic_practice.run_metadata.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cwd": str(Path.cwd()),
        "argv": list(sys.argv),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "repo_root": str(root),
        "git": {
            "available": commit is not None,
            "branch": branch,
            "commit": commit,
            "commit_short": commit[:12] if commit else None,
            "remote_origin": remote,
            "dirty": bool(status_short),
            "status_short": status_short.splitlines() if status_short else [],
        },
    }
