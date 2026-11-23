"""Same2805 binary, J1 physically unplugged: archive, one reset, one5s fixture."""
import argparse,json,subprocess,sys,time
from pathlib import Path
from saleae import automation
import prepare_no_switch_diag as p
from prepare_full_edges_busy_wait import OUT,BUILD
import full_mcsdk_edges_host as host
host.PACKAGE=OUT;host.BUILD=BUILD
def ready_reset(d):
 return (d['pin']['build']==BUILD and not(d['pin']['BDTR']&0x8000) and
  not(d['full']['TIM8_BDTR']&0x8000) and d['full']['backend_flags']==0 and
  d['full']['bus_v']<20 and d['full']['active_fault']==4 and d['pin']['GPIOA_IDR']&64 and
  d['pin']['encoder']['valid_flags']&3==3 and d['full']['rx_bad']==0 and
  d['full']['uart_guard']==0 and d['tx']['hard_error']==0 and
  d['tx']['timeouts']==d['tx']['dma_errors']==d['tx']['full_errors']==0)
def ready_run(d):return host.eligible(d) and d['full']['bus_v']<20
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--j1-physically-unplugged-15v-on',action='store_true');ap.add_argument('--allow-one-reset-and-5s-request',action='store_true');ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
 if not(a.j1_physically_unplugged_15v_on and a.allow_one_reset_and_5s_request):ap.error('Explicit J1 disconnection, auxiliary15V state, one reset/request required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();pr=host.Probe(out/'logs')
 m=json.loads(p.read(OUT/'manifest.json'));assert m['built'] and m['offline_verified']
 for rel,h in m['sealed_sha256'].items():assert p.sha(OUT/rel)==h,rel
 sy=json.loads(p.read(OUT/'verification/symbols.json'))
 r=dict(passed=False,profile='Only auxiliary15V; J1 physically absent; real DC bus below20V; native UV4 required',firmware_BUILD=BUILD,
  firmware_flash_commands=0,reset_commands=0,fixture_requests=0,motor_START_commands=0,CLEAR_commands=0,guards_relaxed=False)
 def save():p.write(out/'report.json',json.dumps(r,indent=2)+'\n')
 def uart_context(label):
  q=subprocess.run([sys.executable,str(p.ROOT/'tools/read_edges_uart_context.py'),'--outdir',str(out/label)],capture_output=True,text=True,timeout=30)
  p.write(out/'logs'/(label+'.log'),q.stdout+q.stderr)
  if q.returncode:raise RuntimeError('UART archive failed; no automatic reset/request retry')
 def capture(manager,label,duration,operation):
  target=out/label;target.mkdir()
  with manager.start_capture(device_id='A7D1BB81883C0092',device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=8_000_000,glitch_filters=[]),capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=duration))) as cap:
   try:operation()
   finally:
    cap.wait();cap.save_capture(str(target/(label+'.sal')));(target/'csv').mkdir();cap.export_raw_data_csv(directory=str(target/'csv'),digital_channels=list(range(8)))
  from analyze_pin_pwm_i2c import analyze
  # D4 was not moved to UART, but its physical point was not reverified.
  # Qualify only the four unchanged U/V probes; keep all eight raw channels.
  wave=analyze(target/'csv/digital.csv',pwm_channels=(0,1,2,3))
  wave['channel_map']['4']='unchanged probe; excluded from PWM qualification'
  p.write(target/'waveform.json',json.dumps(wave,indent=2)+'\n');return wave
 try:
  before=host.read(pr,sy,out,'before_reset');r['before_reset']=before;host.archive(pr,sy,out,'before_reset')
  if not ready_reset(before):raise RuntimeError('Stable low-bus/SD/sensor admission failed; no reset or pulse')
  time.sleep(.5);fresh_before=host.read(pr,sy,out,'fresh_before_reset');r['fresh_before_reset']=fresh_before
  if not(ready_reset(fresh_before) and fresh_before['full']['native_commands_all']>before['full']['native_commands_all'] and fresh_before['pin']['encoder']['reads']>before['pin']['encoder']['reads'] and fresh_before['pin']['encoder']['errors']==before['pin']['encoder']['errors']):raise RuntimeError('Link/sensor not progressing cleanly; no reset or pulse')
  uart_context('before_uart_context')
  print('ARCHIVED: existing SD/I2C/UART records; outputs OFF; one reset next',flush=True)
  with automation.Manager.connect(port=10430,connect_timeout_seconds=3) as manager:
   assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
   def reset_once():
    r['reset_commands']=1;save();pr.call(['-rst'],'one_reset_J1_physically_absent');time.sleep(3)
   capture(manager,'reset_startup',6,reset_once)
   boot=host.read(pr,sy,out,'boot');r['boot']=boot;host.archive(pr,sy,out,'boot')
   if not ready_run(boot):raise RuntimeError('Protected boot not ready; no pulse request, no retry')
   time.sleep(.5);fresh=host.read(pr,sy,out,'fresh');r['fresh']=fresh
   assert ready_run(fresh) and fresh['pin']['ADC_all']>boot['pin']['ADC_all'] and fresh['full']['native_commands_all']>boot['full']['native_commands_all']
   print('BOOT_READY: SD HIGH, native UV4, clean UART/AS5600; one 5s fixture next',flush=True)
   def request_once():
    r['fixture_requests']=1;save();pr.request(sy['mic_pin_request']['address']);time.sleep(6)
   wave=capture(manager,'full5s',10,request_once)
  after=host.read(pr,sy,out,'after');r['after']=after;host.archive(pr,sy,out,'after')
  uart_context('after_uart_context')
  z,f=after['pin'],after['full'];t=f['task_calls_during_5s']
  if z['state']==1:
   r['cancel_requests']=1;save();pr.request(sy['mic_pin_request']['address'],cancel=True);raise RuntimeError('Local stop unconfirmed; canceled, no retry')
  r['encoder_delta_host_interval']={k:z['encoder'][k]-fresh['pin']['encoder'][k] for k in ('reads','errors','NACK','BUSY','deadline','ARLO','BERR_clears','forced_resets','normal_parks')}
  r['elapsed_ms']=z['elapsed_ms'];r['ADC_during5s']=z['ADC_during_5s'];r['ADC_bad']=z['ADC_bad'];r['native_tasks_during5s']=t
  r['I2C_healthy_during_PWM']=z['boundaries'][7]-z['boundaries'][1]==0 and wave['AS5600_complete_read_parts_within_PWM']>700 and not wave['AS5600_target_NACK'] and not wave['partial_frames_within_PWM'] and not wave['unexpected_frames'] and r['encoder_delta_host_interval']['errors']==0
  r['UART_healthy_during_trial']=f['rx_bad']==f['uart_guard']==0 and f['native_commands_during_5s']>=80 and all(after['tx'][k]==0 for k in ('hard_error','timeouts','dma_errors','full_errors'))
  r['I2C_complete_reads_within_PWM']=wave['AS5600_complete_read_parts_within_PWM']
  r['PWM_window_s']=wave['PWM_window_s'];r['qualified_PWM_channels']=[0,1,2,3]
  r['all_six_PWM_outputs_observed']=False
  r['passed']=z['state']==2 and z['reason']==0 and 5000<=z['elapsed_ms']<=5010 and not(z['BDTR']&0x8000) and not(f['TIM8_BDTR']&0x8000) and f['backend_flags']==0 and f['bus_v']<20 and f['active_fault']==f['occurred_fault']==4 and 79000<=z['ADC_during_5s']<=80200 and z['ADC_bad']==0 and t['MC_Run']>=9900 and t['Safety']>=9900 and t['HighFrequency']>=79000 and wave['observed_PWM_outputs_verified'] and not wave['SD_low_intervals'] and r['I2C_healthy_during_PWM'] and r['UART_healthy_during_trial']
  return 0 if r['passed'] else 1
 except Exception as e:r['error']=str(e) or type(e).__name__;return 1
 finally:save();print(json.dumps({k:v for k,v in r.items() if k not in ('before_reset','fresh_before_reset','boot','fresh','after')}),flush=True)
if __name__=='__main__':raise SystemExit(main())
