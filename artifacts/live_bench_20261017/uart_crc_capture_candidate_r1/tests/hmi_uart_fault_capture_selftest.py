from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web_hmi"))
import server  # noqa: E402


def main() -> None:
    line = (
        "DATA state=SAFE mode=VF pwm=0 mc_diag_valid=1 mc_fault_reason=1 "
        "mc_uart_error_flags=0 mc_fault_current_mask=0 mc_fault_occurred_mask=0 "
        "mc_fault_motor_state=2 mc_fault_sequence=7 mc_fault_tx_status=0 "
        "mc_last_bad_valid=1 mc_last_bad_reason=1 mc_last_uart_error_flags=0 "
        "mc_last_tx_status=0 mc_uart_capture_valid=1 mc_uart_capture_age_ms=40 "
        "mc_uart_capture_good_pages=5 mc_uart_capture_bad_pages=0 "
        "mc_uart_capture_build=2026101702 mc_uart_capture_tick_ms=1234 "
        "mc_uart_capture_detail=1 mc_uart_capture_reason=2 mc_uart_capture_flags=4 "
        "mc_uart_capture_ne_count=1 mc_uart_capture_length=3 "
        "mc_uart_capture_frame_hex=aa5503 mc_uart_capture_marks_hex=000400"
    )
    status = server.RpcBridge._parse_status_string(line)
    assert status is not None
    assert status["mc_uart_capture_frame_hex"] == "aa5503"
    assert status["bp_uart_capture_marks_hex"] == "000400"
    detail = status["mc_fault_detail"]
    assert "CRC32C checksum mismatch" in detail
    assert "flags=0x04" in detail and "NE_bytes=1" in detail
    assert "frame=aa5503" in detail and "byte_flags=000400" in detail
    compact = server.MotorFaultRecorder.compact(status, 12.5)
    assert compact["mc_uart_capture_frame_hex"] == "aa5503"
    assert compact["mc_uart_capture_detail"] == 1
    print("PASS HMI status, explanation and fault recorder retain the UART capture")


if __name__ == "__main__":
    main()
