"""Pairing and publication regressions; no matrix run or runner modifications."""

from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from itertools import permutations
import json
import math
import sys

import numpy as np
import pytest

from tools import run_air56b2_dynamic_power as runner


def _row(method, *, work_j=100.0, loss_j=25.0, stored_j=5.0, **changes):
    row = {
        "case": "synthetic_motor_k0",
        "method": method,
        "observer": "current",
        "disturbance": False,
        "speed_fraction": 0.3,
        "noise_seed": 730,
        "duration_s": 6.0,
        "dt_s": 1e-4,
        "plant_substeps": 1,
        "completed_steps": 60000,
        "checks": {
            "complete": True,
            "observer_not_clipped": True,
            "current_within_3p1a": True,
            "settled_speed_mae_below_3rad_s": True,
            "energy_balance": True,
        },
        "status": "PASS",
        "fault": None,
        "probe_complete": True,
        "probe_reason": None,
        "final_id_a": 0.83 if method == "fixed" else 0.7,
        "final_phase": "fixed" if method == "fixed" else "committed",
        "speed_mae_rad_s": 0.01,
        "peak_current_a": 2.0,
        "energy": {
            "input_j": math.fsum((work_j, loss_j, stored_j)),
            "loss_j": loss_j,
            "shaft_work_j": work_j,
            "stored_change_j": stored_j,
            "stator_copper_j": 0.4 * loss_j,
            "rotor_copper_j": 0.3 * loss_j,
            "core_j": 0.2 * loss_j,
            "friction_j": 0.1 * loss_j,
        },
        "probe_events": (),
        "trace": [],
    }
    row.update(changes)
    if "completed_steps" not in changes:
        row["completed_steps"] = round(row["duration_s"] / row["dt_s"])
    return row


def _pair(**changes):
    return [_row("fixed", **changes), _row("fit", loss_j=20.0, **changes)]


def test_complete_same_protocol_pair_is_eligible_and_does_not_mutate_rows():
    rows = _pair()
    before = deepcopy(rows)
    result = runner.paired_comparison(rows)
    assert rows == before
    assert len(result) == 1
    pair = result[0]
    assert pair["eligible"] is True
    assert pair["case"] == "synthetic_motor_k0"
    assert pair["observer"] == "current"
    assert pair["input_saving_j"] == 5.0
    assert pair["loss_saving_j"] == 5.0
    assert pair["work_delta_j"] == pair["stored_delta_j"] == 0.0


@pytest.mark.parametrize("method", ["fixed", "fit"])
@pytest.mark.parametrize(
    "failed_check",
    [
        "complete",
        "observer_not_clipped",
        "current_within_3p1a",
        "settled_speed_mae_below_3rad_s",
        "energy_balance",
    ],
)
def test_failed_or_partial_trials_remain_visible_but_ineligible(method, failed_check):
    rows = _pair()
    failed = next(row for row in rows if row["method"] == method)
    failed["checks"][failed_check] = False
    failed["status"] = "FAIL"
    if failed_check == "complete":
        failed["completed_steps"] -= 1
        failed["fault"] = "synthetic_early_abort"
    pairs = runner.paired_comparison(rows)
    assert len(pairs) == 1
    assert pairs[0]["eligible"] is False
    assert pairs[0]["input_saving_j"] == 5.0


@pytest.mark.parametrize(
    "phase",
    [
        "waiting",
        "baseline",
        "low",
        "high",
        "baseline_repeat",
        "candidateverify",
        "rollback",
    ],
)
def test_complete_simulation_with_unfinished_probe_is_ineligible(phase):
    rows = _pair()
    rows[1].update(probe_complete=False, final_phase=phase)
    assert rows[1]["status"] == "PASS" and rows[1]["checks"]["complete"]
    assert runner.paired_comparison(rows)[0]["eligible"] is False


@pytest.mark.parametrize(
    "reason", ["insufficient_improvement", "baseline_repeat_drift", "stage_timeout:low"]
)
def test_completed_rollback_is_not_dropped_as_an_unsuccessful_optimization(reason):
    rows = [_row("fixed"), _row("fit")]
    rows[1].update(final_phase="rejected", final_id_a=0.83, probe_reason=reason)
    pair = runner.paired_comparison(rows)[0]
    assert pair["eligible"] is True
    assert pair["input_saving_j"] == 0.0


def test_complete_case_gate_does_not_select_only_positive_savings():
    rows = [_row("fixed"), _row("fit", loss_j=30.0)]
    pair = runner.paired_comparison(rows)[0]
    assert pair["eligible"] is True
    assert pair["input_saving_j"] == pair["loss_saving_j"] == -5.0


