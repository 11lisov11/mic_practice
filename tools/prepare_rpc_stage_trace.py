"""Prepare an Uno-only diagnostic image; never access or flash the stand."""
from pathlib import Path
import shutil,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261118/boot_stack_integrity_r1'
OUT=ROOT/'artifacts/live_bench_20261120/rpc_stage_trace_r1'
TRACE=r'''#pragma once
#include <stdint.h>
#if defined(ARDUINO_ARCH_ZEPHYR)
#include <zephyr/kernel.h>
#endif
/* Passive journal, no calls, logs, allocation, reset, UART access or motor gates.
 * Per-slot sequence is committed last under a bounded Uno IRQ lock. Read via
 * SWD with the exact ELF, twice for consistency; it is not an atomic RAM dump.
 */
struct MicRpcTraceEvent {uint32_t sequence,ms,event,a,b,c,d,guard;};
struct MicRpcTrace {uint32_t magic=0x31545052U,version=1,capacity=128,next=0;
 MicRpcTraceEvent rows[128]{};};
inline MicRpcTrace mic_rpc_trace;
inline void mic_rpc_note(uint32_t event,uint32_t a=0,uint32_t b=0,uint32_t c=0,uint32_t d=0){
 const uint32_t now=millis();
#if defined(ARDUINO_ARCH_ZEPHYR)
 const unsigned key=irq_lock();
#endif
 const uint32_t seq=mic_rpc_trace.next+1U;
 MicRpcTraceEvent &r=mic_rpc_trace.rows[(seq-1U)&127U];
 r.sequence=0;r.ms=now;r.event=event;r.a=a;r.b=b;r.c=c;r.d=d;
 r.guard=seq^now^event^a^b^c^d^0x91e6b72dU;
 __atomic_thread_fence(__ATOMIC_RELEASE);r.sequence=seq;mic_rpc_trace.next=seq;
#if defined(ARDUINO_ARCH_ZEPHYR)
 irq_unlock(key);
#endif
}
inline uint32_t mic_rpc_prefix(const uint8_t *p,size_t n){
 uint32_t v=0;for(size_t i=0;i<n&&i<4;++i)v|=(uint32_t)p[i]<<(8U*i);return v;
}
'''

def replace(path,old,new):
    text=path.read_text(encoding='utf-8');assert text.count(old)==1,(path,old[:50]);path.write_text(text.replace(old,new),encoding='utf-8')

def main():
    assert not OUT.exists()
    for folder in ('UNOQ_MOTOR','libraries','web_hmi'):
        shutil.copytree(BASE/folder,OUT/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    src=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino'
    replace(src,'FW_BUILD_ID = 2026111809U','FW_BUILD_ID = 2026112011U')
    hmi=OUT/'web_hmi/server.py'
    hmi.write_text(hmi.read_text(encoding='utf-8').replace('2026111809','2026112011'),encoding='utf-8')
    lib=OUT/'libraries/Arduino_RPClite/src'
    (lib/'mic_rpc_trace.h').write_text(TRACE)
    replace(lib/'mic_rpc_health.h','#include <stdint.h>','#include <stdint.h>\n#include "mic_rpc_trace.h"')
    replace(lib/'decoder.h','            _bytes_stored += bytes_read;', '''            mic_rpc_note(1,bytes_read,_bytes_stored,
                mic_rpc_prefix(_raw_buffer+_bytes_stored,bytes_read),
                bytes_read>4?mic_rpc_prefix(_raw_buffer+_bytes_stored+4,bytes_read-4):0);
            _bytes_stored += bytes_read;''')
    replace(lib/'decoder.h','                if (offset == 0) {','                mic_rpc_note(2,type,bytes_checked,offset,_bytes_stored);\n                if (offset == 0) {')
    replace(lib/'decoder.h','        reset_packet();\n        return consume(packet_size);', '''        mic_rpc_note(3,packet_size,mic_rpc_prefix(buffer,packet_size),
            packet_size>4?mic_rpc_prefix(buffer+4,packet_size-4):0,_packet_type);
        reset_packet();
        return consume(packet_size);''')
    replace(lib/'server.h','        if (!req.unpack_request_headers()) {', '''        mic_rpc_note(4,req.size,mic_rpc_prefix(req.buffer,req.size));
        if (!req.unpack_request_headers()) {
            mic_rpc_note(5,req.size);''')
    replace(lib/'server.h','        req.pack_response_headers();','        mic_rpc_note(6,req.msg_id,req.size,req.type);\n        req.pack_response_headers();')
    replace(lib/'server.h','        dispatcher.call(req.method, req.unpacker, req.packer);', '''        const bool dispatched=dispatcher.call(req.method, req.unpacker, req.packer);
        mic_rpc_note(7,req.msg_id,req.packer.size(),dispatched,req.type);''')
    replace(lib/'server.h','        return decoder->send_response(req.packer);', '''        mic_rpc_note(8,req.msg_id,req.packer.size(),req.type);
        const bool sent=decoder->send_response(req.packer);
        mic_rpc_note(9,req.msg_id,req.packer.size(),sent,req.type);
        return sent;''')
    replace(src,'  const uint32_t timing_started = micros();\n  const unsigned int timing_key = irq_lock();', '  mic_rpc_note(11);\n  const uint32_t timing_started = micros();\n  const unsigned int timing_key = irq_lock();')
    replace(src,'  irq_unlock(timing_done_key);\n  return s;', '  irq_unlock(timing_done_key);\n  mic_rpc_note(12,s.length());\n  return s;')
    hashes={str(f.relative_to(OUT)):hashlib.sha256(f.read_bytes()).hexdigest()
            for folder in ('UNOQ_MOTOR','libraries','web_hmi') for f in (OUT/folder).rglob('*') if f.is_file()}
    (OUT/'source_hashes.json').write_text(json.dumps(hashes,indent=2))
    (OUT/'preparation.json').write_text(json.dumps(dict(Uno=2026112011,Nucleo=2026111810,
        installed=False,diagnostic_only=True,START=0,CLEAR=0,RESET=0,
        native_image_unchanged=True,all_motor_limits_unchanged=True,
        RPC_deadlines_and_scheduling_unchanged=True,old_captures_unchanged=True,
        journal_bytes=4112,events={'1':'transport RX','2':'frame parsed','3':'request popped',
        '4':'unpack begin','5':'unpack failed','6':'headers OK','7':'callback finished',
        '8':'response send begin','9':'response send finished','11':'get entered','12':'get returned'}),indent=2))
    print('Prepared Uno2026112011 trace only. Native1810 unchanged, no hardware IO.')

if __name__=='__main__':main()
