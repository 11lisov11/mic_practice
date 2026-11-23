"""Read the running inverted-mount matrix framebuffer; no reset, writes or flash."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from elftools.elf.elffile import ELFFile
import install_current_peak_capture as wrapper
from verify_unoq_bus_display_runtime import DIGITS


def expected_frame(volts, softstart, mirror_x=False):
    words = [0]*4
    def pixel(x,y):
        index=(7-y)*13+(12-x if mirror_x else x)
        words[index//32] |= 1 << (index%32)
    for pos,digit in enumerate((volts//100,(volts//10)%10,volts%10)):
        if (pos==0 and volts<100) or (pos==1 and volts<10):
            continue
        for y,row in enumerate(DIGITS[digit]):
            for x in range(3):
                if row & (1 << (2-x)):
                    pixel(1+4*pos+x,1+y)
    for x,y in ((0,6),(2,6),(1,7)):
        pixel(x,y)
    if softstart:
        pixel(0,0); pixel(0,1)
    return words


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,required=True)
    parser.add_argument('--display-order-r2',action='store_true',help='Verify UNO-only 2503/2502 and its both-axis matrix mapping')
    args=parser.parse_args(); out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    if args.display_order_r2:
        import install_unoq_display_order_r2 as display_wrapper
        install=display_wrapper.install
    else:
        install=wrapper.install
    report=dict(passed=False,read_only=True,motor_commands=0,reset_commands=0,flash_commands=0,
                physical_led_observation_verified=False)
    try:
        images=install.verify_package()
        image=images[0] if isinstance(images,tuple) else images
        install.io.URL='http://127.0.0.1:18080'
        def status():
            s=install.io.live_status()
            ok,reason=install.precheck(s)
            assert ok,reason
            assert (s['fw_build'],s['mc_fw_build'])==install.NEW
            assert s['matrix_test']==0
            return s
        before=status()
        base=Path.home()/'AppData/Local/Arduino15/packages/arduino'
        core=base/'hardware/zephyr/0.90.0/firmwares/zephyr-arduino_uno_q_stm32u585xx.elf'
        with core.open('rb') as stream:
            elf=ELFFile(stream)
            symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
            assert symbols['framebuffer']==0x20001228 and symbols['i_isr.1']==0x20001714
        cfg=install.ROOT/'tools/read_unoq_matrix.cfg'
        script=cfg.read_text(encoding='utf-8')
        assert 'reset_config none' in script and not re.search(r'^\s*(halt|reset|write_memory|flash|program)\s',script,re.M)
        cmd=[str(base/'tools/remoteocd/0.1.1/remoteocd.exe'),'upload','--adb-path','adb',
             '-s',install.io.UNO_SERIAL,'-f',str(cfg),str(core),str(image)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        log=result.stdout+result.stderr
        (out/'matrix_read.log').write_text(log,encoding='utf-8')
        assert result.returncode==0,'Read-only matrix inspection failed'
        frame=re.search(r'MATRIX_FRAMEBUFFER_BEGIN\s+((?:0x[0-9a-f]+\s+){4})MATRIX_FRAMEBUFFER_END',log,re.I)
        scan=re.search(r'MATRIX_SCAN_BEGIN\s+((?:0x[0-9a-f]+\s+){8})MATRIX_SCAN_END',log,re.I)
        assert frame and scan,'Missing passive memory-read markers'
        actual=[int(w,16) for w in frame[1].split()];actual[3]&=255
        indices=[int(w,16) for w in scan[1].split()]
        after=status()
        candidates={int(s['bp_vdc']+.5) for s in (before,after)}
        matches=[v for v in candidates if actual==expected_frame(v,before['bp_softstart_ready'],args.display_order_r2)]
        assert matches,'Framebuffer differs from the inverted-mount voltage rendering'
        assert all(0<=v<104 for v in indices) and len(set(indices))>1,'Matrix scan not progressing'
        report.update(passed=True,live_pair=list(install.NEW),displayed_volts=matches[0],
            actual_frame=actual,scan_indices=indices,matrix_scan_running=True,
            matrix_orientation_buffer_verified=True,before=before,after=after)
    except Exception as exc:
        report['error']=str(exc)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('passed','displayed_volts','matrix_scan_running','error')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
