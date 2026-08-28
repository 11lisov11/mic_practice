#!/usr/bin/env python3
"""Read-only CPU/GPU environment preflight for reproducible research runs."""
from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


TORCH_PROBE_PREFIX = "GPU_RESEARCH_PREFLIGHT_JSON="
NVIDIA_SMI_COMMAND = (
    "nvidia-smi",
    "--query-gpu=index,name,memory.total,driver_version",
    "--format=csv,noheader,nounits",
)
TORCH_PROBE_CODE = r'''
import json

result = {
    "numpy": {"installed": False, "version": None, "error": None},
    "torch": {
        "installed": False,
        "version": None,
        "cuda_available": False,
        "compiled_cuda_version": None,
        "cudnn_version": None,
        "device_count": 0,
        "arch_list": [],
        "devices": [],
        "smoke_test": {"attempted": False, "pass": False, "error": None},
        "error": None,
    },
}

try:
    import numpy
except Exception as exc:
    result["numpy"]["error"] = f"{type(exc).__name__}: {exc}"
else:
    result["numpy"].update(installed=True, version=numpy.__version__)

try:
    import torch
except Exception as exc:
    result["torch"]["error"] = f"{type(exc).__name__}: {exc}"
else:
    info = result["torch"]
    info["installed"] = True
    info["version"] = torch.__version__
    info["compiled_cuda_version"] = getattr(torch.version, "cuda", None)
    try:
        info["cudnn_version"] = torch.backends.cudnn.version()
    except Exception:
        info["cudnn_version"] = None
    try:
        info["cuda_available"] = bool(torch.cuda.is_available())
        info["device_count"] = int(torch.cuda.device_count()) if info["cuda_available"] else 0
        if info["cuda_available"] and hasattr(torch.cuda, "get_arch_list"):
            info["arch_list"] = list(torch.cuda.get_arch_list())
        for index in range(info["device_count"]):
            properties = torch.cuda.get_device_properties(index)
            capability = torch.cuda.get_device_capability(index)
            info["devices"].append(
                {
                    "index": index,
                    "name": torch.cuda.get_device_name(index),
                    "capability": [int(capability[0]), int(capability[1])],
                    "total_memory_mib": round(int(properties.total_memory) / (1024 * 1024)),
                }
            )
        if info["cuda_available"]:
            smoke = info["smoke_test"]
            smoke["attempted"] = True
            try:
                tensor = torch.ones(16, device="cuda")
                value = float((tensor * 2).sum().cpu().item())
                torch.cuda.synchronize()
                smoke["pass"] = value == 32.0
                if not smoke["pass"]:
                    smoke["error"] = f"unexpected result: {value}"
            except Exception as exc:
                smoke["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"

print("GPU_RESEARCH_PREFLIGHT_JSON=" + json.dumps(result, ensure_ascii=False))
'''


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    timed_out: bool = False


Runner = Callable[[Sequence[str], float], CommandResult]


def run_command(command: Sequence[str], timeout_s: float) -> CommandResult:
    argv = [str(part) for part in command]
    try:
        completed = subprocess.run(
            argv,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
    except FileNotFoundError as exc:
        return CommandResult(argv, None, error=f"{type(exc).__name__}: {exc}")
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            argv,
            None,
            stdout=_decoded_timeout_stream(exc.stdout),
            stderr=_decoded_timeout_stream(exc.stderr),
            error=f"TimeoutExpired: command exceeded {timeout_s:.1f} s",
            timed_out=True,
        )
    except OSError as exc:
        return CommandResult(argv, None, error=f"{type(exc).__name__}: {exc}")
    return CommandResult(argv, completed.returncode, completed.stdout, completed.stderr)


