"""Install only the tested, pinned HMI refresh while the current stand is idle."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.request import ProxyHandler, build_opener

from collect_wifi_telemetry import get_status
from prepare_local_stop_hmi_fix import BASE_SHA, UI_SHA, ROOT

CAL_SHA = "a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17"
REMOTE = "/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi"
FIRST_FIELDS = ("mc_fault_reason", "mc_uart_error_flags", "mc_fault_current_mask",
                "mc_fault_occurred_mask", "mc_fault_motor_state", "mc_fault_sequence",
                "mc_fault_tx_status")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--selftest", required=True, type=Path)
    parser.add_argument("--guards", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--resume-from", type=Path, help="Resume a retained failed HMI-only installation")
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    manifest = json.loads((candidate / "manifest.json").read_text())
    files = {"server.py":candidate / "web_hmi/server.py", "app.js":candidate / "web_hmi/static/app.js"}
    hashes = {"server.py":manifest["hmi_sha256"], "app.js":manifest["ui_sha256"]}
    if manifest["base_sha256"] != BASE_SHA or manifest["base_ui_sha256"] != UI_SHA:
        raise RuntimeError("Unexpected candidate baseline")
    for name, path in files.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
            raise RuntimeError("Tested candidate changed: " + name)
    for path in (args.selftest, args.guards):
        if json.loads(path.read_text()).get("pass") is not True:
            raise RuntimeError("Required offline report failed")
    if args.resume_from:
        previous = json.loads((args.resume_from / "report.json").read_text())
        if (previous.get("schema") != "mic_ai.local_stop_hmi_install.v1"
                or previous.get("pass") is not False
                or previous.get("hmi_sha256") != hashes["server.py"]
                or previous.get("ui_sha256") != hashes["app.js"]):
            raise RuntimeError("Unexpected resume report")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema="mic_ai.local_stop_hmi_install.v1", **{"pass":False},
                  start_commands=0, arm_commands=0, clear_commands=0,
                  mcu_firmware_changed=False, calibration_file_modified=False,
                  first_fault_snapshot_preserved=False, hv_release_approved=False,
                  hmi_sha256=hashes["server.py"], ui_sha256=hashes["app.js"], operations=[])
    if args.resume_from:
        report["resumes_failed_installation"] = str(args.resume_from.resolve())
    ssh = ["ssh", "-p", "2222", "-i", str(ROOT / ".unoq_ssh/id_ed25519"),
           "-o", "UserKnownHostsFile=" + str(ROOT / ".unoq_ssh/known_hosts"),
           "-o", "StrictHostKeyChecking=yes", "arduino@192.168.1.138"]
    scp = ["scp", "-P", "2222", "-i", str(ROOT / ".unoq_ssh/id_ed25519"),
           "-o", "UserKnownHostsFile=" + str(ROOT / ".unoq_ssh/known_hosts"),
           "-o", "StrictHostKeyChecking=yes"]

    def run(command, label, source=None):
        result = subprocess.run(command, input=source, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=40)
        (out / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        report["operations"].append(dict(label=label, exit_code=result.returncode))
        if result.returncode:
            raise RuntimeError(label + " failed; inspect retained log")
        return result.stdout

    opener = build_opener(ProxyHandler({}))

    def read_idle():
        data = get_status(opener, "http://192.168.1.138:8080")
        if ((data.get("fw_build"), data.get("mc_fw_build")) != (2026101205, 2026101204)
                or data.get("state") != "SAFE" or data.get("pwm") != 0
                or data.get("hmi_hv_armed") != 0 or data.get("hmi_powered_trial_enabled") != 0
                or type(data.get("vdc")) not in (int, float) or not 0 <= data["vdc"] <= 2
                or data.get("bp_status") != 141 or data.get("bp_fault") != 1
                or data.get("bp_transport_fault") != 0 or not 0 <= data.get("bp_age_ms", 999) < 300):
            raise RuntimeError("Current idle installation conditions changed")
        return data

    try:
        before = read_idle()
        (out / "before.json").write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
        # Each upload has an unused path; the installed source is checked before staging.
        remote_script = '''
from pathlib import Path
import hashlib
root = Path(REMOTE)
cal = Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
expected = {root/'server.py':BASE_SHA, root/'static/app.js':UI_SHA, cal:CAL_SHA}
for path, digest in expected.items():
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, str(path)
for name in ('server.py', 'app.js'):
    target = root/('local_stop_hmi_'+name+'.staged')
    assert not target.exists(), 'Staging path exists'
print('Pinned installed HMI, UI and original calibration verified')
'''
        settings = f"REMOTE={REMOTE!r}\nBASE_SHA={BASE_SHA!r}\nUI_SHA={UI_SHA!r}\nCAL_SHA={CAL_SHA!r}\n"
        if not args.resume_from:
            run(ssh + [REMOTE + "/.venv/bin/python -"], "remote_precheck", settings + remote_script)
            for name, path in files.items():
                run(scp + [str(path), "arduino@192.168.1.138:" + REMOTE + "/local_stop_hmi_" + name + ".staged"],
                    "stage_" + name.replace(".", "_"))
            read_idle()
        install_script = '''
from pathlib import Path
import hashlib
import shutil
root = Path(REMOTE)
cal = Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
assert hashlib.sha256(cal.read_bytes()).hexdigest() == CAL_SHA
items = [(root/'server.py', root/'local_stop_hmi_server.py.staged', BASE_SHA, NEW_SERVER),
         (root/'static/app.js', root/'local_stop_hmi_app.js.staged', UI_SHA, NEW_UI)]
for target, staged, old, new in items:
    assert hashlib.sha256(target.read_bytes()).hexdigest() == old
    assert hashlib.sha256(staged.read_bytes()).hexdigest() == new
    assert not target.with_name(target.name+'.before_local_stop_hmi_fix').exists()
compile(items[0][1].read_text(), str(items[0][1]), 'exec')
for target, staged, old, new in items:
    shutil.copy2(target, target.with_name(target.name+'.before_local_stop_hmi_fix'))
    staged.chmod(target.stat().st_mode)
    staged.replace(target)
assert hashlib.sha256(cal.read_bytes()).hexdigest() == CAL_SHA
print('Installed tested HMI/UI; backups retained; calibration unchanged')
'''
        settings += f"NEW_SERVER={hashes['server.py']!r}\nNEW_UI={hashes['app.js']!r}\n"
        if not args.resume_from:
            run(ssh + [REMOTE + "/.venv/bin/python -"], "remote_install", settings + install_script)
        # The service runs as arduino with Restart=always. Verify the exact owned
        # process and installed/backup bytes, then let systemd restart that process.
        restart_script = '''
from pathlib import Path
import hashlib
import os
import signal
import subprocess
root = Path(REMOTE)
expected = [(root/'server.py', NEW_SERVER), (root/'static/app.js', NEW_UI),
            (root/'server.py.before_local_stop_hmi_fix', BASE_SHA),
            (root/'static/app.js.before_local_stop_hmi_fix', UI_SHA),
            (Path('/home/arduino/.config/mic-ai/vbus_calibration.json'), CAL_SHA)]
for path, digest in expected:
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, str(path)
def property(name):
    return subprocess.check_output(['systemctl', 'show', 'unoq-hmi.service', '-p', name, '--value'], text=True).strip()
assert property('User') == 'arduino' and property('Restart') == 'always'
pid = int(property('MainPID'))
assert pid > 1
proc = Path('/proc')/str(pid)
assert proc.stat().st_uid == os.getuid()
assert (proc/'cwd').resolve() == root
assert b'server.py' in (proc/'cmdline').read_bytes().split(b'\\x00')
print('Verified exact owned HMI process under systemd; SIGTERM', pid, flush=True)
os.kill(pid, signal.SIGTERM)
'''
        run(ssh + [REMOTE + "/.venv/bin/python -"], "restart_owned_hmi", settings + restart_script)
        after = None
        for attempt in range(15):
            try:
                after = read_idle()
                break
            except Exception:
                if attempt == 14:
                    raise
                time.sleep(1)
        (out / "after.json").write_text(json.dumps(after, indent=2) + "\n", encoding="utf-8")
        assert after["hmi_local_stop_latched"] == 1
        assert after["mc_fault_detail"].startswith("current=LOCAL_STOP_PC13; first=MCSDK_FAULT")
        assert {key:before[key] for key in FIRST_FIELDS} == {key:after[key] for key in FIRST_FIELDS}
        assert after["bp_good"] >= before["bp_good"]
        assert after["bp_bad"] == before["bp_bad"] and after["bp_bad_cnt"] == before["bp_bad_cnt"]
        verify_script = '''
from pathlib import Path
import hashlib
root = Path(REMOTE)
for path, digest in ((root/'server.py', NEW_SERVER), (root/'static/app.js', NEW_UI),
                     (Path('/home/arduino/.config/mic-ai/vbus_calibration.json'), CAL_SHA)):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    print(digest, path)
'''
        run(ssh + [REMOTE + "/.venv/bin/python -"], "remote_verify", settings + verify_script)
        report.update({"pass":True, "first_fault_snapshot_preserved":True,
                       "wifi_latch_matches_raw_status":True, "original_calibration_sha256":CAL_SHA})
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
