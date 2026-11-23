"""Prepare local bounded RouterBridge/RPClite overrides; no hardware access."""
import json
import shutil
from pathlib import Path
import prepare_i2c_first_fault as util

ROOT=util.ROOT
BASE=ROOT/'artifacts/live_bench_20261026/i2c_first_fault_r1'
OUT=ROOT/'artifacts/live_bench_20261026/rpc_coldboot_fix_r1'
LIB=Path.home()/'Documents/Arduino/libraries'
OLD=(2026102605,2026102604);NEW=(2026102607,2026102604)

def main():
    assert not (OUT/'manifest.json').exists(),'Preserve prepared candidate'
    m=json.loads(util.read(BASE/'manifest.json'));assert m['installed'] and m['built']
    for rel,digest in m['source_sha256'].items():assert util.sha(BASE/rel)==digest,rel
    for name in ('UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/name,OUT/name,ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    originals={}
    for name in ('Arduino_RouterBridge','Arduino_RPClite'):
        shutil.copytree(LIB/name,OUT/'libraries'/name,dirs_exist_ok=True)
        originals.update({str(f.relative_to(LIB)).replace('\\','/'):util.sha(f) for f in (LIB/name).rglob('*') if f.is_file()})
    rpc=OUT/'libraries/Arduino_RPClite/src';bridge=OUT/'libraries/Arduino_RouterBridge/src'
    util.write(rpc/'mic_rpc_health.h','''#pragma once
#include <stdint.h>
// Diagnostics only; these counters never authorize motor commands.
struct MicRpcHealth {uint32_t response_timeouts=0,send_timeouts=0,late_responses=0,unknown_methods=0;};
inline MicRpcHealth mic_rpc_health;
inline void mic_rpc_inc(uint32_t *p){__atomic_fetch_add(p,1U,__ATOMIC_RELAXED);}
enum { MIC_RPC_RESPONSE_MS=1500, MIC_RPC_SEND_MS=2000 };
''')
    f=rpc/'Arduino_RPClite.h';s=util.read(f);s=util.once(s,'#define DECODER_BUFFER_SIZE', '#include "mic_rpc_health.h"\n\n#define DECODER_BUFFER_SIZE');util.write(f,s)
    f=rpc/'SerialTransport.h';s=util.read(f)
    s=util.once(s,'            _stream->write(data, size);\n            return size;', '''            // Bridge serializes writers; never ask the core to block for
            // more bytes than its TX ring can accept immediately.
            const int room=_stream->availableForWrite();
            if(room<=0)return 0;
            const size_t n=size<(size_t)room?size:(size_t)room;
            return _stream->write(data,n);''');util.write(f,s)
    f=rpc/'decoder.h';s=util.read(f)
    s=util.once(s,'        if (send(reinterpret_cast<const uint8_t*>(packer.data()), packer.size()) == packer.size()){\n            _msg_id++;',
        '        // Reserve every attempted ID, including a partially sent call.\n        _msg_id++;\n        if (send(reinterpret_cast<const uint8_t*>(packer.data()), packer.size()) == packer.size()){')
    s=util.once(s,'bool get_response(const uint32_t msg_id, RType& result, RpcError& error) {',
        'bool get_response(const uint32_t msg_id, RType& result, RpcError& error, bool discard_late=false) {')
    s=util.once(s,'        if (resp_id != msg_id) return false;', '''        if (resp_id != msg_id) {
            if(discard_late){
                // Only the serialized Bridge call path opts in. Generic
                // RPClite clients retain their existing concurrent semantics.
                const bool head=_response_offset==0;
                consume(_response_size,_response_offset);
                if(head)reset_packet();
                mic_rpc_inc(&mic_rpc_health.late_responses);
            }
            return false;
        }''')
    s=util.once(s,'        size_t offset = 0;\n\n        while (offset < size) {',
        '        size_t offset = 0;\n        const uint32_t began=millis();\n\n        while (offset < size) {\n            if((uint32_t)(millis()-began)>=MIC_RPC_SEND_MS){mic_rpc_inc(&mic_rpc_health.send_timeouts);break;}')
    s=util.once(s,'            offset += bytes_written;', '            if(bytes_written>size-offset)break;\n            offset += bytes_written;\n            if(!bytes_written)delay(1);')
    util.write(f,s)
    f=rpc/'client.h';s=util.read(f)
    s=util.once(s,'bool get_response(const uint32_t wait_id, RType& result, RpcError& error) {',
        'bool get_response(const uint32_t wait_id, RType& result, RpcError& error, bool discard_late=false) {')
    s=util.once(s,'decoder->get_response(wait_id, result, error)', 'decoder->get_response(wait_id, result, error, discard_late)');util.write(f,s)
    f=rpc/'server.h';s=util.read(f)
    s=util.once(s,'        if (method == "" || !dispatcher.hasTag(method, tag)) return false;', '''        if(method=="")return false;
        if(dispatcher.isBound(method)&&!dispatcher.hasTag(method,tag))return false;
        // Unknown calls must be consumed and answered with the existing
        // FUNCTION_NOT_FOUND path. A known wrong-tag call stays queued.
        if(!dispatcher.isBound(method))mic_rpc_inc(&mic_rpc_health.unknown_methods);''');util.write(f,s)
    f=bridge/'bridge.h';s=util.read(f)
    s=util.once(s,'template<typename... Args>\nclass RpcCall {','''struct MicRpcLease {
    struct k_mutex *mutex;bool locked;
    explicit MicRpcLease(struct k_mutex*p):mutex(p),locked(k_mutex_lock(p,K_MSEC(MIC_RPC_RESPONSE_MS))==0){}
    ~MicRpcLease(){if(locked)k_mutex_unlock(mutex);}
};

template<typename... Args>
class RpcCall {''')
    s=util.once(s,'struct k_mutex* wm, Args&&... args):','struct k_mutex* wm, struct k_mutex* om, Args&&... args):')
    s=util.once(s,'write_mutex(wm), callback_params(', 'write_mutex(wm), outgoing_mutex(om), callback_params(')
    s=util.once(s,'                std::apply([this](const auto&... elems) {\n                    client->send_rpc(method, msg_id_wait, elems...);\n                }, callback_params);\n                k_mutex_unlock(write_mutex);',
        '                const bool sent=std::apply([this](const auto&... elems) {\n                    return client->send_rpc(method, msg_id_wait, elems...);\n                }, callback_params);\n                k_mutex_unlock(write_mutex);\n                if(!sent){setError(GENERIC_ERR,"RPC send failed");return false;}')
    s=util.once(s,'        while (true) {\n            if (k_mutex_lock(write_mutex, K_MSEC(10)) == 0) {', '''        const uint32_t admission=millis();
        MicRpcLease lease(outgoing_mutex);
        if(!lease.locked){mic_rpc_inc(&mic_rpc_health.response_timeouts);setError(GENERIC_ERR,"RPC admission timeout");return false;}
        while (true) {
            if((uint32_t)(millis()-admission)>=MIC_RPC_RESPONSE_MS){mic_rpc_inc(&mic_rpc_health.response_timeouts);setError(GENERIC_ERR,"RPC write mutex timeout");return false;}
            if (k_mutex_lock(write_mutex, K_MSEC(10)) == 0) {''')
    s=util.once(s,'        while(true) {\n            if (k_mutex_lock(read_mutex, K_MSEC(10)) == 0 ) {', '''        const uint32_t response_started=millis();
        while(true) {
            if((uint32_t)(millis()-response_started)>=MIC_RPC_RESPONSE_MS){
                mic_rpc_inc(&mic_rpc_health.response_timeouts);
                setError(GENERIC_ERR,"RPC response timeout");return false;
            }
            if (k_mutex_lock(read_mutex, K_MSEC(10)) == 0 ) {''')
    s=util.once(s,'client->get_response(msg_id_wait, result, temp_err)', 'client->get_response(msg_id_wait, result, temp_err, true)')
    s=util.once(s,'    struct k_mutex call_mutex{};', '    struct k_mutex call_mutex{};\n    struct k_mutex* outgoing_mutex;')
    s=util.once(s,'    struct k_mutex bridge_mutex{};', '    struct k_mutex bridge_mutex{};\n    struct k_mutex outgoing_mutex{};')
    s=util.once(s,'        k_mutex_init(&bridge_mutex);', '        k_mutex_init(&bridge_mutex);\n        k_mutex_init(&outgoing_mutex);')
    s=util.once(s,'client, &read_mutex, &write_mutex, std::forward<Args>(args)...', 'client, &read_mutex, &write_mutex, &outgoing_mutex, std::forward<Args>(args)...')
    util.write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=util.read(f)
    s=util.once(s,'FW_BUILD_ID = 2026102605U;', 'FW_BUILD_ID = 2026102607U;')
    s=util.once(s,'    s += " enc_source=nucleo_g431_i2c1";', '''    s += " rpc_response_timeouts=";s += String((unsigned long)mic_rpc_health.response_timeouts);
    s += " rpc_send_timeouts=";s += String((unsigned long)mic_rpc_health.send_timeouts);
    s += " rpc_late_responses=";s += String((unsigned long)mic_rpc_health.late_responses);
    s += " rpc_unknown_methods=";s += String((unsigned long)mic_rpc_health.unknown_methods);
    s += " enc_source=nucleo_g431_i2c1";''');util.write(f,s)
    f=OUT/'web_hmi/server.py';s=util.read(f)
    for a,b in [('(2026102605, 2026102604)','(2026102607, 2026102604)'),('(2026102605,2026102604)','(2026102607,2026102604)')]:s=s.replace(a,a+','+b)
    s=util.once(s,'                "enc_source":', '''                "rpc_response_timeouts": int(kv.get("rpc_response_timeouts","0")),
                "rpc_send_timeouts": int(kv.get("rpc_send_timeouts","0")),
                "rpc_late_responses": int(kv.get("rpc_late_responses","0")),
                "rpc_unknown_methods": int(kv.get("rpc_unknown_methods","0")),
                "enc_source":''');util.write(f,s)
    for folder in ('build/uno','verification'):(OUT/folder).mkdir(parents=True,exist_ok=True)
    metadata=dict(schema='mic_ai.rpc_coldboot_fix.v1',pair_compatibility_ids=list(NEW),predecessor=str(BASE),
        built=False,selftest_pass=False,installed=False,uno_only=True,nucleo_firmware_unchanged=True,
        motor_control_changed=False,thresholds_changed=False,watchdogs_changed=False,calibration_changed=False,
        uart_command_protocol_changed=False,i2c_capture_changed=False,library_overrides_local_only=True,
        vendor_original_sha256=originals,response_timeout_ms=1500,send_no_progress_timeout_ms=2000,
        observed_coldboot_root_cause_proven=False,
        scope='Bound lost RPC responses and TX no-progress; serialize outgoing Bridge calls; discard only stale replies on serialized path; consume unknown methods without losing known safe-tag calls')
    util.write(OUT/'manifest.json',json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(dict(prepared=True,pair=NEW)))

if __name__=='__main__':main()
