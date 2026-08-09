#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from motor_identification.schema import load_capture, load_prior  # noqa: E402
from motor_identification.service import identify_motor, validate_capture_payload  # noqa: E402
from motor_identification.synthetic import make_synthetic_bundle  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _cmd_validate(args: argparse.Namespace) -> int:
    capture = load_capture(args.input)
    report = validate_capture_payload(capture)
    if args.output:
        _write_json(Path(args.output).expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["identification_eligible"] else 2


def _cmd_identify(args: argparse.Namespace) -> int:
    capture = load_capture(args.input)
    prior = load_prior(args.prior)
    result = identify_motor(
        capture,
        prior,
        starts=args.starts,
        seed=args.seed,
        bound_factor=args.bound_factor,
        max_nfev=args.max_nfev,
        condition_limit=args.condition_limit,
        max_fit_nrmse=args.max_fit_nrmse,
        max_validation_nrmse=args.max_validation_nrmse,
        max_relative_ci_half_width=args.max_relative_ci_half_width,
    )
    output = Path(args.output).expanduser().resolve()
    _write_json(output, result)
    summary = {
        "accepted": result.get("accepted"),
        "decision": result.get("decision"),
        "blockers": result.get("blockers"),
        "estimated_params_si": result.get("estimated_params_si"),
        "fit_nrmse": (result.get("fit_metrics") or {}).get("normalized_rmse"),
        "validation_nrmse": (result.get("validation_metrics") or {}).get("normalized_rmse"),
        "output": str(output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result.get("accepted") is True else 3


def _cmd_generate_synthetic(args: argparse.Namespace) -> int:
    capture, prior = make_synthetic_bundle(
        seed=args.seed,
        steps_per_electrical_experiment=args.steps,
    )
    output_dir = Path(args.output_dir).expanduser().resolve()
    capture_path = output_dir / "capture.json"
    prior_path = output_dir / "prior.json"
    _write_json(capture_path, capture)
    _write_json(prior_path, prior)
    print(
        json.dumps(
            {"capture": str(capture_path), "prior": str(prior_path)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed offline identification of induction-motor parameters."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate capture contract without fitting.")
    validate.add_argument("--input", required=True, help="capture.json or a bundle directory")
    validate.add_argument("--output", help="optional JSON contract report")
    validate.set_defaults(func=_cmd_validate)

    identify = sub.add_parser("identify", help="Run rank-gate, fit, and independent validation.")
    identify.add_argument("--input", required=True, help="capture.json or a bundle directory")
    identify.add_argument("--prior", required=True, help="motor prior JSON")
    identify.add_argument("--output", required=True, help="result JSON")
    identify.add_argument("--starts", type=int, default=5)
    identify.add_argument("--seed", type=int, default=0)
    identify.add_argument("--bound-factor", type=float, default=4.0)
    identify.add_argument("--max-nfev", type=int, default=160)
    identify.add_argument("--condition-limit", type=float, default=1.0e8)
    identify.add_argument("--max-fit-nrmse", type=float, default=3.0)
    identify.add_argument("--max-validation-nrmse", type=float, default=3.0)
    identify.add_argument("--max-relative-ci-half-width", type=float, default=0.5)
    identify.set_defaults(func=_cmd_identify)

    synthetic = sub.add_parser(
        "generate-synthetic",
        help="Generate an independent fit/validation bundle for software verification only.",
    )
    synthetic.add_argument("--output-dir", required=True)
    synthetic.add_argument("--seed", type=int, default=20260809)
    synthetic.add_argument("--steps", type=int, default=360)
    synthetic.set_defaults(func=_cmd_generate_synthetic)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
