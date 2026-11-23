"""Deploy only Uno Linux/HMI via pinned key-authenticated SSH; never flash an MCU."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shlex
import subprocess
from typing import Optional
from urllib.parse import urlparse
import urllib.request
import uuid

from install_vbus_hmi_fix_remote import precheck


DEFAULT_URL = "http://192.168.1.138:8080"
DEFAULT_REMOTE = "/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi"


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def fetch_status(base_url: str, timeout: float = 8.0) -> dict:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base_url.rstrip("/")+"/api/status",timeout=timeout) as response:
        payload=json.load(response)
    if payload.get("ok") is not True or not isinstance(payload.get("data"),dict):
        raise RuntimeError(payload.get("error") or "HMI status unavailable")
    return payload["data"]


def safe_for_update(status: dict, max_vdc: float, *, lso_verified_idle=False) -> tuple[bool,str]:
    if type(max_vdc) not in (int,float) or not math.isfinite(max_vdc) or max_vdc not in (2,10):
        return False,"unreviewed update voltage limit"
    ok,reason=precheck(status,int(max_vdc),lso_verified_idle=lso_verified_idle)
    if not ok:return ok,reason
    # mc_bad_integrity is a cumulative since-boot diagnostic counter. A historical
    # rejected frame remains visible in HMI, but does not make a read-only HMI
    # bundle update unsafe when the current response and all active/freshness gates pass.
    if type(status.get("mc_bad_integrity")) is not int or not 0 <= status["mc_bad_integrity"] <= 0xFFFF:
        return False,"invalid diagnostic counter: mc_bad_integrity"
    for key in ("mc_bad_cnt","mc_bad_sequence","mc_uart_error_flags",
                "mc_last_uart_error_flags","uno_tx_short_writes","bp_transport_fault"):
        if type(status.get(key)) is not int or status[key]!=0:
            return False,"transport unhealthy: "+key
    return True,"disarmed, discharged, fresh measurement contract and clean UART"


def identity_options(key: Path, known_hosts: Path) -> list[str]:
    return ["-i",str(key),"-o","BatchMode=yes","-o","IdentitiesOnly=yes",
        "-o","ConnectTimeout=5","-o","StrictHostKeyChecking=yes",
        "-o","UserKnownHostsFile="+str(known_hosts),"-o","UpdateHostKeys=no",
        "-o","PasswordAuthentication=no","-o","KbdInteractiveAuthentication=no",
        "-o","ForwardAgent=no"]


def ssh_base(host: str, port: int, user: str, key: Path,
             known_hosts: Path=Path(".unoq_ssh/known_hosts")) -> list[str]:
    return ["ssh",*identity_options(key,known_hosts),"-p",str(port),f"{user}@{host}"]


def scp_base(host: str, port: int, user: str, key: Path,
             known_hosts: Path=Path(".unoq_ssh/known_hosts")) -> list[str]:
    return ["scp",*identity_options(key,known_hosts),"-P",str(port)]


def matching_host(url: str, override: str="") -> str:
    parsed=urlparse(url)
    if parsed.scheme!="http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("explicit unauthenticated LAN HMI URL required")
    host=parsed.hostname
    if override and override!=host:
        raise ValueError("SSH target must match the guarded HMI host")
    return host


def app_candidate_path(root: Path, include_app_js: bool,
                       explicit: Optional[Path] = None) -> Optional[Path]:
    if explicit is not None and not include_app_js:
        raise ValueError("--candidate-app-js requires --include-app-js")
    if not include_app_js:
        return None
    candidate=(explicit or (root/"web_hmi/static/app.js")).resolve(strict=True)
    if not candidate.is_file() or candidate.suffix.lower()!=".js":
        raise ValueError("candidate app bundle must be a JavaScript file")
    return candidate


def physical_update_confirmation(max_vdc: int, both_off: bool, mains_off: bool) -> bool:
    return (max_vdc == 2 and both_off) or (max_vdc == 10 and (both_off or mains_off))


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url",default=DEFAULT_URL)
    p.add_argument("--host",default="")
    p.add_argument("--user",choices=("arduino",),default="arduino")
    p.add_argument("--ssh-port",type=int,default=2222)
    p.add_argument("--key",type=Path,default=Path(".unoq_ssh/id_ed25519"))
    p.add_argument("--known-hosts",type=Path,default=Path(".unoq_ssh/known_hosts"))
    p.add_argument("--remote",default=DEFAULT_REMOTE)
    p.add_argument("--max-vdc",type=int,choices=(2,10),default=2)
    p.add_argument("--confirm-mains-j4-off",action="store_true")
    p.add_argument("--confirm-mains-off",action="store_true",help="10-V HMI-only tier: J4 may remain on; no MCU writes")
    p.add_argument("--lso-verified-idle",action="store_true",help="Exact 2305/2306 pair, discharged live bus and inactive soft-start")
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("--include-app-js",action="store_true")
    p.add_argument("--reinstall-identical",action="store_true")
    p.add_argument("--outdir",type=Path)
    p.add_argument("--candidate-server",type=Path,help="Explicit reviewed self-contained HMI server; default is repository server")
    p.add_argument("--candidate-app-js",type=Path,help="Explicit reviewed browser bundle used with --include-app-js")
    a=p.parse_args()
    if a.remote!=DEFAULT_REMOTE:p.error("only the scoped HMI target is supported")
    if a.candidate_app_js and not a.include_app_js:
        p.error("--candidate-app-js requires --include-app-js")
    if a.lso_verified_idle and (a.max_vdc != 10 or a.include_app_js or not a.candidate_server):
        p.error("LSO idle mode requires the 10-V server-only update path and an explicit candidate")
    if not a.dry_run and not (a.lso_verified_idle or physical_update_confirmation(
            a.max_vdc,a.confirm_mains_j4_off,a.confirm_mains_off)):
        p.error("2-V tier requires mains/J4 off; 10-V HMI-only tier requires mains off")
    if not 1<=a.ssh_port<=65535:p.error("invalid SSH port")
    host=matching_host(a.url,a.host)
    key=a.key.resolve(strict=True);known=a.known_hosts.resolve(strict=True)
    root=Path(__file__).resolve().parents[1]
    try:
        app_source=app_candidate_path(root,a.include_app_js,a.candidate_app_js)
    except (OSError,ValueError) as exc:
        p.error(str(exc))
    out=(a.outdir or root/"artifacts/hmi_wifi_deploy"/uuid.uuid4().hex).resolve()
    out.mkdir(parents=True,exist_ok=False)
    report=dict(pass_=False,commands=[],transport="pinned_key_wifi_ssh",ssh_port=a.ssh_port,
        mcu_flash_commands=0,actuation_commands=0,scope="Linux HMI only")
    ssh=ssh_base(host,a.ssh_port,a.user,key,known)
    scp=scp_base(host,a.ssh_port,a.user,key,known)

    def run(command: list[str],label: str,timeout=90) -> str:
        result=subprocess.run(command,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout)
        (out/(label+".log")).write_text(result.stdout+result.stderr,encoding="utf-8")
        report["commands"].append(dict(label=label,exit_code=result.returncode))
        if result.returncode:raise RuntimeError(label+" failed; see retained log")
        return result.stdout

    def remote_hash(path: str,label: str) -> str:
        value=run(ssh+["sha256sum "+shell_quote(path)],label).split()[0]
        if len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
            raise RuntimeError("invalid remote SHA256")
        return value

    try:
        report["before"]=before=fetch_status(a.url)
        ok,reason=safe_for_update(before,a.max_vdc,lso_verified_idle=a.lso_verified_idle)
        if not ok:raise RuntimeError(reason)
        if run(ssh+["id -u"],"verify_ssh_identity").strip()!="1000":
            raise RuntimeError("unexpected SSH user identity")
        server=(a.candidate_server or root/"web_hmi/server.py").resolve(strict=True)
        if not server.is_file() or server.suffix!=".py":raise RuntimeError("candidate server must be a Python file")
        expected=hashlib.sha256(server.read_bytes()).hexdigest()
        report["candidate_sha256"]=expected
        cal="/home/arduino/.config/mic-ai/vbus_calibration.json"
        report["calibration_before_sha256"]=remote_hash(cal,"calibration_before")
        installed=remote_hash(a.remote+"/server.py","server_before")
        report["server_before_sha256"]=installed
        if a.dry_run:
            report.update(pass_=True,dry_run=True,files_changed=False)
        elif installed==expected and not a.include_app_js and not a.reinstall_identical:
            report.update(pass_=True,already_current=True,files_changed=False)
        else:
            identifier=uuid.uuid4().hex
            remote_server="/tmp/mic_wifi_hmi_"+identifier+".py"
            remote_installer="/tmp/mic_wifi_installer_"+identifier+".py"
            run(scp+[str(server),f"{a.user}@{host}:{remote_server}"],"stage_server")
            run(scp+[str(root/"tools/install_vbus_hmi_fix_remote.py"),f"{a.user}@{host}:{remote_installer}"],"stage_installer")
            if remote_hash(remote_server,"verify_staged_server")!=expected:
                raise RuntimeError("staged server differs from tested source")
            command=["python3",remote_installer,"--candidate",remote_server,"--sha256",expected]
            if a.max_vdc==10:
                command += ["--max-vdc","10","--lso-verified-idle" if a.lso_verified_idle else "--confirm-mains-off"]
            if a.include_app_js:
                app=app_source
                remote_app="/tmp/mic_wifi_app_"+identifier+".js"
                run(scp+[str(app),f"{a.user}@{host}:{remote_app}"],"stage_app_js")
                command += ["--app-js",remote_app,"--app-js-sha256",hashlib.sha256(app.read_bytes()).hexdigest()]
                report["app_js_candidate"]=str(app)
                report["app_js_sha256"]=hashlib.sha256(app.read_bytes()).hexdigest()
            checked=run(ssh+[shlex.join(command+["--check-only"])],"remote_precheck")
            report["remote_check_only_pass"]='"check_only": true' in checked
            if not report["remote_check_only_pass"]:raise RuntimeError("remote precheck not confirmed")
            report["install_output"]=run(ssh+[shlex.join(command)],"install_hmi",90)
            report["files_changed"]=True
            report["same_content_reinstall"]=installed==expected
            report["server_after_sha256"]=remote_hash(a.remote+"/server.py","server_after")
            if report["server_after_sha256"]!=expected:raise RuntimeError("installed HMI hash mismatch")
            report["pass_"]=True
        report["calibration_after_sha256"]=remote_hash(cal,"calibration_after")
        report["calibration_unchanged"]=report["calibration_before_sha256"]==report["calibration_after_sha256"]
        report["after"]=after=fetch_status(a.url)
        if not safe_for_update(after,a.max_vdc,lso_verified_idle=a.lso_verified_idle)[0] or not report["calibration_unchanged"]:
            raise RuntimeError("post-deployment state/calibration check failed")
        if (after.get("fw_build"),after.get("mc_fw_build"))!=(before.get("fw_build"),before.get("mc_fw_build")):
            raise RuntimeError("unexpected MCU identity change")
    except Exception as e:
        report["pass_"]=False;report["error"]=f"{type(e).__name__}: {e}"
    finally:
        report["pass"]=report.pop("pass_")
        (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report.get(k) for k in ("pass","ssh_port","dry_run","same_content_reinstall",
                    "calibration_unchanged","mcu_flash_commands","actuation_commands","error")}))
    return 0 if report["pass"] else 1


if __name__=="__main__":raise SystemExit(main())
