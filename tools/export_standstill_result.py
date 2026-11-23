"""Save a frozen ID result, including aborted records; no START/CLEAR/ACK."""
import argparse,json,time,hashlib,urllib.request
from pathlib import Path
from standstill_measurement import ROOT,PAIR,SIZE,crc32c
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True);a=p.parse_args()
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);url='http://192.168.1.138:8080'
 token=(ROOT/'.unoq_ssh/control_token').read_text(encoding='utf-8').strip();op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def get(path):
  req=urllib.request.Request(url+path,headers={'X-UNOQ-Control-Token':token})
  with op.open(req,timeout=5) as r:reply=json.load(r)
  assert reply.get('ok') is True,reply
  return reply
 end=time.monotonic()+30
 while True:
  s=get('/api/status')['data']
  assert (s['fw_build'],s['mc_fw_build'])==PAIR and s['pwm']==0 and s['state']=='SAFE','not stopped peer'
  if s.get('id_complete')==1:break
  assert time.monotonic()<end,'frozen pages incomplete';time.sleep(.4)
 raw=bytearray();crc=s['id_result_crc'];run=s['id_run_id']
 for page in range(13):
  r=get('/api/identification?page='+str(page));assert r['crc32c']==crc and r['run_id']==run
  raw.extend(bytes.fromhex(r['hex']))
 assert len(raw)==SIZE and crc32c(raw)==crc
 (out/'capture.bin').write_bytes(raw)
 (out/'status.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
 report=dict(passed=True,crc32c=crc,sha256=hashlib.sha256(raw).hexdigest(),run_id=run,fault=s['id_fault'],
  start_commands=0,clear_commands=0,ack_commands=0,valid_parameter_measurement=s['id_fault']==0)
 (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
