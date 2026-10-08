"""Test diagnostic gap accounting and unchanged UART/guard wiring, no hardware."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from web_hmi_command_guard_selftest import load_server_module

CPP = r'''
#include "link_timing.h"
#include <cassert>
#include <cstdio>
int main() {
 LinkTiming t;
 t.loop(0,false); t.loop(1000000,false); assert(t.loop_active_max_us==0);
 t.loop(1000100,true); t.loop(1400101,false); assert(t.loop_active_max_us==400001);
 t.loop(3400101,false); assert(t.loop_active_max_us==400001);
 t.tx(1,10,32,false); t.tx(1000001,100,32,false); assert(t.tx_active_max_gap_us==0);
 t.tx(1050001,200,32,true); t.tx(1400002,150,31,false);
 assert(t.tx_active_max_gap_us==350001 && t.tx_call_max_us==200 && t.tx_short_writes==1);
 t.tx(9000002,10,32,false); assert(t.tx_active_max_gap_us==350001 && t.tx_count==5);
 t.rx(0,false); t.rx(50000,true); t.rx(451001,false);
 assert(t.rx_active_max_gap_us==401001 && t.rx_count==3);
 t.rpc(10); t.rpc(500); t.rpc(20); assert(t.rpc_max_us==500);
 LinkTiming wrap; wrap.loop(UINT32_MAX-50,true); wrap.loop(49,true);
 assert(wrap.loop_active_max_us==100);
 wrap.tx(UINT32_MAX-50,5,32,true); wrap.tx(49,8,32,true);
 assert(wrap.tx_active_max_gap_us==100);
 wrap.rx(UINT32_MAX-50,true); wrap.rx(49,true); assert(wrap.rx_active_max_gap_us==100);
 wrap.tx_count=UINT32_MAX; wrap.tx_short_writes=UINT32_MAX; wrap.tx(100,0,0,true);
 assert(wrap.tx_count==UINT32_MAX && wrap.tx_short_writes==UINT32_MAX);
 std::puts("PASS diagnostic counters and rollover");
}
'''


def main():
    root = Path(__file__).resolve().parents[1]
    module = load_server_module(root)
    line = "DATA state=SAFE mode=VF pwm=0 freq=0 speed=0 ia=0 ib=0 ic=0 vdc=0 bp_fault=5"
    old = module.RpcBridge._parse_status_string(line)
    assert old['uno_tx_count'] is None
    new = module.RpcBridge._parse_status_string(line + " uno_tx_count=42 uno_tx_active_max_gap_us=350001")
    assert new['uno_tx_count'] == 42 and new['uno_tx_active_max_gap_us'] == 350001
    assert module.RpcBridge._parse_status_string(line + " uno_tx_count=garbage") is None
    with tempfile.TemporaryDirectory() as tmp:
        source, exe = Path(tmp) / 'timing.cpp', Path(tmp) / 'timing.exe'
        source.write_text(CPP, encoding='utf-8')
        subprocess.run([shutil.which('g++') or 'g++','-std=c++17','-Wall','-Wextra','-Werror',
                        '-I',str(root/'UNOQ_MOTOR'),str(source),'-o',str(exe)],check=True)
        result = subprocess.run([str(exe)],check=True,capture_output=True,text=True)
    sketch = (root/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8-sig')
    assert 'NUCLEO_UART_BAUD = 115200;' in sketch and 'NUCLEO_SCALAR_MIN_SEND_US = 50000;' in sketch
    assert 'g_link_timing.tx(timing_tx_end' in sketch
    assert sketch.count('g_link_timing.loop(micros(), g_pwm_enabled);') == 1
    assert 'irq_unlock(timing_loop_key);\n  handle_button();' in sketch
    print(json.dumps({'pass':True,'native':result.stdout.strip(),'hmi_legacy_missing_explicit':True,
                      'scope':'diagnostic bookkeeping only; not wire timing or fault-cause proof'}))


if __name__=='__main__':
    main()
