from __future__ import annotations

import json

import pytest

from tools.run_air56b2_protection_fault_matrix import FAULT_CASES, run_fault_matrix


def test_protection_fault_matrix_is_deterministic_and_latched() -> None:
    first = run_fault_matrix(count=2, master_seed=431)
    second = run_fault_matrix(count=2, master_seed=431)

    assert first == second
    assert first["status"] == "PASS"
    assert first["hardware_release_ready"] is False
    assert first["total_fault_case_count"] == 2 * len(FAULT_CASES)
    assert first["summary"]["failed_fault_cases"] == 0
    assert all(first["gates"].values())
    assert all(
        case["checks"]["fault_latched"]
        and case["checks"]["healthy_request_blocked_while_latched"]
        and case["checks"]["explicit_reset_restores_healthy_request"]
        for sample in first["samples"]
        for case in sample["cases"]
    )
    json.dumps(first)


def test_protection_fault_matrix_rejects_empty_sample_set() -> None:
    with pytest.raises(ValueError):
        run_fault_matrix(count=0, master_seed=1)
