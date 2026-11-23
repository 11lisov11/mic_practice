"""Offline ACIM electrical identification from stationary-axis impedance sweeps.

The fit identifies terminal observables, not the individual physical leakage
inductances. No hardware control, mechanical estimate or FOC release is provided.
"""
from __future__ import annotations

import math
from typing import Mapping

import numpy as np
from scipy.optimize import least_squares

SCHEMA = 'mic_ai.acim_standstill_impedance.v1'


def impedance(frequency_hz, rs: float, transient_h: float, coupling_h: float, tau_r_s: float):
    """Z(s)=Rs+s*Ltransient+s*K/(1+s*tau_r), s=j*omega.

    K=Lm^2/Lr, Ltransient=Ls-K. Phasors use exp(+j*omega*t).
    """
    s = 2j * np.pi * np.asarray(frequency_hz)
    return rs + s * transient_h + s * coupling_h / (1 + s * tau_r_s)


def identify(capture: Mapping) -> dict:
    result = dict(schema='mic_ai.acim_standstill_result.v1', accepted=False,
                  hardware_commands=0, eligible_for_foc_start=False,
                  mechanical_parameters_identified=False, errors=[])
    errors = result['errors']
    if capture.get('schema') != SCHEMA:
        errors.append('capture_schema')
    if capture.get('source_kind') not in ('synthetic', 'hardware'):
        errors.append('source_kind')
    result['source_kind'] = capture.get('source_kind')
    if capture.get('voltage_source') not in ('measured_fundamental', 'calibrated_pwm_reconstruction'):
        errors.append('actual_voltage_required_not_uncompensated_command')
    if capture.get('rotating_field') is not False:
        errors.append('stationary_axis_excitation_required')
    if capture.get('rotor_stationary_verified') is not True:
        errors.append('rotor_standstill_not_verified')
    if capture.get('current_scale') not in ('nominal_datasheet', 'independently_calibrated'):
        errors.append('current_scale_missing')
    result['absolute_current_scale_qualified'] = capture.get('current_scale') == 'independently_calibrated'
    try:
        rs = float(capture['stator_resistance_ohm'])
        if isinstance(capture['stator_resistance_ohm'], bool) or not math.isfinite(rs) or rs <= 0:
            raise ValueError()
        if capture.get('stator_resistance_convention') != 'balanced_star_equivalent':
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        errors.append('measured_star_equivalent_rs_required')
        rs = math.nan
    rows = []
    points = capture.get('points')
    if not isinstance(points, list):
        errors.append('impedance_points_required')
        points = []
    for row in points:
        try:
            f = float(row['frequency_hz'])
            v = complex(*row['voltage_rms_phasor_v'])
            i = complex(*row['current_rms_phasor_a'])
            role, run = row['role'], row['run_id']
            numeric = (f, v.real, v.imag, i.real, i.imag)
            if (not all(math.isfinite(x) for x in numeric) or f <= 0 or abs(i) < 0.02
                    or role not in ('fit', 'validation') or not isinstance(run, str) or not run):
                raise ValueError()
            quality = tuple(float(row[k]) for k in ('coverage_pct', 'settled_cycles', 'samples_per_cycle'))
            if (not all(math.isfinite(x) for x in quality)
                    or quality[0] < 95 or quality[0] > 100
                    or quality[1] < 5 or quality[2] < 20
                    or row['synchronized_voltage_current'] is not True):
                raise ValueError()
            rows.append((f, v / i, role, run))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            errors.append('invalid_or_insufficient_quality_point')
    fit = [row for row in rows if row[2] == 'fit']
    validation = [row for row in rows if row[2] == 'validation']
    if len({row[0] for row in fit}) < 5 or len({row[0] for row in validation}) < 3:
        errors.append('independent_multifrequency_fit_and_validation_required')
    if {r[3] for r in fit} & {r[3] for r in validation}:
        errors.append('fit_validation_run_reused')
    if errors:
        return result
    frequencies = np.array([row[0] for row in fit])
    z = np.array([row[1] for row in fit])
    weights = np.maximum(np.abs(z), rs) * 0.02

    def residual(log_parameters):
        estimate = impedance(frequencies, rs, *np.exp(log_parameters))
        d = (estimate - z) / weights
        return np.r_[d.real, d.imag]

    candidates = []
    for transient, coupling, tau in ((.005, .5, .1), (.02, .2, .03), (.001, 1., .5), (.05, .8, 1.)):
        candidates.append(least_squares(residual, np.log([transient, coupling, tau]),
            bounds=(np.log([1e-6, 1e-5, 1e-4]), np.log([5., 20., 20.])), max_nfev=600))
    best = min(candidates, key=lambda r: np.sum(r.fun*r.fun))
    transient, coupling, tau = map(float, np.exp(best.x))
    singular = np.linalg.svd(best.jac, compute_uv=False)
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else math.inf
    fit_error = float(np.linalg.norm(impedance(frequencies, rs, transient, coupling, tau)-z) / np.linalg.norm(z))
    vf = np.array([row[0] for row in validation])
    vz = np.array([row[1] for row in validation])
    validation_error = float(np.linalg.norm(impedance(vf, rs, transient, coupling, tau)-vz) / np.linalg.norm(vz))
    if not best.success or condition > 1e5:
        errors.append('electrical_model_unidentifiable_or_fit_failed')
    if fit_error > .03 or validation_error > .05:
        errors.append('electrical_model_does_not_explain_independent_data')
    # This is one equivalent T model, not a measurement of two leakage coils.
    ls = transient + coupling
    lm = math.sqrt(coupling * ls)
    leakage = ls - lm
    result.update(accepted=not errors, fit_relative_error=fit_error,
                  validation_relative_error=validation_error,
                  jacobian_condition=condition if math.isfinite(condition) else None,
                  assumed_relative_impedance_uncertainty=0.02,
                  observable_model=dict(Rs_ohm=rs, L_transient_h=transient, K_h=coupling, tau_r_s=tau),
                  equivalent_mcsdk_model=dict(RS=rs, RR=ls/tau, LLS=leakage, LLR=leakage, LMS=lm/1.5),
                  assumption='LLS=LLR selects an equivalent T-model; physical leakage split is not identified',
                  deployment_note='Electrical fit only; current phase/polarity, inverter voltage, flux current, observer tuning and mechanical behavior still require validation')
    return result
