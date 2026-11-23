"""Finish verified1611/1612 receipts and runtime checks. No flash/reset/motor cmds."""
import json,subprocess,time
import install_observer_current_window as install
p=install.p;io=install.io
def main():
    out=p.OUT/'hardware_install_r1';r=json.loads(p.read(out/'report.json'))
    assert r['native_readback_verified'] and r['uno_readback_verified'] and r['hmi_deployment']
    backup=out/'report_before_finish.json';assert not backup.exists();backup.write_bytes((out/'report.json').read_bytes())
    r.pop('error',None)
    def save():p.write(out/'report.json',json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    def run(command,label):
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=20)
        p.write(out/(label+'.log'),result.stdout+result.stderr);result.check_returncode();return result.stdout
    try:
        io.URL='http://127.0.0.1:18080'
        ssh=install.tunneled(install.ssh_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
        r['calibration_after']=run(ssh+['sha256sum /home/arduino/.config/mic-ai/vbus_calibration.json'],'calibration_after').split()[0]
        assert r['calibration_after']==r['calibration_before'];r['calibration_unchanged']=True;save()
        swd=[str(io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+io.STLINK_SERIAL]
        raw=run(swd+['-r32','0x48000000','40','-r32','0x48000400','40','-r32','0x40012c00','104'],'registers_after')
        reg=install.parse_registers(raw);r['native_BKE']=bool(reg[0x40012c44]&4096);r['native_MOE']=bool(reg[0x40012c44]&32768)
        assert r['native_BKE'] and not r['native_MOE']
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            try:
                s=io.live_status();install.safe(s,p.NEW)
                assert s.get('repeat_break',{}).get('available') and s['repeat_break']['fresh']
                assert s.get('observer_trace')==dict(available=False,reason='not_received')
                assert s['hmi_vbus_hv_calibrated']==1
                p.write(out/'after.json',json.dumps(s,ensure_ascii=False,indent=2)+'\n')
                r.update(passed=True,SD=s.get('mc_sd_live'),repeat_break=s['repeat_break'],zero_ready=s['mc_current_zero_ready']);break
            except Exception as exc:r['runtime_pending']=repr(exc);time.sleep(.6)
        if not r['passed']:raise RuntimeError(r.get('runtime_pending','runtime not ready'))
    except Exception as exc:r['error']=repr(exc)
    save();print(json.dumps({k:r.get(k) for k in ('passed','native_readback_verified','uno_readback_verified','calibration_unchanged','native_BKE','native_MOE','zero_ready','error')}))
    return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
