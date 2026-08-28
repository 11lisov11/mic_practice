#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

import gpu_research_preflight as preflight


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


class FixtureRunner:
    def __init__(self, nvidia: preflight.CommandResult, python_probe: preflight.CommandResult) -> None:
        self.nvidia = nvidia
        self.python_probe = python_probe
        self.calls: list[list[str]] = []

    def __call__(self, command: Sequence[str], timeout_s: float) -> preflight.CommandResult:
        del timeout_s
        argv = [str(part) for part in command]
        self.calls.append(argv)
        if argv and argv[0] == "nvidia-smi":
            return self.nvidia
        if len(argv) >= 3 and argv[0] == preflight.sys.executable and "-c" in argv:
            return self.python_probe
        raise AssertionError(f"unexpected command: {argv}")


def command_result(
    command: str,
    *,
    returncode: int | None = 0,
    stdout: str = "",
    stderr: str = "",
    error: str | None = None,
    timed_out: bool = False,
) -> preflight.CommandResult:
    return preflight.CommandResult([command], returncode, stdout, stderr, error, timed_out)


def probe_result(*, numpy: dict[str, Any], torch: dict[str, Any]) -> preflight.CommandResult:
    payload = {"numpy": numpy, "torch": torch}
    stdout = preflight.TORCH_PROBE_PREFIX + json.dumps(payload) + "\n"
    return command_result("python", stdout=stdout)


def numpy_ready() -> dict[str, Any]:
    return {"installed": True, "version": "2.1.3", "error": None}


def torch_fixture(
    *,
    installed: bool = True,
    cuda_available: bool = True,
    arch_list: list[str] | None = None,
    capability: list[int] | None = None,
    smoke_pass: bool = True,
    smoke_error: str | None = None,
) -> dict[str, Any]:
    capability = capability or [12, 0]
    devices = (
        [{"index": 0, "name": "NVIDIA GeForce RTX 5070", "capability": capability, "total_memory_mib": 12227}]
        if cuda_available
        else []
    )
    return {
        "installed": installed,
        "version": "2.8.0+cu128" if installed else None,
        "cuda_available": cuda_available if installed else False,
        "compiled_cuda_version": "12.8" if installed else None,
        "cudnn_version": 91002 if installed else None,
        "device_count": len(devices),
        "arch_list": arch_list if arch_list is not None else (["sm_120"] if cuda_available else []),
        "devices": devices,
        "smoke_test": {
            "attempted": bool(installed and cuda_available),
            "pass": bool(installed and cuda_available and smoke_pass),
            "error": smoke_error,
        },
        "error": None if installed else "ModuleNotFoundError: No module named 'torch'",
    }


def nvidia_ready() -> preflight.CommandResult:
    return command_result(
        "nvidia-smi",
        stdout="0, NVIDIA GeForce RTX 5070, 12227, 591.74\n",
    )


def action_codes(report: dict[str, Any]) -> set[str]:
    return {item["code"] for item in report["recommended_actions"]}


def run_case(name: str, fn) -> CaseResult:
    try:
        evidence = fn()
        return CaseResult(name=name, ok=True, evidence=evidence)
    except Exception as exc:
        return CaseResult(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}")


def gpu_ready_case() -> dict[str, Any]:
    runner = FixtureRunner(
        nvidia_ready(),
        probe_result(numpy=numpy_ready(), torch=torch_fixture()),
    )
    report = preflight.build_report(runner=runner)
    assert report["status"] == "gpu_ready"
    assert report["cpu_ready"] is True
    assert report["gpu_ready"] is True
    assert report["nvidia_smi"]["gpus"][0]["vram_mib"] == 12227
    assert report["torch"]["architecture_coverage"][0]["target_arch"] == "sm_120"
    assert report["torch"]["architecture_coverage"][0]["listed_by_torch"] is True
    assert report["workload_guidance"]["gpu_presence_alone_accelerates_numpy"] is False
    assert len(runner.calls) == 2
    return {"status": report["status"], "actions": sorted(action_codes(report))}


def cpu_ready_without_gpu_case() -> dict[str, Any]:
    missing_nvidia = command_result(
        "nvidia-smi",
        returncode=None,
        error="FileNotFoundError: nvidia-smi",
    )
    runner = FixtureRunner(
        missing_nvidia,
        probe_result(numpy=numpy_ready(), torch=torch_fixture(installed=False, cuda_available=False)),
    )
    report = preflight.build_report(runner=runner)
    assert report["status"] == "cpu_ready"
    assert report["cpu_ready"] is True
    assert report["gpu_ready"] is False
    assert {"restore_nvidia_smi", "install_cuda_torch", "numpy_cpu_only"} <= action_codes(report)
    return {"status": report["status"], "actions": sorted(action_codes(report))}


def torch_cpu_build_case() -> dict[str, Any]:
    runner = FixtureRunner(
        nvidia_ready(),
        probe_result(numpy=numpy_ready(), torch=torch_fixture(cuda_available=False)),
    )
    report = preflight.build_report(runner=runner)
    assert report["status"] == "cpu_ready"
    assert "enable_torch_cuda" in action_codes(report)
    return {"status": report["status"], "actions": sorted(action_codes(report))}


def unsupported_architecture_case() -> dict[str, Any]:
    runner = FixtureRunner(
        nvidia_ready(),
        probe_result(
            numpy=numpy_ready(),
            torch=torch_fixture(
                arch_list=["sm_80", "sm_90"],
                smoke_pass=False,
                smoke_error="RuntimeError: no kernel image is available",
            ),
        ),
    )
    report = preflight.build_report(runner=runner)
    assert report["status"] == "cpu_ready"
    assert report["gpu_ready"] is False
    assert {"fix_cuda_smoke_test", "install_matching_torch_arch"} <= action_codes(report)
    return {"coverage": report["torch"]["architecture_coverage"], "actions": sorted(action_codes(report))}


def missing_numpy_case() -> dict[str, Any]:
    no_numpy = {"installed": False, "version": None, "error": "ModuleNotFoundError: numpy"}
    runner = FixtureRunner(
        nvidia_ready(),
        probe_result(numpy=no_numpy, torch=torch_fixture()),
    )
    report = preflight.build_report(runner=runner)
    assert report["status"] == "not_ready"
    assert report["cpu_ready"] is False
    assert report["gpu_ready"] is False
    assert "install_numpy_in_environment" in action_codes(report)
    return {"status": report["status"], "actions": sorted(action_codes(report))}


def malformed_fixture_case() -> dict[str, Any]:
    malformed_nvidia = command_result("nvidia-smi", stdout="unexpected,columns\n")
    malformed_probe = command_result("python", stdout="not-json\n")
    runner = FixtureRunner(malformed_nvidia, malformed_probe)
    report = preflight.build_report(runner=runner)
    assert report["status"] == "not_ready"
    assert report["nvidia_smi"]["query_ok"] is False
    assert report["probe"]["python_subprocess_ok"] is False
    return {
        "status": report["status"],
        "nvidia_error": report["nvidia_smi"]["error"],
        "probe_error": report["probe"]["error"],
    }


def main() -> int:
    cases = [
        run_case("gpu_ready", gpu_ready_case),
        run_case("cpu_ready_without_gpu", cpu_ready_without_gpu_case),
        run_case("torch_cpu_build", torch_cpu_build_case),
        run_case("unsupported_architecture", unsupported_architecture_case),
        run_case("missing_numpy", missing_numpy_case),
        run_case("malformed_fixture", malformed_fixture_case),
    ]
    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "gpu_research_preflight_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "uses_real_gpu": False,
        "cases": [case.__dict__ for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
