"""Restore an unused short-trial preparation after a cold boot; Wi-Fi only, never ARM/START."""
import argparse
import json
from pathlib import Path
import time

from prepare_rx_short_trial import ROOT, RX, BASE, sha, source_hashes
from clear_rx_maintenance_timeout import safe as zero_safe
from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi
from ipm_break_wifi_selftest import load_module


def clean_idle(report, rows):
    return (report.get('pass') is True and report.get('duration_requested_s',0)>=30
        and report.get('first_builds')=={'fw_build':2026101104,'mc_fw_build':2026101102}
        and len(rows)>=20 and all(zero_safe(s) and s.get('bp_bad_cnt')==0
            and s.get('bp_transport_fault')==0 for s in rows)
        and rows[-1]['bp_good']-rows[0]['bp_good']>=100)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared-install',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--idle',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args(); out=a.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    rep=dict(pass_=False,commands=[],arm_commands=0,start_commands=0,flash_commands=0,
        transport='direct_wifi_http_only')
    h=WifiHmi('http://192.168.1.138:8080',read_token('.unoq_ssh/control_token'),rep['commands'],False)
    try:
        installation=json.loads((a.prepared_install/'report.json').read_text())
        if (installation.get('pass') is not True or installation.get('start_commands')!=0
                or installation.get('arm_commands')!=0 or installation.get('mcu_flash_commands')!=0):
            raise RuntimeError('Prior unused installation/preparation evidence missing')
        proof=json.loads((a.prepared_install/'qualification.json').read_text())
        manifest=json.loads((a.candidate/'manifest.json').read_text())
        if sha(a.candidate/'web_hmi/server.py')!=manifest['hmi_sha256']:
            raise RuntimeError('Prepared HMI changed')
        audit=json.loads((a.candidate/'delta_audit.json').read_text())
        if (source_hashes(RX/'UNOQ_MOTOR')!=audit['source_uno_sha256']
                or source_hashes(BASE/'nucleo')!=audit['source_nucleo_sha256']):
            raise RuntimeError('Source-audited component changed')
        offline_path=ROOT/'artifacts/live_bench_20261011/rx_trial_preparation/regression_r1/report.json'
        if sha(offline_path)!=proof['evidence_sha256']['offline']:
            raise RuntimeError('Retained regression fingerprint mismatch')
        offline=json.loads(offline_path.read_text())
        if not offline['pass'] or not offline['sources_unchanged_during_tests']:
            raise RuntimeError('Retained regression failed')
        # A new preparation helper does not change any previously tested source.
        for relative,expected in offline['source_sha256'].items():
            if sha(ROOT/relative)!=expected: raise RuntimeError('Tested source changed: '+relative)
        idle=json.loads(a.idle.read_text())
        rows=[json.loads(x)['status'] for x in (a.idle.parent/'status.jsonl').read_text().splitlines()]
        if not clean_idle(idle,rows): raise RuntimeError('Fresh autonomous idle checks failed')
        rep['before']=s=h.status()
        if (not zero_safe(s) or s.get('bp_bad_cnt')!=0 or s.get('bp_transport_fault')!=0
                or s.get('hmi_vbus_hv_calibrated')!=1 or s.get('hmi_powered_trial_enabled')!=0
                or s.get('hmi_powered_trial_used',0)!=0):
            raise RuntimeError('Expected disarmed cold-boot state changed')
        now=time.time(); proof.update(issued_at=now,expires_at=now+600)
        proof['evidence_sha256']['idle_wifi']=sha(a.idle)
        mod=load_module(a.candidate/'web_hmi/server.py')
        if not mod.validate_powered_trial_qualification(proof)[0]: raise RuntimeError('Refreshed proof rejected')
        (out/'qualification.json').write_text(json.dumps(proof,indent=2)+'\n')
        h.command('MODE VF'); h.command('SET FREQ 5')
        h.post('/api/powered-trial',dict(action='prepare',confirm='PREPARE UARTV3 TRIAL 3S',qualification=proof),
               'restore unused preparation after cold boot, NOT ARM or START')
        rep['after']=s=h.status()
        if (not zero_safe(s) or s.get('hmi_powered_trial_enabled')!=1 or s.get('freq_cmd')!=5
                or s.get('hmi_hv_armed')!=0 or s.get('hmi_start_runlimit_s')!=3):
            raise RuntimeError('Preparation did not remain disarmed/output-off')
        rep['pass_']=True
    except Exception as exc: rep['error']=f'{type(exc).__name__}: {exc}'
    finally:
        h.close(); rep['pass']=rep.pop('pass_')
        (out/'report.json').write_text(json.dumps(rep,indent=2)+'\n')
    print(json.dumps({k:rep.get(k) for k in ('pass','start_commands','arm_commands','error')}))
    return 0 if rep['pass'] else 1


if __name__=='__main__': raise SystemExit(main())
