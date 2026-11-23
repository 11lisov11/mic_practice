from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control import PROFILES, expected_parameters, readiness
from .runner import dump, probe, probe_red_controller, run_live
from .simulation import export_csv, simulate

HERE=Path(__file__).parent


def main():
    parser=argparse.ArgumentParser(description="T3D load machine: simulator, read-only probe, qualified load run")
    parser.add_argument("command",choices=["check","ports","parameters","probe","red-probe","simulate","run","ui"])
    parser.add_argument("--config",type=Path,default=HERE/"config.template.json")
    parser.add_argument("--profile",choices=PROFILES,default="step")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    config=json.loads(args.config.read_text(encoding="utf-8-sig"))
    if args.command=="ports":
        from serial.tools import list_ports
        result=[dict(port=p.device,description=p.description,vid=p.vid,pid=p.pid,
            serial_number=p.serial_number,location=p.location) for p in list_ports.comports()]
    elif args.command=="check":
        result=dict(ready=not readiness(config),missing=readiness(config),device_commands=0)
    elif args.command=="parameters":
        result={f"P-{k:03}":v for k,v in expected_parameters(config).items()}
        result["P-145"]=0
    elif args.command=="red-probe":
        result=probe_red_controller(config)
        if args.out:dump(args.out,result)
    elif args.command=="probe":
        result=probe(config)
        if args.out:dump(args.out,result)
    elif args.command in ("simulate","run"):
        if not args.out:parser.error("--out must name a new run directory")
        action=simulate if args.command=="simulate" else run_live
        result=action(config,args.profile,args.out)
        export_csv(args.out)
        result={k:result[k] for k in ("completed","simulation","hardware_validated","nonzero_commands","failure")}
    else:
        from .ui import serve
        serve(args.config)
        return
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=="__main__":
    try:main()
    except KeyboardInterrupt:raise SystemExit(130)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}",file=sys.stderr)
        raise SystemExit(2)
