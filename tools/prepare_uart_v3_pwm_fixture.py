"""Create an explicitly zero-bus UART-v3 PWM fixture; never upload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_mcsdk_logic_bench import prepare, replace_once
from prepare_uart_v3_candidate import nucleo_source, uno_source


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir",type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=root/"artifacts/live_bench_20261010/uart_v3_candidate/firmware_r6"
    if (source/"nucleo/Src/main.c").read_text()!=nucleo_source(root):
        raise RuntimeError("Nucleo snapshot changed")
    if (source/"UNOQ_MOTOR/UNOQ_MOTOR.ino").read_text()!=uno_source(root):
        raise RuntimeError("Uno snapshot changed")
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    report=prepare(root,out/"nucleo",production_build=2026101006,bench_build=2026101099,
                   source_override=source/"nucleo")
    uno=out/"UNOQ_MOTOR";shutil.copytree(source/"UNOQ_MOTOR",uno)
    sketch=uno/"UNOQ_MOTOR.ino"
    sketch.write_text(replace_once(sketch.read_text(),"FW_BUILD_ID = 2026101007U","FW_BUILD_ID = 2026101100U"),encoding="utf-8")
    header=uno/"nucleo_fault_diagnostics.h"
    header.write_text(replace_once(header.read_text(),"build == 2026101006U;",
                                  "build == 2026101006U || build == 2026101099U;"),encoding="utf-8")
    report.update(uno_build=2026101100,nucleo_build=2026101099,protocol_version=3,
                  purpose="ZERO BUS ONLY: J1 and U/V/W disconnected, J4 off, not an HV release",
                  new_pins_used=False,automatic_sd_pulse=False,
                  uno_source_sha256=hashlib.sha256(sketch.read_bytes()).hexdigest())
    (out/"manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"pass":report["pass"],"uno_build":report["uno_build"],
                      "nucleo_build":report["nucleo_build"],"project":report["project"]},indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
