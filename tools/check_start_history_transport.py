"""Offline throughput model and bounded read-only RPC export regressions."""
import json,shutil
from pathlib import Path
import prepare_start_history_release as p
from download_start_history_off import collect

def capacity(baud):
 # Discrete 10us model. Same four transport slots, reserve two for control;
 # local journal four rows, no waiting/spin at enqueue. Main polls <=0.5ms.
 tx=[];pending=[];done=0;dropped=0;largest=0;line=0
 period=100;poll=50;duration=500000
 for tick in range(duration+10000):
  if tx and tick>=done:
   tx.pop(0)
   if tx:done=tick+round(43*10/baud*100000)
  if tick<duration and tick%period==0:
   if len(pending)<4:pending.append(tick)
   else:dropped+=1
  if tick<duration and tick%5000==0:
   # command reply plus ordinary telemetry: privileged over journal packets.
   for _ in range(2):
    if len(tx)<4:
     if not tx:done=tick+round(43*10/baud*100000)
     tx.append('control');line+=43
  if tick%poll==0 and pending and len(tx)<=1:
   pending.pop(0)
   if not tx:done=tick+round(43*10/baud*100000)
   tx.append('history');line+=43
  largest=max(largest,len(pending))
 return dict(baud=baud,generated_rows=5000,dropped=dropped,max_local_queue=largest,
  queued_bytes=line,assumed_poll_gap_us=500,hardware_qualification=False)

def main():
 out=p.OUT/'transport_verification';out.mkdir(exist_ok=False)
 record=p.OUT/'verification/synthetic_record'
 parts=[(record/name).read_bytes() for name in ('meta.bin','rows.bin','checkpoints.bin')]
 def rpc(part,page):
  raw=parts[part];chunk=raw[page*192:(page+1)*192]
  return f'NH 305419896 1 {len(raw)} '+(chunk.hex() if raw else '-')
 result=collect(rpc,out/'download')
 assert result['exact']
 for name,raw in zip(('meta.bin','rows.bin','checkpoints.bin'),parts):assert (out/'download'/name).read_bytes()==raw
 # An event in the first sixteen calls has no checkpoint page; zero is explicit.
 parts[1]=parts[1][:22];parts[2]=b''
 early=collect(rpc,out/'empty_checkpoint');assert early['sizes']['checkpoints.bin']==0
 rejected=[]
 for name,fn in (
  ('RUN',lambda part,page:'ERR RUN'),
  ('wrong_epoch',lambda part,page:rpc(part,page).replace('305419896','305419897') if part else rpc(part,page)),
  ('short_page',lambda part,page:rpc(part,page)[:-2])):
  try:collect(fn,out/name)
  except ValueError as exc:rejected.append(dict(case=name,error=str(exc)))
  else:raise AssertionError(name)
 at_new=capacity(921600);at_old=capacity(115200)
 assert at_new['dropped']==0 and at_old['dropped']>0
 report=dict(passed=True,bounded_page_bytes=192,read_only_RPC_method='history',
  whole_download_bit_exact=True,empty_checkpoints_supported=True,rejections=rejected,
  throughput_models=[at_new,at_old],hardware_commands=0,UART_rate_NOT_hardware_qualified=True)
 p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
