import os,pathlib,subprocess,json,time
def run(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=6);return dict(code=r.returncode,stdout=r.stdout,stderr=r.stderr)
d=dict(boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),uptime=pathlib.Path('/proc/uptime').read_text())
for name in ('unoq-hmi.service','arduino-router.service'):
 d[name]=run(['systemctl','show','-p','MainPID','-p','NRestarts','-p','SubState',name])
 d[name+'_journal']=run(['journalctl','-u',name,'-n','120','--no-pager'])
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
d['threads']={p.name:(p/'wchan').read_text().strip() for p in (pathlib.Path('/proc')/str(pid)/'task').iterdir()}
print(json.dumps(d))
