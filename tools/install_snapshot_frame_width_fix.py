"""Apply the tested HMI-only 43-byte frame parser correction on the idle fixture."""
import argparse,json
from pathlib import Path
import pwm_filter_hardware_session as bench
from install_passive_break_decoder_fix import FIRST_FIELDS,ERROR_FIELDS

def main(folder):
    s=bench.Session(folder);p=bench.PACKAGE
    before=s.idle();assert before['mc_break_rx_bad']==0 and before.get('mc_break_reject_valid')==0
    roots=(bench.HMI_ROOT,bench.REMOTE)
    old=[bench.sha(p/name/'web_hmi/server.py.before_frame_width_fix') for name in ('production','fixture')]
    new=[bench.sha(p/name/'web_hmi/server.py') for name in ('production','fixture')]
    common=f'''from pathlib import Path
import hashlib,subprocess,os,signal,shutil,json,time
roots=[Path(x) for x in {list(roots)!r}];old={old!r};new={new!r}
digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
cal=Path('/home/arduino/.config/mic-ai/vbus_calibration.json');assert digest(cal)=={bench.CAL_SHA!r}
def owned(pid,root,primary=False):
 proc=Path('/proc')/str(pid);assert proc.stat().st_uid==os.getuid() and (proc/'cwd').resolve()==root
 args=(proc/'cmdline').read_bytes().split(bytes([0]))
 assert (b'server.py' in args) if primary else (str(root/'server.py').encode() in args)
 return pid
def primary_pid():
 prop=lambda name:subprocess.check_output(['systemctl','show','unoq-hmi.service','-p',name,'--value'],text=True).strip()
 assert prop('User')=='arduino' and prop('Restart')=='always'
 return owned(int(prop('MainPID')),roots[0],True)
def fixture_pid():return owned(int((roots[1]/'hmi.pid').read_text()),roots[1])
'''
    s.remote(common+'''primary_pid();fixture_pid()
for i,root in enumerate(roots):
 assert digest(root/'server.py')==old[i]
 assert not (root/'server.py.before_frame_width_fix').exists()
 assert not (root/'frame_width_fix.staged').exists()
print('Both owned HMI processes and old source hashes verified')
''','frame_width_precheck')
    for name,root in zip(('production','fixture'),roots):
        s.run(s.scp+[p/name/'web_hmi/server.py','arduino@192.168.1.138:'+root+'/frame_width_fix.staged'],'frame_width_stage_'+name,timeout=40)
    s.idle()
    s.remote(common+f'''pid0=primary_pid();pid1=fixture_pid()
for i,root in enumerate(roots):
 target=root/'server.py';stage=root/'frame_width_fix.staged';backup=root/'server.py.before_frame_width_fix'
 assert digest(target)==old[i] and digest(stage)==new[i] and not backup.exists()
 compile(stage.read_text(),str(stage),'exec');shutil.copy2(target,backup)
 assert digest(backup)==old[i];stage.chmod(target.stat().st_mode);stage.replace(target)
 assert digest(target)==new[i]
os.kill(pid0,signal.SIGTERM);os.kill(pid1,signal.SIGTERM)
for attempt in range(20):
 if not (Path('/proc')/str(pid1)).exists():break
 time.sleep(.1)
root=roots[1];log=(root/'hmi.log').open('ab')
args=[{bench.VENV!r},str(root/'server.py'),'--bind','0.0.0.0','--port','8081','--router','/var/run/arduino-router.sock','--standalone-lv','--lv-arm-max-vdc','2','--start-runlimit-sec','3','--control-token-file','/home/arduino/.config/mic-ai/control_token','--log-file',str(root/'events.log')]
process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=str(root))
(root/'hmi.pid').write_text(str(process.pid));assert digest(cal)=={bench.CAL_SHA!r}
print('Only both HMI source files/restarted owned processes changed; MCU images unchanged')
''','frame_width_install')
    h=s.hmi()
    try:after=bench.wait_status(h,lambda d:(d.get('fw_build'),d.get('mc_fw_build'))==bench.PAIR and d.get('mc_break_reject_valid')==0 and d.get('bp_age_ms',9999)<300,25,'corrected diagnostic HMI')
    finally:h.close()
    s.idle();s.hashes('frame_width_final_primary_calibration')
    assert all(before.get(k)==after.get(k) for k in FIRST_FIELDS+ERROR_FIELDS)
    s.state['frame_width_fix_installed']=True;s.state['frame_width_after']=after;s.save()
    print(json.dumps({'pass':True,'mcu_writes':0,'new_hmi_sha256':new[0]}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--session',required=True,type=Path);args=parser.parse_args();main(args.session.resolve())
