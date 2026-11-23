"""Verify a built isolated recorder and export its ELF-derived RAM layout, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from decode_ipm_break_snapshot import SIZE
from prepare_ipm_break_snapshot import BUILD_ID, REFERENCE, source_hashes


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--nm", type=Path, required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    project = candidate / "nucleo"
    current = source_hashes(project)
    if any(current.get(k) != v for k, v in manifest["candidate_sha256"].items()):
        raise RuntimeError("Prepared candidate files changed before packaging")
    if source_hashes(REFERENCE) != manifest["reference_sha256"]:
        raise RuntimeError("Frozen baseline changed")
    build = project / "STM32CubeIDE/Debug"
    manifests = list(build.glob("*.build-manifest.json"))
    if len(manifests) != 1:
        raise RuntimeError("Expected one build manifest")
    result = json.loads(manifests[0].read_text(encoding="utf-8-sig"))
    if (result.get("firmware_build_id") != BUILD_ID or result.get("build_exit_code") != 0
            or result.get("build_errors") != 0):
        raise RuntimeError("Wrong firmware identity or failed build")
    artifacts = {}
    for item in result["artifacts"]:
        path = build / item["file"]
        if sha(path).lower() != item["sha256"].lower() or path.stat().st_size != item["bytes"]:
            raise RuntimeError("Build artifact no longer matches manifest")
        artifacts[path.suffix] = path
    if set(artifacts) != {".bin", ".elf", ".hex"}:
        raise RuntimeError("Incomplete build artifacts")
    symbols = subprocess.run([str(args.nm.resolve(strict=True)), "-S", str(artifacts[".elf"])],
                             check=True, capture_output=True, text=True).stdout
    selected = {}
    expected = {"mic_first_break": SIZE, "mic_first_start_break": SIZE,
                "mic_break_irq_count": 4, "mic_break_start_window": 4,
                "mic_break_context_index": 4, "mic_break_context_valid": 4,
                "mic_break_context": 64}
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[3] in expected:
            address, size = int(fields[0], 16), int(fields[1], 16)
            if fields[2] != "B" or size != expected[fields[3]] or not 0x20000000 <= address < address + size <= 0x20008000:
                raise RuntimeError("RAM layout does not match recorder ABI")
            selected[fields[3]] = dict(address=hex(address), bytes=size)
    if set(selected) != set(expected):
        raise RuntimeError("Missing recorder symbols in linked ELF")
    report = dict(schema="mic_ai.ipm_first_break_package.v1", package_verified=True,
        firmware_build_id=BUILD_ID, record_schema=2, record_bytes=SIZE,
        build_errors=result["build_errors"], build_warnings=result["build_warnings"],
        artifacts={suffix: dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)
                   for suffix, path in artifacts.items()}, ram_symbols=selected,
        extra_ram_bytes=sum(v["bytes"] for v in selected.values()),
        installed=False, hardware_commands=0, hv_release_approved=False,
        note="RAM addresses belong ONLY to this ELF; never reuse with installed 2026101006",
        readback_prerequisites=["Diagnostic image installed and identity verified in a separate low-voltage session",
            "Mains physically disconnected, J4 off, DC bus verified discharged before connecting any PC wire",
            "Preserve MCU supply after event: power cycling, reset, or reset-on-connect erases the .bss record",
            "No automatic ST-Link readback or powered trial is authorized by this package"])
    (candidate / "package.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("package_verified", "firmware_build_id", "extra_ram_bytes", "installed")}))


if __name__ == "__main__":
    main()
