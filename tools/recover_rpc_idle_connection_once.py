"""One router serial reconnect on confirmed J1-OFF bench; preserve both MCU RAMs."""
import json,subprocess,shlex,time
import prepare_rpc_route_recovery as p
import install_bkin_boot_armed_pair as io

def main():
    out=p.OUT/'idle_timeout_diagnosis_r1/connection_recovery_once';out.mkdir(exist_ok=False)
    code='''import sys,json
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
c=RouterClient('/var/run/arduino-router.sock')
for action in ('close','open'):
 r=c.call('$/serial/'+action,['/dev/ttyHS1'],timeout=5,retries=0)
 assert r and r[2] is None and r[3] is True,r
 print(json.dumps({'action':action,'response':r}))
'''
    r=subprocess.run(['adb','-s',io.UNO_SERIAL,'shell','/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(code)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=15)
    p.write(out/'route.log',r.stdout+r.stderr);r.check_returncode()
    io.URL='http://127.0.0.1:18080';report=dict(passed=False,router_reconnect=1,MCU_reset=0,START=0,CLEAR=0)
    for i in range(8):
        try:
            s=io.live_status();p.write(out/f'status_{i}.json',json.dumps(s,ensure_ascii=False,indent=2))
            assert (s['fw_build'],s['mc_fw_build'])==p.NEW and s['pwm']==0 and s['state']=='SAFE'
            report.update(passed=True,status_file=f'status_{i}.json',native_tick=s['native_boot']['native_tick_ms'],
                RPC_timeouts=s['rpc_response_timeouts'],route_renewed=s['rpc_route_renewed']);break
        except Exception as e:report.setdefault('errors',[]).append(str(e));time.sleep(.2)
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
