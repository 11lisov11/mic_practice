"""Version extension gate checks and real orchestration with a delayed fake ACK."""
import copy,json,sys,tempfile,time
from contextlib import contextmanager
from pathlib import Path
import run_persistent_pe_as5600_5hz as wrapper
def main():
 t=wrapper.load_trial();t.configure(2026102709,'NUCLEO')
 base=Path('artifacts/live_bench_20261027/nucleo_i2c_stop_recovery_r1/powered_first_fault_5hz_r1/trial/report.json')
 data=json.loads(base.read_text(encoding='utf-8'));before=copy.deepcopy(data['before']);before.update(fw_build=2026102709,mc_fw_build=2026102710,bp_fw_build=2026102710,run_id=7)
 assert t.setup_ok(before) and t.t.ready(before) and t.capture_ready(before)
 checks=1
 for changes in ({'mc_fw_build':0},{'mc_current_zero_ready':0},{'mc_sd_live':dict(before['mc_sd_live'],level='LOW')},{'mc_sd_live':dict(before['mc_sd_live'],break_irq_enabled=False)},{'mc_transport_fault':7},{'pwm':1},{'hmi_hv_armed':1},{'vdc':400},{'mc_age_ms':301},{'bp_temp_fault':1}):
  assert not (t.setup_ok(dict(before,**changes)) and t.t.ready(dict(before,**changes)));checks+=1
 active=next(copy.deepcopy(x['status']) for x in data['samples'] if x['status'].get('pwm')==1 and x['status'].get('mc_frequency_reference_hz')==5)
 active.update(fw_build=2026102709,mc_fw_build=2026102710,bp_fw_build=2026102710,run_id=8)
 assert t.t.checks.active(active) and t.zero_ready(active) and t.setup_ok(active);checks+=1
 assert wrapper.extension_complete(dict(enc_fault_decode_valid=1,enc_release_decode_valid=1,enc_fault_first_hex='-',enc_fault_pwm_hex='-'))
 assert not wrapper.extension_complete(dict(enc_fault_decode_valid=1,enc_release_decode_valid=1,enc_fault_first_hex='aa',enc_release_first_hex='-'));checks+=2
 shared=dict(began=None,starts=0,clears=0,stops=0,armed=False,ack_done=False)
 class Fake:
  base='http://fake';token='fake'
  def __init__(self,*a):pass
  def close(self):pass
  def command(self,c):
   if c=='CLEAR':shared['clears']+=1;raise AssertionError('No automatic CLEAR')
   if c=='SET FREQ 5':before['freq_cmd']=5
  def post(self,path,body,label):
   if path=='/api/hv-arm':shared['armed']=True;return dict(ok=True)
   assert path=='/api/start-sequence' and body=={'runlimit_s':5.0}
   shared['starts']+=1;shared['began']=time.monotonic();time.sleep(6.2);shared['ack_done']=True
   return dict(ok=True,status=copy.deepcopy(active))
  def status(self):
   if shared['began'] is None:return copy.deepcopy(before)
   elapsed=time.monotonic()-shared['began']
   if elapsed<5:
    s=copy.deepcopy(active);s.update(run_elapsed_ms=int(elapsed*1000),run_limit_ms=5000,run_reason=0,mc_current_window_tick_ms=int(elapsed*5)*200+5000,mc_current_window_ms=200);return s
   s=copy.deepcopy(before);s.update(run_id=8,run_start_ms=10000,run_stop_ms=15000,run_limit_ms=5000,run_elapsed_ms=5000,run_reason=1,hmi_hv_armed=int(shared['armed']));return s
  def fail_safe_stop(self):shared['stops']+=1;shared['armed']=False;return 200,dict(ok=True)
 @contextmanager
 def heartbeat(h):yield dict(errors=[])
 t.WifiHmi=Fake;t.read_token=lambda _: 'fake';t.operator_keepalive=heartbeat
 with tempfile.TemporaryDirectory() as tmp:
  old=sys.argv;sys.argv=['selftest','--confirm-powered-ready','--outdir',str(Path(tmp)/'run'),'--uno-build','2026102709','--sensor-mode','NUCLEO']
  try:code=t.main()
  finally:sys.argv=old
  r=json.loads((Path(tmp)/'run/report.json').read_text(encoding='utf-8'))
  assert code==0 and r['passed'] and shared['starts']==1 and shared['clears']==0 and shared['ack_done']
  assert r['completion']['run_elapsed_ms']==5000 and r['outputs_off_confirmed'] and 'host_backup_stop' not in r;checks+=1
 result=dict(passed=True,checks=checks,hardware_commands=0,exact_pair=[2026102709,2026102710],no_guard_threshold_changes=True,one_start=True,no_clear=True,mcu_limit_ms=5000,fake_http_ack_delay_s=6.2,no_hold_after_http_ack=True)
 dest=Path('artifacts/live_bench_20261027/i2c_persistent_pe_r1/pwm5hz_preparation_r1/runner_selftest.json');dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
