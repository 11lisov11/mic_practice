"""Fit effective IPM timing and conduction loss from synchronized PWM cycles."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np


FIELDS = (
    'capture_id', 'phase', 'period_ns', 'arr', 'ccr', 'high_ns', 'vdc_V',
    'v_high_V', 'v_low_V', 'current_A', 'current_min_A', 'current_max_A', 'pole_mean_V',
)
PHASES = ('U', 'V', 'W')
POLARITY_TRANSITION_A = 0.05  # Same linear transition as ma_current_polarity.


def read_cycles(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or set(FIELDS) - set(reader.fieldnames):
            raise ValueError('CSV is missing calibration columns')
        cycles, excluded = [], 0
        for row in reader:
            try:
                capture, phase = row['capture_id'].strip(), row['phase'].strip().upper()
                period, arr, ccr, high, bus, hi, lo, current, low_i, high_i, mean = (
                    float(row[key]) for key in FIELDS[2:]
                )
                if not all(np.isfinite([period, arr, ccr, high, bus, hi, lo, current, low_i, high_i, mean])):
                    raise ValueError('nonfinite value')
                if not capture or phase not in PHASES or not 0 < high < period:
                    raise ValueError('invalid capture, phase or pulse width')
                if not (arr.is_integer() and ccr.is_integer() and 0 < ccr < arr and bus > 0 and lo < hi):
                    raise ValueError('invalid timer counts or voltage levels')
                if not low_i <= current <= high_i:
                    raise ValueError('invalid current bounds')
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f'{path}:{reader.line_num}: {exc}') from exc
            if low_i <= POLARITY_TRANSITION_A and high_i >= -POLARITY_TRANSITION_A:
                excluded += 1
                continue
            sign = np.sign(current)
            duty = ccr / arr
            measured_duty = high / period
            cycles.append({
                'capture': capture, 'phase': phase, 'sign': int(sign), 'current': abs(current),
                'period': period, 'bus': bus, 'edge_ns': sign * (duty * period - high),
                'conduction_V': sign * (measured_duty * (bus - hi) - (1 - measured_duty) * lo),
                'observed_V': sign * (bus * duty - mean),
            })
    return cycles, excluded


def rms(values):
    return float(np.sqrt(np.mean(np.square(values))))


def residuals(cycles, edge, drop, resistance):
    timing = [row['edge_ns'] - edge for row in cycles]
    conduction = [row['conduction_V'] - (drop + resistance * row['current']) for row in cycles]
    voltage = [
        row['observed_V'] - (row['bus'] * edge / row['period'] + drop + resistance * row['current'])
        for row in cycles
    ]
    closure = [
        row['observed_V'] - (row['bus'] * row['edge_ns'] / row['period'] + row['conduction_V'])
        for row in cycles
    ]
    return {
        'cycles': len(cycles), 'edge_bias_ns': float(np.mean(timing)), 'edge_rms_ns': rms(timing),
        'conduction_bias_V': float(np.mean(conduction)), 'conduction_rms_V': rms(conduction),
        'measured_cycle_mean_bias_V': float(np.mean(voltage)), 'measured_cycle_mean_rms_V': rms(voltage),
        'plateau_approximation_rms_V': rms(closure),
    }


def fit(cycles, holdout, timer_hz, nominal_ticks):
    capture_ids = {row['capture'] for row in cycles}
    if not holdout or not holdout < capture_ids:
        raise ValueError('use distinct nonempty calibration and validation captures')
    calibration = [row for row in cycles if row['capture'] not in holdout]
    validation = [row for row in cycles if row['capture'] in holdout]
    for group in (calibration, validation):
        if {row['sign'] for row in group} != {-1, 1}:
            raise ValueError('capture both current polarities in each group')

    edge = float(np.median([row['edge_ns'] for row in calibration]))
    design = np.array([[1, row['current']] for row in calibration])
    target = [row['conduction_V'] for row in calibration]
    (drop, resistance), _, rank, singular = np.linalg.lstsq(design, target, rcond=None)
    if rank < 2:
        raise ValueError('different current magnitudes are required to fit V0 and R_on')
    if min(edge, drop, resistance) < 0:
        raise ValueError('negative fitted loss parameter: check polarity, offsets and model asymmetry')

    # Validate the quantized parameters used by the embedded model.
    half_ticks = round(2 * (edge * 1e-9 * timer_hz - nominal_ticks))
    drop_mv = round(drop * 1000)
    resistance_mohm = round(resistance * 1000)
    quantized = ((nominal_ticks + half_ticks * 0.5) / timer_hz * 1e9,
                 drop_mv / 1000, resistance_mohm / 1000)

    def summarize(group):
        by_phase_and_sign = {}
        for phase in PHASES:
            for sign in (-1, 1):
                subset = [row for row in group if row['phase'] == phase and row['sign'] == sign]
                if subset:
                    by_phase_and_sign[f'{phase}{sign:+d}'] = residuals(subset, *quantized)
        return {**residuals(group, *quantized), 'by_phase_and_sign': by_phase_and_sign}

    fit_summary, test_summary = summarize(calibration), summarize(validation)
    return {
        'timing_ns': edge, 'conduction_V0_V': float(drop), 'conduction_R_on_ohm': float(resistance),
        'conduction_design_condition': float(singular[0] / singular[-1]),
        'timer_hz': timer_hz, 'model_nominal_deadtime_ticks': nominal_ticks,
        'all_phases_and_signs_in_both_groups': all(
            len(summary['by_phase_and_sign']) == 6 for summary in (fit_summary, test_summary)
        ),
        'trial_model_defines': {
            'MA_IPM_EDGE_ADJUST_HALF_TICKS': half_ticks,
            'MA_IPM_DEVICE_DROP_MV': drop_mv,
            'MA_IPM_ON_MILLIOHMS': resistance_mohm,
        },
        'fit': fit_summary, 'validation': test_summary,
        'fit_captures': sorted(capture_ids - holdout), 'validation_captures': sorted(holdout),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path, help='one row per complete PWM cycle')
    parser.add_argument('--validate-capture', required=True, action='append', help='reserved capture ID')
    parser.add_argument('--timer-hz', type=int, default=170_000_000)
    parser.add_argument('--nominal-model-ticks', type=int, default=229)
    parser.add_argument('--output', type=Path, help='write JSON to a new file')
    args = parser.parse_args()
    if args.timer_hz <= 0 or args.nominal_model_ticks < 0:
        parser.error('invalid model timer configuration')
    try:
        cycles, excluded = read_cycles(args.csv)
        result = fit(cycles, set(args.validate_capture), args.timer_hz, args.nominal_model_ticks)
        result['excluded_near_zero_current_cycles'] = excluded
        encoded = json.dumps(result, indent=2, allow_nan=False) + '\n'
        if args.output:
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(encoded)
        else:
            print(encoded, end='')
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
