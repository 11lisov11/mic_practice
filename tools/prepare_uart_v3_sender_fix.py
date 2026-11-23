"""Clone the known Uno source, canonicalizing ignored scalar bytes; never upload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_mcsdk_logic_bench import replace_once


def patched_sketch(text):
    text = replace_once(text, "FW_BUILD_ID = 2026101007U", "FW_BUILD_ID = 2026101008U")
    return replace_once(text, "uint16_t scalar_vmag_q15 = bp_scalar_vmag_q15();",
        "// MCSDK owns V/f voltage too; its receiver ignores this legacy field.\n"
        "    const uint16_t scalar_vmag_q15 = mcsdk_scalar ? 0U : bp_scalar_vmag_q15();")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir", type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / "artifacts/live_bench_20261010/uart_v3_candidate/firmware_r6/UNOQ_MOTOR"
    out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in source.iterdir() if f.is_file()}
    shutil.copytree(source, out / "UNOQ_MOTOR")
    sketch = out / "UNOQ_MOTOR/UNOQ_MOTOR.ino"
    sketch.write_text(patched_sketch(sketch.read_text(encoding="utf-8-sig")), encoding="utf-8")
    after = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in source.iterdir() if f.is_file()}
    if before != after:
        raise RuntimeError("reference source changed during preparation")
    report = dict(prepared=True, uno_build=2026101008, nucleo_build=2026101006,
        hardware_commands=0, flash_ready=False, hv_release_approved=False,
        purpose="Sender invariant fix only; receiver/protection/timing policy unchanged",
        source_sha256=before, sketch_sha256=hashlib.sha256(sketch.read_bytes()).hexdigest())
    (out/"manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ("prepared","uno_build","nucleo_build","hardware_commands")}))


if __name__ == "__main__": main()
