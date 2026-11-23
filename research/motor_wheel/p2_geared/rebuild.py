"""Change the planetary diameter without silently changing the motor model."""
import argparse,json
from model import ROOT
from planetary import config

def run():
    p=argparse.ArgumentParser(description='P2 nominal CAD variants; dimensions are not measured Max Pro fits')
    p.add_argument('--ring-od',type=float,default=180,help='Stationary internal gear outer diameter in mm, e.g.145 or180')
    p.add_argument('--build-cad',action='store_true',help='Generate native files in running SOLIDWORKS; keep UI idle')
    a=p.parse_args();m=(a.ring_od-20)/100
    if not 1.25<=m<=1.6:raise SystemExit('Validated nominal range: ring OD145..180mm. Outside range requires re-engineering.')
    c=config(m);print(json.dumps(c,indent=2))
    if a.build_cad:
        from build_cad import Hub
        Hub(m).build_hub()

if __name__=='__main__':run()
