"""One persistent current-only research pair. No run, flash or qualification claims."""
import ast,json,os,shutil
from pathlib import Path
import prepare_current_only as old
ROOT=old.ROOT;BASE=old.OUT;OUT=ROOT/'artifacts/live_bench_20261029/research_suite_r1'
OLD=old.NEW;NEW=(2026102911,2026102912)
read,write,sha,once=old.read,old.write,old.sha,old.once

def main():
    from install_current_only import verify_package
    verify_package();assert not OUT.exists()
    for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        def copy(src,dst):
            rel=Path(src).relative_to(BASE/folder)
            if folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for folder in ('nucleo/Src','nucleo/Inc','UNOQ_MOTOR'):
        for f in (OUT/folder).rglob('*'):
            if not f.is_file():continue
            a=read(f);b=a.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
            if a!=b:write(f,b)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        write(OUT/folder/'research_wire.h',read(ROOT/'tools/research_suite/research_wire.h'))
    f=OUT/'nucleo/Src/main.c';s=read(f)
    s=once(s,'#include "current_shunt.h"','#include "current_shunt.h"\n#include "research_wire.h"')
    sender='''static void mic_send_research_page(uint32_t now_ms) {
  static uint32_t last_ms;
  if((uint32_t)(now_ms-last_ms)<1000U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];xp_packet(packet,MIC_NUCLEO_FW_BUILD_ID);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last_ms=now_ms;
}

'''
    s=once(s,'static void mic_send_current_page(uint32_t now_ms) {',sender+'static void mic_send_current_page(uint32_t now_ms) {')
    s=once(s,'mic_send_peak_page(now_ms); }','mic_send_peak_page(now_ms);mic_send_research_page(now_ms); }')
    write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=once(s,'#include "timed_run.h"','#include "timed_run.h"\n#include "research_wire.h"\nstatic xp_receiver g_research_caps={};')
    anchor='      if(buf[2]==WC_WIRE){'
    s=once(s,anchor,'''      if(buf[2]==XP_WIRE){
        const uint32_t now=millis();
        const bool fresh=g_bp_mcsdk_telemetry&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)xp_receive(&g_research_caps,buf,g_bp_fw_build,fresh,now);continue;
      }
'''+anchor)
    s=once(s,'    s += " enc_source=disabled";', '''    s += " enc_source=disabled";
    const bool native_fresh=g_bp_mcsdk_telemetry&&(uint32_t)(millis()-g_bp_last_rsp_ms)<300U;
    s += " research_native_valid=";s += String(xp_fresh(&g_research_caps,native_fresh,millis())?1:0);
    s += " research_native_caps=";s += String((unsigned)g_research_caps.caps);
    s += " research_native_good=";s += String((unsigned long)g_research_caps.good);
    s += " research_native_bad=";s += String((unsigned long)g_research_caps.bad);''')
    # Invalidate capability evidence across peer epochs, like current/zero caches.
    s=once(s,'    g_manual_reference_valid=false;','    g_manual_reference_valid=false;\n    g_research_caps.seen=false;') if s.count('    g_manual_reference_valid=false;')==1 else s
    write(f,s)
    f=OUT/'web_hmi/server.py';s=read(f)
    for pair in ('(2026102901,2026102902)','(2026102901, 2026102902)'):
        s=s.replace(pair,pair+', (2026102911,2026102912)')
    # The exact current-only profile condition is not a compatibility list.
    s=s.replace("!= (2026102901, 2026102902), (2026102911,2026102912):", "not in ((2026102901,2026102902),(2026102911,2026102912)):")
    tree=ast.parse(s);lines=s.splitlines(keepends=True);offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line.encode()))
    raw=s.encode();edits=[]
    for n in ast.walk(tree):
        if not isinstance(n,ast.Tuple) or not all(isinstance(x,ast.Constant) and type(x.value)is int for x in n.elts):continue
        v=tuple(x.value for x in n.elts)
        if len(v)<=2 or OLD[1] not in v or NEW[1] in v:continue
        a=offsets[n.lineno-1]+n.col_offset;b=offsets[n.end_lineno-1]+n.end_col_offset
        edits.append((a,b,raw[a:b][:-1].rstrip().rstrip(b',')+b','+str(NEW[1]).encode()+b')'))
    for a,b,t in sorted(edits,reverse=True):raw=raw[:a]+t+raw[b:]
    s=raw.decode()
    s=once(s,'def with_current_only_profile(data):',read(ROOT/'tools/research_suite/catalog.py')+'\n\ndef with_current_only_profile(data):')
    s=once(s,'    return with_current_only_profile(data)','    return with_research_suite(with_current_only_profile(data))')
    s=once(s,'                "enc_source": kv.get("enc_source", "motor_controller_uart"),',
      ''.join('                "'+k+'": int(kv.get("'+k+'","0")),\n' for k in ('research_native_valid','research_native_caps','research_native_good','research_native_bad'))+'                "enc_source": kv.get("enc_source", "motor_controller_uart"),')
    ast.parse(s);write(f,s)
    f=OUT/'web_hmi/static/app.js';write(f,read(f)+'\n'+read(ROOT/'tools/research_suite/panel.js'))
    f=OUT/'web_hmi/static/index.html';s=read(f)
    s=once(s,'    <section class="panel logs">','    <section class="panel" id="researchPanel"><h2>Исследовательская серия</h2><div id="researchAlgorithms">Ожидание подтверждения Nucleo</div></section>\n    <section class="panel logs">');write(f,s)
    from research_suite.simplify_ui import simplify
    simplify(OUT/'web_hmi')
    from research_suite.enable_ui_sessions import enable
    enable(OUT/'web_hmi')
    write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.research_suite.v1',pair_compatibility_ids=list(NEW),base_pair=list(OLD),
       built=False,installed=False,selftest_pass=False,readback_verified=False,calibration_changed=False,
       thresholds_changed=False,uart_changed=False,motor_control_changed=False,adc_sampling_changed=False,
       as5600_enabled=False,ai_control_enabled=False,actuating_algorithms=['VF_FIXED'],
       requested_other_algorithms_implemented=False),indent=2))
    write(OUT/'archive_references.json',json.dumps({str((BASE/'manifest.json').relative_to(ROOT)):sha(BASE/'manifest.json')},indent=2))
    print(OUT)

if __name__=='__main__':main()
