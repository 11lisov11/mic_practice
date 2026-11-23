"""One router serial reconnection, no MCU reset and no motor commands."""
import json,shlex,subprocess
import prepare_observer_current_window as p
from reopen_clear_recovery_rpc_route import CODE
def main():
    out=p.OUT/'one_CLEAR_idle_r1/route_reopen_once';out.mkdir(exist_ok=False)
    p.write(out/'remote.py',CODE)
    r=subprocess.run(['adb','-s','3880458060','shell','/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(CODE)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=18)
    p.write(out/'stdout.jsonl',r.stdout);p.write(out/'stderr.txt',r.stderr)
    rows=[json.loads(x) for x in r.stdout.splitlines()];s=rows[-1].get('status') or {} if rows else {}
    print(json.dumps(dict(exit=r.returncode,routes=rows[:2],status_received=bool(s),pwm=s.get('pwm'),CLEAR=0,START=0,MCU_resets=0)))
if __name__=='__main__':main()
