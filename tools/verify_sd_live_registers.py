"""Read SD/PA6/BKIN registers without halt, reset or writes on deenergized USB bench."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import install_sd_live_diagnostics_pair as install
from wifi_stop_tail_probe import parse_registers


def main():
    p=argparse.ArgumentParser(description=__doc__)
    physical=p.add_mutually_exclusive_group(required=True)
    physical.add_argument('--confirm-j1-j4-off-meter-below-20v',action='store_true')
    physical.add_argument('--confirm-j1-off-j4-only-usb',action='store_true',
                          help='J1 remains off; only J4 auxiliary 15 V is on, no mains')
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args()
    install.verify_package()
    out=a.outdir.resolve()
    out.mkdir(parents=True,exist_ok=False)
    report=dict(pass_=False,memory_reads_only=True,motor_commands=0,reset_commands=0,
                clear_commands=0,flash_commands=0,register_writes=0,samples=[],
                j4_only_user_confirmed=a.confirm_j1_off_j4_only_usb)
    try:
        for i in range(3):
            s=install.io.live_status()
            safe,reason=install.precheck(s)
            if not safe or (s['fw_build'],s['mc_fw_build'])!=install.NEW:raise RuntimeError(reason)
            observed=s.get('mc_sd_live',{})
            if not observed.get('available') or not observed.get('config_ok'):raise RuntimeError('no current/configured SD observation')
            cmd=[str(install.io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+install.io.STLINK_SERIAL,
                 '-r32','0x48000000','40','-r32','0x40012c00','104']
            p=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
            (out/('registers_'+str(i)+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
            if p.returncode:raise RuntimeError('register read failed')
            regs=parse_registers(p.stdout)
            g=0x48000000;t=0x40012c00
            d=dict(pa6_high=bool(regs[g+0x10]&64),mode=(regs[g]>>12)&3,
                open_drain=bool(regs[g+4]&64),pull=(regs[g+12]>>12)&3,
                af=(regs[g+32]>>24)&15,gpio_locked=bool(regs[g+28]&64),
                bke=bool(regs[t+0x44]&4096),bkp=bool(regs[t+0x44]&8192),
                bidirectional=bool(regs[t+0x44]&(1<<28)),moe=bool(regs[t+0x44]&32768),
                bie=bool(regs[t+12]&128),bif=bool(regs[t+16]&128),
                bkin_enabled=bool(regs[t+0x60]&1),bkin_inverted=bool(regs[t+0x60]&512))
            okay=(d['mode']==2 and d['open_drain'] and d['pull']==1 and d['af']==6 and
                d['bke'] and d['bkp'] and not d['bidirectional'] and not d['moe'] and
                d['bkin_enabled'] and d['bkin_inverted'])
            report['samples'].append(dict(status=s,registers={hex(k):v for k,v in regs.items()},decoded=d,
                telemetry_level_matches_separate_register_read=(observed['level']==('HIGH' if d['pa6_high'] else 'LOW')),
                config_ok=okay))
            if not okay:raise RuntimeError('unexpected PA6/BKIN configuration')
            if report['samples'][-1]['telemetry_level_matches_separate_register_read'] is not True:
                raise RuntimeError('level changed between separate reads or telemetry mismatch; preserve evidence')
            time.sleep(.25)
        report['pass_']=True
    except Exception as exc:report['error']=str(exc)
    report['pass']=report.pop('pass_')
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(pass_=report['pass'],levels=[x['decoded']['pa6_high'] for x in report['samples']],error=report.get('error'))))
    return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
