"""One existing MCU-timed trial after a preserved, independently proved pre-START SD."""
import argparse,hashlib,json,sys,time
from pathlib import Path
import run_persistent_pe_as5600_5hz as runner
from pe_release_capture.preserve_live import complete
from run_wifi_nucleo_pwm_bench import WifiHmi
from collect_wifi_telemetry import read_token

PAIR=(2026102709,2026102710)
ZERO_RUN=('run_id','run_limit_ms','run_elapsed_ms','run_reason','run_start_ms','run_stop_ms')
ROOT=Path(__file__).resolve().parents[1]

def identity(s):
 records={r['kind']:r for r in s['mc_break_snapshots']}
 first=records['first_since_boot'];other=records['first_start_window']
 if not(first['available'] and first['captured'] and other['available'] and not other['captured']):raise ValueError('No unchanged pre-START record')
 raw,event=first['raw'],first['event']
 if not(raw['context_valid']==0 and event['moe_at_irq'] is False and event['during_start_request_window'] is False and event['bke_at_irq'] is True):raise ValueError('Not the missing-context, outputs-OFF startup case')
 wave=s['mc_break_wave_hex']
 if len(bytes.fromhex(wave))!=320 or s['mc_break_wave_bad_pages']!=0 or s['mc_break_rx_bad']!=0:raise ValueError('Incomplete/unverified preserved waveform')
 payload=json.dumps({'pair':[s['fw_build'],s['mc_fw_build']],'raw':raw,'event':event,'wave':wave},sort_keys=True,separators=(',',':')).encode()
 return hashlib.sha256(payload).hexdigest()

def certify(s):
 if not((s['fw_build'],s['mc_fw_build'])==PAIR and s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==s['estop']==0 and s['manual_run_mode']==0 and all(type(s[k]) is int and s[k]==0 for k in ZERO_RUN) and s['freq_cmd']==s['mc_frequency_reference_hz']==0 and 0<=s['vdc']<20 and s['mc_age_ms']<300 and s['enc_errors']==0 and s['enc_bus_ok']==s['enc_ok']==1 and complete(s)):
  raise ValueError('Independent no-previous-START, low-bus proof absent')
 return dict(pair=list(PAIR),SD_identity=identity(s),proven_before_first_START=True)

def same(s,c):
 try:return (s['fw_build'],s['mc_fw_build'])==PAIR and s['run_id'] in (0,1) and identity(s)==c['SD_identity']
 except (KeyError,TypeError,ValueError):return False

def clear_ready(s,c,m):
 # mc_fault_* masks are the FIRST frozen fault in this firmware, not live
 # MCSDK flags (main.c:uno_capture_diagnostics / uno_build_reply). Native
 # MC_AcknowledgeFaultMotor1 still refuses an actually active fault.
 return (same(s,c) and all(s.get(k)==0 for k in ZERO_RUN) and m.t.checks.off(s) and m.t.checks.transport_clean(s) and m.zero_ready(s) and m.setup_ok(s) and m.t.sd_high(s,False) and s.get('enc_errors')==0 and s.get('enc_bus_ok')==s.get('enc_ok')==1 and s.get('estop')==0 and s.get('mc_fault')==s.get('bp_fault')==5 and s.get('mc_fault_reason')==8 and s.get('mc_fault_current_mask')==4 and s.get('mc_fault_occurred_mask') in (4,1028) and s.get('mc_last_bad_reason')==0)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--confirm-powered-ready',action='store_true');ap.add_argument('--boot-proof',type=Path,required=True);ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
 if not a.confirm_powered_ready:ap.error('Fresh autonomous/powered operator confirmation required')
 proof=a.boot_proof.resolve();pr=json.loads((proof/'report.json').read_text());assert pr['passed'] and pr['I2C_errors']==0 and pr['motor_START_commands']==0
 c=certify(json.loads((proof/'saved_status.json').read_text()));out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 (out/'startup_SD_certificate.json').write_text(json.dumps(c,indent=2)+'\n')
 m=runner.load_trial();m.configure(PAIR[0],'NUCLEO');original=m.t.archive_before_start
 # The fallback is bound to the immutable archived waveform and proof of
 # run_id=0 before power was applied. Never invent a missing cached context.
 m.t.archive_before_start=lambda s:original(s) or same(s,c)
 commands=[];h=WifiHmi('http://192.168.1.138:8080',read_token(str(ROOT/'.unoq_ssh/control_token')),commands,False)
 r={'passed':False,'CLEAR_commands':0,'motor_START_commands':0,'flash_commands':0,'records_erased':False,'commands':commands}
 def sample(label):
  s=h.status();(out/(label+'.json')).write_text(json.dumps(s,indent=2)+'\n');return s
 try:
  before=sample('before_ack')
  if not m.t.ready(before):
   if not clear_ready(before,c,m):raise RuntimeError('No eligible startup acknowledgement; no CLEAR/START')
   time.sleep(.3);fresh=sample('fresh_before_ack')
   if not(clear_ready(fresh,c,m) and fresh['enc_reads']>before['enc_reads']):raise RuntimeError('Startup input/link changed; no CLEAR/START')
   r['CLEAR_commands']=1;h.command('CLEAR');deadline=time.monotonic()+5
   while True:
    s=sample('after_ack')
    if m.t.ready(s) and m.setup_ok(s) and same(s,c):break
    if time.monotonic()>=deadline:raise RuntimeError('Single CLEAR did not establish protected ready OFF; no retry')
    time.sleep(.15)
  r['passed']=True
 except Exception as e:r['error']=str(e) or type(e).__name__
 finally:
  h.close();(out/'ack_report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='commands'}),flush=True)
 if not r['passed']:return 1
 # Keep the original watchdog, complete live protection predicates, first-
 # PWM capture gate, current-zero contract and post-stop extension collection.
 runner.load_trial=lambda:m
 old=sys.argv;sys.argv=[old[0],'--confirm-powered-ready','--outdir',str(out/'trial')]
 try:return runner.main()
 finally:sys.argv=old

if __name__=='__main__':raise SystemExit(main())