@pytest.mark.parametrize("methods", [[], ["fixed"], ["fit"]])
def test_missing_counterpart_cannot_create_a_complete_pair(methods):
    assert runner.paired_comparison([_row(method) for method in methods]) == []


@pytest.mark.parametrize("method", ["fixed", "fit"])
@pytest.mark.parametrize("identical", [False, True])
def test_duplicate_methods_raise_instead_of_overwriting_or_selecting_a_winner(
    method, identical
):
    rows = _pair()
    duplicate = deepcopy(next(row for row in rows if row["method"] == method))
    if not identical:
        duplicate["energy"]["input_j"] -= 100.0
        duplicate["status"] = "FAIL"
    for ordering in permutations([*rows, duplicate]):
        with pytest.raises(ValueError, match="duplicate"):
            runner.paired_comparison(list(ordering))


def test_duplicate_unpaired_rows_are_also_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        runner.paired_comparison([_row("fixed"), _row("fixed")])


PROTOCOL_CHANGES = [
    ("case", "different_motor_k0"),
    ("disturbance", True),
    ("speed_fraction", 0.7),
    ("observer", "voltage"),
    ("dt_s", 2e-4),
    ("duration_s", 8.0),
    ("noise_seed", 731),
    ("plant_substeps", 4),
]


@pytest.mark.parametrize("field,value", PROTOCOL_CHANGES)
def test_mixed_protocol_or_noise_seed_cannot_supply_each_others_counterpart(
    field, value
):
    rows = [_row("fixed"), _row("fit", **{field: value})]
    assert runner.paired_comparison(rows) == []
    assert runner.paired_comparison(list(reversed(rows))) == []


@pytest.mark.parametrize("field,value", PROTOCOL_CHANGES)
def test_complete_pairs_from_different_protocols_are_never_cross_paired(field, value):
    rows = [
        *_pair(),
        _row("fixed", work_j=1000.0, loss_j=200.0, **{field: value}),
        _row("fit", work_j=1000.0, loss_j=180.0, **{field: value}),
    ]
    expected = runner.paired_comparison(rows)
    assert len(expected) == 2
    assert all(pair["eligible"] is True for pair in expected)
    assert sorted(pair["input_saving_j"] for pair in expected) == [5.0, 20.0]
    for ordering in permutations(rows):
        assert runner.paired_comparison(list(ordering)) == expected


@pytest.mark.parametrize("legacy_methods", [("fixed",), ("fit",), ("fixed", "fit")])
def test_legacy_rows_without_plant_substeps_match_explicit_one(legacy_methods):
    rows = _pair()
    expected = runner.paired_comparison(rows)
    for row in rows:
        if row["method"] in legacy_methods:
            del row["plant_substeps"]
    before = deepcopy(rows)
    assert runner.paired_comparison(rows) == expected
    assert rows == before
    assert expected[0]["eligible"] is True


@pytest.mark.parametrize("legacy_method", ["fixed", "fit"])
def test_legacy_one_substep_row_cannot_pair_with_multiple_substeps(legacy_method):
    rows = _pair(plant_substeps=4)
    del next(row for row in rows if row["method"] == legacy_method)["plant_substeps"]
    assert runner.paired_comparison(rows) == []
    assert runner.paired_comparison(list(reversed(rows))) == []


@pytest.mark.parametrize("method", ["fixed", "fit"])
def test_legacy_and_explicit_one_substep_duplicates_are_rejected(method):
    rows = _pair()
    legacy = _row(method)
    del legacy["plant_substeps"]
    with pytest.raises(ValueError, match="duplicate"):
        runner.paired_comparison([*rows, legacy])


@pytest.mark.parametrize("base_work_j", [-100.0, -0.5, 0.0, 0.5, 100.0])
@pytest.mark.parametrize("direction", [-1.0, 1.0])
def test_work_matching_uses_absolute_signed_work_and_one_joule_floor(
    base_work_j, direction
):
    tolerance = 0.01 * max(abs(base_work_j), 1.0)
    for scale, eligible in [(0.5, True), (1.5, False)]:
        rows = [
            _row("fixed", work_j=base_work_j),
            _row("fit", work_j=base_work_j + direction * scale * tolerance),
        ]
        pair = runner.paired_comparison(rows)[0]
        assert pair["eligible"] is eligible
        assert pair["work_delta_j"] == pytest.approx(direction * scale * tolerance)


