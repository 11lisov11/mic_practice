from __future__ import annotations

from dataclasses import asdict
import json
import math

import pytest

from models.air56b2_fidelity import (
    F2Priors,
    F3Priors,
    FloatBounds,
    IntBounds,
    fidelity_manifest,
    generate_f2_samples,
    generate_f3_samples,
)
from models.air56b2_nameplate_ensemble import (
    Air56B2Nameplate,
    generate_air56b2_ensemble,
)


def _f1_samples():
    return generate_air56b2_ensemble(3, seed=5602)


def test_f2_and_f3_are_deterministic_and_leave_f1_untouched() -> None:
    f1 = _f1_samples()
    before = [asdict(sample) for sample in f1]

    f2_first = generate_f2_samples(f1, seed=2002)
    f2_second = generate_f2_samples(f1, seed=2002)
    f3_first = generate_f3_samples(f1, seed=3003)
    f3_second = generate_f3_samples(f1, seed=3003)

    assert f2_first == f2_second
    assert f3_first == f3_second
    assert [asdict(sample) for sample in f1] == before
    assert all(sample.transformed_motor is not original.motor for sample, original in zip(f2_first, f1))
    assert all(sample.transformed_motor.J == original.motor.J for sample, original in zip(f2_first, f1))
    assert all(sample.transformed_motor.Lm == original.motor.Lm for sample, original in zip(f2_first, f1))


def test_f2_samples_respect_all_bounds_and_loss_partition() -> None:
    f1 = _f1_samples()
    priors = F2Priors()
    samples = generate_f2_samples(f1, seed=22, priors=priors)

    for f2, f1_sample in zip(samples, f1):
        assert priors.stator_temperature_c.contains(f2.stator_temperature_c)
        assert priors.rotor_temperature_c.contains(f2.rotor_temperature_c)
        assert priors.stator_copper_alpha_per_c.contains(f2.stator_copper_alpha_per_c)
        assert priors.rotor_copper_alpha_per_c.contains(f2.rotor_copper_alpha_per_c)
        assert priors.saturation_knee_flux_scale.contains(f2.saturation_knee_flux_scale)
        assert priors.saturation_exponent.contains(f2.saturation_exponent)
        assert priors.minimum_magnetizing_inductance_scale.contains(
            f2.minimum_magnetizing_inductance_scale
        )
        assert priors.core_loss_scale.contains(f2.core_loss_scale)
        assert priors.rotational_loss_scale.contains(f2.rotational_loss_scale)
        assert priors.viscous_loss_fraction.contains(f2.viscous_loss_fraction)
        assert f2.effective_core_loss_w == pytest.approx(
            f1_sample.core_loss_w * f2.core_loss_scale
        )
        assert f2.effective_rotational_loss_w == pytest.approx(
            f1_sample.rotational_loss_w * f2.rotational_loss_scale
        )
        reconstructed_rotational_loss = (
            f2.effective_viscous_coefficient_nms
            * (2.0 * math.pi * 2720.0 / 60.0) ** 2
            + f2.effective_coulomb_friction_torque_nm
            * (2.0 * math.pi * 2720.0 / 60.0)
        )
        assert reconstructed_rotational_loss == pytest.approx(
            f2.effective_rotational_loss_w
        )
        assert f2.transformed_motor.Rs == pytest.approx(
            f1_sample.motor.Rs * f2.stator_resistance_scale
        )
        assert f2.transformed_motor.Rr == pytest.approx(
            f1_sample.motor.Rr * f2.rotor_resistance_scale
        )


