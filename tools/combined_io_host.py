"""Bounded isolated combined ADC/UART/PWM/AS5600 diagnostic, CRC readback."""
import argparse,json,struct,time,hashlib,subprocess
from pathlib import Path
import pin_pwm_diag_io as pin
from prepare_combined_io_diag import OUT as PACKAGE,OLD,BUILD
Probe=pin.Probe
def decode_pin(raw):
 if len(raw)!=256:raise ValueError('PIN size')
 w=list(struct.unpack('<64I',raw))
 if w[2]!=BUILD:raise ValueError('Combined PIN identity')
 w[2]=2026102795;d=pin.decode(struct.pack('<64I',*w));d['build']=BUILD;return d
def decode_io(raw):
 if len(raw)!=160:raise ValueError('IO size')
 w=struct.unpack('<40I',raw)
 if w[:4]!=(0x314f4943,BUILD,1,40) or w[4]&1 or w[4]!=w[37] or pin.crc32c(raw[20:148])!=w[38] or w[39]!=0x43494f45:raise ValueError('IO CRC/identity/sequence')
 names=('rx_bytes','rx_hardware_flags','rx_frames','rx_bad','rx_overflow','tx_queued','tx_completed','tx_timeouts','tx_dma_errors','tx_full_errors','tx_active','USART_CR1','USART_ISR','last_frame_ms','parser_fault','uart_flags')
 return dict(sequence=w[4],adc_all=w[5],adc_during_run=w[6],adc_stamp=w[7],adc_max_cost=w[8],adc_max_gap=w[9],adc_bad=w[10],
  ADC1_CR=w[11],ADC2_CR=w[12],ADC1_ISR=w[13],ADC2_ISR=w[14],ADC1_JSQR=w[15],ADC2_JSQR=w[16],CCR4=w[17],
  uart=dict(zip(names,w[18:34])),RCC_CCIPR=w[34],guard=w[35],hz=w[36])
def read(pr,sy,out,label):
 result={}
 for name,fn in [('mic_pin_report',decode_pin),('mic_io_report',decode_io)]:
  for n in range(4):
   s=sy[name];raw=pr.read(s['address'],s['bytes'],label+name+str(n));(out/(label+'_'+name+str(n)+'.bin')).write_bytes(raw)
   try:d=fn(raw);break
   except ValueError:
    if n==3:raise
    time.sleep(.1)
  result['pin' if name=='mic_pin_report' else 'io']=d
 (out/(label+'.json')).write_text(json.dumps(result,indent=2)+'\n');return result
