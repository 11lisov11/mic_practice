from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def verify_build(folder: Path, filename: str, expected_id: int) -> None:
    manifest = json.loads((folder / filename).read_text(encoding="utf-8-sig"))
    build_id = manifest.get("firmware_build_id")
    if build_id is None:
        build_id = manifest.get("firmware_build_id")
    assert build_id == expected_id, (folder, build_id)
    for item in manifest["artifacts"]:
        artifact = folder / item["file"]
        assert artifact.stat().st_size == item["bytes"], artifact
        assert sha(artifact) == item["sha256"].upper(), artifact


def main() -> None:
    assert (ROOT / "nucleo/Inc/uart_v3_transport.h").read_bytes() == \
           (ROOT / "UNOQ_MOTOR/uart_v3_transport.h").read_bytes()
    assert (ROOT / "nucleo/Inc/uart_fault_wire.h").read_bytes() == \
           (ROOT / "UNOQ_MOTOR/uart_fault_wire.h").read_bytes()
    assert (ROOT / "nucleo/Inc/break_wire.h").read_bytes() == \
           (ROOT / "UNOQ_MOTOR/break_wire.h").read_bytes()
    verify_build(ROOT / "nucleo/STM32CubeIDE/Debug",
                 "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json", 2026101702)
    verify_build(ROOT / "uno_build", "unoq_mcsdk_scalar.build-manifest.json", 2026101701)
    candidate = json.loads((ROOT / "candidate-manifest.json").read_text(encoding="utf-8-sig"))
    assert candidate["installed"] is False
    assert candidate["hardware_commands"] == 0 and candidate["flash_commands"] == 0
    print("PASS paired headers, image IDs, image hashes, and offline-only manifest")


if __name__ == "__main__":
    main()
