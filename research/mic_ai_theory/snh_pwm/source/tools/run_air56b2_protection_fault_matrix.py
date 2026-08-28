from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.air56b2_fidelity import generate_f3_samples
from models.air56b2_nameplate_ensemble import (
    Air56B2Nameplate,
    generate_air56b2_ensemble,
)
from safety.ai_pwm_gateway import (
    AIPwmRequest,
    AIPwmSafetyGateway,
    FaultFlag,
    GatewayLimits,
)
from tools.build_air56b2_fidelity_bundle import derived_seed, reference_digest


FAULT_CASES = (
    ("overcurrent", FaultFlag.OC_FAULT),
    ("undervoltage", FaultFlag.UNDERVOLTAGE_FAULT),
    ("overvoltage", FaultFlag.OVERVOLTAGE_FAULT),
    ("overtemperature", FaultFlag.OVERTEMP_FAULT),
    ("watchdog", FaultFlag.WATCHDOG_FAULT),
    ("nonfinite_current", FaultFlag.NONFINITE_FAULT),
    ("invalid_vector", FaultFlag.INVALID_VECTOR_FAULT),
)


def _limits(f3) -> GatewayLimits:
    nameplate = Air56B2Nameplate()
    start_current_peak_a = (
        math.sqrt(2.0) * nameplate.line_current_a * nameplate.start_current_ratio
    )
    current_envelope_a = 1.05 * start_current_peak_a
    return GatewayLimits(
        t_pwm_s=1.0 / f3.inverter.pwm_frequency_hz,
        dead_time_s=f3.inverter.dead_time_s,
        min_pulse_s=max(2.0e-6, f3.inverter.dead_time_s),
        i_soft_a=current_envelope_a,
        i_trip_a=1.15 * current_envelope_a,
        vdc_min_v=0.70 * f3.inverter.nominal_vdc_v,
        vdc_max_v=1.30 * f3.inverter.nominal_vdc_v,
        max_switch_events_per_window=1000,
        switch_window_steps=8,
    )


def _healthy_request(limits: GatewayLimits, nominal_vdc_v: float) -> AIPwmRequest:
    return AIPwmRequest(
        vector_id=1,
        dwell_s=limits.t_pwm_s,
        confidence=1.0,
        predicted_i_abs=0.0,
        measured_i_abs=0.0,
        vdc=nominal_vdc_v,
        tj_c=25.0,
        predicted_risk=0.0,
        watchdog_ok=True,
    )


def _fault_request(
    case_id: str,
    healthy: AIPwmRequest,
    limits: GatewayLimits,
) -> AIPwmRequest:
    if case_id == "overcurrent":
        return replace(healthy, measured_i_abs=math.nextafter(limits.i_trip_a, math.inf))
    if case_id == "undervoltage":
        return replace(healthy, vdc=limits.vdc_min_v)
    if case_id == "overvoltage":
        return replace(healthy, vdc=limits.vdc_max_v)
    if case_id == "overtemperature":
        return replace(healthy, tj_c=limits.tj_trip_c)
    if case_id == "watchdog":
        return replace(healthy, watchdog_ok=False)
    if case_id == "nonfinite_current":
        return replace(healthy, measured_i_abs=float("nan"))
    if case_id == "invalid_vector":
        return replace(healthy, vector_id=8)
    raise ValueError(f"unsupported fault case: {case_id}")


