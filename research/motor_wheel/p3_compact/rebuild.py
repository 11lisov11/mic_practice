"""P3 wheel package diameter, keeping the solved electromagnetic geometry."""
import argparse
from calculate import run

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ring-od',type=float,default=165);p.add_argument('--cad',action='store_true');a=p.parse_args()
    if not 165<=a.ring_od<=180:raise SystemExit('P3 nominal ring OD range165..180mm; outside requires a new layout')
    m=(a.ring_od-20)/100;d,out=run(m)
    if a.cad:
        from build_cad import Hub
        Hub(m,d['geometry'],out,d['gear']).build_hub()
