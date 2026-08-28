from __future__ import annotations

import json
import math

import pytest

from models.air56b2_nameplate_ensemble import (
    Air56B2Nameplate,
    derive_nameplate,
    generate_air56b2_ensemble,
)
from models.air56b2_starting_regime import (
    StartingRegimeAssumptions,
    evaluate_starting_regime,
    generate_starting_regime_calibrations,
    starting_regime_manifest,
    starting_torque_scale_for_speed,
)
from models.induction_motor_alpha_beta import (
    AlphaBetaInductionMotorModel,
    AlphaBetaMotorParams,
    AlphaBetaMotorState,
)


def test_f1s_preserves_rated_point_and_matches_starting_ratios() -> None:
    nameplate = Air56B2Nameplate()
    derived = derive_nameplate(nameplate)
    samples = generate_air56b2_ensemble(8, seed=560225)
    calibrations = generate_starting_regime_calibrations(samples)

    for sample, calibration in zip(samples, calibrations):
        rated = evaluate_starting_regime(sample, slip=derived.rated_slip)
        start = evaluate_starting_regime(sample, slip=1.0)
        assert rated.torque_scale == pytest.approx(1.0)
        assert rated.additional_high_slip_loss_w == pytest.approx(0.0, abs=1e-10)
        assert start.current_ratio == pytest.approx(nameplate.start_current_ratio, rel=0.01)
        assert start.corrected_torque_ratio == pytest.approx(
            nameplate.start_torque_ratio,
            rel=1e-12,
        )
        assert start.additional_high_slip_loss_w > 0.0
        assert calibration.corrected_max_torque_ratio == pytest.approx(
            nameplate.max_torque_ratio,
            rel=StartingRegimeAssumptions().maximum_torque_relative_tolerance,
        )
        assert calibration.base_start_torque_ratio > calibration.corrected_start_torque_ratio


def test_speed_mapping_applies_start_correction_only_at_positive_high_slip() -> None:
    sample = generate_air56b2_ensemble(1, seed=8128)[0]
    nameplate = Air56B2Nameplate()
    synchronous_speed = 2.0 * math.pi * nameplate.frequency_hz / nameplate.pole_pairs
    at_start = starting_torque_scale_for_speed(
        sample,
        electrical_frequency_hz=nameplate.frequency_hz,
        mechanical_speed_rad_s=0.0,
    )
    above_synchronous = starting_torque_scale_for_speed(
        sample,
        electrical_frequency_hz=nameplate.frequency_hz,
        mechanical_speed_rad_s=1.01 * synchronous_speed,
    )
    stopped_supply = starting_torque_scale_for_speed(
        sample,
        electrical_frequency_hz=0.0,
        mechanical_speed_rad_s=0.0,
    )
    assert at_start == pytest.approx(
        nameplate.start_torque_ratio / sample.rated_prediction.start_torque_ratio
    )
    assert above_synchronous == 1.0
    assert stopped_supply == 1.0


def test_starting_regime_manifest_discloses_assumption_and_no_hardware_claim() -> None:
    samples = generate_air56b2_ensemble(3, seed=7)
    calibrations = generate_starting_regime_calibrations(samples)
    payload = starting_regime_manifest(samples, calibrations, master_seed=7)

    assert payload["status"] == "PASS"
    assert payload["hardware_claim"] is False
    assert payload["hardware_identified"] is False
    assert payload["parameters_measured"] is False
    assert payload["gates"]["rated_operating_point_preserved"] is True
    assert "transition_exponent" in payload["parameter_provenance"][
        "modeling_assumptions_not_on_nameplate"
    ]
    assert payload["parameter_provenance"]["unique_physical_identification_claimed"] is False
    json.dumps(payload)


def test_dynamic_plant_applies_explicit_torque_scale_without_changing_flux_step() -> None:
    sample = generate_air56b2_ensemble(1, seed=91)[0]
    params = AlphaBetaMotorParams.from_motor_params(sample.motor)
    state = AlphaBetaMotorState(
        psi_s_alpha=0.20,
        psi_s_beta=0.04,
        psi_r_alpha=0.11,
        psi_r_beta=-0.03,
    )
    full = AlphaBetaInductionMotorModel(params, state).next_state(
        10.0,
        -5.0,
        0.0,
        1e-6,
        electromagnetic_torque_scale=1.0,
    )
    reduced = AlphaBetaInductionMotorModel(params, state).next_state(
        10.0,
        -5.0,
        0.0,
        1e-6,
        electromagnetic_torque_scale=0.4,
    )

    assert reduced.state.psi_s_alpha == pytest.approx(full.state.psi_s_alpha)
    assert reduced.state.psi_s_beta == pytest.approx(full.state.psi_s_beta)
    assert reduced.state.psi_r_alpha == pytest.approx(full.state.psi_r_alpha)
    assert reduced.state.psi_r_beta == pytest.approx(full.state.psi_r_beta)
    assert reduced.torque_nm == pytest.approx(0.4 * full.torque_nm)
    assert reduced.state.omega_m == pytest.approx(0.4 * full.state.omega_m)

    with pytest.raises(ValueError, match="torque_scale"):
        AlphaBetaInductionMotorModel(params, state).next_state(
            0.0,
            0.0,
            0.0,
            1e-6,
            electromagnetic_torque_scale=1.1,
        )
