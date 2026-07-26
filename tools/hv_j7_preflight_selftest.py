#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass
from typing import Any


def install_import_stubs() -> None:
    if "grpc" not in sys.modules:
        grpc = types.ModuleType("grpc")
        grpc.RpcError = RuntimeError
        grpc.StatusCode = types.SimpleNamespace(
            DEADLINE_EXCEEDED=object(),
            UNAVAILABLE=object(),
            INTERNAL=object(),
            UNKNOWN=object(),
            ABORTED=object(),
        )
        sys.modules["grpc"] = grpc
    if "saleae" not in sys.modules:
        saleae = types.ModuleType("saleae")
        automation = types.ModuleType("saleae.automation")
        capture = types.ModuleType("saleae.automation.capture")
        grpc_pkg = types.ModuleType("saleae.grpc")
        saleae_pb2 = types.ModuleType("saleae.grpc.saleae_pb2")

        class _DummyManager:
            pass

        class _DummyCapture:
            pass

        automation.Manager = _DummyManager
        capture.Capture = _DummyCapture
        grpc_pkg.saleae_pb2 = saleae_pb2
        sys.modules["saleae"] = saleae
        sys.modules["saleae.automation"] = automation
        sys.modules["saleae.automation.capture"] = capture
        sys.modules["saleae.grpc"] = grpc_pkg
        sys.modules["saleae.grpc.saleae_pb2"] = saleae_pb2


install_import_stubs()

import hv_j7_preflight as hv


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: Any = None


def add_case(results: list[CaseResult], name: str, ok: bool, detail: str = "", evidence: Any = None) -> None:
    results.append(CaseResult(name=name, ok=bool(ok), detail=detail, evidence=evidence))


def base_run_status(vdc_key: str = "bp_vdc", vdc: float = 315.0) -> dict[str, Any]:
    st: dict[str, Any] = {
        "state": "VF_RUN",
        "mode": "VF",
        "diag_mode": 0,
        "duty_mode": 0,
        "pwm": 1,
        "estop": 0,
        "bp_fault": 0,
        "bp_bad": 0,
        "bp_bad_cnt": 0,
        "link": True,
        "bp_rsp_age_ms": 1,
        "freq_cmd": 1.0,
        "freq": 1.0,
    }
    st[vdc_key] = vdc
    return st


def base_estop_status(vdc_key: str = "bp_vdc", vdc: float = 315.0) -> dict[str, Any]:
    st: dict[str, Any] = {
        "state": "SAFE",
        "mode": "VF",
        "pwm": 0,
        "estop": 1,
        "bp_fault": 0,
        "bp_bad": 0,
        "bp_bad_cnt": 0,
        "link": True,
        "bp_rsp_age_ms": 1,
    }
    st[vdc_key] = vdc
    return st


def main() -> int:
    old_bad = os.environ.get("UNOQ_BP_CMD_BAD_BASELINE")
    os.environ["UNOQ_BP_CMD_BAD_BASELINE"] = "0"
    results: list[CaseResult] = []
    try:
        add_case(results, "vdc_none_blocks", not hv.vdc_in_range(None, None, None))
        add_case(results, "vdc_missing_blocks", not hv.vdc_in_range({"state": "SAFE"}, None, None))
        add_case(results, "vdc_nan_blocks", not hv.vdc_in_range({"vdc": "nan"}, None, None))
        add_case(results, "vdc_zero_is_readable", hv.vdc_in_range({"vdc": 0.0}, None, None))
        add_case(results, "bp_vdc_only_is_readable", hv.vdc_in_range({"bp_vdc": 315.0}, 300.0, 330.0))
        add_case(results, "legacy_vdc_only_is_readable", hv.vdc_in_range({"vdc": 315.0}, 300.0, 330.0))
        add_case(results, "vdc_below_min_blocks", not hv.vdc_in_range({"bp_vdc": 250.0}, 300.0, None))
        add_case(results, "vdc_above_max_blocks", not hv.vdc_in_range({"bp_vdc": 350.0}, None, 330.0))

        missing_vdc_run = base_run_status()
        missing_vdc_run.pop("bp_vdc")
        add_case(results, "run_status_missing_vdc_blocks", not hv.require_run_status(missing_vdc_run, 1.0, None, None))
        add_case(results, "run_status_bp_vdc_passes", hv.require_run_status(base_run_status("bp_vdc"), 1.0, 300.0, 330.0))
        add_case(results, "run_status_legacy_vdc_passes", hv.require_run_status(base_run_status("vdc"), 1.0, 300.0, 330.0))

        bad_cnt_run = base_run_status()
        bad_cnt_run["bp_bad_cnt"] = 1
        add_case(results, "run_status_bad_counter_blocks", not hv.require_run_status(bad_cnt_run, 1.0, None, None))

        missing_vdc_estop = base_estop_status()
        missing_vdc_estop.pop("bp_vdc")
        add_case(results, "estop_status_missing_vdc_blocks", not hv.require_estop_status(missing_vdc_estop, None, None))
        add_case(results, "estop_status_bp_vdc_passes", hv.require_estop_status(base_estop_status("bp_vdc"), 300.0, 330.0))
        add_case(results, "format_missing_vdc_blank", hv.format_status_vdc({"state": "SAFE"}) == "")
        add_case(results, "format_bp_vdc_value", hv.format_status_vdc({"bp_vdc": 315.1234567}) == "315.123457")
    finally:
        if old_bad is None:
            os.environ.pop("UNOQ_BP_CMD_BAD_BASELINE", None)
        else:
            os.environ["UNOQ_BP_CMD_BAD_BASELINE"] = old_bad

    fails = [res for res in results if not res.ok]
    for res in results:
        state = "PASS" if res.ok else "FAIL"
        print(f"{state} {res.name} {res.detail}".rstrip())
        if not res.ok and res.evidence is not None:
            print(f"  evidence={res.evidence!r}")
    print(f"SUMMARY: PASS={len(results) - len(fails)} FAIL={len(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
