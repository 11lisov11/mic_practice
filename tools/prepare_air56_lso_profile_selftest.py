#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import prepare_air56_lso_profile as prepare
from mcsdk_release_preflight_selftest import profile as measured_fixture


def main() -> int:
    source = (
        "ProjectManager.ProjectName=OLD\n"
        "ProjectManager.ProjectFileName=OLD.ioc\n"
        "MotorControl.ACIM_CONFIG=VF_OL\n"
    )
    changed = prepare.set_ioc(source, "MotorControl.ACIM_CONFIG", "LSO_FOC")
    merged = prepare.merge_lso_motorcontrol_keys(
        source + "MotorControl.IPParameters=ACIM_CONFIG\n",
        "MotorControl.IPParameters=ACIM_CONFIG,WB_UI_INERTIA\nMotorControl.WB_UI_INERTIA=1700\n",
    )
    missing_rejected = False
    try:
        prepare.set_ioc(source, "MotorControl.MISSING", 1)
    except ValueError:
        missing_rejected = True
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "motor.ioc"
        path.write_text(changed, encoding="utf-8")
        persisted = path.read_text(encoding="utf-8")
    cases = {
        "exact_key_replaced": "MotorControl.ACIM_CONFIG=LSO_FOC" in persisted,
        "unrelated_key_preserved": "ProjectManager.ProjectName=OLD" in persisted,
        "missing_key_rejected": missing_rejected,
        "lso_only_key_merged": "MotorControl.WB_UI_INERTIA=1700" in merged,
        "lso_parameter_list_merged": "MotorControl.IPParameters=ACIM_CONFIG,WB_UI_INERTIA" in merged,
    }
    p = measured_fixture(prepare.gate.REQUIRED_PROFILE_SOURCE_KIND)
    p.update(magnetizing_current_rms_a=0.6, viscous_friction_nm_s=0.0002)
    board = ("MotorControl.M1_RSHUNT=0.04\nMotorControl.M1_AMPLIFICATION_GAIN=2.1\n"
             "MotorControl.ADC_REFERENCE_VOLTAGE=3.3\n")
    v = prepare.lso_values(p, board)
    scale = 65536 * 0.04 * 2.1 / 3.3
    cases.update({
        "rated_current_is_peak_digital_not_amperes": v["MotorControl.ACIM_NOMINAL_CURRENT"] == round(math.sqrt(2) * scale),
        "magnetizing_current_rms_to_peak": math.isclose(v["MotorControl.IMAGN_A"], math.sqrt(2)*0.6, abs_tol=1e-7),
        "flux_replaces_demo_motor_reference": v["MotorControl.ACIM_DEFAULT_FLUX_COMPONENT"] == round(math.sqrt(2)*0.6*scale),
        "torque_current_has_vector_headroom": v["MotorControl.ACIM_IQMAX"] == math.floor(math.sqrt(2)*scale*0.8),
        "inertia_si_to_micro_si": v["MotorControl.WB_UI_INERTIA"] == 1000,
        "friction_si_to_micro_si": v["MotorControl.WB_UI_FRICTION"] == 200,
        "mutual_inductance_uses_workbench_factor": math.isclose(v["MotorControl.LM"], 1.5*p["magnetizing_inductance_h"]),
        "rotor_time_constant_recomputed": math.isclose(v["MotorControl.TAU_R"], v["MotorControl.LR"]/p["rotor_resistance_ohm"]),
        "stator_time_constant_recomputed": math.isclose(v["MotorControl.TAU_S"], v["MotorControl.M1_LS"]/p["stator_resistance_ohm"]),
        "both_stator_resistance_fields_match": v["MotorControl.ACIM_RS"] == v["MotorControl.M1_RS"] == p["stator_resistance_ohm"],
        "frequency_ceiling_uses_synchronous_speed": v["MotorControl.ACIM_MAX_APPLICATION_SPEED"] == 1500,
    })
    for name, mutation in {
        "unknown_magnetizing_current": {"magnetizing_current_rms_a": None},
        "unknown_friction": {"viscous_friction_nm_s": None},
        "im_above_nominal": {"magnetizing_current_rms_a": 1.1},
        "im_equals_nominal": {"magnetizing_current_rms_a": 1.0},
        "infinite_im": {"magnetizing_current_rms_a": math.inf},
        "nan_friction": {"viscous_friction_nm_s": math.nan},
        "boolean_im": {"magnetizing_current_rms_a": True},
        "catalog_only": {"source_kind": prepare.gate.VF_CATALOG_SOURCE_KIND},
    }.items():
        try:
            prepare.lso_values({**p, **mutation}, board)
            cases[name+"_rejected"] = False
        except ValueError:
            cases[name+"_rejected"] = True
    for name, bad_board in {
        "missing_vref": board.replace("MotorControl.ADC_REFERENCE_VOLTAGE=3.3\n", ""),
        "nan_gain": board.replace("GAIN=2.1", "GAIN=nan"),
        "current_overrange": board.replace("RSHUNT=0.04", "RSHUNT=4.0"),
    }.items():
        try:
            prepare.lso_values(p, bad_board)
            cases[name+"_rejected"] = False
        except ValueError:
            cases[name+"_rejected"] = True
    # Use the actual installed ST IOC when present, not just a mock key list.
    official = Path("C:/Program Files (x86)/STMicroelectronics/MC_SDK_6.4.2/Utilities/PC_Software/STMCWB/assets/examples/ACIM-NUCLEOG431RB-IPM15B-LSO_FOC.ioc")
    if official.is_file():
        template = official.read_text(encoding="utf-8")
        values = prepare.lso_values(p, template)
        for key, value in values.items():
            template = prepare.set_ioc(template, key, value)
        cases["all_keys_exist_in_official_lso_ioc"] = True
        cases["official_lso_current_uses_correct_units"] = "MotorControl.ACIM_NOMINAL_CURRENT=2359\n" in template
    result = {"tool": "prepare_air56_lso_profile_selftest", "pass": all(cases.values()), "cases": cases}
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