def _decoded_timeout_stream(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def parse_nvidia_smi(result: CommandResult) -> dict[str, Any]:
    report: dict[str, Any] = {
        "available": result.returncode is not None,
        "query_ok": result.returncode == 0,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "error": result.error,
        "stderr": result.stderr.strip() or None,
        "gpus": [],
    }
    if result.returncode != 0:
        return report

    try:
        rows = csv.reader(line for line in result.stdout.splitlines() if line.strip())
        for row in rows:
            if len(row) != 4:
                raise ValueError(f"expected 4 CSV fields, received {len(row)}")
            index_text, name, memory_text, driver = (item.strip() for item in row)
            report["gpus"].append(
                {
                    "index": int(index_text),
                    "name": name,
                    "vram_mib": int(memory_text),
                    "driver_version": driver,
                }
            )
    except (TypeError, ValueError) as exc:
        report["query_ok"] = False
        report["error"] = f"nvidia-smi output parse failed: {exc}"
        report["gpus"] = []
    return report


def parse_python_probe(result: CommandResult) -> dict[str, Any]:
    fallback = {
        "probe_ok": False,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "error": result.error,
        "stderr": result.stderr.strip() or None,
        "numpy": {"installed": False, "version": None, "error": None},
        "torch": {
            "installed": False,
            "version": None,
            "cuda_available": False,
            "compiled_cuda_version": None,
            "cudnn_version": None,
            "device_count": 0,
            "arch_list": [],
            "devices": [],
            "smoke_test": {"attempted": False, "pass": False, "error": None},
            "error": None,
        },
    }
    if result.returncode != 0:
        if fallback["error"] is None:
            fallback["error"] = "Python dependency probe exited with a non-zero status"
        return fallback

    payload_text = None
    for line in reversed(result.stdout.splitlines()):
        if line.startswith(TORCH_PROBE_PREFIX):
            payload_text = line[len(TORCH_PROBE_PREFIX) :]
            break
    if payload_text is None:
        fallback["error"] = "Python dependency probe did not emit its JSON payload"
        return fallback

    try:
        payload = json.loads(payload_text)
        numpy_info = payload["numpy"]
        torch_info = payload["torch"]
        if not isinstance(numpy_info, dict) or not isinstance(torch_info, dict):
            raise TypeError("numpy and torch entries must be JSON objects")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        fallback["error"] = f"Python dependency probe output parse failed: {exc}"
        return fallback

    fallback.update(probe_ok=True, error=None, numpy=numpy_info, torch=torch_info)
    return fallback


def _python_info() -> dict[str, Any]:
    return {
        "executable": sys.executable,
        "version": platform.python_version(),
        "version_info": [sys.version_info.major, sys.version_info.minor, sys.version_info.micro],
        "implementation": platform.python_implementation(),
        "architecture": platform.architecture()[0],
        "platform": platform.platform(),
        "supported": sys.version_info >= (3, 9),
    }


def _torch_arch_coverage(torch_info: dict[str, Any]) -> list[dict[str, Any]]:
    arch_list = {str(item).lower() for item in torch_info.get("arch_list") or []}
    coverage = []
    for device in torch_info.get("devices") or []:
        capability = device.get("capability") or []
        target = None
        supported = None
        if len(capability) == 2:
            target = f"sm_{int(capability[0])}{int(capability[1])}"
            if arch_list:
                supported = target in arch_list or f"compute_{target[3:]}" in arch_list
        coverage.append(
            {
                "index": device.get("index"),
                "capability": capability,
                "target_arch": target,
                "listed_by_torch": supported,
            }
        )
    return coverage


def _recommendations(
    python_info: dict[str, Any],
    nvidia_info: dict[str, Any],
    probe: dict[str, Any],
    gpu_ready: bool,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    def add(priority: str, code: str, message: str) -> None:
        actions.append({"priority": priority, "code": code, "message": message})

    if not python_info["supported"]:
        add("required", "upgrade_python", "Use Python 3.9 or newer for the research tools.")
    if not probe["probe_ok"]:
        add("required", "repair_python_probe", "Run the reported Python executable directly and resolve the dependency probe error.")
    if not probe["numpy"].get("installed"):
        add("required", "install_numpy_in_environment", "Install NumPy in this Python environment before running the existing CPU models.")
    if not nvidia_info["available"]:
        add("gpu", "restore_nvidia_smi", "Install or repair the NVIDIA driver and ensure nvidia-smi is available on PATH.")
    elif not nvidia_info["query_ok"] or not nvidia_info["gpus"]:
        add("gpu", "repair_nvidia_driver", "Resolve the nvidia-smi query error before scheduling CUDA runs.")

    torch_info = probe["torch"]
    if not torch_info.get("installed"):
        add("gpu", "install_cuda_torch", "Install a CUDA-enabled PyTorch build compatible with the installed NVIDIA driver in this Python environment.")
    elif not torch_info.get("cuda_available"):
        add("gpu", "enable_torch_cuda", "PyTorch cannot use CUDA; verify that the build includes CUDA and is compatible with the NVIDIA driver.")
    elif not torch_info.get("smoke_test", {}).get("pass"):
        add("gpu", "fix_cuda_smoke_test", "CUDA was detected but a tiny tensor operation failed; use the reported error to fix driver or PyTorch architecture compatibility.")

    unsupported = [item for item in _torch_arch_coverage(torch_info) if item["listed_by_torch"] is False]
    if unsupported:
        targets = ", ".join(str(item["target_arch"]) for item in unsupported)
        add("gpu", "install_matching_torch_arch", f"The PyTorch build does not list {targets}; install a build that supports the GPU compute capability.")
    if gpu_ready:
        add("recommended", "pin_environment", "Record Python, PyTorch, CUDA, driver and GPU metadata with every mass-run result.")
        add("recommended", "verify_cuda_code_path", "Confirm that tensor models and batches are explicitly placed on a CUDA device before expecting acceleration.")
    add(
        "information",
        "numpy_cpu_only",
        "The current NumPy-only models remain CPU-bound; an installed GPU does not accelerate them unless they are deliberately ported and validated on a GPU-capable backend.",
    )
    return actions


def build_report(runner: Runner = run_command, timeout_s: float = 8.0) -> dict[str, Any]:
    python_info = _python_info()
    nvidia_result = runner(NVIDIA_SMI_COMMAND, timeout_s)
    probe_result = runner((sys.executable, "-I", "-c", TORCH_PROBE_CODE), timeout_s)
    nvidia_info = parse_nvidia_smi(nvidia_result)
    probe = parse_python_probe(probe_result)
    torch_info = probe["torch"]
    arch_coverage = _torch_arch_coverage(torch_info)

    cpu_ready = bool(
        python_info["supported"]
        and probe["probe_ok"]
        and probe["numpy"].get("installed")
    )
    arch_supported = all(item["listed_by_torch"] is not False for item in arch_coverage)
    gpu_ready = bool(
        cpu_ready
        and nvidia_info["query_ok"]
        and nvidia_info["gpus"]
        and torch_info.get("installed")
        and torch_info.get("cuda_available")
        and int(torch_info.get("device_count") or 0) > 0
        and torch_info.get("smoke_test", {}).get("pass")
        and arch_supported
    )
    status = "gpu_ready" if gpu_ready else "cpu_ready" if cpu_ready else "not_ready"

    return {
        "schema_version": 1,
        "tool": "gpu_research_preflight",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "cpu_ready": cpu_ready,
        "gpu_ready": gpu_ready,
        "python": python_info,
        "numpy": probe["numpy"],
        "nvidia_smi": nvidia_info,
        "torch": {**torch_info, "architecture_coverage": arch_coverage},
        "probe": {
            "python_subprocess_ok": probe["probe_ok"],
            "returncode": probe["returncode"],
            "timed_out": probe["timed_out"],
            "error": probe["error"],
            "stderr": probe["stderr"],
        },
        "workload_guidance": {
            "numpy_models_are_cpu_only": True,
            "gpu_presence_alone_accelerates_numpy": False,
            "summary": "Use GPU readiness only for CUDA-aware code; existing NumPy-only simulations remain CPU-bound.",
        },
        "recommended_actions": _recommendations(python_info, nvidia_info, probe, gpu_ready),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose Python, NumPy, NVIDIA and PyTorch CUDA readiness without installing or changing anything."
    )
    parser.add_argument("--json-output", type=Path, help="Also write the JSON report to this path")
    parser.add_argument("--timeout-seconds", type=float, default=8.0, help="Timeout for each read-only probe")
    parser.add_argument("--require-gpu", action="store_true", help="Return non-zero unless the CUDA smoke test passes")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive")
    report = build_report(timeout_s=args.timeout_seconds)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    ready = report["gpu_ready"] if args.require_gpu else report["cpu_ready"]
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
