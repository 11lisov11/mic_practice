"""Restart owned HMI once over WiFi; no MCU reset, serial-route or motor commands."""
import shlex,subprocess
import prepare_observer_current_window as p
from unoq_wifi_hmi_deploy import ssh_base
from recover_clear_recovery_hmi_once import RESTART
def main():
    out=p.OUT/'one_CLEAR_powered_20261117_r1/HMI_restart_once';out.mkdir(exist_ok=False)
    p.write(out/'remote.py',RESTART)
    ssh=ssh_base('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
    r=subprocess.run(ssh+['python3 -c '+shlex.quote(RESTART)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=15)
    p.write(out/'result.json',r.stdout);p.write(out/'stderr.txt',r.stderr);r.check_returncode();print(r.stdout)
if __name__=='__main__':main()
