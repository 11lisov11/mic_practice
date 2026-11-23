"""Reproduce the scheduling failure envelope with the real 300-ms transport watchdog."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from prepare_unoq_deadline_fix import BASE, ROOT, HMI_BASE, sketch, timing, hmi
from install_unoq_rx_fix import deadline_maintenance_safe
from ipm_break_wifi_selftest import load_module
from web_hmi_command_guard_selftest import safe_status


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args(); out=a.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    old=(BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(); fixed=sketch(old)
    hb=int(re.search(r'NUCLEO_HEARTBEAT_MS = (\d+)',old).group(1))
    assert hb==50 and 'g_nucleo_keepalive_ms) >= 100)' in old
    assert fixed.index('nucleo_send_stop(false);',fixed.index('void loop()'))<fixed.index('  handle_button();',fixed.index('void loop()'))
    # All ADC operations are inside the legacy branch, not the MCSDK branch.
    c=fixed[fixed.index('static void control_step() {'):fixed.index('  if (g_estop_latched)',fixed.index('static void control_step() {'))]
    assert c.index('if (!NUCLEO_MCSDK_ACIM_BACKEND)')<c.index('analogRead(')<c.index('  } else {')
    assert 'analogRead(' not in c[c.index('  } else {'):]
    with tempfile.TemporaryDirectory() as folder:
        d=Path(folder); (d/'link_timing.h').write_text(timing((BASE/'UNOQ_MOTOR/link_timing.h').read_text()))
        server_path=d/'server.py'; server_path.write_text(hmi((HMI_BASE/'web_hmi/server.py').read_text()))
        mod=load_module(server_path)
        # Even a caller-supplied calibration override cannot grant unrestricted ARM.
        s=safe_status(fw_build=2026101105,mc_fw_build=2026101102)
        assert not mod.hv_arm_precheck(s,mod.HvArmConfig(enabled=True),True)[0]
        off=dict(fw_build=2026101104,mc_fw_build=2026101102,state='SAFE',pwm=0,hmi_hv_armed=0,
            estop=0,bp_status=25,vdc=0.,bp_vdc=0.,bp_vbus_raw=0,bp_vbus_valid=1,
            bp_age_ms=10,mc_age_ms=10,bp_vbus_age_ms=10,bp_fault=2,bp_bad_cnt=1,
            bp_transport_fault=7,mc_diag_valid=1,mc_fault_reason=13,mc_last_bad_reason=13,
            bp_bad=0,bp_bad_integrity=0,bp_bad_sequence=0,mc_uart_error_flags=0,
            mc_last_uart_error_flags=0,uno_rx_dropped=0,uno_rx_hw_errors=0,uno_rx_hw_flags=0,
            bp_temp_fault=0,bp_clear_pending=0,precharge=0,pfc=0,brake=0,bp_ext=0)
        assert deadline_maintenance_safe(off)
        assert deadline_maintenance_safe(dict(off,bp_fault=5,bp_bad_cnt=0,bp_transport_fault=0,
            mc_fault_reason=8,mc_last_bad_reason=0,mc_fault_current_mask=4,mc_fault_occurred_mask=4))
        for key,value in dict(pwm=1,hmi_hv_armed=1,vdc=3.,bp_vbus_raw=21,bp_age_ms=300,
            bp_bad=1,uno_rx_dropped=1,uno_rx_hw_errors=1,fw_build=0,precharge=1).items():
            assert not deadline_maintenance_safe({**off,key:value}),key
        unit=d/'test.cpp'; exe=d/'test.exe'
        unit.write_text(r'''#include <cassert>
#include <cstdio>
#include "uart_v3_transport.h"
#include "link_timing.h"
void packet(uv3_rx &rx, uint32_t t, unsigned seq, bool clear=false) {
 uint8_t f[UV3_FRAME]{}; f[0]=0xaa; f[1]=0x55; f[2]=3; f[3]=clear?8:0; f[5]=seq;
 uv3_seal(f); uv3_result result=UV3_WAIT;
 for(unsigned i=0;i<UV3_FRAME;++i) result=uv3_byte(&rx,f[i],0,t+i/12);
 assert(result==UV3_READY); uv3_commit(&rx,t+4,false,false,clear);
}
int main() {
 unsigned old_timeouts=0,fixed_ok=0;
 for(unsigned phase=0;phase<100;++phase) {
  uv3_rx old{}, fixed{}; uv3_init(&old,true); uv3_init(&fixed,true);
  packet(old,0,0,true); packet(fixed,0,0,true);
  const unsigned blocked=233, end=phase+blocked;
  if(uv3_tick(&old,end)==UV3_LINK_TIMEOUT) ++old_timeouts;
  if(phase>=50) packet(fixed,phase,1);
  if(uv3_tick(&fixed,end)==UV3_WAIT) ++fixed_ok;
 }
 assert(old_timeouts>0 && fixed_ok==100);
 uv3_rx r{}; uv3_init(&r,true); packet(r,0,0,true);
 assert(uv3_tick(&r,305)==UV3_LINK_TIMEOUT); // Real loss is NOT waived.
 uv3_init(&r,true); uint8_t f[UV3_FRAME]{}; f[0]=0xaa; f[1]=0x55; f[2]=3;
 uv3_seal(f); f[8]^=1; uv3_result rc=UV3_WAIT;
 for(unsigned i=0;i<UV3_FRAME;++i) rc=uv3_byte(&r,f[i],0,0);
 assert(rc==UV3_BAD_CRC);
 LinkTiming t; t.tx(10000,0,43,false); t.tx(343000,0,43,false);
 assert(t.tx_all_max_gap_us==333000 && t.tx_last_gap_us==333000 && t.tx_gaps_over_watchdog==1);
 assert(t.tx_active_max_gap_us==0); // Previous active-only counter misses the same stall.
 t.tx(393000,0,43,false); assert(t.tx_last_gap_us==50000 && t.tx_gaps_over_watchdog==1);
 std::printf("{\"baseline_timeout_phases\":%u,\"fixed_ok_phases\":%u}",old_timeouts,fixed_ok);
}
''')
        compiler=shutil.which('g++')
        if not compiler: raise RuntimeError('Host g++ required')
        subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(d),'-I',str(BASE/'UNOQ_MOTOR'),
                        str(unit),'-o',str(exe)],check=True)
        proc=subprocess.run([str(exe)],capture_output=True,text=True)
        if proc.returncode: raise RuntimeError('Scheduling/watchdog negative control failed: '+proc.stderr)
        result=json.loads(proc.stdout)
    result.update(pass_=True,observed_service_gap_ms=233,watchdog_ms=300,hardware_commands=0,
        scope='Deterministic observed-delay envelope, not an exclusive diagnosis of the live event')
    result['pass']=result.pop('pass_'); (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__': main()
