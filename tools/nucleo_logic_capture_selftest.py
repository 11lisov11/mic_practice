#!/usr/bin/env python3
from copy import deepcopy
from nucleo_logic_capture import CHANNEL_MAP, capture_checks


def main() -> None:
    base = {"channels": {str(ch): {"initial": 0, "final": 0, "edges": 0} for ch in range(6)},
            "no_overlap_pass": True, "timing_resolution_pass": True}
    assert [CHANNEL_MAP[ch]["gpio"] for ch in range(6)] == ["PA8", "PA7", "PA9", "PB0", "PA10", "PB1"]
    assert capture_checks(base, False)["pass"]
    assert not capture_checks(base, True)["pass"]
    high = deepcopy(base)
    high["channels"]["1"].update(initial=1, final=1)
    assert not capture_checks(high, False)["pass"]
    active = deepcopy(base)
    active["channels"]["0"]["edges"] = 20
    assert not capture_checks(active, True)["pass"]
    for channel in active["channels"].values():
        channel["edges"] = 20
    assert capture_checks(active, True)["pass"]
    active["no_overlap_pass"] = False
    assert not capture_checks(active, True)["pass"]
    missing = deepcopy(base)
    del missing["channels"]["5"]
    assert not capture_checks(missing, False)["pass"]
    slow = deepcopy(base)
    slow["timing_resolution_pass"] = False
    assert not capture_checks(slow, False)["pass"]
    print("PASS nucleo_logic_capture_selftest: 9 checks")


if __name__ == "__main__":
    main()
