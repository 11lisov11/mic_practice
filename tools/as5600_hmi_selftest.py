"""Check direct UNO Q encoder diagnostics without changing motor UART semantics."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_hmi.server import RpcBridge


def main():
    line = ("DATA state=SAFE mode=VF pwm=0 enc_source=uno_q_i2c2 enc_bus_ok=1 "
            "enc_status=32 enc_ok=1 enc_speed_ok=1 enc_raw=4095 enc_deg=359.9 "
            "enc_rpm=2720 enc_reads=123 enc_errors=2 enc_io_error=0 enc_age_ms=3 "
            "enc_init_error=0 enc_scl=1 enc_sda=0 "
            "bp_fault=0 bp_status=1 bp_bad=0 bp_age_ms=20 bp_fw_build=2026100601 "
            "rpc_schema=3 mc_caps=1")
    data = RpcBridge._parse_status_string(line)
    assert data is not None
    expected = {"enc_source": "uno_q_i2c2", "enc_bus_ok": 1, "enc_status": 32,
                "enc_speed_ok": 1, "enc_reads": 123, "enc_errors": 2,
                "enc_io_error": 0, "enc_age_ms": 3, "enc_raw": 4095,
                "enc_init_error": 0, "enc_scl": 1, "enc_sda": 0}
    assert all(data[k] == value for k, value in expected.items())
    for replacement in ("enc_ok=0", "enc_bus_ok=0", "enc_status=0", "enc_io_error=-5"):
        key, value = replacement.split("=")
        old = f"{key}={data[key]}"
        parsed = RpcBridge._parse_status_string(line.replace(old, replacement))
        assert parsed[key] == int(value)
        assert parsed["pwm"] == 0 and parsed["mc_fault"] == 0
    legacy = RpcBridge._parse_status_string("DATA state=SAFE mode=VF pwm=0")
    assert legacy["enc_source"] == "motor_controller_uart"
    assert legacy["enc_bus_ok"] == 0 and legacy["enc_age_ms"] == 999999
    print("PASS: direct encoder fields, four failures, legacy defaults")


if __name__ == "__main__":
    main()
