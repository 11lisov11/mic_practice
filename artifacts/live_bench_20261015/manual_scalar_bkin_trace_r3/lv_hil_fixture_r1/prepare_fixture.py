"""Prepare, but do not flash, a low-voltage external-SD fixture for pair 1507/1506.

The temporary image reuses the installed peer build ID for HMI protocol
compatibility. Its distinct SHA and fixture-only scope are recorded below.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(r"C:\mic_practice")
HERE = Path(__file__).resolve().parent
CANDIDATE_NUCLEO = ROOT / "artifacts/live_bench_20261015/manual_scalar_bkin_trace_r3/nucleo"
SOURCE_OVERRIDE = HERE / "source_override"
FIXTURE_OUT = HERE / "fixture"
BASE_PREPARER = ROOT / "tools/prepare_mcsdk_logic_bench.py"
PREPARER_COPY = HERE / "prepare_mcsdk_logic_bench_current.py"

if FIXTURE_OUT.exists() or SOURCE_OVERRIDE.exists() or PREPARER_COPY.exists():
    raise SystemExit("Refusing to overwrite an existing fixture artifact")

shutil.copytree(CANDIDATE_NUCLEO, SOURCE_OVERRIDE,
                ignore=shutil.ignore_patterns("Debug", "Release", ".settings", ".metadata", "__pycache__"))
text = BASE_PREPARER.read_text(encoding="utf-8")
replacements = {
    "allowed_pairs = {(2026100707, BENCH_BUILD), (2026100801, 2026100899), (2026101006, 2026101099)}":
        "allowed_pairs = {(2026100707, BENCH_BUILD), (2026100801, 2026100899), (2026101006, 2026101099), (2026101506, 2026101506)}",
    "if (production_build, bench_build) != (2026101006, 2026101099) or not source.is_relative_to(root.resolve()):":
        "if (production_build, bench_build) not in ((2026101006, 2026101099), (2026101506, 2026101506)) or not source.is_relative_to(root.resolve()):",
    "if bus_limit_v != 2 and (production_build, bench_build) != (2026100801, 2026100899):":
        "if bus_limit_v != 2 and (production_build, bench_build) not in ((2026100801, 2026100899), (2026101506, 2026101506)):",
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise SystemExit(f"Expected exactly one fixture-policy anchor: {old}")
    text = text.replace(old, new, 1)
PREPARER_COPY.write_text(text, encoding="utf-8", newline="\n")

spec = importlib.util.spec_from_file_location("current_bkin_fixture_preparer", PREPARER_COPY)
if spec is None or spec.loader is None:
    raise SystemExit("Could not load isolated fixture preparer")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
report = module.prepare(ROOT, FIXTURE_OUT, production_build=2026101506,
                        bench_build=2026101506, bus_limit_v=10,
                        automatic_sd_pulse=True, source_override=SOURCE_OVERRIDE)
report["temporary_image_identity"] = {
    "uno_build": 2026101507,
    "nucleo_protocol_build_id": 2026101506,
    "reason_for_reuse": "preserve the installed UNO/HMI peer-build contract during this isolated fixture only",
    "image_is_not_production": True,
    "required_physical_setup": [
        "mains disconnected",
        "STEVAL J1 physically disconnected",
        "motor J3 physically disconnected",
        "only auxiliary J4 may be energized, and DC bus must stay <=10 V",
        "Nucleo PC8 CN10-2 to STEVAL TP23 through 1 kohm series resistor",
    ],
}
(HERE / "fixture_manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "prepared": report["pass"],
    "fixture_project": report["project"],
    "external_stimulus": report["external_stimulus"],
    "changed_files": list(report["changed_files"]),
    "hardware_validated": False,
}, indent=2))
