"""GET-only original Go serial path; passive MCU and Linux UART observations.
No proxy, raw-mode changes, START/CLEAR/ARM, MCU halt/reset or flash.
Always restore the existing main router's port after the owned router exits.
"""
import os,sys,json,time,pathlib,subprocess,signal,fcntl,struct
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient


def main():
    work=pathlib.Path(sys.argv[1]);work.mkdir(exist_ok=False)
    root=RouterClient('/var/run/arduino-router.sock');child=None;observer=None;log=None
    stats=dict(passed=False,GET=0,START=0,CLEAR=0,MCU_reset=0,proxy=False)
    def route(action):
        r=root.call('$/serial/'+action,['/dev/ttyHS1'],timeout=5,retries=0)
        assert r and r[2] is None and r[3] is True,r
        return r
    def capture(label):
        cfg=work/(label+'.cfg')
        text='''$_CHIPNAME.ap0 configure -event examine-end {}
$_TARGETNAME configure -event examine-end {}
init
'''
        for name,addr,n in [('decoder',0x200141FC,1056),('serial',0x20019B7C,236),
                ('rpc_health',0x20019434,16),('bridge',0x20019680,376),
                ('worker',0x20014EA8,264),('updater',0x200196E8,264)]:
            text+=f'dump_image {work}/{name}_{label}.bin {addr:#x} {n}\n'
        text+='echo "LPUART_ISR: [read_memory 0x46002400 32 8]"\necho "CORE_AFTER: [$_TARGETNAME curstate]"\nshutdown\n'
        cfg.write_text(text)
        r=subprocess.run(['/opt/openocd/bin/openocd','-s','/opt/openocd','-s','/opt/openocd/share/openocd/scripts',
                '-f','/opt/openocd/openocd_gpiod.cfg','-f',str(cfg)],capture_output=True,text=True,timeout=20)
        (work/(label+'_read.log')).write_text(r.stdout+r.stderr);state=dict(OpenOCD_exit=r.returncode)
        for code,name,n in [(0x545D,'icount',80),(0x541B,'input_pending_bytes',4),(0x5411,'output_pending_bytes',4)]:
            try:
                b=bytearray(n);fcntl.ioctl(observer,code,b,True);state[name]=list(struct.unpack('<'+str(n//4)+'i',b))
            except OSError as e:state[name+'_error']=str(e)
        for item in ('runtime_status','runtime_suspended_time','runtime_active_time','control'):
            try:state[item]=pathlib.Path('/sys/class/tty/ttyHS1/device/power',item).read_text().strip()
            except OSError:pass
        stats[label]=state
    try:
        stats['main_close']=route('close')
        # This descriptor never reads/writes data or configures termios.
        observer=os.open('/dev/ttyHS1',os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
        log=(work/'router.log').open('wb')
        child=subprocess.Popen(['/usr/bin/arduino-router','--unix-port',str(work/'rpc.sock'),
            '--monitor-port','127.0.0.1:17500','--serial-port','/dev/ttyHS1','--serial-baudrate','115200','--verbose'],stdout=log,stderr=subprocess.STDOUT)
        stats['owned_router_pid']=child.pid;c=RouterClient(str(work/'rpc.sock'));began=time.monotonic();r=None
        while time.monotonic()-began<30:
            r=c.call('get',[],timeout=3,retries=0)
            if r and r[2] is None and isinstance(r[3],str):break
            time.sleep(.2)
        assert r and r[2] is None,'Direct router never qualified'
        stats['initial_response']=r[3];capture('baseline')
        with (work/'GETs.jsonl').open('w') as f:
            while time.monotonic()-began<720:
                start=time.monotonic();r=c.call('get',[],timeout=4,retries=0);stats['GET']+=1
                if not r or r[2] is not None:raise RuntimeError('Direct GET timeout/error: '+repr(r))
                fields=dict(x.split('=',1) for x in r[3].split() if '=' in x)
                assert fields['pwm']=='0' and fields['state']=='SAFE' and fields['fw_build']=='2026111609'
                f.write(json.dumps(dict(t=time.monotonic()-began,latency=time.monotonic()-start,response=r))+'\n');f.flush()
                if stats['GET']%30==0:print(json.dumps(dict(elapsed_s=round(time.monotonic()-began),GET=stats['GET'])),flush=True)
                time.sleep(.2)
        stats['passed']=True
    except Exception as e:
        stats['error']=str(e)
        if child and child.poll() is None:
            capture('failure');child.send_signal(signal.SIGQUIT)
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        if observer is not None:os.close(observer)
        if log:log.close()
        try:stats['main_open']=route('open')
        except Exception as e:stats['restore_error']=str(e)
        (work/'report.json').write_text(json.dumps(stats,indent=2)+'\n')
        print(json.dumps({k:v for k,v in stats.items() if k!='initial_response'}),flush=True)
    return 0 if stats['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
