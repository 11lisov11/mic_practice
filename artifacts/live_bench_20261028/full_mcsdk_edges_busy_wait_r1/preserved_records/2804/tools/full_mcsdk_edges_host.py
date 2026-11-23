"""Install/status/one explicit5s fixture capture; never commands a motor START."""
import argparse,json,struct,time,subprocess
from pathlib import Path
import prepare_no_switch_diag as p
from prepare_full_mcsdk_edges import OUT as PACKAGE,BUILD
import pin_pwm_diag_io as pin
import full_mcsdk_host as predecessor
Probe=pin.Probe
def decode_pin(raw):
 w=list(struct.unpack('<64I',raw))
 if w[:4]!=[0x314e4950,2,BUILD,64]:raise ValueError('Edges report identity')
 w[1]=1;w[2]=2026102795;d=pin.decode(struct.pack('<64I',*w));d['build']=BUILD;d['schema']=2
 for old,new in [('RCC_AHB2ENR','ADC_all'),('PSC','ADC_bad'),('SMCR','ADC_during_5s'),('SysTick_LOAD','ADC_max_cost')]:d[new]=d.pop(old)
 return d
def decode_full(raw):
 w=list(struct.unpack('<24I',raw))
 if w[:4]!=[0x31444d46,BUILD,2,24]:raise ValueError('Full report identity')
 w[1]=2026102803;w[2]=1;d=predecessor.decode_full(struct.pack('<24I',*w))
 d['TIM8_BDTR']=d.pop('rx_good');d['backend_flags']=d.pop('fixture_denials');d['schema']=2;return d
def read(pr,sy,out,label):
 d={}
 for name,key,fn in [('mic_pin_report','pin',decode_pin),('mic_full_report','full',decode_full)]:
  for n in range(4):
   s=sy[name];raw=pr.read(s['address'],s['bytes'],label+name+str(n));(out/(label+'_'+name+str(n)+'.bin')).write_bytes(raw)
   try:d[key]=fn(raw);break
   except ValueError:
    if n==3:raise
    time.sleep(.1)
 s=sy['mic_uart_tx'];raw=pr.read(s['address'],s['bytes'],label+'tx');(out/(label+'_mic_uart_tx.bin')).write_bytes(raw)
 d['tx']=dict(zip(('head','tail','active','started_ms','late_reported','hard_error','queued','completed','timeouts','full_errors','dma_errors','last_status','early_tc'),struct.unpack('<13I',raw[:52])))
 p.write(out/(label+'.json'),json.dumps(d,indent=2)+'\n');return d
def eligible(d):
 a,b,t=d['pin'],d['full'],d['tx']
 return a['build']==BUILD and a['state']==a['reason']==a['attempted']==a['local_stop']==0 and a['hz']==170000000 and a['BDTR']&0x1000 and not(a['BDTR']&0xc000) and a['CCER']==0x555 and a['GPIOA_IDR']&64 and a['encoder']['valid_flags']&3==3 and a['ADC_all']>100 and a['ADC_bad']==0 and b['boot_completed']==1 and b['motor_state'] in (10,11) and b['active_fault']==b['occurred_fault']==4 and b['bus_v']<20 and b['native_commands_all']>0 and b['backend_flags']==b['rx_bad']==b['uart_guard']==0 and not(b['TIM8_BDTR']&0xc000) and t['completed']>0 and t['timeouts']==t['full_errors']==t['dma_errors']==t['hard_error']==0
