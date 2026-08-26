#!/usr/bin/env python3
"""Verify hashes and required artifacts in the locally built firmware bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"{label}:missing_manifest:{path}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label}:invalid_manifest:{exc}")
        return {}


def verify_artifacts(
    *,
    directory: Path,
    manifest: dict[str, Any],
    expected_schema: str,
    expected_files: set[str],
    label: str,
    errors: list[str],
) -> None:
    if manifest.get("schema") != expected_schema:
        errors.append(f"{label}:unexpected_schema")
    entries = manifest.get("artifacts")
    if not isinstance(entries, list):
        errors.append(f"{label}:artifacts_missing")
        return
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            errors.append(f"{label}:invalid_artifact_entry")
            continue
        name = entry["file"]
        seen.add(name)
        path = directory / name
        if not path.is_file():
            errors.append(f"{label}:missing_artifact:{name}")
            continue
        if path.stat().st_size <= 1024:
            errors.append(f"{label}:artifact_too_small:{name}")
        if entry.get("bytes") != path.stat().st_size:
            errors.append(f"{label}:size_mismatch:{name}")
        if entry.get("sha256") != sha256(path):
            errors.append(f"{label}:hash_mismatch:{name}")
    if seen != expected_files:
        errors.append(f"{label}:unexpected_artifact_set:{sorted(seen)}")


def verify_binary_signatures(path: Path, label: str, errors: list[str]) -> None:
    elf = path / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf"
    if elf.is_file() and elf.read_bytes()[:4] != b"\x7fELF":
        errors.append(f"{label}:invalid_elf_magic")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Verify the generated UNO Q and Nucleo firmware bundle.")
    parser.add_argument(
        "--nucleo-directory",
        type=Path,
        default=root
        / "mcsdk_reference"
        / "AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
        / "STM32CubeIDE"
        / "Debug",
    )
    parser.add_argument("--uno-directory", type=Path, default=root / "firmware" / "unoq_mcsdk_scalar")
    args = parser.parse_args()

    nucleo_dir = args.nucleo_directory
    uno_dir = args.uno_directory
    errors: list[str] = []
    nucleo_manifest = read_json(
        nucleo_dir / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json", errors, "nucleo"
    )
    uno_manifest = read_json(uno_dir / "unoq_mcsdk_scalar.build-manifest.json", errors, "uno")
    verify_artifacts(
        directory=nucleo_dir,
        manifest=nucleo_manifest,
        expected_schema="mic_ai.mcsdk.acim_reference_build.v1",
        expected_files={
            "ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf",
            "ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin",
            "ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex",
        },
        label="nucleo",
        errors=errors,
    )
    verify_binary_signatures(nucleo_dir, "nucleo", errors)
    verify_artifacts(
        directory=uno_dir,
        manifest=uno_manifest,
        expected_schema="mic_ai.unoq_mcsdk_scalar_build.v1",
        expected_files={
            "UNOQ_MOTOR.ino.elf",
            "UNOQ_MOTOR.ino.hex",
            "UNOQ_MOTOR.ino.bin",
            "UNOQ_MOTOR.ino.elf-zsk.bin",
        },
        label="uno",
        errors=errors,
    )
    if uno_manifest.get("flash_artifact") != "UNOQ_MOTOR.ino.elf-zsk.bin":
        errors.append("uno:unexpected_flash_artifact")

    report = {
        "tool": "verify_firmware_bundle",
        "pass": not errors,
        "nucleo_directory": str(nucleo_dir),
        "uno_directory": str(uno_dir),
        "failures": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
