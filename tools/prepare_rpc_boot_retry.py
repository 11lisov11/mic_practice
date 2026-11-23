"""Complete bounded RPC with reusable startup retries, no automatic MCU reset."""
import json
import shutil
from pathlib import Path
import prepare_rpc_coldboot_fix as base
ROOT,LIB,util=base.ROOT,base.LIB,base.util
BASE=base.OUT
OUT=ROOT/'artifacts/live_bench_20261026/rpc_boot_retry_r1'
OLD=(2026102607,2026102604);NEW=(2026102609,2026102604)
def main():
    assert not (OUT/'manifest.json').exists()
    m=json.loads(util.read(BASE/'manifest.json'))
    assert m['built'] and m['selftest_pass']
    assert json.loads(util.read(BASE/'install_r1/report.json'))['uno_readback_verified']
    for name in ('UNOQ_MOTOR','web_hmi','libraries'):
        shutil.copytree(BASE/name,OUT/name,ignore=shutil.ignore_patterns('__pycache__'))
    f=OUT/'libraries/Arduino_RouterBridge/src/bridge.h';s=util.read(f)
    s=util.once(s,'    bool started = false;','    bool started = false;\n    bool transport_initialized = false;')
    a=s.index('        k_mutex_init(&read_mutex);',s.index('bool begin('))
    b=s.index('        bool res = false;',a)
    setup=s[a:b]
    setup=util.once(setup,'        if (is_started()) return true;\n\n        k_mutex_lock(&bridge_mutex, K_FOREVER);\n\n','')
    s=s[:a]+'        if(!transport_initialized){\n'+setup+'            transport_initialized=true;\n        }\n        if(is_started())return true;\n        k_mutex_lock(&bridge_mutex,K_FOREVER);\n\n'+s[b:]
    s=util.once(s,'        notify(SET_BUF_METHOD, BRIDGE_RPC_BUFFER_SIZE);','        if(started)notify(SET_BUF_METHOD, BRIDGE_RPC_BUFFER_SIZE);')
    util.write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=util.read(f)
    s=util.once(s,'FW_BUILD_ID = 2026102607U;','FW_BUILD_ID = 2026102609U;')
    s=util.once(s,'''    // This function already refuses active local or peer PWM. A failed begin
    // still owns a running updater thread: do not recreate it in-place.
    if (NUCLEO_MCSDK_ACIM_BACKEND) { NVIC_SystemReset(); return; }''',
'''    // The local Bridge override reuses its transport and updater. Retry only
    // here, where local and remote PWM are already required to be OFF.''')
    s=util.once(s,'    if (!Bridge.begin(RPC_BAUD) && NUCLEO_MCSDK_ACIM_BACKEND) NVIC_SystemReset();',
        '    (void)Bridge.begin(RPC_BAUD); // Bounded failure; idle bridge_tick retries without resetting control.')
    util.write(f,s)
    f=OUT/'web_hmi/server.py';s=util.read(f)
    for a,b in [('(2026102607, 2026102604)','(2026102609, 2026102604)'),('(2026102607,2026102604)','(2026102609,2026102604)')]:s=s.replace(a,a+','+b)
    util.write(f,s)
    for folder in ('build/uno','verification','diagnosis'):(OUT/folder).mkdir(parents=True)
    m={k:v for k,v in m.items() if k not in ('source_sha256','build_sha256','verification_sha256')}
    m.update(pair_compatibility_ids=list(NEW),predecessor=str(BASE),built=False,selftest_pass=False,installed=False,
        rpc_startup_retry_changed=True,automatic_mcu_reset_on_rpc_begin_failure=False,
        transport_objects_reused_on_retry=True,observed_coldboot_root_cause_proven=False)
    util.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(prepared=True,pair=NEW)))
if __name__=='__main__':main()
