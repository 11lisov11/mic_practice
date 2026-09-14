from dataclasses import replace
import json

import numpy as np
import pytest
import torch

from control.air56b2_measured_loss_fit import ProbeMeasurement
from models.air56b2_loss_thermal import evaluate_operating_point, loss_params_from_fidelity_bundle, MotorThermalState
from models.air56b2_measurement_context import (
    MeasurementContextPolicy, MeasurementProtocol, accept_verification,
    context_features, window_rejection_reason,
)
from tools.run_air56b2_measurement_adaptation import (
    REPO, CONDITIONS, build_cases, evaluate_shaft_point, observe,
    score_cases, split_indices, state_digest, train_policy,
    annotate_common_cases, _cluster_ci,
)


def _probes():
    protocol = MeasurementProtocol()
    return [ProbeMeasurement(id_a, 30.0 * id_a**2 + 10.0 / id_a**2 + 100.0,
                             1.5, 130.0) for id_a in protocol.sequence]


def test_context_is_invariant_to_common_power_offset():
    probes = _probes()
    shifted = [replace(p, power_w=p.power_w + 5000.0) for p in probes]
    assert np.array_equal(context_features(probes, 100.0, MeasurementProtocol()),
                          context_features(shifted, 100.0, MeasurementProtocol()))


def test_drift_gate_repeats_same_excitation_not_different_flux_probes():
    probes = _probes()
    assert window_rejection_reason(probes, MeasurementProtocol()) is None
    probes[-1] = replace(probes[-1], power_w=probes[-1].power_w + 8.0)
    assert window_rejection_reason(probes, MeasurementProtocol()) == "repeat_probe_drift"


def test_reordered_probe_window_is_not_silently_used():
    probes = _probes()
    probes[1], probes[2] = probes[2], probes[1]
    with pytest.raises(ValueError, match="sequence"):
        context_features(probes, 100.0, MeasurementProtocol())


def test_verification_checks_measured_improvement_and_limits():
    config = MeasurementProtocol()
    baseline = _probes()[0]
    better = replace(baseline, id_a=0.7, power_w=baseline.power_w - 3.0)
    assert accept_verification(baseline, better, config)
    assert not accept_verification(baseline, replace(better, power_w=baseline.power_w - 1.0), config)
    assert not accept_verification(baseline, replace(better, current_peak_a=4.0), config)
    assert not accept_verification(baseline, replace(better, voltage_peak_v=190.0), config)


def test_motor_splits_are_disjoint_and_reproducible():
    first = split_indices(256, 96, 32, 32, 32)
    assert first == split_indices(256, 96, 32, 32, 32)
    all_indices = sum(first.values(), [])
    assert len(all_indices) == len(set(all_indices)) == 192
    with pytest.raises(ValueError):
        split_indices(10, 4, 4, 4, 4)


@pytest.fixture(scope="module")
def bundle():
    return json.loads((REPO / "artifacts/air56b2_fidelity_bundle.json").read_text(encoding="utf-8"))


def test_shaft_torque_includes_mechanical_losses_in_required_iq(bundle):
    params, _ = loss_params_from_fidelity_bundle(bundle, 0)
    thermal = MotorThermalState(35.0, 40.0)
    corrected = evaluate_shaft_point(params, 200.0, 0.4, 0.83, thermal)
    legacy = evaluate_operating_point(params, speed_rad_s=200.0, torque_nm=0.4,
                                      id_a=0.83, thermal_state=thermal)
    assert corrected.iq_a > legacy.iq_a
    effective_torque = 1.5 * params.pole_pairs * (corrected.effective_lm_h /
                         (corrected.effective_lm_h + params.llr_h)) * corrected.flux_wb * corrected.iq_a
    assert effective_torque == pytest.approx(0.4 + corrected.mechanical_w / 200.0)


def test_corrected_voltage_channels_close_core_free_power_balance(bundle):
    params, _ = loss_params_from_fidelity_bundle(bundle, 4)
    thermal = MotorThermalState(60.0, 95.0)
    speed, torque, id_a = 210.0, 0.5, 0.75
    point = evaluate_shaft_point(params, speed, torque, id_a, thermal)
    lm = point.effective_lm_h
    lr = lm + params.llr_h
    leakage = params.lls_h + lm * params.llr_h / lr
    rs = params.rs_ref_ohm * (1 + params.stator_temp_coeff_per_c * (thermal.stator_temp_c - params.reference_temp_c))
    omega_e = point.electrical_frequency_hz * 2 * np.pi
    vd = rs * id_a - omega_e * leakage * point.iq_a
    vq = rs * point.iq_a + omega_e * (leakage * id_a + lm / lr * point.flux_wb)
    assert point.phase_voltage_peak_v == pytest.approx(np.hypot(vd, vq))
    electromagnetic_power = torque * speed + point.mechanical_w
    assert 1.5 * (vd * id_a + vq * point.iq_a) == pytest.approx(
        electromagnetic_power + point.stator_copper_w + point.rotor_copper_w, abs=1e-10)


