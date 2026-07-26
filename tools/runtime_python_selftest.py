#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import runtime_python


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


def existing_module_noop() -> dict[str, Any]:
    runtime_python.ensure_modules_or_reexec(["sys"], "MIC_PRACTICE_RUNTIME_SELFTEST_REEXEC")
    return {"module": "sys"}


def loaded_stub_without_spec_noop() -> dict[str, Any]:
    name = "_mic_runtime_loaded_stub"
    old = sys.modules.get(name)
    stub = types.ModuleType(name)
    stub.__spec__ = None
    sys.modules[name] = stub
    try:
        runtime_python.ensure_modules_or_reexec([name], "MIC_PRACTICE_RUNTIME_SELFTEST_REEXEC")
        return {"module": name, "loaded": True}
    finally:
        if old is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = old


def missing_module_reexec_proxy() -> dict[str, Any]:
    old_run = runtime_python.subprocess.run
    old_argv = sys.argv[:]
    old_flag = os.environ.pop("MIC_PRACTICE_RUNTIME_SELFTEST_REEXEC", None)
    calls: list[dict[str, Any]] = []

    class FakeProc:
        returncode = 7
        stdout = "reexec stdout\n"
        stderr = "reexec stderr\n"

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": [str(x) for x in cmd], "env_flag": kwargs.get("env", {}).get("MIC_PRACTICE_RUNTIME_SELFTEST_REEXEC")})
        return FakeProc()

    runtime_python.subprocess.run = fake_run
    sys.argv = [str(Path(__file__).resolve()), "--selftest-arg"]
    out = io.StringIO()
    err = io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                runtime_python.ensure_modules_or_reexec(["_mic_runtime_missing_module_xyz"], "MIC_PRACTICE_RUNTIME_SELFTEST_REEXEC")
            except SystemExit as exc:
                code = int(exc.code)
            else:
                raise RuntimeError("expected SystemExit from reexec proxy")
    finally:
        runtime_python.subprocess.run = old_run
        sys.argv = old_argv
        if old_flag is None:
            os.environ.pop("MIC_PRACTICE_RUNTIME_SELFTEST_REEXEC", None)
        else:
            os.environ["MIC_PRACTICE_RUNTIME_SELFTEST_REEXEC"] = old_flag

    if code != 7:
        raise RuntimeError(f"expected proxied return code 7, got {code}")
    if len(calls) != 1:
        raise RuntimeError(f"expected one subprocess call, got {len(calls)}")
    if calls[0]["env_flag"] != "1":
        raise RuntimeError("reexec flag was not propagated")
    if "reexec stdout" not in out.getvalue() or "reexec stderr" not in err.getvalue():
        raise RuntimeError("proxied stdout/stderr were not forwarded")
    return {"code": code, "cmd0": calls[0]["cmd"][0], "env_flag": calls[0]["env_flag"]}


def missing_module_guarded_exits_2() -> dict[str, Any]:
    old_flag = os.environ.get("MIC_PRACTICE_RUNTIME_SELFTEST_GUARDED")
    os.environ["MIC_PRACTICE_RUNTIME_SELFTEST_GUARDED"] = "1"
    err = io.StringIO()
    try:
        with redirect_stderr(err):
            try:
                runtime_python.ensure_modules_or_reexec(["_mic_runtime_missing_module_guarded"], "MIC_PRACTICE_RUNTIME_SELFTEST_GUARDED")
            except SystemExit as exc:
                code = int(exc.code)
            else:
                raise RuntimeError("expected SystemExit for guarded missing module")
    finally:
        if old_flag is None:
            os.environ.pop("MIC_PRACTICE_RUNTIME_SELFTEST_GUARDED", None)
        else:
            os.environ["MIC_PRACTICE_RUNTIME_SELFTEST_GUARDED"] = old_flag
    if code != 2:
        raise RuntimeError(f"expected exit code 2, got {code}")
    if "missing Python module" not in err.getvalue():
        raise RuntimeError("missing-module error was not printed")
    return {"code": code}


def main() -> int:
    cases = [
        run_case("existing_module_noop", existing_module_noop),
        run_case("loaded_stub_without_spec_noop", loaded_stub_without_spec_noop),
        run_case("missing_module_reexec_proxy", missing_module_reexec_proxy),
        run_case("missing_module_guarded_exits_2", missing_module_guarded_exits_2),
    ]
    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "runtime_python_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
