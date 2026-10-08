"""Negative and saturation regressions for passive UART verification."""
import json
from as5600_wifi_readonly_probe import controller_link_evidence


def main():
    base = dict(mc_good=10, mc_seq=254, mc_fw_build=2026100708, mc_age_ms=10,
                mc_bad_cnt=0, mc_bad_integrity=0, mc_bad_sequence=0)
    normal = [base, dict(base, mc_good=11, mc_seq=255), dict(base, mc_good=12, mc_seq=0)]
    saturated = [dict(base, mc_good=65535, mc_seq=s) for s in (254, 255, 0)]
    checks = []

    def check(rows, expected):
        evidence = controller_link_evidence(rows, 2026100708)
        assert evidence["controller_link_pass"] is expected, (rows, evidence)
        checks.append(True)
        return evidence

    assert check(normal, True)["new_uart_messages"] == 2
    sat = check(saturated, True)
    assert sat["new_uart_messages"] is None and sat["observed_sequence_changes"] == 2
    check([dict(base, mc_good=65534), *saturated], True)
    check([base, base], False)
    check([saturated[0]] * 3, False)
    for field, value in (("mc_age_ms", 300), ("mc_age_ms", float("nan")),
                         ("mc_bad_cnt", 1), ("mc_bad_integrity", 1), ("mc_bad_sequence", 1),
                         ("mc_fw_build", 0), ("mc_good", -1), ("mc_good", 65536),
                         ("mc_good", None), ("mc_good", 1)):
        check([normal[0], dict(normal[1], **{field: value}), normal[2]], False)
    for value in (None, -1, 256, "254"):
        check([dict(s, mc_seq=value) for s in saturated], False)
    check([], False)
    check([base], False)
    check([dict(s, mc_bad_cnt=1) for s in saturated], True)  # no *new* errors; history remains visible
    print(json.dumps({"pass": True, "checks": len(checks), "no_hardware_commands": True}))


if __name__ == "__main__":
    main()
