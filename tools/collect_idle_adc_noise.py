"""Export OFF-only ADC diagnostics via read-only local page selection; no motor commands."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shlex
import statistics
import struct
import subprocess
from unoq_wifi_hmi_deploy import ssh_base
from configure_multi_algorithm import crc32c

ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026102941,2026102940)
SIZE=2176


def decode(raw, expected=PAIR[1]):
 if len(raw)!=SIZE:raise ValueError('Wrong noise capture length')
 h=struct.unpack_from('<20I',raw)
 if h[:3]!=(0x314e4441,1,expected) or h[8:10]!=(4,128):raise ValueError('Wrong noise format or peer')
 cases=[]
 names=('alternating_original','fixed_u1_v2','fixed_v1_w2','same_v_on_both_adcs')
 paths={0:('U1','V2'),2:('V1','W2'),3:('V1','V2')}
 for k,name in enumerate(names):
  rows=[];groups={}
  for j in range(128):
   a,b=struct.unpack_from('<HH',raw,128+4*(k*128+j));pair=a>>12;a&=4095
   if b>4095 or pair not in paths:raise ValueError('Invalid raw ADC/pair')
   if (k==0 and pair not in (0,2)) or (k>0 and pair!=(0 if k==1 else 2 if k==2 else 3)):
    raise ValueError('Case/context does not match capture')
   rows.append(dict(pair=pair,a=a,b=b))
   for path,value in zip(paths[pair],(a,b)):groups.setdefault(path,[]).append(value)
  stats={key:dict(n=len(v),minimum=min(v),maximum=max(v),span=max(v)-min(v),mean=statistics.mean(v),
      standard_deviation_counts=statistics.stdev(v)) for key,v in groups.items()}
  a=[r['a'] for r in rows];b=[r['b'] for r in rows]
  cov=sum((x-statistics.mean(a))*(y-statistics.mean(b)) for x,y in zip(a,b))/(len(a)-1)
  denom=statistics.stdev(a)*statistics.stdev(b)
  case=dict(name=name,paths=stats,raw=rows,covariance_counts_squared=cov,
      correlation=cov/denom if denom else None)
  if k==3:
   difference=[x-y for x,y in zip(a,b)]
   case.update(same_input_difference_mean_counts=statistics.mean(difference),
       same_input_difference_sd_counts=statistics.stdev(difference),
       common_component_sd_counts=statistics.stdev([(x+y)/2 for x,y in zip(a,b)]))
  cases.append(case)
 return dict(schema=1,firmware=expected,device_id=h[4]&0xfff,revision_id=h[4]>>16,
  cpu_hz=h[3],fault=h[5],duration_us=((h[7]-h[6])&0xffffffff)/h[3]*1e6,
  all_cases_complete=h[10]==4 and not h[5],cases=cases,
  registers=dict(zip(('adc1_smpr1','adc1_smpr2','adc2_smpr1','adc2_smpr2','common_ccr','adc1_cfgr','adc2_cfgr','tim1_ccr4'),h[12:20])),
  limitation='No filtering or inferred physical amperes. Same-input sampling changes the loading of that pin and shares VREF; correlation alone does not distinguish input, analog bias and reference-supply noise. Partial/aborted captures cannot qualify measurement.')


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True)
 p.add_argument('--offline',type=Path);p.add_argument('--host',default='192.168.1.138')
 p.add_argument('--port',type=int,default=2222);a=p.parse_args()
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 if a.offline:
  raw=a.offline.read_bytes();meta=dict(source_kind='synthetic',hardware_commands=0)
 else:
  code='''import sys,json
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RpcBridge
b=RpcBridge('/var/run/arduino-router.sock')
ok,s,error=b.get();assert ok,error
def off(v):
 return (v['fw_build'],v['mc_fw_build'])==(2026102941,2026102940) and v['state']=='SAFE' and v['pwm']==0 and not(v['bp_status']&0x22) and v['mc_age_ms']<300 and v['vdc']<=20
assert off(s) and s['noise_complete']==1
crc=s['noise_crc'];parts=[]
for page in range(17):
 ok,error=b.cmd('NOISE PAGE '+str(page));assert ok,error
 ok,v,error=b.get();assert ok,error
 assert off(v) and v['noise_complete']==1 and v['noise_crc']==crc and v['noise_view_page']==page
 parts.append(v['noise_page_hex'])
print(json.dumps(dict(hex=''.join(parts),crc=crc,status=s)))
'''
  cmd=ssh_base(a.host,a.port,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
  r=subprocess.run(cmd+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(code)],
   capture_output=True,text=True,timeout=110)
  (out/'export.log').write_text(r.stderr,encoding='utf-8');r.check_returncode()
  meta=json.loads(r.stdout);raw=bytes.fromhex(meta.pop('hex'));assert crc32c(raw)==meta['crc']
  meta.update(source_kind='hardware',page_selection_commands=17,start_commands=0,clear_commands=0,ack_commands=0)
 # Save before decoding, including invalid/aborted buffers. Never ACK/erase.
 (out/'capture.bin').write_bytes(raw)
 meta['sha256']=hashlib.sha256(raw).hexdigest()
 (out/'transport.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
 result=decode(raw);result['source_kind']=meta['source_kind'];result['sha256']=meta['sha256']
 (out/'decoded.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(dict(complete=result['all_cases_complete'],fault=result['fault'],sha256=meta['sha256'],source_kind=meta['source_kind'])))
 return 0 if result['all_cases_complete'] else 1


if __name__=='__main__':raise SystemExit(main())
