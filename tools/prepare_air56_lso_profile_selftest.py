#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import prepare_air56_lso_profile as prepare


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
    result = {"tool": "prepare_air56_lso_profile_selftest", "pass": all(cases.values()), "cases": cases}
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
