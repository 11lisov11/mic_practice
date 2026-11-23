"""Build a short-lived host attestation from retained stand evidence; no hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from web_hmi_command_guard_selftest import load_server_module


def qualification(root, pwm_path, offline_path, idle_path, physical_path):
    mod = load_server_module(root)
    paths = dict(pwm=pwm_path, offline=offline_path, idle_wifi=idle_path, physical_idle=physical_path)
    reports = {key: json.loads(path.read_text(encoding="utf-8-sig")) for key, path in paths.items()}
    pwm, offline, idle, physical = (reports[key] for key in paths)
    if not pwm.get("pass") or not pwm.get("restored") or not pwm.get("code_equivalence", {}).get("pass"):
        raise ValueError("PWM qualification/restoration/code equivalence failed")
    cases = pwm.get("cases", {})
    if set(cases) != set(mod.UART_V3_TRIAL_CASES) or any(c.get("pass") is not True for c in cases.values()):
        raise ValueError("all eight PWM scenarios required")
    if not all(pwm.get(key) is True for key in ("restore_uno_byte_verified", "restore_nucleo_byte_verified")):
        raise ValueError("normal image verification missing")
    images = {key: pwm.get("images", {}).get(key) for key in mod.UART_V3_TRIAL_IMAGES}
    if images != mod.UART_V3_TRIAL_IMAGES:
        raise ValueError("wrong qualified images")
    for key, relative in (
        ("production_uno", "uno_build/UNOQ_MOTOR.ino.elf-zsk.bin"),
        ("production_nucleo", "nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin")):
        image = root / "artifacts/live_bench_20261010/uart_v3_candidate/firmware_r6" / relative
        if hashlib.sha256(image.read_bytes()).hexdigest() != images[key]:
            raise ValueError("qualified image file changed")
    if (offline.get("pass") is not True or offline.get("sources_unchanged_during_tests") is not True
            or len(offline.get("tests", [])) < 40
            or not any(t.get("test") == "powered_trial_selftest" and t.get("pass") is True
                       for t in offline["tests"])):
        raise ValueError("trial-aware offline regression required")
    from uart_update_regression import source_hashes
    if offline.get("source_sha256") != source_hashes(root):
        raise ValueError("source changed since regression")
    if idle.get("pass") is not True or physical.get("confirmed", {}).get("pass") is not True:
        raise ValueError("post-restoration idle evidence failed")
    if idle.get("first_builds") != dict(zip(("fw_build", "mc_fw_build"), mod.UART_V3_TRIAL_PAIR)):
        raise ValueError("idle peer identities mismatch")
    now = time.time()
    proof = dict(schema="mic_ai.powered_trial.v1", pair=list(mod.UART_V3_TRIAL_PAIR), images=images,
        cases={key: True for key in cases}, normal_restore_verified=True, offline_pass=True,
        offline_suites=len(offline["tests"]), idle_wifi_pass=True, physical_idle_pass=True,
        hv_release_approved=False, issued_at=now, expires_at=now+3600,
        evidence_sha256={key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()})
    if not mod.validate_powered_trial_qualification(proof)[0]:
        raise ValueError("server rejected generated attestation")
    return proof


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("pwm", "offline", "idle", "physical", "out"):
        p.add_argument("--"+name, type=Path, required=True)
    args = p.parse_args()
    result = qualification(Path(__file__).resolve().parents[1], args.pwm, args.offline, args.idle, args.physical)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2); stream.write("\n")
    print(json.dumps({"prepared": True, "hardware_commands": 0, "expires_at": result["expires_at"]}))


if __name__ == "__main__": main()
