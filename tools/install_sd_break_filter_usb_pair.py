"""Use the same verified installer over Uno USB/ADB tunnels, without Wi-Fi.

SSH remains key-authenticated against the original pinned Uno host key. All
programming/off/voltage guards and before/after calibration checks are retained.
"""
import subprocess
import sys
import shlex
import install_sd_break_filter_pair as install
from unoq_wifi_hmi_deploy import ssh_base, scp_base


def tunneled(factory):
    def command(host, port, user, key, known_hosts):
        if host != '192.168.1.138' or port != 2222:
            raise RuntimeError('unexpected USB tunnel destination')
        cmd = factory(host, 12222, user, key, known_hosts)
        return cmd[:1] + ['-o', 'HostName=127.0.0.1', '-o',
                         'HostKeyAlias=[192.168.1.138]:2222'] + cmd[1:]
    return command


def restart_owned_hmi():
    """Reconnect the HMI RPC client after flashing; no controller reset."""
    code = '''import os,pathlib,signal,subprocess,json
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
restart=subprocess.check_output(['systemctl','show','-p','Restart','--value','unoq-hmi.service'],text=True).strip()
p=pathlib.Path('/proc')/str(pid)
assert pid>1 and restart=='always' and p.stat().st_uid==os.geteuid()
assert (p/'cwd').resolve()==pathlib.Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
assert 'server.py' in (p/'cmdline').read_bytes().decode().split('\\0')
os.kill(pid,signal.SIGTERM)
print(json.dumps(dict(hmi_pid=pid,reconnect_requested=True,mcu_reset_commands=0,motor_commands=0)))
'''
    return subprocess.check_output(['adb', '-s', install.io.UNO_SERIAL, 'shell',
        'python3 -c ' + shlex.quote(code)], text=True)


def main():
    if '--verify-package-only' in sys.argv:
        return install.base.main()
    if '--confirm-j1-off-usb-bus-below-20v' not in sys.argv:
        raise RuntimeError('physical programming state confirmation required')
    install.verify_package()
    adb = ['adb', '-s', install.io.UNO_SERIAL]
    state = subprocess.check_output(adb + ['get-state'], text=True).strip()
    if state != 'device':
        raise RuntimeError('expected Uno USB/ADB not available')
    for local, remote in ((18080, 8080), (12222, 2222)):
        subprocess.run(adb + ['forward', 'tcp:' + str(local), 'tcp:' + str(remote)], check=True, capture_output=True)
    install.io.URL = 'http://127.0.0.1:18080'
    install.io.ssh_base = tunneled(ssh_base)
    install.base.ssh_base = tunneled(ssh_base)
    install.base.scp_base = tunneled(scp_base)
    return install.base.main()


if __name__ == '__main__':
    raise SystemExit(main())
