#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import mcsdk_release_preflight as gate


def lso_profile_errors(profile: dict) -> list[str]:
    """FOC needs a measured flux current, not the demo motor's retained Id."""
    errors = gate.profile_errors(profile)
    if profile.get("source_kind") != gate.REQUIRED_PROFILE_SOURCE_KIND:
        errors.append("lso_requires_measured_motor_model")
    for name in ("magnetizing_current_rms_a", "viscous_friction_nm_s"):
        value = profile.get(name)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0
                or (name == "magnetizing_current_rms_a" and value == 0)):
            errors.append(f"lso_missing_or_invalid_{name}")
    im, nominal = profile.get("magnetizing_current_rms_a"), profile.get("rated_current_a")
    if (not isinstance(im, bool) and isinstance(im, (int, float))
            and not isinstance(nominal, bool) and isinstance(nominal, (int, float))
            and math.isfinite(im) and math.isfinite(nominal) and im >= nominal):
        errors.append("lso_magnetizing_current_must_be_below_rated_current")
    return sorted(set(errors))


def lso_values(profile: dict, ioc_text: str) -> dict[str, object]:
    """Apply MCSDK 6.4.2 Workbench ACIM conventions (S1n/Acn in its UI).

    Profile Lm is the Workbench LMS input, not its generated 1.5*LMS.
    ACIM currents are signed 16-bit units, with RMS converted to peak.
    Workbench mechanical fields use micro-SI (division by 1e6 in _1n).
    """
    errors = lso_profile_errors(profile)
    if errors:
        raise ValueError("Measured motor profile rejected: " + ", ".join(errors))

    def board_value(key: str) -> float:
        match = re.search(rf"(?m)^MotorControl\.{re.escape(key)}=([^\r\n]+)$", ioc_text)
        if not match:
            raise ValueError(f"Missing current sensing parameter: {key}")
        value = float(match.group(1))
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid current sensing parameter: {key}")
        return value

    scale = 65536.0 * board_value("M1_RSHUNT") * board_value("M1_AMPLIFICATION_GAIN") / board_value("ADC_REFERENCE_VOLTAGE")
    nominal = math.sqrt(2.0) * float(profile["rated_current_a"]) * scale
    imag_peak = math.sqrt(2.0) * float(profile["magnetizing_current_rms_a"])
    flux = imag_peak * scale
    if not 0 < flux < nominal < 32767:
        raise ValueError("FOC currents exceed the signed MCSDK current range")
    lm = 1.5 * float(profile["magnetizing_inductance_h"])
    ls = lm + float(profile["stator_leakage_inductance_h"])
    lr = lm + float(profile["rotor_leakage_inductance_h"])
    rs, rr = float(profile["stator_resistance_ohm"]), float(profile["rotor_resistance_ohm"])
    phase_v = float(profile.get("controller_equivalent_phase_voltage_v", float(profile["rated_line_voltage_v"]) / math.sqrt(3.0)))
    speed_limit = math.ceil(60.0 * float(profile["rated_frequency_hz"]) / int(profile["pole_pairs"]))
    return {
        "MotorControl.ACIM_CONFIG": "LSO_FOC",
        "MotorControl.M1_MOTOR_NAME": str(profile.get("motor_id", "IEK_AIR56B2_MEASURED")),
        "MotorControl.ACIM_POLE_PAIR_NUM": int(profile["pole_pairs"]),
        "MotorControl.NOMINAL_FREQ": float(profile["rated_frequency_hz"]),
        "MotorControl.NOMINAL_PHASE_VOLTAGE": round(phase_v, 6),
        "MotorControl.ACIM_NOMINAL_CURRENT": round(nominal),
        "MotorControl.IMAGN_A": round(imag_peak, 7),
        "MotorControl.ACIM_DEFAULT_FLUX_COMPONENT": round(flux),
        "MotorControl.ACIM_IQMAX": math.floor(math.sqrt(nominal * nominal - flux * flux)),
        "MotorControl.ACIM_MAX_APPLICATION_SPEED": speed_limit,
        "MotorControl.M1_MAX_APPLICATION_SPEED": speed_limit,
        "MotorControl.M1_MOTOR_MAX_SPEED_RPM": speed_limit,
        "MotorControl.M1_RS": rs,
        "MotorControl.ACIM_RS": rs,
        "MotorControl.RR": rr,
        "MotorControl.LLS": float(profile["stator_leakage_inductance_h"]),
        "MotorControl.LLR": float(profile["rotor_leakage_inductance_h"]),
        "MotorControl.LMS": float(profile["magnetizing_inductance_h"]),
        "MotorControl.LM": lm,
        "MotorControl.M1_LS": ls,
        "MotorControl.LR": lr,
        "MotorControl.TAU_S": ls / rs,
        "MotorControl.TAU_R": lr / rr,
        "MotorControl.SIGMA": 1.0 - lm * lm / (ls * lr),
        "MotorControl.WB_UI_INERTIA": float(profile["rotor_inertia_kg_m2"]) * 1e6,
        "MotorControl.WB_UI_FRICTION": float(profile["viscous_friction_nm_s"]) * 1e6,
    }


