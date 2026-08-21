#!/usr/bin/env python3
"""Restore the CMSIS-DSP include entry omitted by some CubeMX regenerations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


CMSIS_INCLUDE = 'value="../../Drivers/CMSIS/Include"/>'
DSP_INCLUDE = 'value="../../Drivers/CMSIS/DSP/Include"/>'


def patch_cproject(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing CubeIDE project file: {path}")

    text = path.read_text(encoding="utf-8")
    if DSP_INCLUDE in text:
        return {"path": str(path), "changed": False, "reason": "already_present"}

    lines = text.splitlines(keepends=True)
    patched: list[str] = []
    inserts = 0
    for line in lines:
        patched.append(line)
        if CMSIS_INCLUDE not in line:
            continue
        indent = line[: len(line) - len(line.lstrip())]
        newline = "\r\n" if line.endswith("\r\n") else "\n"
        patched.append(f'{indent}<listOptionValue builtIn="false" {DSP_INCLUDE}{newline}')
        inserts += 1

    if inserts == 0:
        raise RuntimeError("Could not find a CMSIS include list entry to extend.")

    path.write_text("".join(patched), encoding="utf-8", newline="")
    return {"path": str(path), "changed": True, "insertions": inserts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cproject", type=Path, help="Path to STM32CubeIDE/.cproject")
    args = parser.parse_args()
    print(json.dumps(patch_cproject(args.cproject), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
