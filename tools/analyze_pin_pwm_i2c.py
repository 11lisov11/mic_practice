"""Stream CSV: D0..4 phases, D5=SDA,D6=SD,D7=SCL; no analog claims."""
import csv,json,statistics,argparse
from pathlib import Path
def analyze(path,sda_channel=5,scl_channel=7,sd_channel=6,pwm_channels=(0,1,2,3,4)):
 prev=None;previous_t=None;bits=[];packet=[];active=False;began=0
 parts=[];aborted=[];rises=[0]*6;last=[None]*6;periods=[[] for _ in range(6)]
 first_edge=None;last_edge=None;overlap=[0]*3;clock_edges=0;data_edges=0;sd_lows=[];sd_start=None
 def finish(t,kind):
  if not active:return
  part=dict(start_s=began,end_s=t,end=kind,bytes=[dict(value=x,ack=ack==0) for x,ack in packet])
  if packet:parts.append(part)
  # STOP/repeated START setup may add one SCL rising edge after the ACK.
  if len(bits)>1:aborted.append(dict(start_s=began,end_s=t,partial_bits=len(bits),end=kind))
 with Path(path).open(newline='') as f:
  reader=csv.reader(f);header=next(reader);names=[''.join(c.lower() for c in s if c.isalnum()) for s in header]
  cols=[names.index('channel'+str(i)) for i in range(8)]
  for row in reader:
   if not row:continue
   t=float(row[0]);v=[int(row[c]) for c in cols]
   if any(x not in (0,1) for x in v) or (previous_t is not None and t<previous_t):raise ValueError('Invalid CSV')
   if prev is not None:
    for ch in pwm_channels:
     if v[ch]!=prev[ch]:
      if first_edge is None:first_edge=t
      last_edge=t
     if v[ch] and not prev[ch]:
      rises[ch]+=1
      if last[ch] is not None:periods[ch].append(t-last[ch])
      last[ch]=t
    if t>previous_t:
     for leg in range(3):
      if 2*leg in pwm_channels and 2*leg+1 in pwm_channels:overlap[leg]+=int(prev[2*leg] and prev[2*leg+1])
    if sd_channel is not None:
     if prev[sd_channel] and not v[sd_channel]:sd_start=t
     if not prev[sd_channel] and v[sd_channel]:sd_lows.append(dict(start_s=sd_start,end_s=t));sd_start=None
    scl,sda=v[scl_channel],v[sda_channel];old_scl,old_sda=prev[scl_channel],prev[sda_channel]
    clock_edges+=scl!=old_scl;data_edges+=sda!=old_sda
    if old_scl and scl and sda!=old_sda:
     if not sda:
      finish(t,'repeated_start');began=t;active=True;packet=[];bits=[]
     else:
      finish(t,'stop');active=False;packet=[];bits=[]
    elif active and scl and not old_scl:
     bits.append(sda)
     if len(bits)==9:
      value=0
      for b in bits[:8]:value=(value<<1)|b
      packet.append((value,bits[8]));bits=[]
   prev=v;previous_t=t
 if active:finish(previous_t,'capture_end')
 target_nack=[];normal_read_nacks=0;unexpected=[];valid_reads=0;read_values=[];PWM_read_parts=0
 for part in parts:
  bs=part['bytes'];a=bs[0]['value'];read=bool(a&1);address=a>>1
  if address!=0x36:unexpected.append(part);continue
  if not bs[0]['ack']:target_nack.append(dict(time_s=part['start_s'],kind='address',read=read))
  if not read:
   for b in bs[1:]:
    if not b['ack']:target_nack.append(dict(time_s=part['start_s'],kind='write_data'))
  else:
   for index,b in enumerate(bs[1:],1):
    if not b['ack']:
     if index==len(bs)-1 and part['end']=='stop':normal_read_nacks+=1
     else:unexpected.append(dict(kind='early_read_NACK',part=part))
   if len(bs)==4 and bs[0]['ack'] and all(x['ack'] for x in bs[1:3]) and not bs[3]['ack'] and part['end']=='stop':
    valid_reads+=1;read_values.append([x['value'] for x in bs[1:]])
    if first_edge is not None and first_edge<=part['start_s'] and part['end_s']<=last_edge:PWM_read_parts+=1
 frequencies=[1/statistics.median(x) if x else None for x in periods]
 pwm_seconds=last_edge-first_edge if first_edge is not None else None
 pairs={name:overlap[i] if 2*i in pwm_channels and 2*i+1 in pwm_channels else None for i,name in enumerate(('U','V','W'))}
 return dict(channel_map={'0':'UH','1':'UL','2':'VH','3':'VL','4':'WH',str(sda_channel):'SDA',str(scl_channel):'SCL',**({str(sd_channel):'SD'} if sd_channel is not None else {})},
  sample_rate_hz=8_000_000,resolution_ns=125,PWM_rising_edges={str(i):rises[i] for i in pwm_channels},median_carrier_hz={str(i):frequencies[i] for i in pwm_channels},
  PWM_first_edge_s=first_edge,PWM_last_edge_s=last_edge,PWM_window_s=pwm_seconds,complementary_overlap_intervals=pairs,
  observed_PWM_outputs_verified=all(rises[i]>1000 for i in pwm_channels) and all(frequencies[i] is not None and 15000<frequencies[i]<17000 for i in pwm_channels) and not any(overlap) and pwm_seconds is not None and 3.99<pwm_seconds<4.01,
  all_six_PWM_outputs_observed=len(pwm_channels)==6,SD_low_intervals=sd_lows,
  SCL_edges=clock_edges,SDA_edges=data_edges,I2C_parts=len(parts),AS5600_valid_reads=valid_reads,
  AS5600_complete_read_parts_within_PWM=PWM_read_parts,partial_frames_within_PWM=[a for a in aborted if first_edge is not None and a['start_s']>=first_edge and a['end_s']<=last_edge],
  AS5600_target_NACK=target_nack,normal_controller_final_read_NACKs=normal_read_nacks,
  unexpected_frames=unexpected[:100],partial_frames=aborted[:100],last_sensor_bytes=read_values[-10:],
  first_parts=parts[:10],analog_ringing_or_sub125ns_glitches_qualified=False)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('csv',type=Path);p.add_argument('--out',type=Path);a=p.parse_args()
 r=analyze(a.csv)
 if a.out:a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in r.items() if k not in ('first_parts','last_sensor_bytes','unexpected_frames','partial_frames')}))
