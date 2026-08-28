from __future__ import annotations

import json

import pytest

from tools.build_air56b2_fidelity_bundle import build_bundle


def test_fidelity_bundle_is_deterministic_aligned_and_json_safe() -> None:
    first = build_bundle(count=3, master_seed=560225)
    second = build_bundle(count=3, master_seed=560225)

    assert first == second
    assert first["schema"] == "air56b2-fidelity-bundle-v1"
    assert first["status"] == "PASS"
    assert first["hardware_claim"] is False
    assert first["sample_count"] == 3
    assert first["starting_regime"]["status"] == "PASS"
    assert first["fidelity"]["nameplate_unchanged"] is True
    assert all(first["gates"].values())
    assert len(first["f1_reference"]["sample_reference_sha256"]) == 64
    json.dumps(first)


def test_fidelity_bundle_rejects_empty_ensemble() -> None:
    with pytest.raises(ValueError):
        build_bundle(count=0, master_seed=1)