@pytest.mark.parametrize("base_work_j", [-100.0, 0.0, 100.0])
@pytest.mark.parametrize("direction", [-1.0, 1.0])
def test_exact_work_tolerance_boundary_is_inclusive(base_work_j, direction):
    tolerance = 0.01 * max(abs(base_work_j), 1.0)
    rows = [
        _row("fixed", work_j=base_work_j),
        _row("fit", work_j=base_work_j + direction * tolerance),
    ]
    assert runner.paired_comparison(rows)[0]["eligible"] is True


@pytest.mark.parametrize("base_work_j", [-100.0, 0.0, 100.0])
@pytest.mark.parametrize("work_direction", [-1.0, 1.0])
@pytest.mark.parametrize("stored_delta_j", [-3.0, 3.0])
@pytest.mark.parametrize("loss_saving_j", [-2.0, 2.0])
def test_signed_work_and_storage_preserve_the_paired_energy_identity(
    base_work_j, work_direction, stored_delta_j, loss_saving_j
):
    work_delta_j = work_direction * 0.005 * max(abs(base_work_j), 1.0)
    base = _row("fixed", work_j=base_work_j, loss_j=30.0, stored_j=-1.0)
    adaptive = _row(
        "fit",
        work_j=base_work_j + work_delta_j,
        loss_j=30.0 - loss_saving_j,
        stored_j=-1.0 + stored_delta_j,
    )
    pair = runner.paired_comparison([base, adaptive])[0]
    assert pair["eligible"] is True
    assert pair["work_delta_j"] == pytest.approx(work_delta_j)
    assert pair["stored_delta_j"] == pytest.approx(stored_delta_j)
    assert pair["loss_saving_j"] == pytest.approx(loss_saving_j)
    # E_fixed - E_fit = loss saving - added shaft work - added stored energy.
    assert pair["input_saving_j"] == pytest.approx(
        pair["loss_saving_j"] - pair["work_delta_j"] - pair["stored_delta_j"],
        abs=1e-12,
    )


@pytest.mark.parametrize("complete", [np.bool_(False), np.bool_(True)])
def test_numpy_eligibility_inputs_produce_native_json_booleans(complete):
    rows = _pair()
    rows[1]["probe_complete"] = complete
    for row in rows:
        row["energy"] = {
            name: np.float64(value) for name, value in row["energy"].items()
        }
    pairs = runner.paired_comparison(rows)
    assert type(pairs[0]["eligible"]) is bool
    assert pairs[0]["eligible"] is bool(complete)
    # The CLI's final stdout summary intentionally has no custom default.
    assert json.loads(json.dumps({"pairs": pairs}, allow_nan=False))["pairs"] == pairs


@pytest.mark.parametrize(
    "scalar,expected,native_type",
    [
        (np.bool_(True), True, bool),
        (np.bool_(False), False, bool),
        (np.int32(-4), -4, int),
        (np.int64(7), 7, int),
        (np.uint64(2**63), 2**63, int),
        (np.float32(1.25), 1.25, float),
        (np.float64(-2.5), -2.5, float),
    ],
)
def test_cli_json_scalar_converts_numpy_values_without_stringifying(
    scalar, expected, native_type
):
    converted = runner._json_scalar(scalar)
    assert type(converted) is native_type
    assert converted == expected
    decoded = json.loads(
        json.dumps({"value": scalar}, default=runner._json_scalar, allow_nan=False)
    )
    assert type(decoded["value"]) is native_type
    assert decoded["value"] == expected


@pytest.mark.parametrize(
    "bad", [np.float32(math.nan), np.float32(math.inf), np.float64(-math.inf)]
)
def test_cli_json_scalar_cannot_bypass_nonfinite_json_rejection(bad):
    with pytest.raises(ValueError):
        json.dumps({"value": bad}, default=runner._json_scalar, allow_nan=False)


@pytest.mark.parametrize(
    "bad", [object(), {1, 2}, np.array([1, 2]), np.complex128(1 + 2j)]
)
def test_cli_json_scalar_rejects_unsupported_objects_instead_of_silently_stringifying(
    bad,
):
    with pytest.raises(TypeError, match="unsupported JSON type"):
        json.dumps({"value": bad}, default=runner._json_scalar, allow_nan=False)


@dataclass(frozen=True)
class _CliParams:
    resistance_ohm: float = 1.0


class _InlineExecutor:
    """Exercise main/_run_job without launching expensive simulation workers."""

    def __init__(self, max_workers):
        assert max_workers == 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future


