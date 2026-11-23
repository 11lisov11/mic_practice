#pragma once
#include <stdint.h>
// Diagnostics only; these counters never authorize motor commands.
struct MicRpcHealth {uint32_t response_timeouts=0,send_timeouts=0,late_responses=0,unknown_methods=0;};
inline MicRpcHealth mic_rpc_health;
inline void mic_rpc_inc(uint32_t *p){__atomic_fetch_add(p,1U,__ATOMIC_RELAXED);}
enum { MIC_RPC_RESPONSE_MS=1500, MIC_RPC_SEND_MS=2000 };
