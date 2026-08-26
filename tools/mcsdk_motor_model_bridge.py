#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from motor_identification.mcsdk_bridge import (  # noqa: E402
    MotorModelBridgeError,
    build_motor_model_bundle,
    canonical_sha256,
    validate_motor_model_bundle,
)


def _load(path: str) -> dict:
    value = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MotorModelBridgeError(f"{path} must contain a JSON object")
    return value


def _write(path: str, payload: dict) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return target


def _render(args: argparse.Namespace) -> int:
    result = _load(args.identification)
    profile = _load(args.profile)
    bundle = build_motor_model_bundle(
        result,
        profile,
        allow_synthetic=bool(args.allow_synthetic_dry_run),
    )
    target = _write(args.output, bundle)
    print(
        json.dumps(
            {
                "pass": True,
                "output": str(target),
                "bundle_sha256": canonical_sha256(bundle),
                "deployment_class": bundle["deployment_class"],
                "eligible_for_foc_project_generation": bundle["eligible_for_foc_project_generation"],
                "eligible_for_hv_release": bundle["eligible_for_hv_release"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _validate(args: argparse.Namespace) -> int:
    bundle = _load(args.input)
    validate_motor_model_bundle(bundle, require_hardware=bool(args.require_hardware))
    print(
        json.dumps(
            {
                "pass": True,
                "bundle_sha256": canonical_sha256(bundle),
                "deployment_class": bundle["deployment_class"],
                "eligible_for_foc_project_generation": bundle["eligible_for_foc_project_generation"],
                "eligible_for_hv_release": bundle["eligible_for_hv_release"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed bridge from accepted motor identification to an MCSDK model bundle."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render", help="Build a deterministic motor_model_bundle.v1 JSON file.")
    render.add_argument("--identification", required=True)
    render.add_argument("--profile", required=True)
    render.add_argument("--output", required=True)
    render.add_argument(
        "--allow-synthetic-dry-run",
        action="store_true",
        help="Permit a simulation-only mapping artifact; never enables firmware or HV release.",
    )
    render.set_defaults(func=_render)

    validate = sub.add_parser("validate", help="Validate a motor_model_bundle.v1 artifact.")
    validate.add_argument("--input", required=True)
    validate.add_argument("--require-hardware", action="store_true")
    validate.set_defaults(func=_validate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (OSError, json.JSONDecodeError, MotorModelBridgeError, ValueError) as exc:
        print(json.dumps({"pass": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
