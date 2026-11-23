"""Passive evidence of failed1609 long test, before port recovery; no halt/reset/flash."""
import json,subprocess
import prepare_rpc_short_lock as p

def main():
    out=p.OUT/'idle_failure_RAM_r1';out.mkdir(exist_ok=False)
    source=p.read(p.ROOT/'tools/unoq_idle_rpc_RAM_readonly.cfg')
    remote='/tmp/unoq_rpc1609_idle_RAM.bin'
    cfg=out/'capture.cfg';p.write(cfg,source.replace('/tmp/unoq_idle_rpc_RAM.bin',remote))
    adb=['adb','-s','3880458060']
    def run(cmd,label,timeout=20):
        r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=timeout)
        p.write(out/(label+'.log'),r.stdout+r.stderr);r.check_returncode();return r.stdout+r.stderr
    run(adb+['push',str(cfg),'/tmp/rpc1609_capture.cfg'],'stage')
    log=run(adb+['shell','/opt/openocd/bin/openocd','-s','/opt/openocd','-s','/opt/openocd/share/openocd/scripts','-f','/opt/openocd/openocd_gpiod.cfg','-f','/tmp/rpc1609_capture.cfg'],'RAM_read',150)
    assert 'CORE_AFTER: running' in log
    run(adb+['pull',remote,str(out/'Uno_RAM_nonatomic.bin')],'RAM_pull')
    assert (out/'Uno_RAM_nonatomic.bin').stat().st_size==786432
    import inspect_unoq_idle_RAM as inspect
    inspect.OUT=out;inspect.APP=p.OUT/'build/uno/UNOQ_MOTOR.ino.elf';inspect.RAM=(out/'Uno_RAM_nonatomic.bin').read_bytes()
    inspect.main()
    import decode_unoq_idle_waits as decode
    decode.main()
    p.write(out/'report.json',json.dumps(dict(START=0,CLEAR=0,reset=0,halt=0,flash=0,atomic=False,
        RAM_SHA256=p.sha(out/'Uno_RAM_nonatomic.bin'),core_after='running'),indent=2)+'\n')
if __name__=='__main__':main()
