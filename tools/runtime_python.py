#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def ensure_modules_or_reexec(module_names: list[str], flag_name: str) -> None:
    missing: list[str] = []
    for name in module_names:
        if name in sys.modules:
            continue
        try:
            found = importlib.util.find_spec(name) is not None
        except ValueError:
            found = name in sys.modules
        if not found:
            missing.append(name)
    if not missing:
        return

    repo_root = Path(__file__).resolve().parents[1]
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists() and os.environ.get(flag_name) != "1":
        env = dict(os.environ)
        env[flag_name] = "1"
        proc = subprocess.run(
            [str(venv_python), "-u", str(Path(sys.argv[0]).resolve()), *sys.argv[1:]],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.stdout:
            sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)

    joined = ", ".join(missing)
    print(
        f"ERROR: missing Python module(s): {joined}. "
        "Install requirements.txt or run with .venv\\Scripts\\python.exe.",
        file=sys.stderr,
    )
    raise SystemExit(2)
