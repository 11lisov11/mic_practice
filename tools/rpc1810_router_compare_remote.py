"""GET-only isolation: stock router on a private PTY, with both wire directions saved.

Never call cmd, reset, flash, ARM or CLEAR. Restore the original serial owner and
resume the identified web process in finally. No MCU address/layout assumptions.
"""
import os, sys, time, json, pathlib, signal, subprocess, threading, select, pty, termios, fcntl
import msgpack
sys.path.insert(0, '/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient


def main():
    work = pathlib.Path(sys.argv[1]); work.mkdir()
    root = RouterClient('/var/run/arduino-router.sock')
    fd = master = slave = child = web_pid = None
    paused = closed = False
    stop = threading.Event(); thread = None
    report = dict(START=0, CLEAR=0, ARM=0, RESET=0, flash=0, requests=[], errors=[])

    def route(action):
        value = root.call('$/serial/' + action, ['/dev/ttyHS1'], timeout=5, retries=0)
        assert value and value[2] is None and value[3] is True, value

    def raw(port):
        a = termios.tcgetattr(port)
        a[0] = a[1] = a[3] = 0; a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[4] = a[5] = termios.B115200; a[6][termios.VMIN] = a[6][termios.VTIME] = 0
        termios.tcsetattr(port, termios.TCSANOW, a)

    def proxy():
        buffers = {fd: bytearray(), master: bytearray()}
        assembly=bytearray()
        packet_mode=len(sys.argv)>3 and sys.argv[3]=='packet'
        report['packet_mode']=packet_mode
        with (work/'from_MCU.bin').open('wb') as rx, (work/'to_MCU.bin').open('wb') as tx:
            try:
                while not stop.is_set():
                    rd, wr, _ = select.select([fd, master], [p for p,b in buffers.items() if b], [], .02)
                    for port in rd:
                        try: data = os.read(port, 65536)
                        except BlockingIOError: continue
                        if not data: continue
                        target = master if port == fd else fd
                        if port==master and packet_mode:
                            assembly.extend(data)
                            while assembly:
                                try:
                                    msgpack.unpackb(assembly,raw=False)
                                    n=len(assembly)
                                except msgpack.ExtraData as extra:
                                    n=len(assembly)-len(extra.extra)
                                except (ValueError,msgpack.OutOfData):break
                                buffers[fd].extend(assembly[:n]);del assembly[:n]
                        else:buffers[target].extend(data)
                        log = rx if port == fd else tx; log.write(data); log.flush()
                    for port in wr:
                        try: n = os.write(port, buffers[port])
                        except BlockingIOError: continue
                        del buffers[port][:n]
                    assert max(map(len, buffers.values())) < 262144
            except Exception as e:
                report['errors'].append(repr(e))
            finally:
                report['proxy_pending']={str(p):len(b) for p,b in buffers.items()}
                report['assembly_pending']=len(assembly)

    try:
        web_pid = int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'], text=True))
        proc = pathlib.Path('/proc')/str(web_pid)
        assert web_pid > 1 and proc.stat().st_uid == os.geteuid()
        assert (proc/'cwd').resolve() == pathlib.Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
        os.kill(web_pid, signal.SIGSTOP); paused = True
        route('close'); closed = True
        fd = os.open('/dev/ttyHS1', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); raw(fd)
        master, slave = pty.openpty(); raw(slave); os.set_blocking(master, False)
        thread = threading.Thread(target=proxy); thread.start()
        with (work/'router.log').open('wb') as log:
            child = subprocess.Popen(['/usr/bin/arduino-router','--unix-port',str(work/'rpc.sock'),
                '--monitor-port','127.0.0.1:0','--serial-port',os.ttyname(slave),
                '--serial-baudrate','115200','--verbose'], stdout=log, stderr=subprocess.STDOUT)
            start = time.monotonic()
            while not (work/'rpc.sock').exists() and time.monotonic()-start < 3: time.sleep(.05)
            client = RouterClient(str(work/'rpc.sock'))
            # Bound the test; do not issue any command method even on failure.
            duration = float(sys.argv[2]) if len(sys.argv)>2 else 0
            calls = [('history',[0,0]), ('get',[]), ('get',[])]
            while calls or time.monotonic()-start < duration:
                method, params = calls.pop(0) if calls else ('get',[])
                time.sleep(.2 if duration else 2)
                began = time.monotonic(); response = client.call(method, params, timeout=5, retries=0)
                item = dict(method=method, seconds=time.monotonic()-began, response=response)
                report['requests'].append(item)
                print(json.dumps({k:v for k,v in item.items() if k!='response'} | {'answered':response is not None}), flush=True)
                if response is None:
                    report['failure_after_s'] = time.monotonic()-start
                    # Exact 1809 layout from its loader+sketch ELF, passive reads.
                    assert any(isinstance(x['response'],list) and isinstance(x['response'][3],str)
                               and 'fw_build=2026111809' in x['response'][3] for x in report['requests'])
                    cfg = work/'failure_read.cfg'
                    cfg.write_text('''$_CHIPNAME.ap0 configure -event examine-end {}
$_TARGETNAME configure -event examine-end {}
init
dump_image WORK/failure_decoder.bin 0x20014ecc 0x420
dump_image WORK/failure_serial.bin 0x20036854 0xec
dump_image WORK/failure_health.bin 0x2003610c 16
dump_image WORK/failure_bridge.bin 0x20036358 0x178
dump_image WORK/failure_worker.bin 0x20015b78 0x108
dump_image WORK/failure_control.bin 0x20016500 20
dump_image WORK/failure_worker_stack.bin 0x20036a30 0x1000
dump_image WORK/failure_bridge_stack.bin 0x2004b0d0 0x1000
echo "CORE_AFTER: [$_TARGETNAME curstate]"
shutdown
'''.replace('WORK',str(work)))
                    cap = subprocess.run(['/opt/openocd/bin/openocd','-s','/opt/openocd','-s',
                        '/opt/openocd/share/openocd/scripts','-f','/opt/openocd/openocd_gpiod.cfg',
                        '-f',str(cfg)],capture_output=True,text=True,timeout=20)
                    (work/'failure_read.log').write_text(cap.stdout+cap.stderr)
                    # Stack trace only of this process's child, never the system router.
                    child.send_signal(signal.SIGQUIT)
                    child.wait(timeout=3)
                    break
            client.close()
    except Exception as e:
        report['error'] = repr(e)
    finally:
        if child is not None:
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        stop.set()
        if thread: thread.join(timeout=2)
        for port in (fd,master,slave):
            if port is not None: os.close(port)
        if closed:
            try: route('open'); report['original_router_reopened'] = True
            except Exception as e: report['restore_error'] = repr(e)
        if paused:
            os.kill(web_pid, signal.SIGCONT); report['web_resumed'] = True
        (work/'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({k:v for k,v in report.items() if k!='requests'}), flush=True)


if __name__ == '__main__': main()
