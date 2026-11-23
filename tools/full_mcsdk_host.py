"""One isolated full-application observation; preserves UV and never commands START."""
import argparse,json,struct,time,subprocess
from pathlib import Path
import prepare_no_switch_diag as p
from prepare_full_mcsdk_diag import OUT as PACKAGE,OLD,BUILD
import no_switch_diag_snapshot_io as ld
import combined_io_host as previous
previous.BUILD=2026102802
Probe=ld.Probe

def decode_load(raw):
 w=list(struct.unpack('<72I',raw))
 if w[2]!=BUILD:raise ValueError('Load build identity')
 w[2]=2026102792;d=ld.decode(struct.pack('<72I',*w));d['build']=BUILD;return d
def decode_full(raw):
 w=struct.unpack('<24I',raw)
 if w[:4]!=(0x31444d46,BUILD,1,24) or w[4]&1 or w[4]!=w[21] or ld.crc32c(raw[20:84])!=w[22] or w[23]!=0x464d4445:raise ValueError('Full identity/CRC/sequence')
 return dict(sequence=w[4],boot_completed=w[5],motor_state=w[6],active_fault=w[7],occurred_fault=w[8],bus_v=w[9],BDTR=w[10],
  task_calls_during_5s=dict(zip(('MC_Run','Safety','Medium','HighFrequency'),w[11:15])),
  native_commands_all=w[15],native_commands_during_5s=w[16],rx_good=w[17],rx_bad=w[18],fixture_denials=w[19],uart_guard=w[20])
def read(pr,sy,out,label):
 d={}
 for name,key,fn in [('mic_load_report','load',decode_load),('mic_full_report','full',decode_full)]:
  for n in range(4):
   raw=pr.read(sy[name]['address'],sy[name]['bytes'],label+name+str(n));(out/(label+'_'+name+str(n)+'.bin')).write_bytes(raw)
   try:d[key]=fn(raw);break
   except ValueError:
    if n==3:raise
    time.sleep(.1)
 s=sy['mic_uart_tx'];raw=pr.read(s['address'],s['bytes'],label+'uart_tx');(out/(label+'_mic_uart_tx.bin')).write_bytes(raw)
 d['tx']=dict(zip(('head','tail','active','started_ms','late_reported','hard_error','queued','completed','timeouts','full_errors','dma_errors','last_status','early_tc'),struct.unpack('<13I',raw[:52])))
 p.write(out/(label+'.json'),json.dumps(d,indent=2)+'\n');return d
def eligible(d):
 a,b,t=d['load'],d['full'],d['tx']
 return a['build']==BUILD and a['state']==a['attempted']==a['reason']==0 and a['actual_bus_v']<20 and a['phase_pins_gpio_low']==1 and not(a['TIM1_BDTR']&0x8000) and a['TIM1_BDTR']&0x1000 and a['adc_seen']>100 and a['guard_flags']==a['local_stop']==0 and b['boot_completed']==1 and b['native_commands_all']>0 and b['rx_good']>0 and b['rx_bad']==b['uart_guard']==0 and t['completed']>0 and t['timeouts']==t['full_errors']==t['dma_errors']==t['hard_error']==0
def archive(pr,sy,out,label):
 for name in ('fault_record','release_probe','bus_clear','uno_transport'):
  if name in sy:
   s=sy[name];(out/(label+'_'+name+'.bin')).write_bytes(pr.read(s['address'],s['bytes'],label+name))
