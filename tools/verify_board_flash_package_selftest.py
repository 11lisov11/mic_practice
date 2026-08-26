#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(verifier: Path, package: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(verifier), str(package)],
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    verifier = root / "tools" / "verify_board_flash_package.py"
    source = root / "firmware" / "ready_to_flash"
    clean = run(verifier, source)
    if clean.returncode != 0:
        print(clean.stdout)
        return 1

    with tempfile.TemporaryDirectory() as temporary:
        copied = Path(temporary) / "package"
        shutil.copytree(source, copied)
        target = copied / "linux" / "web_hmi" / "server.py"
        target.write_bytes(target.read_bytes() + b"\n# tamper\n")
        tampered = run(verifier, copied)
        if tampered.returncode == 0 or "artifact_hash:linux/web_hmi/server.py" not in tampered.stdout:
            print(tampered.stdout)
            return 1

    print("PASS verify_board_flash_package_selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
