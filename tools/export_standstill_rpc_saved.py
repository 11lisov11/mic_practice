"""Read the frozen result over authenticated SSH/RPC, never START/CLEAR/ACK."""
import json,subprocess,shlex,hashlib
from pathlib import Path
from unoq_wifi_hmi_deploy import ssh_base
from standstill_measurement import ROOT,SIZE,crc32c
CODE='''import sys,json,time
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RpcBridge
bridge=RpcBridge('/var/run/arduino-router.sock')
ok,s,error=bridge.get();assert ok,error
assert (s['fw_build'],s['mc_fw_build'])==(2026102931,2026102932) and s['state']=='SAFE' and s['pwm']==0
assert s['id_complete']==1
crc=s['id_result_crc'];run=s['id_run_id'];parts=[]
for page in range(13):
 ok,error=bridge.cmd('IDENT PAGE '+str(page));assert ok,error
 ok,v,error=bridge.get();assert ok,error
 assert v['state']=='SAFE' and v['pwm']==0 and v['id_result_crc']==crc and v['id_run_id']==run and v['id_view_page']==page
 parts.append(v['id_page_hex'])
print(json.dumps(dict(hex=''.join(parts),crc=crc,run_id=run,status=s)))
'''
def main():
 out=ROOT/'artifacts/live_bench_20261029/standstill_commissioning_r1/first_dc_point_r1/raw_abort'
 assert not (out/'capture.bin').exists()
 cmd=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
 r=subprocess.run(cmd+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)],capture_output=True,text=True,timeout=70)
 (out/'rpc_export.log').write_text(r.stderr,encoding='utf-8');r.check_returncode()
 data=json.loads(r.stdout);raw=bytes.fromhex(data.pop('hex'));assert len(raw)==SIZE and crc32c(raw)==data['crc']
 (out/'capture.bin').write_bytes(raw)
 data.update(passed=True,sha256=hashlib.sha256(raw).hexdigest(),clear_commands=0,start_commands=0,ack_commands=0,
  valid_parameter_measurement=False,transport='authenticated SSH / registered RPC')
 (out/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:data[k] for k in ('passed','sha256','crc','run_id','valid_parameter_measurement')}))
if __name__=='__main__':main()
