#pragma once
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
