"""Qualify an external SD pulse against six measured PWM outputs, not a log flag."""
from __future__ import annotations


def physical_sd_checks(times, values):
    if len(times) < 2 or any(ch not in values or len(values[ch]) != len(times) for ch in range(7)):
        return {"pass": False, "error": "seven complete channels required"}
    if any(b <= a for a, b in zip(times, times[1:])):
        return {"pass": False, "error": "timestamps must increase"}
    if any(v not in (0, 1) for ch in range(7) for v in values[ch]):
        return {"pass": False, "error": "binary samples required"}
    edges = {ch: [i for i in range(1, len(times)) if values[ch][i] != values[ch][i-1]]
             for ch in range(7)}
    first_pwm = min((times[e[0]] for ch, e in edges.items() if ch < 6 and e), default=None)
    falls = [i for i in edges[6] if values[6][i] == 0
             and first_pwm is not None and times[i] > first_pwm]
    trip = falls[0] if falls else None
    release = next((i for i in edges[6] if trip is not None and i > trip and values[6][i] == 1), None)
    tf = times[trip] if trip is not None else None
    tr = times[release] if release is not None else None
    last = max((times[e[-1]] for ch, e in edges.items() if ch < 6 and e), default=None)
    checks = {
        "seven_channels_valid": True,
        "SD_initially_high": values[6][0] == 1,
        "one_clean_SD_pulse": len(edges[6]) == 2 and trip is not None and release is not None,
        "PWM_running_immediately_before_trip": tf is not None and all(
            sum(tf - .005 <= times[i] < tf for i in edges[ch]) >= 8
            and any(tf - .0002 <= times[i] < tf for i in edges[ch]) for ch in range(6)),
        "SD_held_low_at_least_20ms": tr is not None and tr - tf >= .02,
        "all_outputs_LOW_within_100us": tf is not None and last is not None
            and last <= tf + .0001
            and all(values[ch][i] == 0 for ch in range(6) for i, t in enumerate(times) if t >= tf + .0001),
        "SD_release_stable_100ms": tr is not None and times[-1] - tr >= .1
            and all(values[6][i] == 1 for i in range(release, len(times))),
        "no_PWM_restart_after_release": tr is not None
            and all(values[ch][i] == 0 for ch in range(6) for i in range(release, len(times))),
    }
    return {"pass": all(checks.values()), "checks": checks, "sd_edges": len(edges[6]),
            "sd_falling_s": tf, "sd_release_s": tr,
            "last_pwm_edge_s": last,
            "trip_to_last_pwm_edge_upper_bound_us": max(0., last-tf)*1e6
            if last is not None and tf is not None else None,
            "scope": "external SD waveform and PWM cessation; not intrinsic IPM OC/UVLO qualification"}
