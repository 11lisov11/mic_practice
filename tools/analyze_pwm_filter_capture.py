"""Retain waveform modulation and transport timelines before restoring the boards."""
import argparse
import json
from pathlib import Path
from pwm_filter_hardware_session import Session,ERROR_FIELDS
from analyze_mcsdk_modulation import analyze
from collect_wifi_telemetry import get_logs

def main(folder):
    s=Session(folder);p=Path(s.state['last_run'])
    rows=json.loads((p/'status.json').read_text());base=s.state['ready_status']
    counters={k:{'ready':base.get(k),'first':rows[0]['status'].get(k),'last':rows[-1]['status'].get(k),
        'values':sorted(set(r['status'].get(k) for r in rows))} for k in ERROR_FIELDS}
    (p/'counter_timeline.json').write_text(json.dumps(counters,indent=2)+'\n')
    m=analyze(p/'csv/digital.csv',4_000_000,5);(p/'modulation.json').write_text(json.dumps(m,indent=2)+'\n')
    (p/'hmi_logs_after.txt').write_text(get_logs(s.opener,'http://192.168.1.138:8081',s.token,2),encoding='utf-8')
    s.remote('''from pathlib import Path
p=Path('/home/arduino/.local/share/mic-ai/pwm-filter-hil-20261014')
for name in ('events.log','hmi.log'):
 print('FILE',name)
 print((p/name).read_text()[-150000:])
''','capture_remote_logs')
    w=json.loads((p/'waveform.json').read_text())
    print(json.dumps({'run':str(p),'samples':len(rows),'counter_changes':{k:v for k,v in counters.items() if v['ready']!=v['last']},
                     'pairs':w['pairs'],'modulation':m},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',type=Path,required=True);a=p.parse_args();main(a.session.resolve())
