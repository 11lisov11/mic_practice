"""Check bounded deferred logs and keep blocking IPC out of the production loop."""
from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile

CPP = r'''
#include "deferred_log.h"
#include <cassert>
#include <cstdio>
int main() {
 DeferredLogQueue q; DeferredLogLine line;
 assert(!q.pop(line));
 for(unsigned i=0;i<16;++i) assert(q.push("LOG TEST",i));
 assert(!q.push("OVERFLOW",17) && q.dropped==1 && q.count==16);
 for(unsigned i=0;i<16;++i) { assert(q.pop(line)); assert(line.timestamp_us==i); }
 assert(!q.pop(line));
 for(unsigned n=0;n<1000;++n) { assert(q.push("WRAP",n)); assert(q.pop(line)); assert(line.timestamp_us==n); }
 char longline[97]; memset(longline,'A',96); longline[96]=0;
 assert(!q.push(longline,0) && q.dropped==2);
 q.dropped=UINT32_MAX; assert(!q.push(longline,0) && q.dropped==UINT32_MAX);
 std::puts("PASS bounded logs, overflow, FIFO order and rollover");
}
'''


def main():
    root=Path(__file__).resolve().parents[1]
    text=(root/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8-sig')
    normal_loop=text[text.rindex('void loop() {'):]
    assert 'bridge_tick();' not in normal_loop
    assert 'Monitor.println' not in normal_loop
    notify=re.search(r'static void bridge_notify_line\(.*?\n\}',text,re.S).group()
    router=notify[notify.index('#if USE_ROUTER_BRIDGE'):notify.index('#elif USE_MSGPACK_RPC')]
    assert 'g_deferred_log.push' in router and 'Monitor' not in router
    assert 'CONFIG_NUM_PREEMPT_PRIORITIES - 1, 0, K_NO_WAIT' in text
    assert 'bridge_service_begin();' in text
    with tempfile.TemporaryDirectory() as folder:
        src,exe=Path(folder)/'logs.cpp',Path(folder)/'logs.exe'
        src.write_text(CPP,encoding='utf-8')
        subprocess.run([shutil.which('g++') or 'g++','-std=c++17','-Wall','-Wextra','-Werror',
                        '-I',str(root/'UNOQ_MOTOR'),str(src),'-o',str(exe)],check=True)
        r=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
    print(json.dumps({'pass':True,'native':r.stdout.strip(),'main_loop_blocking_ipc_removed':True,
                      'scope':'logging architecture, not a hardware scheduler guarantee'}))


if __name__=='__main__':
    main()
