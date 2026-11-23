"""Offline rejection checks for sender-only component evidence; no stand access."""
import copy
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import prepare_uart_v3_sender_trial as prep
from install_uart_v3_sender_fix import IMAGE_SHA
from verify_uart_v3_sender_idle import idle_check
from web_hmi_command_guard_selftest import load_server_module, safe_status


def main():
    root = Path(__file__).resolve().parents[1]
    mod = load_server_module(root)
    s = safe_status(fw_build=2026101008, mc_fw_build=2026101006, vdc=0., bp_vdc=0.,
        bp_vbus_raw=0, mc_age_ms=20, bp_temp_age_ms=20, hmi_hv_armed=0,
        bp_mcsdk_telemetry=1, bp_vbus_valid=1, hmi_vbus_hv_calibrated=1,
        mc_bad_cnt=0, mc_bad_integrity=0, mc_bad_sequence=0, mc_uart_error_flags=0,
        mc_last_uart_error_flags=0, uno_tx_short_writes=0, bp_transport_fault=0)
    assert idle_check(s)[0]; cases = 1
    for key, value in (("fw_build", 2026101007), ("mc_fw_build", 2026101099),
                       ("mc_bad_cnt", 1), ("mc_bad_cnt", True), ("bp_transport_fault", 5),
                       ("pwm", 1), ("estop", 1), ("hmi_vbus_hv_calibrated", 0),
                       ("vdc", 322), ("mc_age_ms", 300)):
        assert not idle_check(dict(s, **{key: value}))[0], key; cases += 1
    now = time.time()
    base = dict(schema="mic_ai.powered_trial.v1", pair=list(mod.UART_V3_TRIAL_PAIR),
        images=dict(mod.UART_V3_TRIAL_IMAGES), cases={k: True for k in mod.UART_V3_TRIAL_CASES},
        normal_restore_verified=True, offline_pass=True, offline_suites=42,
        idle_wifi_pass=True, physical_idle_pass=True, hv_release_approved=False,
        issued_at=now-1, expires_at=now+100,
        evidence_sha256={k: "a"*64 for k in ("pwm", "offline", "idle_wifi", "physical_idle")})
    with tempfile.TemporaryDirectory() as folder:
        d = Path(folder)
        image = d / "sender.bin"; image.write_bytes(b"mock pinned image")
        install_path = d / "install.json"; idle_path = d / "idle.json"
        (d / "manifest.json").write_text("{}")
        (d / "flash_verify_uno.log").write_text("UNO Q loader and sketch verification PASSED\n")
        install = dict(uno_flash_verified=True, nucleo_flashed=False,
                       image_sha256=prep.sha(image), pass_=False)
        idle = dict(pass_=True, observation_sec=30, new_good_frames=100,
                    arm_commands=0, start_commands=0, samples=[s], after=s)
        idle["pass"] = idle.pop("pass_")
        def call(i, j):
            install_path.write_text(json.dumps(i)); idle_path.write_text(json.dumps(j))
            return prep.sender_qualification(root, d/"pwm", d/"offline", d/"oldidle", d/"physical",
                                             d, install_path, idle_path)
        with patch.object(prep, "qualification", lambda *a: copy.deepcopy(base)), \
                patch.object(prep, "verify_candidate", lambda *a: image):
            result = call(install, idle)
            assert result["new_pair_active_pwm_measured"] is False
            assert result["pwm_evidence_pair"] == list(mod.UART_V3_TRIAL_PAIR)
            assert result["pair"] == list(mod.UART_V3_SENDER_TRIAL_PAIR); cases += 3
            for key, value in (("uno_flash_verified", False), ("nucleo_flashed", True),
                               ("image_sha256", IMAGE_SHA)):
                try: call(dict(install, **{key: value}), idle)
                except ValueError: cases += 1
                else: raise AssertionError(key)
            for key, value in (("pass", False), ("observation_sec", 29), ("new_good_frames", 99),
                               ("start_commands", 1), ("arm_commands", 1), ("samples", []),
                               ("after", dict(s, mc_bad_cnt=1)), ("samples", [dict(s, pwm=1)])):
                try: call(install, dict(idle, **{key: value}))
                except ValueError: cases += 1
                else: raise AssertionError(key)
            (d / "flash_verify_uno.log").write_text("programming failed")
            try: call(install, idle)
            except ValueError: cases += 1
            else: raise AssertionError("missing successful readback accepted")
    print(json.dumps(dict(pass_=True, cases=cases, hardware_commands=0)))


if __name__ == "__main__":
    main()
