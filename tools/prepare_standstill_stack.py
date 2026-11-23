"""Preserve timing candidate; fix the measured RPC callback stack deficit."""
import os,shutil,json
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261029/standstill_timing_r1'
OUT=ROOT/'artifacts/live_bench_20261029/standstill_stack_r1'
NEW=(2026102935,2026102936)
def main():
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  assert not (OUT/folder).exists()
  def copy(src,dest):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dest);return dest
   return shutil.copy2(src,dest)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Src','nucleo/Inc','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026102933','2026102935').replace('2026102934','2026102936')
    if n!=s:write(f,n)
 write(OUT/'nucleo/Inc/identify_core.h',read(ROOT/'tools/motor_commissioning/identify_fast_core.h'))
 f=OUT/'libraries/Arduino_RouterBridge/src/bridge.h';s=read(f)
 s=once(s,'#define UPDATE_THREAD_STACK_SIZE    500','#define UPDATE_THREAD_STACK_SIZE    4096')
 s=once(s,'    bool getRouterVersion(MsgPack::str_t& version) {',r'''
    uint32_t micStackFree() const {
#if defined(CONFIG_INIT_STACKS) && defined(CONFIG_THREAD_STACK_INFO)
        if(!upd_tid)return UINT32_MAX;
        const volatile uint8_t* p=(const volatile uint8_t*)upd_thread_data.stack_info.start;
        size_t available=upd_thread_data.stack_info.size,n=0;
        while(n<available&&p[n]==0xAAU)++n;
        return (uint32_t)n;
#else
        return UINT32_MAX;
#endif
    }
    uint32_t micStackBudget() const {return UPDATE_THREAD_STACK_SIZE;}
    bool getRouterVersion(MsgPack::str_t& version) {''')
 write(f,s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 anchor='    s += " rpc_unknown_methods=";s += String((unsigned long)mic_rpc_health.unknown_methods);'
 s=once(s,anchor,anchor+'\n    s += " rpc_stack_budget=";s += String((unsigned long)Bridge.micStackBudget());\n    s += " rpc_stack_free=";s += String((unsigned long)Bridge.micStackFree());')
 write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 anchor='                "rpc_unknown_methods": int(kv.get("rpc_unknown_methods","0")),'
 s=once(s,anchor,anchor+'\n                "rpc_stack_budget": int(kv.get("rpc_stack_budget","0")),\n                "rpc_stack_free": int(kv.get("rpc_stack_free","4294967295")),')
 s=s.replace('(2026102931,2026102932), (2026102935,2026102936)',
   '(2026102931,2026102932), (2026102933,2026102934), (2026102935,2026102936)')
 write(f,s)
 f=OUT/'web_hmi/static/index.html';write(f,read(f).replace('2933-timing','2935-stack'))
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.standstill_stack.v1',pair=list(NEW),base_pair=[2026102933,2026102934],
  built=False,installed=False,physical_qualification=False,thresholds_changed=False,adc_guard_changed=False,
  start_commands=0,rpc_updater_stack_bytes=4096),indent=2))
 print('2935/2936 prepared; only native identity and RPC stack/reporting differ from timing candidate')
if __name__=='__main__':main()
