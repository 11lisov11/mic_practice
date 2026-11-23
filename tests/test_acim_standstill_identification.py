import math

import numpy as np
import pytest

from motor_identification.standstill import SCHEMA, identify, impedance


def make_capture(noise=0.0):
    rng = np.random.default_rng(251012)
    c = dict(schema=SCHEMA, source_kind='synthetic', stator_resistance_ohm=12.23,
             stator_resistance_convention='balanced_star_equivalent',
             voltage_source='measured_fundamental', current_scale='nominal_datasheet',
             rotating_field=False, rotor_stationary_verified=True, points=[])
    # Independent phase-domain circuit calculation, not the fitter's Z routine.
    rs, rr, leakage, lm = 12.23, 9.0, .012, .45
    for role, frequencies in [('fit', [1., 2., 5., 10., 20., 50., 100., 200.]),
                              ('validation', [3., 8., 30., 80.])]:
        for f in frequencies:
            s = 2j * math.pi * f
            ls = lr = lm + leakage
            z = rs + s*ls - s*s*lm*lm / (rr+s*lr)
            current = .2 * np.exp(.3j)
            voltage = z*current * (1 + noise*(rng.normal()+1j*rng.normal()))
            c['points'].append(dict(frequency_hz=f, voltage_rms_phasor_v=[voltage.real, voltage.imag],
                                   current_rms_phasor_a=[current.real, current.imag], role=role,
                                   run_id=role+'-independent-run', coverage_pct=100,
                                   settled_cycles=8, samples_per_cycle=64, synchronized_voltage_current=True))
    return c


def test_independent_equivalent_circuit_recovery():
    r = identify(make_capture())
    assert r['accepted'], r
    assert r['equivalent_mcsdk_model']['RR'] == pytest.approx(9., rel=1e-6)
    assert r['equivalent_mcsdk_model']['LLS'] == pytest.approx(.012, rel=1e-6)
    assert r['equivalent_mcsdk_model']['LMS'] == pytest.approx(.3, rel=1e-6)
    assert not r['eligible_for_foc_start']
    assert not r['mechanical_parameters_identified']
    assert not r['absolute_current_scale_qualified']


def test_noise_and_independent_validation():
    r = identify(make_capture(.002))
    assert r['accepted'], r
    assert r['equivalent_mcsdk_model']['RR'] == pytest.approx(9., rel=.08)


@pytest.mark.parametrize('field,value', [
    ('rotating_field', True), ('rotor_stationary_verified', False),
    ('voltage_source', 'uncompensated_duty_command'), ('current_scale', None),
    ('stator_resistance_ohm', math.nan), ('stator_resistance_ohm', True),
    ('stator_resistance_convention', 'physical_delta_winding'),
])
def test_rejects_bad_conditions(field, value):
    c = make_capture(); c[field] = value
    assert not identify(c)['accepted']


@pytest.mark.parametrize('field,value', [
    ('coverage_pct', 94), ('settled_cycles', 1), ('samples_per_cycle', 4),
    ('synchronized_voltage_current', False), ('frequency_hz', math.nan),
    ('coverage_pct', math.nan), ('settled_cycles', math.inf), ('samples_per_cycle', math.nan),
])
def test_rejects_bad_point_quality(field, value):
    c = make_capture(); c['points'][0][field] = value
    assert not identify(c)['accepted']


def test_rejects_reused_validation_run():
    c = make_capture()
    for p in c['points']: p['run_id'] = 'same-run'
    assert not identify(c)['accepted']


def test_detects_voltage_error_on_independent_repeat():
    c = make_capture()
    for p in c['points']:
        if p['role'] == 'validation':
            p['voltage_rms_phasor_v'] = [v*1.3 for v in p['voltage_rms_phasor_v']]
    assert not identify(c)['accepted']


def test_cannot_use_old_12_frame_peak_as_impedance_sweep():
    c = make_capture(); c['points'] = c['points'][:3]
    assert not identify(c)['accepted']


def test_standstill_transfer_matches_terminal_circuit():
    r = identify(make_capture()); m = r['observable_model']
    f = np.geomspace(.01, 10000, 200)
    s = 2j*np.pi*f
    expected = 12.23 + s*.462 - s*s*.45**2/(9.+s*.462)
    actual = impedance(f, m['Rs_ohm'], m['L_transient_h'], m['K_h'], m['tau_r_s'])
    assert np.max(np.abs(actual-expected)) < 1e-6
