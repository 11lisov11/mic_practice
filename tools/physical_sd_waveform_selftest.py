"""Synthetic counterexamples for the physical SD waveform acceptance rule."""
from physical_sd_waveform import physical_sd_checks


def trace(*, trip=.021, stop=.021001, release=.08, restart=False, bounce=False):
    events = {0., .3, trip, stop, release}
    period = 1/16000
    n = 0
    while .001 + n*period < stop:
        base = .001 + n*period
        for dt in (0., period/2-1.35e-6, period/2+1.35e-6, period-1.35e-6):
            if base+dt < stop:
                events.add(base+dt)
        n += 1
    if bounce:
        events.update((trip+.001, trip+.002))
    if restart:
        events.update((release+.01, release+.02))
    times = sorted(events)
    values = {ch: [] for ch in range(7)}
    for t in times:
        phase = (t-.001) % period
        active = .001 <= t < stop
        for ch in range(6):
            value = active and (phase < period/2-1.35e-6 if ch%2 == 0
                                else period/2+1.35e-6 <= phase < period-1.35e-6)
            if restart and release+.01 <= t < release+.02:
                value = ch%2 == 0
            values[ch].append(int(value))
        values[6].append(int(not(trip <= t < release)
                             or (bounce and trip+.001 <= t < trip+.002)))
    return times, values


def main():
    assert physical_sd_checks(*trace())["pass"]
    for kwargs in ({"stop": .025}, {"stop": .020}, {"restart": True},
                   {"bounce": True}, {"release": .299}, {"release": .022}):
        assert not physical_sd_checks(*trace(**kwargs))["pass"], kwargs
    times, values = trace()
    values[6] = [1]*len(times)
    assert not physical_sd_checks(times, values)["pass"]
    assert not physical_sd_checks([0., 0.], {ch: [0, 0] for ch in range(7)})["pass"]
    print('PASS physical trip, late stop, premature stop, restart, bounce, short hold, absent SD and bad time')


if __name__ == '__main__':
    main()
