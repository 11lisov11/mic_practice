"""J1 explicitly OFF: archive Linux/HMI evidence, restart ONLY owned web process once."""
import json,pathlib,shlex,subprocess,urllib.request
from unoq_wifi_hmi_deploy import ssh_base

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/live_bench_20261116/clear_recovery_r1/powered_FOC_NIS_5Hz_r1/HMI_recovery_r2'
READ="""import os,pathlib,subprocess,json,time
def run(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=6);return dict(code=r.returncode,stdout=r.stdout,stderr=r.stderr)
d=dict(boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),uptime=pathlib.Path('/proc/uptime').read_text())
for name in ('unoq-hmi.service','arduino-router.service'):
 d[name]=run(['systemctl','show','-p','MainPID','-p','NRestarts','-p','SubState',name])
 d[name+'_journal']=run(['journalctl','-u',name,'-n','120','--no-pager'])
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
d['threads']={p.name:(p/'wchan').read_text().strip() for p in (pathlib.Path('/proc')/str(pid)/'task').iterdir()}
print(json.dumps(d))
"""
RESTART="""import os,pathlib,signal,subprocess,json
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
restart=subprocess.check_output(['systemctl','show','-p','Restart','--value','unoq-hmi.service'],text=True).strip()
p=pathlib.Path('/proc')/str(pid)
assert pid>1 and restart=='always' and p.stat().st_uid==os.geteuid()
assert (p/'cwd').resolve()==pathlib.Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
assert 'server.py' in (p/'cmdline').read_bytes().decode().split('\\0')
os.kill(pid,signal.SIGTERM)
print(json.dumps(dict(HMI_terminated_pid=pid,HMI_restarts=1,MCU_resets=0,START=0,CLEAR=0)))
"""

def main():
    OUT.mkdir(exist_ok=False)
    token=(ROOT/'.unoq_ssh/control_token').read_text().strip()
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        req=urllib.request.Request('http://192.168.1.138:8080/api/logs',headers={'X-UNOQ-Control-Token':token})
        with op.open(req,timeout=5) as f:raw=f.read()
        (OUT/'HMI_logs_before_restart.json').write_bytes(raw)
    except Exception as e:(OUT/'HMI_log_error.txt').write_text(str(e),encoding='utf-8')
    ssh=ssh_base('192.168.1.138',2222,'arduino',ROOT/'.unoq_ssh/id_ed25519',ROOT/'.unoq_ssh/known_hosts')
    report=dict(J1_OFF_confirmed=True,START=0,CLEAR=0,MCU_resets=0,HMI_restarts=0)
    for name,code in [('before',READ),('restart',RESTART)]:
        (OUT/(name+'.py')).write_text(code,encoding='utf-8')
        r=subprocess.run(ssh+['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(code)],
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=22)
        (OUT/(name+'.json')).write_text(r.stdout,encoding='utf-8');(OUT/(name+'_stderr.txt')).write_text(r.stderr,encoding='utf-8')
        assert r.returncode==0,name
        if name=='restart':report.update(json.loads(r.stdout))
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