def set_ioc(text: str, key: str, value: object) -> str:
    rendered = str(value)
    pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    if not pattern.search(text):
        raise ValueError(f"IOC key is missing: {key}")
    return pattern.sub(f"{key}={rendered}", text, count=1)


def merge_lso_motorcontrol_keys(text: str, template_text: str) -> str:
    current_keys = {
        match.group(1)
        for match in re.finditer(r"(?m)^(MotorControl\.[^=]+)=.*$", text)
    }
    template_entries = re.findall(r"(?m)^(MotorControl\.[^=]+)=(.*)$", template_text)
    template_map = dict(template_entries)
    if "MotorControl.IPParameters" in template_map:
        text = set_ioc(text, "MotorControl.IPParameters", template_map["MotorControl.IPParameters"])
    additions = [
        f"{key}={value}"
        for key, value in template_entries
        if key not in current_keys
    ]
    if additions:
        text = text.rstrip() + "\n" + "\n".join(additions) + "\n"
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a measured AIR56B2 MCSDK LSO-FOC IOC seed")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--motor-profile", type=Path, required=True)
    parser.add_argument("--lso-template", type=Path, required=True)
    parser.add_argument("--project-name", default="ACIM-NUCLEOG431RB-IPM15B-AIR56B2-LSO_FOC")
    parser.add_argument("--validate-only", action="store_true", help="Check profile without copying or modifying a project")
    args = parser.parse_args()

    project = args.project.resolve()
    profile = gate.read_json(args.motor_profile.resolve())
    errors = lso_profile_errors(profile)
    if args.validate_only:
        print(json.dumps({"passed": not errors, "errors": errors,
                          "motor_profile": str(args.motor_profile.resolve()),
                          "hardware_commands": 0, "project_modified": False}, indent=2))
        return 0 if not errors else 2
    if errors:
        raise SystemExit("Measured motor profile rejected: " + ", ".join(errors))
    if profile.get("source_kind") != gate.REQUIRED_PROFILE_SOURCE_KIND:
        raise SystemExit("LSO-FOC requires source_kind=nameplate_and_measurement")

    ioc_files = list(project.glob("*.ioc"))
    if len(ioc_files) != 1:
        raise SystemExit(f"Expected one IOC in {project}, found {len(ioc_files)}")
    ioc = ioc_files[0]
    text = ioc.read_text(encoding="utf-8", errors="strict")
    text = merge_lso_motorcontrol_keys(
        text,
        args.lso_template.resolve().read_text(encoding="utf-8", errors="strict"),
    )

    values = lso_values(profile, text)
    values.update({
        "ProjectManager.ProjectName": args.project_name,
        "ProjectManager.ProjectFileName": f"{args.project_name}.ioc",
    })
    for key, value in values.items():
        text = set_ioc(text, key, value)

    destination = ioc.with_name(f"{args.project_name}.ioc")
    destination.write_text(text, encoding="utf-8")
    if destination != ioc:
        ioc.unlink()
    report = {
        "tool": "prepare_air56_lso_profile",
        "pass": True,
        "ioc": str(destination),
        "project_name": args.project_name,
        "control": "LSO_FOC",
        "motor_profile": str(args.motor_profile.resolve()),
        "applied": values,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
