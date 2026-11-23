"""Prepare an HMI-only refresh, reusing MCU artifacts only for identical MCU sources."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_ipm_break_wifi import prepare, source_hashes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old-candidate", required=True, type=Path)
    p.add_argument("--outdir", required=True, type=Path)
    args = p.parse_args()
    old = args.old_candidate.resolve(strict=True)
    out = args.outdir.resolve()
    previous = json.loads((old / "manifest.json").read_text())
    fresh = prepare(out)
    for component, key in (("nucleo", "candidate_nucleo"), ("UNOQ_MOTOR", "candidate_uno")):
        actual = source_hashes(old / component)
        if fresh[key] != previous[key] or any(actual.get(k) != v for k, v in previous[key].items()):
            raise RuntimeError("MCU sources/configuration changed; actual rebuild required")
    for folder, name in (("uno_build", "unoq_mcsdk_scalar.build-manifest.json"),
                         ("nucleo/STM32CubeIDE/Debug", "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json")):
        build = json.loads((old / folder / name).read_text(encoding="utf-8-sig"))
        for artifact in build["artifacts"]:
            path = old / folder / artifact["file"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"].lower() or path.stat().st_size != artifact["bytes"]:
                raise RuntimeError("Previously compiled artifact changed")
        shutil.copytree(old / folder, out / folder)
    fresh["reused_verified_mcu_builds_from"] = str(old)
    fresh["mcu_source_bytes_identical"] = True
    (out / "manifest.json").write_text(json.dumps(fresh, indent=2) + "\n")
    print(json.dumps({"prepared": True, "mcu_rebuild_required": False, "mcu_sources_identical": True}))


if __name__ == "__main__":
    main()
