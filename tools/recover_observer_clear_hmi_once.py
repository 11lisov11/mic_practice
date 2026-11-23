"""Restart only the owned HMI once; no MCU reset/CLEAR/START/flash."""
import json,shlex,subprocess,time
import prepare_observer_current_window as p
from recover_clear_recovery_hmi_once import RESTART
def main():
    out=p.OUT/'one_CLEAR_idle_r1/HMI_restart_once';out.mkdir(exist_ok=False)
    p.write(out/'remote_restart.py',RESTART)
    r=subprocess.run(['adb','-s','3880458060','shell','python3 -c '+shlex.quote(RESTART)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=15)
    p.write(out/'result.json',r.stdout);p.write(out/'stderr.txt',r.stderr);r.check_returncode()
    print(r.stdout)
if __name__=='__main__':main()
