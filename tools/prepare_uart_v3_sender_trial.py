"""Attest an unchanged Nucleo PWM component plus verified sender delta, not a new PWM capture."""
import argparse
import hashlib
import json
from pathlib import Path

from install_uart_v3_sender_fix import verify_candidate, sha
from prepare_powered_trial import qualification
from verify_uart_v3_sender_idle import idle_check
from web_hmi_command_guard_selftest import load_server_module


def sender_qualification(root, pwm, offline, old_idle, physical, snapshot, install_path, idle_path):
    proof = qualification(root, pwm, offline, old_idle, physical)
    mod = load_server_module(root)
    image = verify_candidate(root, snapshot, offline)
    install = json.loads(install_path.read_text(encoding="utf-8-sig"))
    # A warm-reset RPC timeout does not erase successful flash readback. Fresh
    # idle evidence below is mandatory and independent of that installer result.
    if (install.get("uno_flash_verified") is not True or install.get("nucleo_flashed") is not False
            or install.get("image_sha256") != sha(image)
            or "UNO Q loader and sketch verification PASSED" not in
                (install_path.parent / "flash_verify_uno.log").read_text(encoding="utf-8")):
        raise ValueError("verified sender programming evidence missing")
    idle = json.loads(idle_path.read_text(encoding="utf-8-sig"))
    if (idle.get("pass") is not True or idle.get("observation_sec", 0) < 30
            or idle.get("new_good_frames", 0) < 100
            or idle.get("arm_commands") != 0 or idle.get("start_commands") != 0
            or not idle.get("samples")
            or not all(idle_check(s)[0] for s in idle["samples"])
            or not idle_check(idle.get("after", {}))[0]):
        raise ValueError("fresh new-pair idle qualification failed")
    delta = snapshot / "manifest.json"
    proof.update(schema="mic_ai.powered_trial.sender_delta.v1",
        scope="unchanged_nucleo_pwm_plus_sender_delta",
        pwm_evidence_pair=proof["pair"], pwm_evidence_images=proof["images"],
        pair=list(mod.UART_V3_SENDER_TRIAL_PAIR), images=dict(mod.UART_V3_SENDER_TRIAL_IMAGES),
        sender_delta_verified=True, sender_flash_verified=True, fresh_idle_wifi_pass=True,
        new_pair_active_pwm_measured=False)
    proof["evidence_sha256"].update(sender_delta=sha(delta), sender_install=sha(install_path),
                                    idle_wifi=sha(idle_path))
    if not mod.validate_powered_trial_qualification(proof)[0]:
        raise ValueError("server rejected scoped sender trial")
    return proof


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("pwm", "offline", "old-idle", "physical", "snapshot", "install", "idle", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    result = sender_qualification(Path(__file__).resolve().parents[1], a.pwm, a.offline,
        a.old_idle, a.physical, a.snapshot, a.install, a.idle)
    with a.out.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2); f.write("\n")
    print(json.dumps(dict(prepared=True, hardware_commands=0,
                         new_pair_active_pwm_measured=False, expires_at=result["expires_at"])))


if __name__ == "__main__":
    main()
