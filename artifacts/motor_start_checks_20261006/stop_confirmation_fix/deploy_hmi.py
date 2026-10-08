"""Deploy this reviewed HMI fix only, while the known production MCUs are SAFE."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from run_wifi_nucleo_pwm_bench import WifiHmi, read_control_token, verify_unpowered_preflash
from verify_production_guard_semantics import production_off


def adb(*args, input=None):
    result = subprocess.run(["adb", "-s", "3880458060", *args], input=input,
                            text=True, capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout


def main():
    source = ROOT / "web_hmi/server.py"
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    remote = "/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py"
    pending = remote + ".pending_stop_confirmation_20261006"
    backup = remote + ".before_stop_confirmation_20261006"
    token = read_control_token("adb", "3880458060", "/home/arduino/.config/mic-ai/control_token")
    hmi = WifiHmi("http://192.168.1.138:8080", token, [], via_wsl=True)
    report = {"scope": "Linux HMI only; no MCU firmware change", "local_sha256": expected}
    try:
        report["before"] = hmi.status()
        verify_unpowered_preflash(report["before"])
        if (report["before"].get("fw_build") != 2026092901
                or report["before"].get("mc_fw_build") != 2026091401
                or report["before"].get("mode") != "VF"):
            raise RuntimeError("Unexpected production identity")
        code, response = hmi.fail_safe_stop()
        if code != 200 or response.get("ok") is not True:
            raise RuntimeError("Wi-Fi STOP not confirmed")
        adb("push", str(source), pending)
        script = f"""
import os,signal,subprocess,hashlib,shutil,json
from pathlib import Path
path=Path({remote!r}); pending=Path({pending!r}); backup=Path({backup!r})
assert hashlib.sha256(path.read_bytes()).hexdigest()=='8f8730a29d70f50d8f5e1d132147bc408c9156f5571ad623808bfd9f4518a9a6'
assert hashlib.sha256(pending.read_bytes()).hexdigest()=={expected!r}
compile(pending.read_text(encoding='utf-8-sig'),str(pending),'exec')
pid=int(subprocess.check_output(['systemctl','show','unoq-hmi.service','--property=MainPID','--value'],text=True).strip())
assert pid>1 and os.stat('/proc/'+str(pid)).st_uid==os.getuid()
argv=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(bytes([0]))
cwd=Path(os.readlink('/proc/'+str(pid)+'/cwd'))
assert any((cwd/a.decode()).resolve()==path.resolve() for a in argv if a.endswith(b'.py'))
assert not backup.exists()
shutil.copy2(path,backup)
os.chmod(pending,path.stat().st_mode & 0o777)
os.replace(pending,path)
os.kill(pid,signal.SIGTERM)
print(json.dumps({{'old_pid':pid,'backup':str(backup)}}))
"""
        report["deploy"] = json.loads(adb("shell", "python3", "-", input=script))
        for _ in range(30):
            try:
                status = hmi.status()
                pid = int(adb("shell", "systemctl", "show", "unoq-hmi.service",
                              "--property=MainPID", "--value").strip())
                if pid > 1 and pid != report["deploy"]["old_pid"] and production_off(status):
                    report["after"] = status
                    report["new_pid"] = pid
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Updated HMI did not return to production SAFE/HV profile")
        report["remote_sha256"] = adb("shell", "sha256sum", remote).split()[0]
        report["pass"] = report["remote_sha256"] == expected
    except Exception as exc:
        report["pass"] = False
        report["error"] = str(exc)
    finally:
        report["final_stop_http"] = hmi.fail_safe_stop()[0]
        hmi.close()
        (Path(__file__).parent / "deployment_verified.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in
                      ("pass", "error", "new_pid", "remote_sha256", "final_stop_http")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
