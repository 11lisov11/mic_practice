"""Run existing guard suites against a prepared HMI, not the installed service."""
import argparse
import contextlib
import importlib
import io
import json
import hashlib
from pathlib import Path

from ipm_break_wifi_selftest import load_module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--outdir", required=True, type=Path)
    args = p.parse_args(); out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    results = []
    for name in ("web_hmi_command_guard_selftest", "powered_trial_selftest", "coast30_gate_selftest",
                 "web_hmi_control_access_selftest", "vbus_calibration_identity_selftest"):
        suite = importlib.import_module(name)
        loader_name = "load_server_module" if hasattr(suite, "load_server_module") else "load_server"
        old = getattr(suite, loader_name)
        setattr(suite, loader_name, lambda root: load_module(args.candidate.resolve() / "web_hmi/server.py"))
        log = io.StringIO()
        try:
            with contextlib.redirect_stdout(log):
                code = suite.main()
            passed = code in (None, 0)
        finally:
            setattr(suite, loader_name, old)
            (out / f"{name}.log").write_text(log.getvalue(), encoding="utf-8")
        results.append({"suite": name, "pass": passed})
        if not passed:
            raise RuntimeError("Candidate HMI guard suite failed: " + name)
    report = {"pass": True, "suites": results, "hardware_commands": 0,
              "hmi_sha256": hashlib.sha256((args.candidate.resolve()/"web_hmi/server.py").read_bytes()).hexdigest(),
              "scope": "Existing command, trial, authentication and calibration tests against prepared HMI"}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"pass": True, "suites": len(results)}))


if __name__ == "__main__":
    main()
