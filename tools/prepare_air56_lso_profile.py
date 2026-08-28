#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import mcsdk_release_preflight as gate


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
    args = parser.parse_args()

    project = args.project.resolve()
    profile = gate.read_json(args.motor_profile.resolve())
    errors = gate.profile_errors(profile)
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

    controller_phase_v = float(profile.get(
        "controller_equivalent_phase_voltage_v",
        float(profile["rated_line_voltage_v"]) / math.sqrt(3.0),
    ))
    speed_limit = math.ceil(float(profile["rated_speed_rpm"]) * 1.05)
    values = {
        "ProjectManager.ProjectName": args.project_name,
        "ProjectManager.ProjectFileName": f"{args.project_name}.ioc",
        "MotorControl.ACIM_CONFIG": "LSO_FOC",
        "MotorControl.M1_MOTOR_NAME": str(profile.get("motor_id", "IEK_AIR56B2_MEASURED")),
        "MotorControl.ACIM_POLE_PAIR_NUM": int(profile["pole_pairs"]),
        "MotorControl.NOMINAL_FREQ": float(profile["rated_frequency_hz"]),
        "MotorControl.NOMINAL_PHASE_VOLTAGE": round(controller_phase_v, 6),
        "MotorControl.ACIM_NOMINAL_CURRENT": float(profile["rated_current_a"]),
        "MotorControl.M1_MAX_APPLICATION_SPEED": speed_limit,
        "MotorControl.M1_MOTOR_MAX_SPEED_RPM": speed_limit,
        "MotorControl.M1_RS": float(profile["stator_resistance_ohm"]),
        "MotorControl.RR": float(profile["rotor_resistance_ohm"]),
        "MotorControl.LLS": float(profile["stator_leakage_inductance_h"]),
        "MotorControl.LLR": float(profile["rotor_leakage_inductance_h"]),
        "MotorControl.LMS": float(profile["magnetizing_inductance_h"]),
        "MotorControl.WB_UI_INERTIA": float(profile["rotor_inertia_kg_m2"]),
    }
    for key, value in values.items():
        text = set_ioc(text, key, value)
    text = set_ioc(text, "MotorControl.ACIM_RS", float(profile["stator_resistance_ohm"]))

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
