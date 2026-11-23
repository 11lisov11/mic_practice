"""Prepare an honest one-shot trial schema from the measured 1204-derived fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from ipm_break_wifi_selftest import load_module
from prepare_ipm_break_wifi import source_hashes
from prepare_mcsdk_logic_bench import replace_once

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "artifacts/live_bench_20261012/local_button"
BASE = HERE / "hmi_stop_candidate_r1/web_hmi/server.py"
BASE_SHA = "21bda96fae14b0fa13db27d1fb21edd6f059e6d2037199944bdae50999569276"
CAPTURE = HERE / "pwm_session_r2/manual_run_1791818470131763700"
PATHS = dict(
    fixture_pwm=CAPTURE / "report.json", fixture_capture=CAPTURE / "operator_capture.sal",
    fixture_code=HERE / "pwm_fixture_code_r1/report.json",
    fixture_selftest=HERE / "pwm_fixture_selftest_r5/report.json",
    production_idle=HERE / "post_cold_boot_r1/summary.json",
    production_restore_nucleo=HERE / "pwm_session_r2/restore_nucleo_readback.bin",
    production_restore_uno=HERE / "pwm_session_r2/verify_reset_unchanged_uno.log",
    baseline_offline=HERE / "regression_r1/report.json",
    calibration_contract=HERE / "selftest_r6/report.json",
    sd_sample=ROOT / "artifacts/live_bench_20261012/boot_trial/prepare_r1/qualification.json",
    hmi_guards=HERE / "hmi_stop_guards_r1/report.json",
)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding="utf-8-sig"))


def audit():
    assert sha(BASE) == BASE_SHA
    for component, folder in (("nucleo", HERE / "candidate_r5/nucleo"),
                              ("uno", HERE / "uno_peer_r2/UNOQ_MOTOR")):
        manifest=read(HERE / ("candidate_r5/manifest.json" if component=="nucleo" else "uno_peer_r2/manifest.json"))
        assert source_hashes(folder)==manifest["candidate_sha256" if component=="nucleo" else "source_sha256"]
    pwm=read(PATHS["fixture_pwm"]);code=read(PATHS["fixture_code"])
    assert pwm["pass"] and pwm["production_image_active_pwm_measured"] is False
    assert pwm["capture_sha256"]==sha(PATHS["fixture_capture"])
    assert code["pass"] and len(code["functions"])==10 and all(x["equal"] for x in code["functions"].values())
    assert code["timer_initializer_source_identical"]
    for key in ("fixture_selftest","production_idle","baseline_offline","calibration_contract","hmi_guards"):
        assert read(PATHS[key])["pass"] is True,key
    offline=read(PATHS["baseline_offline"])
    assert len(offline["tests"])>=57 and all(x["pass"] for x in offline["tests"])
    assert sha(PATHS["production_restore_nucleo"])=="f35dfb3c583b1e6f4822d62f3e7971f3a7cac0e3beed76565f273dbfa203e949"
    assert "verification PASSED; restarting unchanged images" in PATHS["production_restore_uno"].read_text()
    sd=read(PATHS["sd_sample"])
    assert sd["sd_sample_operator_reported"] is True and sd["sd_sample_v"]==2.6
    fixture=HERE / "pwm_fixture_r1"
    images=dict(fixture_uno=sha(fixture / "uno_build/UNOQ_MOTOR.ino.elf-zsk.bin"),
                fixture_nucleo=sha(fixture / "nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin"))
    return images,{key:sha(path) for key,path in PATHS.items()}


def patched(text,images,evidence):
    asset=(ROOT / "research/local_stop/fixture_trial_gate.py").read_text()
    asset=asset.replace("__LOCAL_STOP_FIXTURE_IMAGES__",repr(images)).replace("__LOCAL_STOP_RETAINED_EVIDENCE__",repr(evidence))
    text=replace_once(text,"def validate_boot_trial(proof):",asset+"\n\ndef validate_boot_trial(proof):")
    return replace_once(text,'    if proof.get("schema") == BOOT_TRIAL_SCHEMA:',
        '    if proof.get("schema") == LOCAL_STOP_FIXTURE_SCHEMA:\n'
        '        return validate_local_stop_fixture_trial(proof)\n'
        '    if proof.get("schema") == BOOT_TRIAL_SCHEMA:')


def prepare(out):
    images,evidence=audit();out.mkdir(parents=True,exist_ok=False)
    target=out / "web_hmi/server.py";target.parent.mkdir()
    target.write_text(patched(BASE.read_text(encoding="utf-8"),images,evidence),encoding="utf-8",newline="\n")
    module=load_module(target)
    now=time.time()
    proof=dict(schema=module.LOCAL_STOP_FIXTURE_SCHEMA,pair=list(module.BOOT_TRIAL_PAIR),
        images=dict(module.BOOT_TRIAL_IMAGES),fixture_pair=list(module.LOCAL_STOP_FIXTURE_PAIR),
        fixture_images=images,profile="short",scope="local_stop_fixture_equivalence_one_powered_trial",
        max_run_s=3,max_frequency_hz=5,offline_suites=len(read(PATHS["baseline_offline"])["tests"]),
        evidence_sha256=evidence,sd_sample_v=2.6,idle_tx_max_gap_us=51003,
        issued_at=now,expires_at=now+600)
    for key in ("fixture_six_pwm_and_local_stop_pass","fixture_stop_source_identical",
                "fixture_ten_code_sections_identical","production_images_restored_verified",
                "production_idle_wifi_pass","production_calibration_contract_pass",
                "retained_sd_sample_operator_reported","offline_pass"):proof[key]=True
    for key in ("new_pair_active_pwm_measured","physical_idle_registers_current",
                "exact_button_to_off_latency_measured","forced_enable_hardware_validated",
                "hv_release_approved","current_telemetry_qualified"):proof[key]=False
    assert module.validate_powered_trial_qualification(proof)[0]
    (out / "qualification_seed.json").write_text(json.dumps(proof,indent=2)+"\n")
    report=dict(schema="mic_ai.local_stop_fixture_trial_preparation.v1",prepared=True,
                installed=False,hardware_commands=0,mcu_firmware_changed=False,
                calibration_file_modified=False,source_hmi_sha256=BASE_SHA,hmi_sha256=sha(target),
                pair=list(module.BOOT_TRIAL_PAIR),max_run_s=3,max_frequency_hz=5,
                limits_and_live_monitoring_unchanged=True,production_active_pwm_claimed=False,
                evidence_sha256=evidence)
    (out / "manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--outdir",type=Path,required=True)
    a=p.parse_args();r=prepare(a.outdir.resolve())
    print(json.dumps({k:v for k,v in r.items() if k!="evidence_sha256"},indent=2))