def test_training_replay_and_single_probe_ablation():
    torch.set_num_threads(2)
    rng = np.random.default_rng(20)
    x = rng.normal(size=(20, 9)).astype(np.float32)
    y = np.linspace(0.0, 1.0, 20).astype(np.float32)
    a, _ = train_policy(x[:12], y[:12], x[12:], y[12:], seed=123, epochs=8, device="cpu")
    b, _ = train_policy(x[:12], y[:12], x[12:], y[12:], seed=123, epochs=8, device="cpu")
    assert state_digest(a) == state_digest(b)
    model = MeasurementContextPolicy(single_probe=True)
    altered = x.copy()
    altered[:, 3:] = 1000.0
    with torch.no_grad():
        assert torch.equal(model(torch.from_numpy(x)), model(torch.from_numpy(altered)))


def test_common_random_measurements_and_complete_scoring(bundle):
    protocol = MeasurementProtocol()
    cases = build_cases(bundle, [0], protocol, CONDITIONS[1], grid_points=9)
    assert len(cases) == 24
    first = observe(cases[0], CONDITIONS[1], protocol, 42)
    second = observe(cases[0], CONDITIONS[1], protocol, 42)
    assert first[0] == second[0]
    assert np.array_equal(first[1], second[1])
    states = {"context": MeasurementContextPolicy().state_dict(),
              "single": MeasurementContextPolicy(single_probe=True).state_dict()}
    rows = score_cases(cases, CONDITIONS[1], protocol, states, realization=42, seed=123)
    assert len(rows) == 24 * 5
    assert {row["method"] for row in rows} == {"fixed", "best_probe", "analytic_fit", "neural_context", "neural_single"}
    assert all(row["measurement_window_budget"] <= 5 for row in rows)
    assert all(row["loss_saving_pct"] == 0.0 for row in rows if row["method"] == "fixed" and not row["stop_requested"])


def test_infeasible_test_windows_are_retained(bundle):
    protocol = MeasurementProtocol(current_limit_a=0.001)
    cases = build_cases(bundle, [0], protocol, CONDITIONS[0], grid_points=5)
    states = {"context": MeasurementContextPolicy().state_dict(),
              "single": MeasurementContextPolicy(single_probe=True).state_dict()}
    rows = score_cases(cases, CONDITIONS[0], protocol, states, realization=0, seed=0)
    assert len(rows) == 120
    assert all(not row["accepted"] for row in rows)
    assert all(row["window_rejection"] == "measured_probe_overcurrent" for row in rows)
    assert all(row["stop_requested"] for row in rows)
    assert all(row["loss_saving_pct"] is None for row in rows)


def test_voltage_guard_uses_observed_dc_bus(bundle):
    protocol = MeasurementProtocol()
    cases = build_cases(bundle, [0], protocol, CONDITIONS[-1], grid_points=5)
    case = cases[0]
    condition = replace(CONDITIONS[-1], voltage_noise_v=0.0)
    _, _, _, observed_protocol = observe(case, condition, protocol, 0)
    assert observed_protocol.voltage_limit_v == pytest.approx(min(
        protocol.voltage_limit_v, 0.95 * case.params.vdc_v / np.sqrt(3.0)))
    assert observed_protocol.voltage_limit_v < protocol.voltage_limit_v


def test_bootstrap_uses_row_weighting_for_unequal_clusters():
    rows = [{"sample_index": motor, "value": 0.0} for motor in range(9) for _ in range(20)]
    rows.append({"sample_index": 9, "value": 100.0})
    lo, hi = _cluster_ci(rows, "value", replicates=5000)
    assert lo <= 100.0 / 181 <= hi
    assert hi < 3.0  # Equal weighting of motor means would put this near 30.


def test_same_measurements_are_used_for_each_training_seed(bundle):
    protocol = MeasurementProtocol()
    cases = build_cases(bundle, [0], protocol, CONDITIONS[1], grid_points=5)
    states = {"context": MeasurementContextPolicy().state_dict(),
              "single": MeasurementContextPolicy(single_probe=True).state_dict()}
    first = score_cases(cases, CONDITIONS[1], protocol, states, realization=10, seed=1)
    second = score_cases(cases, CONDITIONS[1], protocol, states, realization=10, seed=999)
    assert [{k: v for k, v in r.items() if k != "seed"} for r in first] == [
        {k: v for k, v in r.items() if k != "seed"} for r in second]
    annotate_common_cases(first)
    first[1]["selected_feasible"] = False
    annotate_common_cases(first)
    assert all(not row["common_comparison_eligible"] for row in first[:5])
