"""USB read-only direct GET, archive full raw response and wire-size budget."""
import json,subprocess,shlex
import prepare_clear_recovery as p

CODE="""import sys,json
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
c=RouterClient('/var/run/arduino-router.sock')
r=c.call('get',[],timeout=4,retries=0)
print(json.dumps(r))
"""

def main():
    out=p.OUT/'USB_recheck_after_shared_bank_r1/RPC_read';out.mkdir(exist_ok=False)
    r=subprocess.run(['adb','-s','3880458060','shell','/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=12)
    p.write(out/'raw_RPC.json',r.stdout);p.write(out/'stderr.txt',r.stderr)
    assert r.returncode==0
    reply=json.loads(r.stdout);assert reply and reply[2] is None and isinstance(reply[3],str)
    text=reply[3];payload=len(text.encode('utf-8'))
    report=dict(GET=1,START=0,CLEAR=0,RESET=0,flash=0,RPC_body_bytes=payload,
        ideal_wire_time_ms=payload*10/115200*1000,RPC_send_deadline_ms=2000,
        partial_send_root_cause_proven=False,
        hex_field_lengths={token.split('=',1)[0]:len(token.split('=',1)[1]) for token in text.split() if '=' in token and ('hex=' in token or 'wave=' in token)})
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
