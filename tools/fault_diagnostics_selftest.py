"""Offline packet/API/log checks for the production first-fault extension."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from web_hmi_command_guard_selftest import load_server_module


CPP = r'''
#include "nucleo_fault_diagnostics.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
int main() {
 unsigned cases=0; uint8_t f[32]={}; f[11]=0x8c;
 assert(!decode_nucleo_fault_diagnostics(f,true,2026100601).valid);
 assert(!decode_nucleo_fault_diagnostics(f,false,2026100701).valid);
 assert(!decode_nucleo_fault_diagnostics(nullptr,true,2026100701).valid);
 cases+=3;
 for (unsigned marker=0; marker<256; ++marker) {
  f[11]=marker; auto d=decode_nucleo_fault_diagnostics(f,true,2026100701);
  assert(d.valid == ((marker&0xf0)==0x80 && (marker&15)<=13)); ++cases;
 }
 f[11]=0x8c; f[12]=10; f[13]=6; f[22]=3; f[30]=255;
 for (unsigned mask=0; mask<65536; ++mask) {
  f[15]=mask; f[16]=mask>>8; f[27]=~mask; f[28]=(~mask)>>8;
  auto d=decode_nucleo_fault_diagnostics(f,true,2026100701);
  assert(d.valid && d.reason==12 && d.uart_errors==10 && d.motor_state==6);
  assert(d.current_faults==mask && d.occurred_faults==(uint16_t)~mask);
  assert(d.sequence==255 && d.tx_status==3); ++cases;
 }
 f[11]=0x9c; f[22]=0xc3; f[13]=6|(2<<5);
 for (unsigned first=0; first<16; ++first) for(unsigned last=0; last<16; ++last) {
  f[12]=first|(last<<4);
  auto d=decode_nucleo_fault_diagnostics(f,true,2026100702);
  assert(d.valid && d.last_bad_valid && d.reason==12 && d.last_bad_reason==12);
  assert(d.uart_errors==first && d.last_uart_errors==last);
  assert(d.motor_state==6 && d.tx_status==3 && d.last_tx_status==2); ++cases;
 }
 f[11]=0x9e; f[22]=0xe0;
 assert(!decode_nucleo_fault_diagnostics(f,true,2026100702).valid);
 auto overflow=decode_nucleo_fault_diagnostics(f,true,2026100703);
 assert(overflow.valid && overflow.reason==14 && overflow.last_bad_reason==14); cases+=2;
 auto startup=decode_nucleo_fault_diagnostics(f,true,2026100705);
 assert(startup.valid && startup.last_bad_valid && startup.reason==14); ++cases;
 assert(!decode_nucleo_fault_diagnostics(f,true,2026100706).valid); ++cases;
 auto break_fix=decode_nucleo_fault_diagnostics(f,true,2026100707);
 assert(break_fix.valid && break_fix.last_bad_valid && break_fix.reason==14); ++cases;
 for (unsigned marker=0; marker<256; ++marker) {
  f[11]=marker; auto d=decode_nucleo_fault_diagnostics(f,true,2026100708);
  assert(d.valid == ((marker&0xf0)==0x90 && (marker&15)<=14)); ++cases;
 }
 for (uint32_t build : {2026100710U,2026100801U,2026100899U}) {
  for (unsigned marker=0;marker<256;++marker) {
   f[11]=marker; auto d=decode_nucleo_fault_diagnostics(f,true,build);
   assert(d.valid==((marker&0xf0)==0x90 && (marker&15)<=14)); ++cases;
  }
 }
 f[11]=0x98;
 assert(!decode_nucleo_fault_diagnostics(f,true,2026100803U).valid); ++cases;
 std::printf("{\"pass\":true,\"decoder_cases\":%u}\n",cases);
}
'''


def main():
    root = Path(__file__).resolve().parents[1]
    mod = load_server_module(root)
    line = ('DATA freq=0 speed=0 ia=0 ib=0 ic=0 vdc=0 state=SAFE mode=VF pwm=0 '
            'bp_fault=5 mc_diag_valid=1 mc_fault_reason=12 mc_uart_error_flags=10 '
            'mc_fault_motor_state=6 mc_fault_current_mask=64 mc_fault_occurred_mask=1088 '
            'mc_fault_sequence=255 mc_fault_tx_status=3')
    d = mod.RpcBridge._parse_status_string(line)
    assert d is not None and d['mc_fault_reason'] == 12 and d['mc_uart_error_flags'] == 10
    assert 'FE|ORE' in d['mc_fault_detail'] and 'MC_OVER_CURR' in d['mc_fault_detail']
    assert 'MC_DP_FAULT' in d['mc_fault_detail'] and 'TX_status=3' in d['mc_fault_detail']
    legacy = mod.RpcBridge._parse_status_string('DATA freq=0 speed=0 ia=0 ib=0 ic=0 vdc=0 state=SAFE mode=VF pwm=0 bp_fault=5')
    assert legacy['mc_diag_valid'] == 0 and 'unavailable' in legacy['mc_fault_detail']
    header = (root/'mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV/Inc/mc_type.h').read_text()
    for bit, name in mod.MCSDK_FAULT_BITS.items():
        found = re.search(r'#define\s+'+name+r'\s+\(\(uint16_t\)(0x[0-9a-fA-F]+)\)', header)
        assert found and int(found[1],16) == bit, name
    class Logs:
        def __init__(self): self.rows=[]
        def add(self, line): self.rows.append(line)
    class Rpc: pass
    logs = Logs()
    app = mod.AppState(Rpc(), logs, status_log_interval=60.0)
    app.maybe_log_status(d)
    app.maybe_log_status(d)
    assert sum('MC_FAULT_DIAG' in row for row in logs.rows) == 1
    app.maybe_log_status(dict(d,bp_fault=1,mc_fault=1))
    assert sum('MC_FAULT_DIAG' in row for row in logs.rows) == 1, 'ESTOP must not replace first cause'
    app.maybe_log_status(dict(d,bp_fault=0,mc_fault=0,mc_fault_reason=0,bp_fault_reason=0))
    app.maybe_log_status(d)
    assert sum('MC_FAULT_DIAG' in row for row in logs.rows) == 2, 'new fault after CLEAR must be logged'
    app.maybe_log_status(dict(d,mc_bad_cnt=1,bp_bad_cnt=1,mc_last_bad_valid=1,mc_last_bad_reason=12,mc_last_uart_error_flags=8))
    assert sum('MC_FAULT_DIAG' in row for row in logs.rows) == 3, 'each observed counter increase must be logged'
    values = [0] * 87
    values[75:79] = [3,1,1,2026100701]
    values[79:87] = [1,12,10,6,64,1088,255,3]
    bridge = mod.RpcBridge.__new__(mod.RpcBridge)
    bridge._call = lambda *args, **kwargs: [1,0,None,values]
    ok, parsed, error = bridge.get()
    assert ok and error is None and parsed['mc_fault_reason']==12
    assert parsed['mc_fault_occurred_mask']==1088 and 'FE|ORE' in parsed['mc_fault_detail']
    values.extend([1,12,8,2])
    ok, parsed, error=bridge.get()
    assert ok and parsed['mc_last_bad_reason']==12 and parsed['mc_last_tx_status']==2
    assert 'last_bad=UART_RX_ERROR' in parsed['mc_fault_detail']
    with tempfile.TemporaryDirectory() as tmp:
        unit=Path(tmp)/'decoder.cpp'; exe=Path(tmp)/'decoder.exe'
        unit.write_text(CPP,encoding='utf-8')
        subprocess.run([shutil.which('g++') or 'g++','-std=c++17','-Wall','-Wextra','-Werror',
                        '-I',str(root/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],check=True)
        # A freshly linked executable can briefly remain locked by Windows scanning.
        # Retry the same unchanged file; persistent access denial is still a failure.
        for attempt in range(20):
            try:
                result=json.loads(subprocess.check_output([str(exe)],text=True))
                result['execution_permission_retries']=attempt
                break
            except PermissionError as exc:
                if getattr(exc,'winerror',None) not in (5,32) or attempt==19:
                    raise
                time.sleep(.25)
    print(json.dumps({**result,'api_roundtrip':True,'legacy_explicit_unknown':True,
                      'fault_masks_match_mc_type_header':True,'event_not_throttled_or_overwritten':True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
