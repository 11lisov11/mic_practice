import math

import pytest

from config.env_air56b2_iek_025kw_delta_foc import (
    ENV,
    FOC_TUNING_CANDIDATE_INDEX,
    HARDWARE_IDENTIFIED,
    HARDWARE_RELEASE_READY,
    NAMEPLATE_AIR56B2_025KW_DELTA,
    OMEGA_BASE_RAD_S,
    PARAMETER_PROVENANCE,
    PARAMETER_SAMPLE_INDEX,
    PARAMETER_SAMPLE_SEED,
    PROFILE_SCHEMA,
    RATED_TORQUE_NM,
    create_env_for_sample,
)


def test_foc_profile_uses_exact_nameplate_and_explicit_simulation_prior() -> None:
    assert PROFILE_SCHEMA == "air56b2-foc-ppo-profile-v1"
    assert HARDWARE_IDENTIFIED is False
    assert HARDWARE_RELEASE_READY is False
    assert NAMEPLATE_AIR56B2_025KW_DELTA == {
        "P_n": 250.0,
        "U_ll": 220.0,
        "I_n": 1.24,
        "cos_phi_n": 0.78,
        "eta_n": 0.68,
        "f_n": 50.0,
        "p": 1,
        "n_rated": 2720.0,
        "connection": "D",
    }
    assert math.isclose(OMEGA_BASE_RAD_S, 2.0 * math.pi * 2720.0 / 60.0)
    assert math.isclose(RATED_TORQUE_NM, 250.0 / OMEGA_BASE_RAD_S)


def test_foc_profile_is_bound_to_canonical_ensemble_and_tuning() -> None:
    assert PARAMETER_SAMPLE_INDEX == 128
    assert PARAMETER_SAMPLE_SEED == 7420220382412596443
    assert FOC_TUNING_CANDIDATE_INDEX == 5
    assert ENV.sim.mode == "foc"
    assert ENV.sim.dt == pytest.approx(1e-4)
    assert ENV.omega_base_rad_s == pytest.approx(OMEGA_BASE_RAD_S)
    assert ENV.motor.Rs == pytest.approx(5.3904332409174565)
    assert ENV.motor.Rr == pytest.approx(14.222749867637607)
    assert ENV.motor.Lm == pytest.approx(0.48240691185340717)
    assert ENV.motor.I_n == pytest.approx(1.24)
    assert ENV.foc.id_ref == pytest.approx(0.5072957794837314 / ENV.motor.Lm)
    assert ENV.foc.iq_limit == pytest.approx(1.3305040694264063 * 1.24)
    assert ENV.foc.v_limit == pytest.approx(0.9367226126622612 * 325.0 / math.sqrt(3.0))
    assert PARAMETER_PROVENANCE["hardware_identified"] is False
    assert PARAMETER_PROVENANCE["hardware_release_ready"] is False


def test_profile_can_materialize_other_ensemble_samples_without_mutating_default() -> None:
    sample = create_env_for_sample(0)
    assert sample.motor.Rs != ENV.motor.Rs
    assert sample.motor.Lm != ENV.motor.Lm
    assert ENV.motor.Rs == pytest.approx(5.3904332409174565)
    with pytest.raises(IndexError):
        create_env_for_sample(999)
