"""Capture first-fault diagnostics over Wi-Fi; never send a controller command."""
import argparse
import getpass
import json
from pathlib import Path
import time

from run_wifi_nucleo_pwm_bench import WifiHmi
from verify_wifi_command_path import get_wifi_logs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=10)
    parser.add_argument('--logs', action='store_true')
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.duration <= 120:
        parser.error('duration outside 1..120 seconds')
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    token = getpass.getpass('Read-only log credential (not echoed): ').strip() if args.logs else ''
    h = WifiHmi('http://192.168.1.138:8080',token,[],via_wsl=True)
    rows=[]; report={'pass':False,'scope':'read-only; no motor or calibration commands','commands_sent':0}
    try:
        began=time.monotonic()
        while time.monotonic()-began < args.duration:
            s=h.status()
            rows.append(s)
            if s.get('pwm') != 0 or s.get('hmi_hv_armed') != 0:
                raise RuntimeError('stand is not disarmed with outputs off')
            time.sleep(.25)
        report.update(samples=len(rows),first=rows[0],last=rows[-1])
        report['diagnostics_available']=all(s.get('mc_diag_valid')==1 for s in rows)
        report['last_bad_information_available']=all(s.get('mc_last_bad_valid')==1 for s in rows)
        report['uart_fresh']=all(0<=float(s.get('mc_age_ms',999999))<300 for s in rows)
        report['no_new_errors']=all(s.get(k)==rows[0].get(k) for s in rows
                                    for k in ('mc_bad_integrity','mc_bad_sequence','mc_bad_cnt'))
        report['first_reason_stable']=len({s.get('mc_fault_detail') for s in rows})==1
        report['new_uart_messages']=rows[-1]['mc_good']-rows[0]['mc_good']
        report['host_counter_saturated']=all(s.get('mc_good')==65535 for s in rows)
        report['uart_progress']=any(b.get('mc_good',0)>a.get('mc_good',0)
                                   or b.get('mc_seq')!=a.get('mc_seq')
                                   for a,b in zip(rows,rows[1:]))
        report['new_controller_messages']=rows[-1]['mc_good_cnt']-rows[0]['mc_good_cnt']
        report['pass']=all(report[k] for k in ('diagnostics_available','last_bad_information_available','uart_fresh','no_new_errors','first_reason_stable','uart_progress'))
        if args.logs:
            (out/'wifi_logs.txt').write_text(get_wifi_logs(h,token),encoding='utf-8')
    except Exception as exc:
        report['error']=str(exc)
    finally:
        h.close()
        (out/'samples.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('pass','samples','new_uart_messages','error')},indent=2))
    if rows:
        print(rows[-1].get('mc_fault_detail','no diagnostics'))
    return 0 if report['pass'] else 1


if __name__=='__main__':
    raise SystemExit(main())
