"""Check disarmed Wi-Fi commands at zero bus; never ARM or start the motor."""
import argparse
import getpass
import json
from pathlib import Path

from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status
from verify_wifi_command_path import get_wifi_logs


def safe(s):
    try:
        return (s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0
                and s['vdc']==0 and s['bp_vdc']==0 and s['bp_vbus_raw']==0
                and 0<=s['mc_age_ms']<300 and not(s['bp_status']&0x22)
                and s['fw_build']==2026100707 and s['mc_fw_build']==2026100707)
    except (KeyError,TypeError,ValueError):
        return False


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True)
    args=p.parse_args()
    out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    token=getpass.getpass('Control credential (not echoed): ').strip()
    if len(token)<16: raise RuntimeError('missing credential')
    report={'pass':False,'scope':'disarmed zero-bus Wi-Fi command acknowledgements; not active PWM',
            'commands':[],'samples':[],'arm_commands':0,'start_commands':0}
    h=WifiHmi('http://192.168.1.138:8080',token,report['commands'],via_wsl=True)
    try:
        before=h.status(); report['before']=before
        if not safe(before): raise RuntimeError('zero-bus disarmed precheck failed')
        h.post('/api/stop-sequence',{'emergency':False},'STOP')
        h.command('MODE VF')
        for hz in (5,20,0):
            if not safe(h.status()): raise RuntimeError('lost zero-bus SAFE state')
            h.command(f'SET FREQ {hz}')
            s=wait_status(h,lambda v:safe(v) and v.get('freq_cmd')==hz,5,f'{hz} Hz acknowledged while off')
            report['samples'].append(s)
        report['pass']=all(s['mc_bad_cnt']==before['mc_bad_cnt']
                           and s['mc_bad_integrity']==before['mc_bad_integrity']
                           and s['mc_bad_sequence']==before['mc_bad_sequence'] for s in report['samples'])
    except Exception as exc:
        report['error']=str(exc)
    finally:
        code,response=h.fail_safe_stop()
        report['final_stop']={'http':code,'ok':response.get('ok')}
        try:
            report['after']=h.status()
            report['pass']=report['pass'] and code==200 and response.get('ok') is True and safe(report['after'])
            (out/'wifi_logs.txt').write_text(get_wifi_logs(h,token),encoding='utf-8')
        except Exception as exc:
            report['pass']=False; report['final_error']=str(exc)
        h.close()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('pass','error','final_stop','arm_commands','start_commands')}))
    return 0 if report['pass'] else 1


if __name__=='__main__':
    raise SystemExit(main())
