"""Decode observed1152008N1 RX bits and CRC32C frames; no inferred MCU timing."""
import argparse,bisect,csv,json
from pathlib import Path
from no_switch_diag_snapshot_io import crc32c
def decode(edges,initial=1,baud=115200,end=None):
 ts=[x[0] for x in edges];vs=[x[1] for x in edges];bit=1.0/baud
 def at(t):
  i=bisect.bisect_right(ts,t)-1;return initial if i<0 else vs[i]
 decoded=[];glitches=[];available=-1;prev=initial
 for t,v in edges:
  falling=prev==1 and v==0;prev=v
  if not falling or t<available-bit*.05:continue
  if end is not None and t+9.5*bit>end:break
  if at(t+.5*bit)!=0:glitches.append(t);continue
  value=sum(at(t+(1.5+i)*bit)<<i for i in range(8));stop=at(t+9.5*bit)
  decoded.append(dict(t=t,value=value,stop_high=bool(stop)));available=t+9.7*bit
 frames=[];i=0
 while i+43<=len(decoded):
  block=decoded[i:i+43];raw=bytes(x['value'] for x in block)
  if raw[:3]==b'\xaa\x55\x03':
   stored=int.from_bytes(raw[39:43],'little');calculated=crc32c(raw[:39]);framing=all(x['stop_high'] for x in block)
   item=dict(start_s=block[0]['t'],end_s=block[-1]['t']+10*bit,sequence=raw[5],flags=raw[3],mode=raw[4],frequency_millihz=int.from_bytes(raw[6:10],'little'),crc_valid=stored==calculated,framing_valid=framing,raw_hex=raw.hex())
   frames.append(item);i+=43 if stored==calculated and framing else 1
  else:i+=1
 return dict(baud=baud,decoded_bytes=len(decoded),framing_errors=[x for x in decoded if not x['stop_high']],short_start_glitches_s=glitches,
  valid_frames=sum(f['crc_valid'] and f['framing_valid'] for f in frames),invalid_candidate_frames=[f for f in frames if not(f['crc_valid'] and f['framing_valid'])],frames=frames)
def analyze(path):
 edges=[];sd=[];initial=None;prev=None;last=0
 with Path(path).open(newline='') as f:
  rd=csv.reader(f);h=next(rd);names=[''.join(c.lower() for c in s if c.isalnum()) for s in h];i=names.index('channel4');j=names.index('channel6')
  for row in rd:
   if not row:continue
   t=float(row[0]);v=int(row[i]);s=int(row[j]);last=t
   if initial is None:initial=v;old_sd=s
   elif v!=prev:edges.append((t,v))
   if s!=old_sd:sd.append(dict(t=t,level=s));old_sd=s
   prev=v
 r=decode(edges,initial,end=last);r['SD_edges']=sd;r['capture_end_s']=last
 r['frames_near_SD']=[a for a in r['frames'] if any(abs(a['start_s']-e['t'])<.025 for e in sd)]
 r['wire_only_limitation']='Digital samples at125ns; cannot measure analog thresholds/ringing or prove MCU interrupt latency'
 return r
def main():
 ap=argparse.ArgumentParser();ap.add_argument('csv',type=Path);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();r=analyze(a.csv);a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in r.items() if k not in ('frames','invalid_candidate_frames','framing_errors','short_start_glitches_s')},default=str))
if __name__=='__main__':main()
