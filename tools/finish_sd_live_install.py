"""Finish only an archived programming watchdog timeout; never reset through SD fault."""
import argparse
import json
from pathlib import Path
import time
import install_sd_live_diagnostics_pair as install


def isolated_timeout(s,trace):
    okay,_=install.precheck(s)
    sd=s.get('mc_sd_live',{})
    records=trace.get('records',[])
    fatal=records[-1] if len(records)==2 else {}
    low_bus=(s.get('mc_fault_reason')==8 and s.get('mc_fault_current_mask') in (0,4)
             and s.get('mc_fault_occurred_mask')==4)
    no_bus_fault=(s.get('mc_fault_reason')==13 and s.get('mc_fault_current_mask')==0
                  and s.get('mc_fault_occurred_mask')==0)
    return bool(okay and (s.get('fw_build'),s.get('mc_fw_build'))==install.NEW
        and s.get('mc_fault')==2 and s.get('bp_fault')==2
        and s.get('mc_transport_fault')==7 and s.get('bp_transport_fault')==7
        and s.get('mc_last_bad_reason')==13 and (low_bus or no_bus_fault)
        and s.get('mc_uart_error_flags')==0 and s.get('mc_last_uart_error_flags')==0
        and s.get('mc_break_wave_hex')=='-'
        and len(s.get('mc_break_snapshots',[]))==2
        and all(x.get('available') and not x.get('captured') for x in s['mc_break_snapshots'])
        and sd.get('available') and sd.get('level')=='HIGH' and sd.get('config_ok')
        and sd.get('break_irq_enabled') and sd.get('capture_running') and not sd.get('first_record_ready')
        and trace.get('available') and fatal.get('reason_code')==7
        and fatal.get('uart_flags')==0 and fatal.get('length')==0
        and fatal.get('tick_ms',0)-fatal.get('last_valid_ms',0)==301)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    physical=p.add_mutually_exclusive_group(required=True)
    physical.add_argument('--confirm-j1-j4-off-meter-below-20v',action='store_true')
    physical.add_argument('--confirm-j1-off-usb-bus-below-20v',action='store_true',
                          help='J4 auxiliary may remain on; J1 off, USB and bus below20V')
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();install.verify_package();out=a.outdir.resolve()
    installed=json.loads((out/'report.json').read_text(encoding='utf-8'))
    if not (installed['pass'] and installed['mcu_flash_commands']==2 and installed['calibration_unchanged']):
        raise RuntimeError('verified installation required')
    archive=json.loads((out/'boot_read/read_only_report.json').read_text(encoding='utf-8'))
    saved=json.loads((out/'boot_read/uart_reject_trace.json').read_text(encoding='utf-8'))['data']
    if not archive['pass'] or not isolated_timeout(archive['samples'][-1],saved):
        raise RuntimeError('archived isolated programming timeout required')
    # Negative controls for this off-bench completion predicate.
    sample=archive['samples'][-1]
    for key,value in [('pwm',1),('vdc',21),('mc_fault_current_mask',0x404),
        ('mc_fault_occurred_mask',0x404),('mc_transport_fault',2),('mc_last_bad_reason',1)]:
        assert not isolated_timeout(dict(sample,**{key:value}),saved),key
    assert not isolated_timeout(dict(sample,mc_sd_live=dict(sample['mc_sd_live'],level='LOW')),saved)
    assert not isolated_timeout(sample,dict(saved,records=[{},dict(saved['records'][-1],reason_code=2)]))
    r=dict(pass_=False,reset_commands=0,motor_commands=0,clear_commands=0,flash_commands=0,samples=[])
    try:
        before=install.io.live_status();r['before']=before
        if not isolated_timeout(before,saved):raise RuntimeError('current state differs from archived programming-only timeout')
        (out/'pre_finish_reset_status.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
        install.io.run([str(install.io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG',
            'sn='+install.io.STLINK_SERIAL,'-rst'],'finish_nucleo_reset_only',out,r,20)
        r['reset_commands']=1
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            s=install.io.live_status();r['samples'].append(s)
            sd=s.get('mc_sd_live',{})
            okay,reason=install.precheck(s)
            ready=(okay and (s['fw_build'],s['mc_fw_build'])==install.NEW and
                all(s.get(k)==0 for k in ('mc_transport_fault','bp_transport_fault','mc_bad','mc_bad_integrity','mc_bad_sequence','uno_rx_dropped')) and
                s.get('mc_fault_occurred_mask') in (0,4) and s.get('mc_fault_current_mask') in (0,4) and
                sd.get('available') and sd.get('level')=='HIGH' and sd.get('config_ok') and sd.get('capture_running') and
                not sd.get('first_record_ready') and s.get('mc_uart_reject_hex')=='-' and s.get('mc_break_wave_hex')=='-')
            if ready and len(r['samples'])>=7:
                r['pass_']=True;break
            time.sleep(.35)
        if not r['pass_']:raise RuntimeError('post-reset verification incomplete; preserve current evidence')
        r['calibration_after']=install.io.calibration_hash(out,r)
        if r['calibration_after']!=installed['calibration_before']:raise RuntimeError('calibration mismatch')
    except Exception as exc:r['pass_']=False;r['error']=str(exc)
    r['pass']=r.pop('pass_')
    (out/'finish_install_verification.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('pass','reset_commands','motor_commands','clear_commands','error')}))
    return 0 if r['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
