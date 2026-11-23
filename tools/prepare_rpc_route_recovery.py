"""Prepare Uno-only RPC route renewal; no MCU/reset/motor commands."""
import json, shutil
import prepare_clear_recovery as base

ROOT=base.ROOT
BASE=base.OUT
OUT=ROOT/'artifacts/live_bench_20261116/rpc_route_recovery_r1'
NEW=(2026111607,2026111606)
read,write,once,sha=base.read,base.write,base.once,base.sha

def main():
    assert not OUT.exists(), 'Preserve previous candidates and captures'
    source=json.loads(read(BASE/'source_hashes.json'))
    for rel,h in source.items(): assert sha(BASE/rel)==h,rel
    for name in ('UNOQ_MOTOR','libraries','web_hmi'):
        shutil.copytree(BASE/name,OUT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.log'))
    f=OUT/'libraries/Arduino_RPClite/src/server.h';s=read(f)
    s=once(s,'    bool hasTag(','''    bool isBound(const MsgPack::str_t& name) const { return dispatcher.isBound(name); }

    bool hasTag(''');write(f,s)
    f=OUT/'libraries/Arduino_RouterBridge/src/bridge.h';s=read(f)
    # Re-register a previously bound callback, without reset, rebinding, or allocating a wrapper.
    # Preserve provide() duplicate rejection, avoiding a broad change to vendor semantics.
    s=once(s,'    template<typename F>\n    bool provide_safe(','''    uint8_t refreshProvided(const MsgPack::str_t& name) {
        k_mutex_lock(&bridge_mutex, K_FOREVER);
        bool result = false;
        uint8_t status=0;
        if(started && server && server->isBound(name)) {
            auto registration=call(BIND_METHOD,name);
            if(registration.result(result) && result) status=1;
            // Router0.5.3 rejects duplicates, including the same owner.
            // EXISTS is distinct from a confirmed new registration.
            else if(registration.getErrorCode()==5 &&
                registration.getErrorMessage()==MsgPack::str_t("route already exists: ")+name) status=2;
        }
        k_mutex_unlock(&bridge_mutex);
        return status;
    }

    template<typename F>
    bool provide_safe(''');write(f,s)
    # Pure policy shared with the host test; it cannot send commands or alter protection.
    write(OUT/'UNOQ_MOTOR/rpc_route_policy.h','''#pragma once
#include <stdint.h>
struct RpcRoutePolicy {
  uint32_t last_attempt=0,attempts=0,failures=0,last_reply=0,renewed=0;
  bool due(uint32_t now,bool local_pwm,bool outputs,bool remote_pwm,bool ready) {
    if(local_pwm||outputs||remote_pwm||!ready||(uint32_t)(now-last_attempt)<5000U)return false;
    last_attempt=now;__atomic_fetch_add(&attempts,1U,__ATOMIC_RELAXED);return true;
  }
  void finish(uint32_t now,uint8_t cmd,uint8_t get){
    if(!cmd||!get)__atomic_fetch_add(&failures,1U,__ATOMIC_RELAXED);
    else __atomic_store_n(&last_reply,now,__ATOMIC_RELAXED);
    if(cmd==1||get==1)__atomic_fetch_add(&renewed,1U,__ATOMIC_RELAXED);
  }
};
''')
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=s.replace('2026111605',str(NEW[0]))
    s=once(s,'#include "scoped_control_lock.h"','#include "scoped_control_lock.h"\n#include "rpc_route_policy.h"\nstatic RpcRoutePolicy g_rpc_routes;')
    s=once(s,'    s += " rpc_unknown_methods=";', '''    s += " rpc_route_attempts=";s+=String((unsigned long)__atomic_load_n(&g_rpc_routes.attempts,__ATOMIC_RELAXED));
    s += " rpc_route_failures=";s+=String((unsigned long)__atomic_load_n(&g_rpc_routes.failures,__ATOMIC_RELAXED));
    s += " rpc_route_reply_ms=";s+=String((unsigned long)__atomic_load_n(&g_rpc_routes.last_reply,__ATOMIC_RELAXED));
    s += " rpc_route_renewed=";s+=String((unsigned long)__atomic_load_n(&g_rpc_routes.renewed,__ATOMIC_RELAXED));
    s += " rpc_unknown_methods=";''')
    s=once(s,'  if (!g_bridge_announced && g_bridge_cmd_ready && g_bridge_get_ready && g_monitor_ready) {', '''  // A router reconnect may forget routes while the local callbacks still exist.
  // Renew routes only OFF, retaining dispatcher instances, buffers and motor evidence.
  if(g_rpc_routes.due(now,g_pwm_enabled,g_pwm_outputs_active,
      (g_bp_status & BP_STATUS_PWM_ACTIVE)!=0U,g_bridge_cmd_ready&&g_bridge_get_ready)) {
    const uint8_t cmd_result=Bridge.refreshProvided("cmd");
    const uint8_t get_result=Bridge.refreshProvided("get");
    g_rpc_routes.finish(millis(),cmd_result,get_result);
  }
  if (!g_bridge_announced && g_bridge_cmd_ready && g_bridge_get_ready && g_monitor_ready) {''')
    write(f,s)
    f=OUT/'web_hmi/server.py';s=read(f)
    # Candidate HMI targets this exact pair. Never rewrite tuple expressions
    # into comma expressions: equality checks are also protection gates.
    s=s.replace('2026111605','2026111607')
    s=once(s,'                "rpc_unknown_methods":', '''                "rpc_route_attempts": int(kv.get("rpc_route_attempts","0")),
                "rpc_route_failures": int(kv.get("rpc_route_failures","0")),
                "rpc_route_reply_ms": int(kv.get("rpc_route_reply_ms","0")),
                "rpc_route_renewed": int(kv.get("rpc_route_renewed","0")),
                "rpc_unknown_methods":''');write(f,s)
    history={}
    for f in BASE.rglob('*'):
        if f.is_file() and not any(x in f.parts for x in ('Debug','__pycache__')):
            history[f.relative_to(ROOT).as_posix()]=sha(f)
    write(OUT/'preserved_hashes.json',json.dumps(history,indent=2)+'\n')
    manifest=dict(pair=list(NEW),base_pair=[2026111605,2026111606],uno_only=True,
        nucleo_image_unchanged=True,built=False,installed=False,START=0,CLEAR=0,RESET=0,
        thresholds_changed=False,controller_equations_changed=False,original_RPC_outage_cause_proven=False,
        observed_route_loss_recovery_fixed_in_source=True,route_refresh_period_ms=5000,
        note='Restores lost registrations only OFF. No MCU reset, no snapshot erasure, no automatic motor retry.')
    write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))

if __name__=='__main__':main()