def test_f3_samples_respect_inverter_adc_and_as5600_bounds() -> None:
    f1 = _f1_samples()
    priors = F3Priors()
    samples = generate_f3_samples(f1, seed=33, priors=priors)

    for sample in samples:
        inverter = sample.inverter
        adc = sample.adc
        encoder = sample.as5600
        assert priors.vdc_ripple_fraction_peak.contains(inverter.ripple_fraction_peak)
        assert priors.vdc_ripple_frequency_hz.contains(inverter.ripple_frequency_hz)
        assert priors.dead_time_s.contains(inverter.dead_time_s)
        assert priors.switch_r_on_ohm.contains(inverter.switch_r_on_ohm)
        assert priors.switch_voltage_drop_v.contains(inverter.switch_voltage_drop_v)
        assert inverter.ripple_peak_v == pytest.approx(
            priors.nominal_vdc_v * inverter.ripple_fraction_peak
        )
        assert inverter.vdc_at(0.001) > 0.0
        assert priors.adc_bits.contains(adc.bits)
        assert priors.adc_current_full_scale_a.contains(adc.current_full_scale_a)
        assert priors.adc_voltage_full_scale_v.contains(adc.voltage_full_scale_v)
        assert priors.adc_current_gain_scale.contains(adc.current_gain_scale)
        assert priors.adc_voltage_gain_scale.contains(adc.voltage_gain_scale)
        assert priors.adc_sample_delay_pwm_periods.contains(
            adc.sample_delay_s * priors.pwm_frequency_hz
        )
        assert -adc.current_full_scale_a <= adc.quantize_current(99.0) <= adc.current_full_scale_a
        assert 0.0 <= adc.quantize_voltage(999.0) <= adc.voltage_full_scale_v
        assert priors.as5600_bits.contains(encoder.bits)
        assert priors.as5600_delay_s.contains(encoder.sample_delay_s)
        assert encoder.angle_lsb_rad == pytest.approx(2.0 * math.pi / (1 << encoder.bits))
        assert 0.0 <= encoder.quantize_angle(-0.1) < 2.0 * math.pi


def test_manifest_is_json_serializable_preserves_nameplate_and_has_no_hardware_claim() -> None:
    f1 = _f1_samples()
    f2 = generate_f2_samples(f1, seed=44)
    f3 = generate_f3_samples(f1, seed=55)
    payload = fidelity_manifest(f1, f2, f3, f2_seed=44, f3_seed=55)

    assert payload["status"] == "simulation_prior_only"
    assert payload["hardware_claim"] is False
    assert payload["hardware_identified"] is False
    assert payload["parameters_measured"] is False
    assert payload["nameplate_unchanged"] is True
    assert payload["nameplate"] == asdict(Air56B2Nameplate())
    assert all(not sample["parameters_measured"] for sample in payload["f2_samples"])
    assert all(not sample["hardware_identified"] for sample in payload["f3_samples"])
    json.dumps(payload)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: FloatBounds(2.0, 1.0),
        lambda: FloatBounds(float("nan"), 1.0),
        lambda: IntBounds(14, 10),
        lambda: F2Priors(stator_temperature_c=FloatBounds(10.0, 40.0)),
        lambda: F2Priors(
            minimum_magnetizing_inductance_scale=FloatBounds(0.5, 1.1)
        ),
        lambda: F3Priors(dead_time_s=FloatBounds(0.0, 60e-6)),
        lambda: F3Priors(adc_bits=IntBounds(1, 12)),
        lambda: F3Priors(
            adc_current_offset_fraction_fs=FloatBounds(-0.30, 0.01)
        ),
        lambda: F3Priors(adc_current_full_scale_a=FloatBounds(2.0, 5.0)),
        lambda: F3Priors(adc_voltage_full_scale_v=FloatBounds(300.0, 320.0)),
    ],
)
def test_invalid_bounds_fail_hard(factory) -> None:
    with pytest.raises(ValueError):
        factory()


def test_manifest_rejects_mismatched_f1_references() -> None:
    f1 = _f1_samples()
    f2 = generate_f2_samples(f1, seed=66)
    f3 = generate_f3_samples(f1, seed=77)
    with pytest.raises(ValueError, match="F2 references"):
        fidelity_manifest(f1, list(reversed(f2)), f3, f2_seed=66, f3_seed=77)
