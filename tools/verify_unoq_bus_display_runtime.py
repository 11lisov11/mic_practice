"""Read-only USB check of live Uno bus display; no motor/reset/flash commands."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request

import install_unoq_bus_display as install
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base

DIGITS=((7,5,5,5,7),(2,6,2,2,7),(7,1,7,4,7),(7,1,7,1,7),(5,5,7,1,1),
        (7,4,7,1,7),(7,4,7,5,7),(7,1,2,2,2),(7,5,7,5,7),(7,5,7,1,7))


def expected_frame(volts, softstart):
    words=[0,0,0,0]
    def pixel(x,y):
        i=y*13+12-x;words[i//32]|=1<<(i%32)
    for pos,digit in enumerate((volts//100,(volts//10)%10,volts%10)):
        if (pos==0 and volts<100) or (pos==1 and volts<10):continue
        for y,row in enumerate(DIGITS[digit]):
            for x in range(3):
                if row&(1<<(2-x)):pixel(1+4*pos+x,1+y)
    for x,y in ((0,6),(2,6),(1,7)):pixel(x,y)
    if softstart:
        pixel(0,0);pixel(0,1)
    return [w if i<3 else w&255 for i,w in enumerate(words)]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True)
    args=p.parse_args();out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(passed=False,read_only=True,start_commands=0,arm_commands=0,clear_commands=0,
                reset_commands=0,flash_commands=0,samples=[],startup_read_errors=[],physical_led_observation_verified=False)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def status():
        with opener.open('http://127.0.0.1:18080/api/status',timeout=6) as response:body=json.load(response)
        assert body['ok'];s=body['data'];report['samples'].append(s)
        okay,reason=install.precheck(s);assert okay,reason
        assert (s['fw_build'],s['mc_fw_build'])==install.NEW
        return s
    try:
        image=install.verify_package()
        adb=['adb','-s',install.io.UNO_SERIAL]
        for local,remote in ((18080,8080),(12222,2222)):
            subprocess.run(adb+['forward',f'tcp:{local}',f'tcp:{remote}'],capture_output=True,check=True)
        for attempt in range(6):
            try:s=status();break
            except (urllib.error.URLError,TimeoutError) as exc:
                report['startup_read_errors'].append(str(exc))
                if attempt==5:raise
                time.sleep(2)
        for _ in range(3):time.sleep(.3);s=status()
        base=Path.home()/'AppData/Local/Arduino15/packages/arduino'
        core=base/'hardware/zephyr/0.90.0/firmwares/zephyr-arduino_uno_q_stm32u585xx.elf'
        command=[str(base/'tools/remoteocd/0.1.1/remoteocd.exe'),'upload','--adb-path','adb','-s',install.io.UNO_SERIAL,
                 '-f',str(install.ROOT/'tools/read_unoq_matrix.cfg'),str(core),str(image)]
        report['matrix_attempts']=[]
        for attempt in range(3):
            before=status()
            read=subprocess.run(command,capture_output=True,text=True,timeout=30)
            log=read.stdout+read.stderr;(out/f'matrix_read_{attempt+1}.log').write_text(log,encoding='utf-8')
            assert read.returncode==0,'Passive matrix read failed'
            match=re.search(r'MATRIX_FRAMEBUFFER_BEGIN\s+((?:0x[0-9a-f]+\s+){4})MATRIX_FRAMEBUFFER_END',log,re.I)
            scan=re.search(r'MATRIX_SCAN_BEGIN\s+((?:0x[0-9a-f]+\s+){8})MATRIX_SCAN_END',log,re.I)
            assert match and scan,'Matrix read markers missing'
            actual=[int(w,16) for w in match[1].split()];actual[3]&=255
            indices=[int(w,16) for w in scan[1].split()]
            after=status()
            candidates={int(s['bp_vdc']+.5) for s in (before,after)}
            matches=[v for v in candidates if actual==expected_frame(v,before['bp_softstart_ready'])]
            item=dict(actual_frame=actual,scan_indices=indices,scan_running=all(0<=i<104 for i in indices) and len(set(indices))>1,
                      observed_voltages_v=[before['bp_vdc'],after['bp_vdc']],matching_display_volts=matches)
            report['matrix_attempts'].append(item)
            if matches and item['scan_running']:
                report.update(matrix_runtime_buffer_verified=True,displayed_volts=matches[0],matrix_scan_running=True);break
            time.sleep(.3)
        assert report.get('matrix_runtime_buffer_verified'),'Live framebuffer does not match fresh voltage/V-marker with running scan'
        assert report['samples'][-1]['mc_good']>report['samples'][0]['mc_good'],'No fresh Nucleo reply progress'
        ssh=tunneled(ssh_base)('192.168.1.138',2222,'arduino',install.ROOT/'.unoq_ssh/id_ed25519',install.ROOT/'.unoq_ssh/known_hosts')
        paths=['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py','/home/arduino/.config/mic-ai/vbus_calibration.json']
        hashes=subprocess.run(ssh+['sha256sum '+' '.join(paths)],capture_output=True,text=True,timeout=20)
        (out/'hmi_calibration_hashes.log').write_text(hashes.stdout+hashes.stderr,encoding='utf-8');assert hashes.returncode==0
        actual=[line.split()[0] for line in hashes.stdout.splitlines()]
        m=json.loads((install.C/'manifest.json').read_text())
        assert actual==[install.io.sha(install.C/'web_hmi/server.py'),m['calibration_sha256']]
        installed=json.loads((install.ROOT/'artifacts/live_bench_20261024/uno_bus_display_install_usb_r2/report.json').read_text())
        assert installed['uno_readback_verified'] and installed['uno_flash_commands']==1 and installed['nucleo_flash_commands']==0
        report.update(passed=True,live_pair=list(install.NEW),calibration_unchanged=True,calibration_sha256=actual[1],hmi_files_match=True,
                      uno_at_install_flash_readback_verified=True,final_status=status())
    except Exception as exc:report['error']=str(exc)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('passed','live_pair','displayed_volts','matrix_scan_running','calibration_unchanged','error')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