def eligible(d):
 p,i=d['pin'],d['io']
 return p['build']==BUILD and p['state']==p['reason']==p['attempted']==0 and p['BDTR']&0x1000 and not(p['BDTR']&0xc000) and p['CCER']==0x555 and p['local_stop']==0 and p['GPIOA_IDR']&64 and p['encoder']['valid_flags']&3==3 and i['guard']==0 and i['adc_all']>100 and i['uart']['rx_frames']>0 and i['uart']['tx_completed']>0
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('install','status','run'));p.add_argument('--isolation-confirmed',action='store_true');p.add_argument('--outdir',type=Path,required=True);a=p.parse_args()
 if not a.isolation_confirmed:p.error('J1/J4OFF, ribbon disconnected, MCUUSB and retained probe map required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();pr=Probe(out/'logs')
 m=json.loads((PACKAGE/'manifest.json').read_text());assert m['built'] and m['offline_verified']
 for rel,h in m['sealed_sha256'].items():assert hashlib.sha256((PACKAGE/rel).read_bytes()).hexdigest()==h,rel
 sy=json.loads((PACKAGE/'verification/symbols.json').read_text())
 r=dict(passed=False,flash_commands=0,pin_requests=0,motor_commands=0,clear_commands=0,reset_commands=0)
 def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n')
 def archive(symbols,label):
  for name in ('fault_record','release_probe','bus_clear','mic_uart_tx','uno_transport'):
   if name in symbols:
    s=symbols[name];(out/(label+'_'+name+'.bin')).write_bytes(pr.read(s['address'],s['bytes'],label+name))
 try:
  if a.action=='install':
   old=json.loads((OLD/'verification/symbols.json').read_text());s=old['mic_pin_report']
   for attempt in range(4):
    raw=pr.read(s['address'],s['bytes'],'before2795_'+str(attempt));(out/('before2795_'+str(attempt)+'.bin')).write_bytes(raw)
    try:
     words=list(struct.unpack('<64I',raw));observed_build=words[2];words[2]=2026102795
     before=pin.decode(struct.pack('<64I',*words));before['build']=observed_build;break
    except ValueError:
     if attempt==3:raise
     time.sleep(.1)
   expected_build=json.loads((OLD/'manifest.json').read_text())['build']
   assert before['build']==expected_build and before['state'] in (0,2,3) and before['reason'] in (0,32) and not(before['BDTR']&0x8000)
   archive(old,'before2795');r['flash_commands']=1;save()
   q=subprocess.run([str(pin.PROGRAMMER),'-c','port=SWD','mode=UR','reset=HWrst','sn='+pin.SERIAL,'-w',str(PACKAGE/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'),'-v','-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
   (out/'logs/flash_readback.log').write_text(q.stdout+q.stderr,encoding='utf-8')
   if q.returncode or 'Download verified successfully' not in q.stdout:raise RuntimeError('Readback unconfirmed; no retry')
   r['readback_verified']=True;time.sleep(3);d=read(pr,sy,out,'boot');r['boot']=d;r['passed']=eligible(d);archive(sy,'boot')
   return 0 if r['passed'] else 1
  before=read(pr,sy,out,'before');r['before']=before
  if not eligible(before):raise RuntimeError('Combined ADC/UART/AS5600 admission failed; no request')
  time.sleep(.5);fresh=read(pr,sy,out,'fresh');r['fresh']=fresh
  assert eligible(fresh) and fresh['io']['adc_all']>before['io']['adc_all'] and fresh['io']['uart']['rx_frames']>before['io']['uart']['rx_frames'] and fresh['io']['uart']['tx_completed']>before['io']['uart']['tx_completed']
  if a.action=='status':r['passed']=True;return 0
  archive(sy,'before');before=fresh
  from saleae import automation
  with automation.Manager.connect(port=10430,connect_timeout_seconds=3) as manager:
   assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
   with manager.start_capture(device_id='A7D1BB81883C0092',device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=8_000_000,glitch_filters=[]),capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=10))) as cap:
    try:r['pin_requests']=1;save();pr.request(sy['mic_pin_request']['address']);time.sleep(6)
    finally:
     cap.wait();cap.save_capture(str(out/'combined_io.sal'));(out/'csv').mkdir();cap.export_raw_data_csv(directory=str(out/'csv'),digital_channels=list(range(8)))
  after=read(pr,sy,out,'after');r['after']=after;archive(sy,'after')
  b=after['pin']['boundaries'];final_phase=after['pin']['phase'];r['phases']=[]
  for index,(name,i) in enumerate([('quiet',0),('fixed_PWM',2),('modulated_PWM',4)],1):
   if index<final_phase or after['pin']['state']==2:r['phases'].append(dict(stage=name,reads=b[i+2]-b[i],errors=b[i+3]-b[i+1],complete=True))
   elif index==final_phase:r['phases'].append(dict(stage=name,reads=b[6]-b[i],errors=b[7]-b[i+1],complete=False))
  keys=('reads','errors','NACK','deadline','BUSY','ARLO','BERR_clears','forced_resets','normal_parks')
  r['encoder_delta']={k:after['pin']['encoder'][k]-before['pin']['encoder'][k] for k in keys}
  keys=('rx_bytes','rx_frames','rx_bad','tx_queued','tx_completed','tx_timeouts','tx_dma_errors','tx_full_errors')
  r['uart_delta']={k:after['io']['uart'][k]-before['io']['uart'][k] for k in keys}
  r['ADC_active_count']=after['io']['adc_during_run'];r['ADC_bad']=after['io']['adc_bad'];r['IO_guard']=after['io']['guard']
  p=after['pin'];r['passed']=p['state']==2 and p['reason']==0 and 5000<=p['elapsed_ms']<=5010 and not(p['BDTR']&0x8000) and 79000<=r['ADC_active_count']<=80200 and r['ADC_bad']==0
  return 0 if r['passed'] else 1
 except Exception as e:r['error']=str(e) or type(e).__name__;return 1
 finally:save();print(json.dumps({k:v for k,v in r.items() if k not in ('before','after','fresh','boot')}),flush=True)
if __name__=='__main__':raise SystemExit(main())
