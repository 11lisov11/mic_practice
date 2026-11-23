"""Finish this deenergized install with one Nucleo reset after saved boot timeout.

No firmware writes, START, ARM or CLEAR. Requires the exact expected isolated
programming watchdog latch; never resets through an unexplained hardware fault.
"""
import argparse
import json
from pathlib import Path
import time
import install_bkin_fast_capture_pair as install

def ready_low_bus(s):
    ok,_=install.precheck(s)
    if not ok or (s.get('fw_build'),s.get('mc_fw_build'))!=install.NEW:return False
    if any(s.get(k)!=0 for k in ('mc_transport_fault','bp_transport_fault',
        'mc_uart_error_flags','bp_uart_error_flags')):return False
    if s.get('mc_fault')==0 and s.get('bp_fault')==0:
        return s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0
    # With J1 off, MCSDK's low-bus fault is expected. Retain it; never issue
    # CLEAR just to make a deenergized installation report look fault-free.
    return (s.get('mc_fault')==5 and s.get('bp_fault')==5 and s.get('mc_fault_reason')==8
        and s.get('mc_fault_current_mask') in (0,4) and s.get('mc_fault_occurred_mask')==4)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-j1-j4-off-meter-below-20v',action='store_true')
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--verify-only',action='store_true',help='verify after an already logged reset; no further reset')
    args=p.parse_args()
    if not args.confirm_j1_j4_off_meter_below_20v:p.error('physical off confirmation required')
    install.verify_package()
    out=args.outdir.resolve()
    installed=json.loads((out/'report.json').read_text(encoding='utf-8'))
    if not (installed['pass'] and installed['mcu_flash_commands']==2 and installed['calibration_unchanged']):
        raise RuntimeError('verified installation required')
    r={'pass':False,'reset_commands':0,'motor_commands':0,'clear_commands':0,'flash_commands':0,'samples':[]}
    try:
        before=install.io.live_status();r['before']=before
        ok,reason=install.precheck(before)
        if not ok or (before.get('fw_build'),before.get('mc_fw_build'))!=install.NEW:
            raise RuntimeError(reason)
        if not args.verify_only and not (before['mc_fault']==2 and before['bp_fault']==2 and before['mc_fault_reason']==13
            and before['mc_transport_fault']==7 and before['bp_transport_fault']==7
            and before['mc_fault_current_mask']==0 and before['mc_fault_occurred_mask']==0
            and before['mc_uart_error_flags']==0 and before['mc_last_uart_error_flags']==0
            and before['mc_break_wave_hex']=='-'
            and all(not x.get('captured') for x in before['mc_break_snapshots'])):
            raise RuntimeError('not the isolated programming timeout; preserve current evidence')
        if not args.verify_only:
            (out/'pre_finish_reset_status.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
            command=[str(install.io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG',
                'sn='+install.io.STLINK_SERIAL,'-rst']
            install.io.run(command,'finish_nucleo_reset_only',out,r,20);r['reset_commands']=1
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            s=install.io.live_status();r['samples'].append(s)
            if ready_low_bus(s):
                if len(r['samples'])>=6:r['pass']=True;break
            time.sleep(.25)
        if not r['pass']:raise RuntimeError('clean reply verification timed out')
        r['calibration_after']=install.io.calibration_hash(out,r)
        if r['calibration_after']!=installed['calibration_before']:raise RuntimeError('calibration hash mismatch')
    except Exception as exc:r['pass']=False;r['error']=str(exc)
    name='finish_after_reset_verification.json' if args.verify_only else 'finish_install_verification.json'
    (out/name).write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('pass','reset_commands','motor_commands','clear_commands','error')}))
    return 0 if r['pass'] else 1

if __name__=='__main__':raise SystemExit(main())
