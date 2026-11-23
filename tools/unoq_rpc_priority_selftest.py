"""Check control/RPC isolation and run the real watchdog during simulated bulk replies."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from prepare_unoq_rpc_priority_fix import ROOT, BASE, sketch, sensor, hmi
from ipm_break_wifi_selftest import load_module
from web_hmi_command_guard_selftest import safe_status


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args(); out=a.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    old=(BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(); new=sketch(old)
    assert new.index('#define __loopHook mic_router_compat_hook')<new.index('#include <Arduino.h>')
    assert 'void __loopHook() {\n  if (!NUCLEO_MCSDK_ACIM_BACKEND) mic_router_compat_hook();' in new
    assert 'k_thread_priority_set(k_current_get(), 4)' in new
    assert 'owner.release();\n#endif\n#if defined(ARDUINO_ARCH_ZEPHYR)\n  if (NUCLEO_MCSDK_ACIM_BACKEND) k_msleep(1)' in new
    assert new.count('void loop()')==old.count('void loop()')
    assert 'UPDATE_THREAD_PRIORITY == 5' in new
    assert '4, 0, K_NO_WAIT);' in sensor((BASE/'UNOQ_MOTOR/as5600_teacher.cpp').read_text())
    with tempfile.TemporaryDirectory() as folder:
        d=Path(folder); path=d/'server.py'; path.write_text(hmi((BASE/'web_hmi/server.py').read_text()))
        mod=load_module(path)
        assert not mod.hv_arm_precheck(safe_status(fw_build=2026101106,mc_fw_build=2026101102),
            mod.HvArmConfig(enabled=True),True)[0]
        unit=d/'test.cpp'; exe=d/'test.exe'
        unit.write_text(r'''#include <cassert>
#include <cstdio>
#include "uart_v3_transport.h"
uv3_result feed(uv3_rx &r, unsigned t, unsigned seq) {
 uint8_t f[UV3_FRAME]{}; f[0]=0xaa; f[1]=0x55; f[2]=3; f[3]=1; f[4]=3; f[5]=seq;
 f[6]=0x88; f[7]=0x13; uv3_seal(f); uv3_result result=UV3_WAIT;
 for(unsigned i=0;i<UV3_FRAME;++i) result=uv3_byte(&r,f[i],0,t+i/12);
 if(result==UV3_READY) uv3_commit(&r,t+4,true,false,false);
 return result;
}
int main() {
 unsigned failed_old=0,passed_new=0,max_gap=0;
 for(unsigned start=100;start<200;++start) {
  uv3_rx old{},fixed{}; uv3_init(&old,true); uv3_init(&fixed,true);
  assert(feed(old,0,0)==UV3_READY && feed(fixed,0,0)==UV3_READY);
  unsigned old_send=0,new_send=0,old_seq=1,new_seq=1;
  bool old_failed=false;
  for(unsigned t=5;t<1000;++t) {
   // Two 240-ms replies occupy priority 5; old priority 14 cannot run.
   bool bulk=t>=start && t<start+480;
   if(!old_failed && !bulk && t-old_send>=50) {
    if(feed(old,t,old_seq++)!=UV3_READY) old_failed=true;
    old_send=t;
   }
   if(!old_failed && uv3_tick(&old,t)!=UV3_WAIT) old_failed=true;
   // Priority 4 control wakes every ms. Formatting may hold ownership for 4 ms.
   bool formatting=(t>=start && t<start+4)||(t>=start+240 && t<start+244);
   if(!formatting && t-new_send>=50) {
    assert(feed(fixed,t,new_seq++)==UV3_READY);
    if(t-new_send>max_gap) max_gap=t-new_send;
    new_send=t;
   }
   assert(uv3_tick(&fixed,t+4)==UV3_WAIT);
  }
  failed_old+=old_failed; ++passed_new;
  assert(uv3_tick(&fixed,new_send+305)==UV3_LINK_TIMEOUT); // Actual control freeze still trips.
 }
 assert(failed_old==100 && passed_new==100 && max_gap<=54);
 uv3_rx r{}; uv3_init(&r,true); assert(feed(r,0,0)==UV3_READY);
 assert(feed(r,50,0)==UV3_BAD_SEQUENCE); // No autonomous replay keeps a frozen controller alive.
 std::printf("{\"old_bulk_timeouts\":%u,\"new_bulk_pass\":%u,\"model_max_gap_ms\":%u}",failed_old,passed_new,max_gap);
}
''')
        compiler=shutil.which('g++')
        if not compiler: raise RuntimeError('g++ required')
        subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(BASE/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],capture_output=True,text=True)
        if run.returncode: raise RuntimeError('Bulk-reply priority model failed: '+run.stderr)
        result=json.loads(run.stdout)
    result.update(pass_=True,hardware_commands=0,watchdog_ms=300,
        scope='Source wiring plus real transport under a synthetic scheduler, not a measured bench result')
    result['pass']=result.pop('pass_'); (out/'report.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))


if __name__=='__main__': main()
