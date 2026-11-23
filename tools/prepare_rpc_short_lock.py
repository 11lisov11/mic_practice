"""Uno-only1609: release route mutex before waiting for registration ACK."""
import json,shutil
import prepare_rpc_route_recovery as previous
ROOT=previous.ROOT;BASE=previous.OUT;OUT=ROOT/'artifacts/live_bench_20261116/rpc_short_lock_r1'
NEW=(2026111609,2026111606)
read,write,once,sha=previous.read,previous.write,previous.once,previous.sha

def main():
    assert not OUT.exists()
    for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
    for name in ('UNOQ_MOTOR','libraries','web_hmi'):
        shutil.copytree(BASE/name,OUT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    f=OUT/'libraries/Arduino_RouterBridge/src/bridge.h';s=read(f)
    s=once(s,'''        uint8_t status=0;
        if(started && server && server->isBound(name)) {''','''        const bool eligible=started && server && server->isBound(name);
        k_mutex_unlock(&bridge_mutex);
        // Existing handlers and client/server live for the whole sketch lifetime.
        // Outgoing calls retain their own lease; do not block the updater's
        // is_started() while waiting for ACK or timeout on the full-duplex link.
        uint8_t status=0;
        if(eligible) {''')
    s=once(s,'''        k_mutex_unlock(&bridge_mutex);
        return status;''','''        return status;''');write(f,s)
    for rel in ('UNOQ_MOTOR/UNOQ_MOTOR.ino','web_hmi/server.py'):
        f=OUT/rel;write(f,read(f).replace('2026111607','2026111609'))
    history=json.loads(read(BASE/'preserved_all_hashes.json'))
    for folder in ('idle_timeout_diagnosis_r1','idle_qualification_r2','install_r1','FOC_preparation_r1'):
        for f in (BASE/folder).rglob('*'):
            if f.is_file():history[f.relative_to(ROOT).as_posix()]=sha(f)
    write(OUT/'preserved_all_hashes.json',json.dumps(history,indent=2)+'\n')
    m=json.loads(read(BASE/'manifest.json'))
    for key in ('artifacts','acceptance_sha256','installation_scope','latest_idle_outage'):m.pop(key,None)
    m.update(pair=list(NEW),base_pair=[2026111607,2026111606],built=False,installed=False,
        host_tests_passed=False,OFF_route_reconnect_verified=False,current_RPC_usable=False,
        original_RPC_outage_cause_proven=False,route_wait_blocks_updater_fixed_in_source=True,
        qualification='Uninstalled candidate. Fixes captured updater starvation; initiating serial/decoder failure not yet identified.',
        thresholds_changed=False,controller_equations_changed=False,START=0,CLEAR=0,RESET=0)
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(prepared=True,pair=NEW,preserved_files=len(history))))
if __name__=='__main__':main()