def archive(pr,sy,out,label):
 for name in ('fault_record','release_probe','bus_clear','uno_transport','mic_first_break','mic_first_start_break','mic_bkin_record'):
  if name in sy:
   s=sy[name];(out/(label+'_'+name+'.bin')).write_bytes(pr.read(s['address'],s['bytes'],label+name))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=('install','status','run'));ap.add_argument('--isolation-confirmed',action='store_true');ap.add_argument('--allow-one-5s-fixture-request',action='store_true');ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
 if not a.isolation_confirmed:ap.error('J1/J4 OFF,34pin ribbon removed, Nucleo USB, retained Saleae mapping required')
 if a.action=='run' and not a.allow_one_5s_fixture_request:ap.error('Explicit one5s fixture request flag required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();pr=Probe(out/'logs')
 m=json.loads(p.read(PACKAGE/'manifest.json'));assert m['built'] and m['offline_verified']
 for rel,h in m['sealed_sha256'].items():assert p.sha(PACKAGE/rel)==h,rel
 sy=json.loads(p.read(PACKAGE/'verification/symbols.json'))
 r=dict(passed=False,flash_commands=0,fixture_requests=0,motor_START_commands=0,CLEAR_commands=0,RESET_commands=0)
 def save():p.write(out/'report.json',json.dumps(r,indent=2)+'\n')
 try:
  if a.action=='install':
   old=json.loads(p.read(PACKAGE/'verification/predecessor_symbols.json'))
   before=predecessor.read(pr,old,out,'before2803');r['before2803']=before;z=before['load']
   assert z['state']==2 and z['reason']==0 and z['actual_bus_v']<20 and not(z['TIM1_BDTR']&0x8000)
   archive(pr,old,out,'before2803');r['flash_commands']=1;save()
   q=subprocess.run([str(pin.PROGRAMMER),'-c','port=SWD','mode=UR','reset=HWrst','sn='+pin.SERIAL,'-w',str(PACKAGE/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'),'-v','-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
   p.write(out/'logs/flash_readback.log',q.stdout+q.stderr)
   if q.returncode or 'Download verified successfully' not in q.stdout:raise RuntimeError('Readback not confirmed; no retry')
   r['readback_verified']=True;time.sleep(3);d=read(pr,sy,out,'boot');r['boot']=d;archive(pr,sy,out,'boot');r['passed']=eligible(d)
   return 0 if r['passed'] else 1
  before=read(pr,sy,out,'before');r['before']=before
  if not eligible(before):raise RuntimeError('Admission failed; no fixture request')
  time.sleep(.5);fresh=read(pr,sy,out,'fresh');r['fresh']=fresh
  assert eligible(fresh) and fresh['pin']['ADC_all']>before['pin']['ADC_all'] and fresh['full']['native_commands_all']>before['full']['native_commands_all'] and fresh['tx']['completed']>before['tx']['completed']
  if a.action=='status':r['passed']=True;return 0
  before=fresh;archive(pr,sy,out,'before')
  from saleae import automation
  with automation.Manager.connect(port=10430,connect_timeout_seconds=3) as manager:
   assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
   with manager.start_capture(device_id='A7D1BB81883C0092',device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=8_000_000,glitch_filters=[]),capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=10))) as cap:
    try:r['fixture_requests']=1;save();pr.request(sy['mic_pin_request']['address']);time.sleep(6)
    finally:
     cap.wait();cap.save_capture(str(out/'full_mcsdk_edges.sal'));(out/'csv').mkdir();cap.export_raw_data_csv(directory=str(out/'csv'),digital_channels=list(range(8)))
  after=read(pr,sy,out,'after');r['after']=after;archive(pr,sy,out,'after')
  if after['pin']['state']==1:
   r['cancel_requests']=1;save();pr.request(sy['mic_pin_request']['address'],cancel=True);raise RuntimeError('Local stop unconfirmed; canceled, no retry')
  from analyze_pin_pwm_i2c import analyze
  wave=analyze(out/'csv/digital.csv');p.write(out/'waveform.json',json.dumps(wave,indent=2)+'\n')
  z,f=after['pin'],after['full'];t=f['task_calls_during_5s']
  r['encoder_delta_host_interval']={k:z['encoder'][k]-before['pin']['encoder'][k] for k in ('reads','errors','NACK','deadline','BUSY','ARLO','BERR_clears','forced_resets','normal_parks')}
  r['I2C_no_new_errors']=r['encoder_delta_host_interval']['errors']==0
  r['task_calls_during_5s']=t;r['native_commands_during_5s']=f['native_commands_during_5s']
  r['ADC_during_5s']=z['ADC_during_5s'];r['ADC_bad']=z['ADC_bad'];r['elapsed_ms']=z['elapsed_ms']
  r['passed']=z['state']==2 and z['reason']==0 and 5000<=z['elapsed_ms']<=5010 and not(z['BDTR']&0x8000) and not(f['TIM8_BDTR']&0x8000) and f['backend_flags']==0 and f['active_fault']==4 and z['ADC_bad']==0 and 79000<=z['ADC_during_5s']<=80200 and t['MC_Run']>=9900 and t['Safety']>=9900 and t['HighFrequency']>=79000 and r['native_commands_during_5s']>=90 and wave['observed_PWM_outputs_verified']
  r['scope']='Native protected MCSDK OFF/FAULT and independent physical TIM1 waveform; not normal motor RUN'
  return 0 if r['passed'] else 1
 except Exception as e:r['error']=str(e) or type(e).__name__;return 1
 finally:save();print(json.dumps({k:v for k,v in r.items() if k not in ('before2803','before','fresh','after','boot')}),flush=True)
if __name__=='__main__':raise SystemExit(main())
