"""Build-only preparation of the 1204-derived detached zero-bus LOCAL STOP fixture."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil

from prepare_ipm_break_wifi import source_hashes
from prepare_mcsdk_logic_bench import FIXTURE_STATE, BENCH_BUS_READY, replace_once, function_span

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "artifacts/live_bench_20261012/local_button"
NUCLEO = HERE / "candidate_r5/nucleo"
UNO = HERE / "uno_peer_r2/UNOQ_MOTOR"
HMI = HERE / "hmi_stop_candidate_r1/web_hmi/server.py"
PAIR = (2026101298, 2026101299)
VF = "MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/acim_vf_control.c"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_server(text):
    # Additional restrictions apply only to the separate fixture process.
    return replace_once(text, ') -> tuple[bool, str]:\n    if not cfg.enabled:\n',
        ') -> tuple[bool, str]:\n'
        '    if cfg.profile != ARM_PROFILE_LV:\n'
        '        return False, "detached fixture prohibits HV arming"\n'
        '    if data is None or (data.get("fw_build"), data.get("mc_fw_build")) != (2026101298, 2026101299):\n'
        '        return False, "detached fixture peer identity mismatch"\n'
        '    if cfg.max_vdc > 2 or not 0 <= _as_float(data, "vdc", 999) <= 2:\n'
        '        return False, "detached fixture requires real bus <=2 V"\n'
        '    if _as_float(data, "freq_cmd", 999) > 5:\n'
        '        return False, "detached fixture is limited to 5 Hz"\n'
        '    if not cfg.enabled:\n')


def prepare(out):
    original = source_hashes(NUCLEO)
    recorded = json.loads((HERE / "candidate_r5/manifest.json").read_text())
    if original != recorded["candidate_sha256"]:
        raise RuntimeError("Frozen 1204 sources changed")
    if sha(HMI) != "21bda96fae14b0fa13db27d1fb21edd6f059e6d2037199944bdae50999569276":
        raise RuntimeError("Unexpected HMI baseline")
    uno_before = source_hashes(UNO)
    if uno_before != json.loads((HERE / "uno_peer_r2/manifest.json").read_text())["source_sha256"]:
        raise RuntimeError("Frozen 1205 sources changed")
    out.mkdir(parents=True, exist_ok=False)
    project = out / "nucleo"
    shutil.copytree(NUCLEO, project, ignore=shutil.ignore_patterns("Debug", "Release", ".metadata"))
    path = project / "Src/main.c"
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "#define MIC_NUCLEO_FW_BUILD_ID 2026101204UL",
                        "#define MIC_NUCLEO_FW_BUILD_ID 2026101299UL")
    text = replace_once(text, "static void uno_link_init(void);",
                        "static void uno_link_init(void);\nbool mic_logic_bench_bus_ready(void);")
    a, b = function_span(text, "uno_update_softstart_state")
    text = text[:a] + BENCH_BUS_READY + text[b:]
    text = replace_once(text,
        "      ((uint32_t)MOTOR_MAX_SPEED_RPM * (uint32_t)POLE_PAIR_NUM * 1000U) / 60U;",
        "      5000U; /* Detached fixture: no command above 5 Hz. */")
    path.write_text(text, encoding="utf-8")
    path = project / "Src/mc_tasks.c"
    text = path.read_text(encoding="utf-8")
    state = FIXTURE_STATE.replace(
        ">= 15000U", ">= 3000U").replace("15 s", "3 s")
    text = replace_once(text, "__weak void TSK_SafetyTask_PWMOFF(uint8_t bMotor)",
                        state + "\n__weak void TSK_SafetyTask_PWMOFF(uint8_t bMotor)")
    anchor = "CodeReturn |= errMask[bMotor] & RVBS_CalcAvVbus(&BusVoltageSensor_M1, rawValueM1);"
    text = replace_once(text, anchor, anchor +
                        "\n    CodeReturn = mic_logic_bench_observe_bus(rawValueM1, CodeReturn);")
    path.write_text(text, encoding="utf-8")
    path = project / VF
    text = replace_once(path.read_text(encoding="utf-8"),
        "uint16_t hVbus_V = VBS_GetAvBusVoltage_V(pBVS);",
        "/* DETACHED FIXTURE ONLY: real ADC telemetry remains unchanged. */\n"
        "  (void)pBVS;\n  uint16_t hVbus_V = 310U;")
    path.write_text(text, encoding="utf-8")
    path = project / "Inc/break_wire.h"
    path.write_text(replace_once(path.read_text(), "BW_NUCLEO_BUILD 2026101204UL",
                                 "BW_NUCLEO_BUILD 2026101299UL"), encoding="utf-8")
    target = out / "UNOQ_MOTOR"
    shutil.copytree(UNO, target)
    path = target / "UNOQ_MOTOR.ino"
    path.write_text(replace_once(path.read_text(), "FW_BUILD_ID = 2026101205U",
                                 "FW_BUILD_ID = 2026101298U"), encoding="utf-8")
    path = target / "nucleo_fault_diagnostics.h"
    path.write_text(replace_once(path.read_text(), "build == 2026101204U;",
        "build == 2026101204U || build == 2026101299U;"), encoding="utf-8")
    path = target / "break_wire.h"
    path.write_text(replace_once(path.read_text(), "BW_NUCLEO_BUILD 2026101204UL",
                                 "BW_NUCLEO_BUILD 2026101299UL"), encoding="utf-8")
    after = source_hashes(project)
    changed = {k for k in set(after) | set(original) if after.get(k) != original.get(k)}
    if changed != {"Src/main.c", "Src/mc_tasks.c", VF, "Inc/break_wire.h"}:
        raise RuntimeError("Unexpected Nucleo fixture changes: " + str(changed))
    uno_after = source_hashes(target)
    if {k for k in uno_before if uno_before[k] != uno_after[k]} != {
            "UNOQ_MOTOR.ino", "nucleo_fault_diagnostics.h", "break_wire.h"}:
        raise RuntimeError("Unexpected Uno changes")
    if (target / "break_wire.h").read_bytes() != (project / "Inc/break_wire.h").read_bytes():
        raise RuntimeError("Snapshot peers disagree")
    web = out / "web_hmi/server.py"
    web.parent.mkdir()
    web.write_text(fixture_server(HMI.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    report = dict(schema="mic_ai.local_stop_zero_bus_fixture.v1", prepared=True, installed=False,
                  fixture_pair=list(PAIR), production_pair=[2026101205, 2026101204],
                  nucleo_source_sha256=after, uno_source_sha256=uno_after,
                  changed_nucleo_files=sorted(changed), hmi_sha256=sha(web),
                  purpose="J1 AND U/V/W DETACHED, J4 OFF, MEASURED BUS <=2V; NO HV OR MOTOR",
                  max_run_s=3, max_frequency_hz=5, mcu_filtered_bus_limit_v=2,
                  production_image_active_pwm_measured=False, hv_release_approved=False,
                  hardware_commands=0, original_calibration_modified=False)
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.outdir.resolve())
    print(json.dumps({k:v for k,v in result.items() if not k.endswith("source_sha256")}, indent=2))
