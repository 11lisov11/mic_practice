from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.air56b2_nameplate_ensemble import ensemble_manifest, generate_air56b2_ensemble


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic AIR56B2 nameplate-constrained simulation ensemble."
    )
    parser.add_argument("--count", type=int, default=256)
    parser.add_argument("--seed", type=int, default=560225)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    samples = generate_air56b2_ensemble(args.count, seed=args.seed)
    payload = ensemble_manifest(samples, master_seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "sample_count": len(samples),
                "output": str(args.output.resolve()),
                "hardware_identified": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
