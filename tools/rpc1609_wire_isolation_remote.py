"""Run only GET through a temporary, user-owned router and a lossless serial logger.
J1 stays OFF. Both MCUs keep running. Always restore the main router's serial port.
"""
import os,sys,json,time,termios,pty,select,threading,subprocess,signal,pathlib,fcntl,struct
import msgpack
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient

def main():
    work=pathlib.Path(sys.argv[1]);work.mkdir(exist_ok=False)
    root=RouterClient('/var/run/arduino-router.sock')
    stats=dict(GET=0,START=0,CLEAR=0,MCU_reset=0,passed=False,proxy_errors=[],invalid_packets=[],physical_written=0)
    child=None;fd=None;master=None;slave=None;worker=None;stop=threading.Event();raw_log=None
    def route(action):
        r=root.call('$/serial/'+action,['/dev/ttyHS1'],timeout=5,retries=0)
        assert r and r[2] is None and r[3] is True,r
        return r
    def raw_mode(port,baud=True):
        a=termios.tcgetattr(port);a[0]=0;a[1]=0;a[3]=0;a[2]=termios.CS8|termios.CREAD|termios.CLOCAL
        if baud:a[4]=a[5]=termios.B115200
        a[6][termios.VMIN]=0;a[6][termios.VTIME]=0
        termios.tcsetattr(port,termios.TCSANOW,a)
    def capture(label):
        # Observe both ring indices and kernel serial counts before reconnect.
        # Never halt/reset, write target memory or read UART RDR.
        cfg=work/(label+'_readonly.cfg')
        cfg.write_text('''$_CHIPNAME.ap0 configure -event examine-end {}
$_TARGETNAME configure -event examine-end {}
init
dump_image REPLACE/decoder_LABEL.bin 0x200141FC 0x420
dump_image REPLACE/serial_LABEL.bin 0x20019B7C 0xEC
dump_image REPLACE/rpc_health_LABEL.bin 0x20019434 16
dump_image REPLACE/bridge_LABEL.bin 0x20019680 376
dump_image REPLACE/worker_LABEL.bin 0x20014EA8 264
dump_image REPLACE/updater_LABEL.bin 0x200196E8 264
echo "LPUART_ISR: [read_memory 0x46002400 32 8]"
echo "CORE_AFTER: [$_TARGETNAME curstate]"
shutdown
'''.replace('REPLACE',str(work)).replace('LABEL',label))
        before=(work/'from_MCU.bin').stat().st_size;tx_before=stats['physical_written']
        cap=subprocess.run(['/opt/openocd/bin/openocd','-s','/opt/openocd','-s','/opt/openocd/share/openocd/scripts',
            '-f','/opt/openocd/openocd_gpiod.cfg','-f',str(cfg)],capture_output=True,text=True,timeout=20)
        (work/(label+'_read.log')).write_text(cap.stdout+cap.stderr)
        stats[label+'_capture']=dict(exit=cap.returncode,wire_before=before,wire_after=(work/'from_MCU.bin').stat().st_size,
            physical_written_before=tx_before,physical_written_after=stats['physical_written'])
        try:
            counters=bytearray(80);fcntl.ioctl(fd,0x545D,counters,True) # TIOCGICOUNT, read only
            stats[label+'_capture']['Linux_uart_icount']=list(struct.unpack('<20i',counters))
        except OSError as e:stats[label+'_capture']['Linux_uart_icount_error']=str(e)
        for item in ('runtime_status','runtime_suspended_time','runtime_active_time','control'):
            try:stats[label+'_capture'][item]=pathlib.Path('/sys/class/tty/ttyHS1/device/power',item).read_text().strip()
            except OSError:pass
    try:
        stats['main_close']=route('close')
        fd=os.open('/dev/ttyHS1',os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK);raw_mode(fd)
        master,slave=pty.openpty();raw_mode(slave);os.set_blocking(master,False)
        slave_name=os.ttyname(slave)
        def proxy():
            to_mcu=bytearray();to_router=bytearray();decode=msgpack.Unpacker(raw=False,max_buffer_size=2**22)
            batch_delay=float(sys.argv[2]) if len(sys.argv)>2 else 0.0
            pending_since=None
            count=0
            with (work/'from_MCU.bin').open('wb') as rx,(work/'to_MCU.bin').open('wb') as tx,(work/'physical_to_MCU.bin').open('wb') as actual,(work/'wire_events.jsonl').open('w') as events:
                while not stop.is_set():
                    rd,wr,_=select.select([fd,master],[p for p,b in ((fd,to_mcu),(master,to_router)) if b],[],.02)
                    for port in rd:
                        try:data=os.read(port,65536)
                        except BlockingIOError:continue
                        if not data:continue
                        if port==fd:
                            rx.write(data);rx.flush();to_router.extend(data);count+=len(data)
                            try:
                                decode.feed(data)
                                for obj in decode:
                                    good=isinstance(obj,list) and len(obj) in (3,4) and obj[0] in (0,1,2)
                                    if not good:stats['invalid_packets'].append(dict(byte_at=count,object=repr(obj)[:180]))
                                    events.write(json.dumps(dict(t=time.monotonic(),bytes_received=count,
                                        packet_type=obj[0] if isinstance(obj,list) and obj else None,
                                        id=obj[1] if isinstance(obj,list) and len(obj)>1 else None,
                                        good=good))+'\n');events.flush()
                            except Exception as error:
                                stats['proxy_errors'].append(dict(where='wire decode',byte_at=count,error=str(error)))
                                decode=msgpack.Unpacker(raw=False,max_buffer_size=2**22)
                        else:
                            tx.write(data);tx.flush()
                            if not to_mcu:pending_since=time.monotonic()
                            to_mcu.extend(data)
                    for port in wr:
                        if port==fd and pending_since is not None and time.monotonic()-pending_since<batch_delay:continue
                        b=to_mcu if port==fd else to_router
                        try:n=os.write(port,b)
                        except BlockingIOError:continue
                        if port==fd:actual.write(b[:n]);actual.flush()
                        del b[:n]
                        if port==fd:stats['physical_written']+=n
                        if port==fd and not b:pending_since=None
                    if max(len(to_mcu),len(to_router))>262144:raise RuntimeError('Proxy backlog exceeded bound')
            stats['MCU_wire_bytes']=count
            stats['pending_to_MCU']=len(to_mcu);stats['pending_to_router']=len(to_router)
        def worker_main():
            try:proxy()
            except Exception as e:stats['proxy_errors'].append(dict(where='proxy thread',error=str(e)))
        worker=threading.Thread(target=worker_main);worker.start()
        raw_log=(work/'temporary_router.log').open('wb')
        child=subprocess.Popen(['/usr/bin/arduino-router','--unix-port',str(work/'rpc.sock'),
            '--monitor-port','127.0.0.1:17500','--serial-port',slave_name,'--serial-baudrate','115200','--verbose'],stdout=raw_log,stderr=subprocess.STDOUT)
        stats['owned_router_pid']=child.pid
        began=time.monotonic();deadline=began+30;c=RouterClient(str(work/'rpc.sock'));response=None
        while time.monotonic()<deadline:
            response=c.call('get',[],timeout=3,retries=0)
            if response and response[2] is None and isinstance(response[3],str):break
            time.sleep(.2)
        assert response and response[2] is None,'Temporary routing never qualified'
        stats['first_reply_bytes']=len(response[3]);stats['initial_response']=response[3]
        capture('baseline')
        with (work/'GETs.jsonl').open('w') as log:
            while time.monotonic()-began<720:
                started=time.monotonic();r=c.call('get',[],timeout=4,retries=0);stats['GET']+=1
                if not r or r[2] is not None:raise RuntimeError('GET failed in temporary router: '+repr(r))
                body=r[3];assert isinstance(body,str)
                fields=dict(tok.split('=',1) for tok in body.split() if '=' in tok)
                assert fields['pwm']=='0' and fields['state']=='SAFE','Controller not OFF'
                log.write(json.dumps(dict(t=time.monotonic()-began,latency=time.monotonic()-started,response=r))+'\n');log.flush()
                if stats['GET']%30==0:print(json.dumps(dict(elapsed_s=round(time.monotonic()-began),GET=stats['GET'],invalid_packets=len(stats['invalid_packets']),errors=len(stats['proxy_errors']))),flush=True)
                time.sleep(.2)
        stats['passed']=not stats['invalid_packets'] and not stats['proxy_errors']
    except Exception as error:
        stats['error']=str(error)
        if child and child.poll() is None:
            capture('failure')
            # SIGQUIT applies only to the child router owned by this handle.
            child.send_signal(signal.SIGQUIT)
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        stop.set()
        if worker:worker.join(timeout=5)
        for port in (fd,master,slave):
            if port is not None:
                try:os.close(port)
                except OSError:pass
        if raw_log:raw_log.close()
        try:stats['main_open']=route('open')
        except Exception as error:stats['main_restore_error']=str(error)
        (work/'report.json').write_text(json.dumps(stats,indent=2)+'\n')
        summary={k:v for k,v in stats.items() if k not in ('initial_response','invalid_packets')}
        summary['invalid_packet_count']=len(stats['invalid_packets'])
        print(json.dumps(summary),flush=True)
    return 0 if stats['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