def main():
 a=argparse.ArgumentParser();a.add_argument('action',choices=('install','status','run'));a.add_argument('--isolation-confirmed',action='store_true');a.add_argument('--outdir',type=Path,required=True);a=a.parse_args()
 if not a.isolation_confirmed:raise ValueError('Existing J1/J4 OFF, ribbon disconnected and USB/probe map required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();pr=Probe(out/'logs')
 m=json.loads(p.read(PACKAGE/'manifest.json'));assert m['built'] and m['offline_verified']
 for rel,h in m['sealed_sha256'].items():assert p.sha(PACKAGE/rel)==h,rel
 sy=json.loads(p.read(PACKAGE/'verification/symbols.json'))
 r=dict(passed=False,flash_commands=0,load_requests=0,motor_start_commands=0,clear_commands=0,reset_commands=0)
 def save():p.write(out/'report.json',json.dumps(r,indent=2)+'\n')
 try:
  if a.action=='install':
   old=json.loads(p.read(OLD/'verification/symbols.json'))
   d=previous.read(pr,old,out,'before2802');r['before2802']=d
   assert d['pin']['state']==2 and d['pin']['reason']==0 and not(d['pin']['BDTR']&0x8000)
   archive(pr,old,out,'before2802');r['flash_commands']=1;save()
   image=PACKAGE/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
   q=subprocess.run([str(ld.PROGRAMMER),'-c','port=SWD','mode=UR','reset=HWrst','sn='+ld.SERIAL,'-w',str(image),'-v','-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
   p.write(out/'logs/flash_readback.log',q.stdout+q.stderr)
   if q.returncode or 'Download verified successfully' not in q.stdout:raise RuntimeError('Readback unconfirmed; no retry')
   r['readback_verified']=True;time.sleep(3);d=read(pr,sy,out,'boot');r['boot']=d;archive(pr,sy,out,'boot');r['passed']=eligible(d)
   return 0 if r['passed'] else 1
  before=read(pr,sy,out,'before');r['before']=before
  if not eligible(before):raise RuntimeError('Full application admission failed; no request')
  time.sleep(.5);fresh=read(pr,sy,out,'fresh');r['fresh']=fresh
  assert eligible(fresh) and fresh['load']['adc_seen']>before['load']['adc_seen'] and fresh['full']['native_commands_all']>before['full']['native_commands_all'] and fresh['tx']['completed']>before['tx']['completed']
  if a.action=='status':r['passed']=True;return 0
  before=fresh;archive(pr,sy,out,'before')
  from saleae import automation
  with automation.Manager.connect(port=10430,connect_timeout_seconds=3) as manager:
   assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
   with manager.start_capture(device_id='A7D1BB81883C0092',device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=8_000_000,glitch_filters=[]),capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=10))) as cap:
    try:r['load_requests']=1;save();pr.request(sy['mic_load_request']['address']);time.sleep(6)
    finally:
     cap.wait();cap.save_capture(str(out/'full_mcsdk.sal'));(out/'csv').mkdir();cap.export_raw_data_csv(directory=str(out/'csv'),digital_channels=list(range(8)))
  after=read(pr,sy,out,'after');r['after']=after;archive(pr,sy,out,'after')
  if after['load']['state']==1:
   r['cancel_requests']=1;save();pr.request(sy['mic_load_request']['address'],cancel=True);raise RuntimeError('Local stop unconfirmed; canceled, no retry')
  r['encoder_delta']={k:after['load']['encoder'][k]-before['load']['encoder'][k] for k in ('reads','errors','NACK','deadline','BUSY','ARLO','BERR_clears','forced_resets','normal_parks')}
  r['tx_delta']={k:after['tx'][k]-before['tx'][k] for k in ('queued','completed','timeouts','full_errors','dma_errors')}
  r['native_commands_during_5s']=after['full']['native_commands_during_5s'];r['task_calls_during_5s']=after['full']['task_calls_during_5s']
  z=after['load'];t=r['task_calls_during_5s']
  r['passed']=z['state']==2 and z['reason']==0 and 5000<=z['elapsed_ms']<=5010 and not(z['TIM1_BDTR']&0x8000) and z['phase_pins_gpio_low']==1 and 79000<=z['tim_updates']<=80200 and 79000<=z['adc_calls']<=80200 and 2450<=z['medium_updates']<=2501 and t['MC_Run']>=9900 and t['Safety']>=9900 and t['HighFrequency']>=79000 and r['native_commands_during_5s']>=90 and r['encoder_delta']['errors']==0
  return 0 if r['passed'] else 1
 except Exception as e:r['error']=str(e) or type(e).__name__;return 1
 finally:save();print(json.dumps({k:v for k,v in r.items() if k not in ('before2802','boot','before','fresh','after')}),flush=True)
if __name__=='__main__':raise SystemExit(main())