@pytest.mark.parametrize("substeps_option", [None, 4])
def test_cli_main_publishes_numpy_scalar_rows_events_and_valid_hashes(
    tmp_path, monkeypatch, capsys, substeps_option
):
    out = tmp_path / "smoke"
    expected_substeps = 1 if substeps_option is None else substeps_option
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_air56b2_dynamic_power.py",
            "--out",
            str(out),
            "--smoke",
            "--workers",
            "1",
            "--models",
            "1",
            "--duration",
            "6",
            "--dt",
            "0.0001",
            "--seed",
            "92061",
            "--observer",
            "current",
            "--speeds",
            "0.3",
            "0.7",
            *(
                []
                if substeps_option is None
                else ["--plant-substeps", str(substeps_option)]
            ),
        ],
    )
    monkeypatch.setattr(runner, "ProcessPoolExecutor", _InlineExecutor)
    monkeypatch.setattr(runner, "as_completed", lambda futures: reversed(futures))
    monkeypatch.setattr(
        runner, "source_hashes", lambda: {"frozen_source.py": "unchanged"}
    )
    monkeypatch.setattr(
        runner,
        "build_cases",
        lambda count, seed: [("synthetic_motor_k0", _CliParams(), _CliParams())],
    )

    def fake_trial(
        plant,
        control,
        *,
        method,
        disturbance,
        duration_s,
        dt_s,
        observer_kind,
        speed_fraction,
        plant_substeps,
    ):
        assert isinstance(plant, _CliParams) and isinstance(control, _CliParams)
        assert plant_substeps == expected_substeps
        row = _row(
            method,
            loss_j=25.0 if method == "fixed" else 20.0,
            disturbance=disturbance,
            duration_s=duration_s,
            dt_s=dt_s,
            observer=observer_kind,
            speed_fraction=speed_fraction,
            plant_substeps=plant_substeps,
        )
        row["checks"] = {key: np.bool_(value) for key, value in row["checks"].items()}
        row["probe_complete"] = np.bool_(True)
        row["completed_steps"] = np.int64(row["completed_steps"])
        row["peak_current_a"] = np.float32(2.0)
        row["energy"] = {
            name: np.float64(value) for name, value in row["energy"].items()
        }
        row["probe_events"] = (
            {"kind": "measurement", "measurement": {"power_w": np.float32(1.25)}},
        )
        return row

    monkeypatch.setattr(runner, "run_trial", fake_trial)
    runner.main()

    study = json.loads((out / "study.json").read_text(encoding="utf-8"))
    protocol = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert protocol["seed"] == 92061
    assert protocol["speeds"] == [0.3]
    assert protocol["observer"] == "current"
    assert protocol["plant_substeps"] == expected_substeps
    assert len(study["rows"]) == 2
    assert [row["method"] for row in study["rows"]] == ["fit", "fixed"]
    assert len(study["pairs"]) == 1 and study["pairs"][0]["eligible"] is True
    for row in study["rows"]:
        assert all(type(value) is bool for value in row["checks"].values())
        assert row["probe_complete"] is True
        assert type(row["completed_steps"]) is int
        assert row["completed_steps"] == 60000
        assert row["plant_substeps"] == expected_substeps
        assert row["peak_current_a"] == 2.0
        assert row["probe_events"][0]["measurement"]["power_w"] == 1.25
    assert manifest["sources"] == {"frozen_source.py": "unchanged"}
    assert set(manifest["outputs"]) == {"study.json", "protocol.json"}
    for name, checksum in manifest["outputs"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == checksum
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert summary["pairs"] == study["pairs"]


@pytest.mark.parametrize("method", ["fixed", "fit"])
@pytest.mark.parametrize("plant_substeps", [1, 4])
def test_short_real_trial_has_native_check_booleans_and_serializable_output(
    method, plant_substeps
):
    _, plant, control = runner.build_cases(1, 92061)[0]
    row = runner.run_trial(
        plant,
        control,
        method=method,
        duration_s=0.001,
        dt_s=1e-4,
        plant_substeps=plant_substeps,
    )
    assert row["completed_steps"] == 10
    assert row["plant_substeps"] == plant_substeps
    assert row["checks"]["complete"] is True
    assert all(type(value) is bool for value in row["checks"].values())
    assert row["probe_complete"] is (method == "fixed")
    assert row["final_phase"] == ("fixed" if method == "fixed" else "waiting")
    assert (
        json.loads(json.dumps(row, default=runner._json_scalar, allow_nan=False))[
            "checks"
        ]
        == row["checks"]
    )
