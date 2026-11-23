"""Passive installed image/register/HMI check. No reset, CLEAR or motor command."""
import argparse
import json
import re
import shlex
import subprocess
import time
from pathlib import Path
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base
import install_sd_dual_capture_pair as install
install.configure()

def words(log):
    out={}
    for m in re.finditer(r'(?m)^(0x[0-9a-fA-F]+) : ([0-9a-fA-F ]+)$',log):
        out.update({int(m[1],16)+4*i:int(w,16) for i,w in enumerate(m[2].split())})
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--report-name',default='completion_verification.json')
    a=p.parse_args();out=a.outdir.resolve()
    if Path(a.report_name).name!=a.report_name or not a.report_name.endswith('.json'):
        raise RuntimeError('report-name must be a JSON filename')
    target=out/a.report_name
    if target.exists():raise RuntimeError('preserve existing verification')
    install.verify_package();installed=json.loads((out/'report.json').read_text(encoding='utf-8'))
    assert installed['mcu_flash_commands']==2 and installed['hmi_installed']
    assert installed['uno_readback_verified'] and installed['nucleo_readback_verified']
    assert installed['calibration_unchanged']
    work=out/target.stem
    work.mkdir(exist_ok=False)
    r=dict(passed=False,read_only=True,flash_commands=0,reset_commands=0,clear_commands=0,motor_commands=0,
           original_installer_passed=installed['pass'],samples=[])
    try:
        install.io.URL='http://127.0.0.1:18080'
        for local,remote in ((18080,8080),(12222,2222)):
            subprocess.run(['adb','-s',install.io.UNO_SERIAL,'forward','tcp:'+str(local),'tcp:'+str(remote)],check=True,capture_output=True)
        for _ in range(10):
            s=install.io.live_status();r['samples'].append(s)
            okay,reason=install.precheck(s);assert okay,reason
            assert (s['fw_build'],s['mc_fw_build'])==install.NEW
            assert s['hmi_vbus_hv_calibrated']==1 and s['hmi_manual_scalar_supported']==1
            assert s['mc_bad_integrity']==0 and s['mc_bad_sequence']==0 and s['mc_uart_error_flags']==0
            time.sleep(.5)
        assert r['samples'][-1]['mc_good']>r['samples'][0]['mc_good'],'no UART reply progress'
        connect=[str(install.io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+install.io.STLINK_SERIAL]
        binary=install.C/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin'
        readback=work/'nucleo_flash_readback.bin'
        install.io.run(connect+['-u','0x08000000',str(binary.stat().st_size),str(readback)],'nucleo_flash_read_only',work,r,30)
        assert readback.read_bytes()==binary.read_bytes(),'Nucleo flash mismatch'
        gpio=words(install.io.run(connect+['-r32','0x48000000','0x28'],'gpioa_read_only',work,r,20))
        tim=words(install.io.run(connect+['-r32','0x40012C00','0x68'],'tim1_read_only',work,r,20))
        timer=words(install.io.run(connect+['-r32','0x40000028','0x08'],'tim2_read_only',work,r,20))
        mode,pull,idr=gpio[0x48000000],gpio[0x4800000c],gpio[0x48000010]
        assert (mode>>8)&3==0 and (pull>>8)&3==0,'PA4 is not passive INPUT/NOPULL'
        assert (mode>>12)&3==2 and (pull>>12)&3==1,'PA6 BKIN mode mismatch'
        bdtr=tim[0x40012c44]
        assert (bdtr>>16)&15==9 and bdtr&0x1000 and not bdtr&0xc000
        assert tim[0x40012c60]==0x201 and tim[0x40012c00]&0x300==0x100
        assert timer[0x40000028]==0 and timer[0x4000002c]==33,'sampling timer scale mismatch'
        r.update(nucleo_byte_for_byte_match=True,nucleo_verified_bytes=binary.stat().st_size,
                 pa4_input_nopull=True,pa4_level='HIGH' if idr&16 else 'LOW',
                 pa6_level='HIGH' if idr&64 else 'LOW',bkin_filter=9,break_enabled=True,
                 pwm_output_enabled=False,automatic_restart=False,tim2_prescaler=0,tim2_arr=33)
        ssh=tunneled(ssh_base)('192.168.1.138',2222,'arduino',install.ROOT/'.unoq_ssh/id_ed25519',install.ROOT/'.unoq_ssh/known_hosts')
        remote='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/'
        paths=[remote+'server.py',remote+'static/app.js','/home/arduino/.config/mic-ai/vbus_calibration.json']
        log=install.io.run(ssh+[shlex.join(['sha256sum']+paths)],'live_hmi_calibration_hashes',work,r,20)
        actual=[x.split()[0] for x in log.splitlines()]
        assert actual==[install.io.sha(install.C/'web_hmi/server.py'),install.io.sha(install.C/'web_hmi/static/app.js'),installed['calibration_before']]
        after=install.io.live_status();assert install.precheck(after)[0]
        assert (after['fw_build'],after['mc_fw_build'])==install.NEW
        assert 'UNO Q loader and sketch verification PASSED' in (out/'verify_uno.log').read_text()
        r.update(passed=True,live_pair=list(install.NEW),hmi_files_match=True,calibration_unchanged=True,
                 calibration_sha256=actual[2],uno_at_install_flash_readback_verified=True,after=after,
                 capture_record_hardware_test_performed=False,powered_motor_test_performed=False)
    except Exception as exc:r['error']=str(exc)
    target.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('passed','live_pair','nucleo_byte_for_byte_match','pa4_input_nopull','pa4_level','pa6_level','calibration_unchanged','error')}))
    return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
