from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.air56b2_fidelity import (
    fidelity_manifest,
    generate_f2_samples,
    generate_f3_samples,
)
from models.air56b2_nameplate_ensemble import generate_air56b2_ensemble
from models.air56b2_starting_regime import (
    generate_starting_regime_calibrations,
    starting_regime_manifest,
)


def derived_seed(master_seed: int, label: str) -> int:
    digest = hashlib.sha256(f"AIR56B2:{master_seed}:{label}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big")


def reference_digest(samples) -> str:
    raw = json.dumps(
        [(int(sample.index), int(sample.seed)) for sample in samples],
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def build_bundle(*, count: int, master_seed: int) -> dict:
    if count < 1:
        raise ValueError("count must be positive")
    f2_seed = derived_seed(master_seed, "F2")
    f3_seed = derived_seed(master_seed, "F3")
    f1_samples = generate_air56b2_ensemble(count, seed=master_seed)
    f1s = generate_starting_regime_calibrations(f1_samples)
    f2 = generate_f2_samples(f1_samples, seed=f2_seed)
    f3 = generate_f3_samples(f1_samples, seed=f3_seed)
    starting = starting_regime_manifest(
        f1_samples,
        f1s,
        master_seed=master_seed,
    )
    fidelity = fidelity_manifest(
        f1_samples,
        f2,
        f3,
        f2_seed=f2_seed,
        f3_seed=f3_seed,
    )
    gates = {
        "starting_regime_pass": starting["status"] == "PASS",
        "fidelity_has_no_hardware_claim": fidelity["hardware_claim"] is False,
        "sample_counts_match": (
            starting["sample_count"] == fidelity["sample_count"] == count
        ),
        "nameplate_is_unchanged": fidelity["nameplate_unchanged"] is True,
    }
    return {
        "schema": "air56b2-fidelity-bundle-v1",
        "status": "PASS" if all(gates.values()) else "FAIL",
        "hardware_claim": False,
        "hardware_identified": False,
        "parameters_measured": False,
        "master_seed": int(master_seed),
        "component_seeds": {"F2": f2_seed, "F3": f3_seed},
        "sample_count": int(count),
        "f1_reference": {
            "schema": "air56b2-nameplate-ensemble-v2",
            "master_seed": int(master_seed),
            "sample_count": int(count),
            "sample_reference_sha256": reference_digest(f1_samples),
        },
        "levels": {
            "F1": "linear_nameplate_constrained_equivalent_circuit",
            "F1S": "nameplate_calibrated_high_slip_loss_extension",
            "F2": "bounded_saturation_temperature_and_loss_mechanical_priors",
            "F3": "bounded_nonideal_inverter_and_sensor_chain_priors",
        },
        "gates": gates,
        "starting_regime": starting,
        "fidelity": fidelity,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic AIR56B2 F1/F1S/F2/F3 simulation bundle."
    )
    parser.add_argument("--count", type=int, default=256)
    parser.add_argument("--seed", type=int, default=560225)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_bundle(count=args.count, master_seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": payload["status"] == "PASS",
                "status": payload["status"],
                "sample_count": payload["sample_count"],
                "output": str(args.output.resolve()),
                "hardware_identified": False,
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
