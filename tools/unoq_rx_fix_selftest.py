"""Exercise actual RX storage and generated IRQ ownership; never accesses hardware."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from prepare_unoq_rx_fix import ASSETS, BASE, ROOT, sketch, hmi
from install_unoq_rx_fix import maintenance_safe


def main():
    compiler = shutil.which('g++') or shutil.which('clang++')
    if not compiler:
        raise RuntimeError('Host C++ compiler required')
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)
        source = path/'test.cpp'
        source.write_text('''#include "bounded_rx.h"
#include <assert.h>
int main() {
 BoundedRx<64> old;
 BoundedRx<1024> fixed;
 for (int i=0;i<86;++i) { old.put(i); fixed.put(i); }
 assert(old.count==64 && old.dropped==22);
 assert(fixed.count==86 && fixed.dropped==0 && fixed.high_water==86);
 for (int i=0;i<86;++i) assert(fixed.read()==i);
 assert(fixed.read()==-1);
 for (int round=0;round<10000;++round) {
   for (int i=0;i<86;++i) assert(fixed.put(i));
   for (int i=0;i<86;++i) { assert(fixed.read(false)==i); assert(fixed.read()==i); }
 }
 assert(!fixed.dropped);
 for (int i=0;i<1024;++i) assert(fixed.put(i%256));
 assert(!fixed.put(42) && fixed.dropped==1 && fixed.count==1024);
 fixed.dropped=UINT32_MAX; assert(!fixed.put(42) && fixed.dropped==UINT32_MAX);
 for (int i=0;i<1024;++i) assert(fixed.read()==i%256);
}
''')
        exe=path/'test.exe'
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(ASSETS), str(source), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    old=(BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8-sig')
    new=sketch(old)
    rpc=new[new.index('static String rpc_get() {'):new.index('static void serial_poll() {')]
    # No heap allocation or formatting within the final IRQ mask.
    tail=rpc[rpc.index('const unsigned int timing_done_key = irq_lock();'):]
    assert 's +=' not in tail and tail.index('irq_unlock') < tail.index('return s;')
    assert 's.reserve(4096);' in rpc
    assert new[new.index('static void nucleo_uart_poll() {'):new.index('static void nucleo_spi_init() {')].count('uv3_crc_ok(buf)') == 3
    assert 'if (!integrity_ok)' in new and 'g_nucleo_rx_bad_integrity++' in new
    assert '#define NUCLEO_SERIAL g_nucleo_serial' in new
    assert 'FW_BUILD_ID = 2026101104U' in new
    hmi_text=hmi((BASE/'web_hmi/server.py').read_text(encoding='utf-8-sig'))
    compile(hmi_text, 'candidate_hmi', 'exec')
    assert 'uno_rx_rejected_hex' in hmi_text
    assert 'mc_break_snapshots' in hmi_text
    safe=dict(fw_build=2026101103,mc_fw_build=2026101102,state='SAFE',pwm=0,
        hmi_hv_armed=0,estop=0,bp_status=0,vdc=0.,bp_vdc=0.,mc_age_ms=10,
        bp_vbus_age_ms=10,bp_vbus_valid=1,bp_vbus_raw=0,bp_bad_cnt=0,
        bp_transport_fault=0,bp_bad_sequence=0,bp_bad=643,bp_bad_integrity=643,
        bp_fault=5,mc_diag_valid=1,mc_fault_reason=8,mc_fault_current_mask=4,
        mc_fault_occurred_mask=4,bp_clear_pending=0,precharge=0,pfc=0,brake=0,bp_ext=0)
    assert maintenance_safe(safe)
    for key,value in dict(pwm=1,hmi_hv_armed=1,estop=1,bp_status=0x20,vdc=322.,
            bp_vdc=322.,mc_age_ms=300,bp_vbus_age_ms=300,bp_vbus_valid=0,
            bp_vbus_raw=21,bp_bad_cnt=1,bp_transport_fault=1,bp_bad_sequence=1,
            bp_clear_pending=1,precharge=1,pfc=1,brake=1,bp_ext=1,fw_build=0).items():
        assert not maintenance_safe({**safe,key:value}), key
    assert not maintenance_safe({**safe,'vdc':float('nan')})
    for key in safe: assert not maintenance_safe({k:v for k,v in safe.items() if k!=key}),key
    print(json.dumps(dict(pass_=True, queue_cycles=10000, baseline_86_byte_burst_drops=22,
                         fixed_86_byte_burst_drops=0, irq_formatting_removed=True,
                         crc_checks_retained=True, hardware_commands=0)))


if __name__=='__main__': main()