def _run_case(f3, *, case_id: str, expected_flag: FaultFlag) -> dict[str, Any]:
    limits = _limits(f3)
    gateway = AIPwmSafetyGateway(limits)
    nominal_vdc = f3.adc.quantize_voltage(f3.inverter.nominal_vdc_v)
    healthy = _healthy_request(limits, nominal_vdc)
    precondition = gateway.evaluate(healthy)
    injected = gateway.evaluate(_fault_request(case_id, healthy, limits))
    blocked = gateway.evaluate(healthy)
    gateway.clear_fault_latch()
    recovered = gateway.evaluate(healthy)
    checks = {
        "healthy_precondition_accepted": precondition.accepted and precondition.pwm_enabled,
        "expected_fault_flag_present": expected_flag in injected.fault_flags,
        "fault_request_rejected": not injected.accepted,
        "pwm_disabled_on_critical_fault": not injected.pwm_enabled,
        "all_gates_off_on_critical_fault": not any(
            (
                injected.gates.AH,
                injected.gates.AL,
                injected.gates.BH,
                injected.gates.BL,
                injected.gates.CH,
                injected.gates.CL,
            )
        ),
        "fault_latched": injected.fault_latched,
        "healthy_request_blocked_while_latched": (
            not blocked.accepted and not blocked.pwm_enabled and blocked.fault_latched
        ),
        "explicit_reset_restores_healthy_request": (
            recovered.accepted and recovered.pwm_enabled and not recovered.fault_latched
        ),
    }
    return {
        "case_id": case_id,
        "expected_fault_flag": expected_flag.name,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "injected_fault_flags": int(injected.fault_flags),
        "injected_fallback_reason": injected.fallback_reason,
    }


def run_fault_matrix(*, count: int, master_seed: int) -> dict[str, Any]:
    if count < 1:
        raise ValueError("count must be positive")
    f1_samples = generate_air56b2_ensemble(count, seed=master_seed)
    f3_seed = derived_seed(master_seed, "F3")
    f3_samples = generate_f3_samples(f1_samples, seed=f3_seed)
    samples = []
    for f1, f3 in zip(f1_samples, f3_samples):
        cases = [
            _run_case(f3, case_id=case_id, expected_flag=expected_flag)
            for case_id, expected_flag in FAULT_CASES
        ]
        samples.append(
            {
                "index": f1.index,
                "f1_seed": f1.seed,
                "f3_seed": f3.seed,
                "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
                "cases": cases,
            }
        )
    all_cases = [case for sample in samples for case in sample["cases"]]
    gates = {
        "all_fault_cases_passed": all(case["status"] == "PASS" for case in all_cases),
        "every_fault_tested_on_every_sample": len(all_cases)
        == count * len(FAULT_CASES),
        "critical_faults_disable_all_gates": all(
            case["checks"]["all_gates_off_on_critical_fault"] for case in all_cases
        ),
        "fault_latch_requires_explicit_reset": all(
            case["checks"]["healthy_request_blocked_while_latched"]
            and case["checks"]["explicit_reset_restores_healthy_request"]
            for case in all_cases
        ),
        "hardware_claim_absent": True,
    }
    return {
        "schema": "air56b2-protection-fault-matrix-v1",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "evidence_level": "host_gateway_sil_only",
        "hardware_claim": False,
        "hardware_identified": False,
        "hardware_release_ready": False,
        "master_seed": int(master_seed),
        "component_seeds": {"F3": f3_seed},
        "sample_count": len(samples),
        "fault_case_count_per_sample": len(FAULT_CASES),
        "total_fault_case_count": len(all_cases),
        "f1_reference": {
            "schema": "air56b2-nameplate-ensemble-v2",
            "master_seed": int(master_seed),
            "sample_count": len(f1_samples),
            "sample_reference_sha256": reference_digest(f1_samples),
        },
        "fault_cases": [case_id for case_id, _ in FAULT_CASES],
        "gates": gates,
        "summary": {
            "passed_samples": sum(sample["status"] == "PASS" for sample in samples),
            "failed_samples": sum(sample["status"] != "PASS" for sample in samples),
            "passed_fault_cases": sum(case["status"] == "PASS" for case in all_cases),
            "failed_fault_cases": sum(case["status"] != "PASS" for case in all_cases),
        },
        "samples": samples,
        "limitations": [
            "This is software-in-the-loop validation of the host gateway, not an IPM propagation-time model.",
            "Gate-driver UVLO, DESAT, analog comparator timing, relay behavior, and MCU reset timing require HIL or bench measurements.",
            "Passing this matrix does not authorize high-voltage commissioning.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run AIR56B2/F3 critical-fault checks through the protected PWM gateway."
    )
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--master-seed", type=int, default=560225)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run_fault_matrix(count=args.count, master_seed=args.master_seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": payload["status"] == "PASS",
                "status": payload["status"],
                "sample_count": payload["sample_count"],
                "fault_case_count": payload["total_fault_case_count"],
                "output": str(args.output.resolve()),
                "hardware_release_ready": False,
            }
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
