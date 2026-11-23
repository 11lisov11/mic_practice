"""Verify the actual patched transport, receiver and immutable motor code offline."""
from pathlib import Path
import json,hashlib,subprocess,importlib.util,sys,shutil,re
ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'artifacts/live_bench_20261018/uart_resync_fix_r1'
BASE=ROOT/'artifacts/live_bench_20261018/bkin_fast_capture_r1'
T=ROOT/'tools/uart_resync_fix'
def read(p):return p.read_text(encoding='utf-8-sig')
def main():
    work=C/'selftest';results=[]
    def check(v,name):
        results.append(dict(name=name,pass_=bool(v)))
        if not v:raise AssertionError(name)
    def run(cmd,label,cwd=work):
        p=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True)
        (work/(label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        if p.returncode:raise RuntimeError(label+': '+(p.stderr or p.stdout)[-3000:])
        return p.stdout
    flags=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror']
    probes=[]
    for label,folder in [('old',BASE),('fixed',C)]:
        exe=work/(label+'_probe.exe')
        run(flags+['-I',str(folder/'nucleo/Inc'),str(ROOT/'tools/uart_resync_probe.cpp'),'-o',str(exe)],label+'_probe_compile')
        probes.append(json.loads(run([str(exe)],label+'_probe_run').splitlines()[0]))
    check(probes[0]['unexpected_latches_after_two_damaged_frames']==16,'old implementation reproduces 16 false latches in 83968 cases')
    check(probes[1]['unexpected_latches_after_two_damaged_frames']==0,'same sweep fixed without changing discard budget')
    executable=work/'contract.exe'
    run(flags+['-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR'),str(T/'contract_test.cpp'),'-o',str(executable)],'contract_compile')
    contract=json.loads(run([str(executable)],'contract_run'))
    check(contract['pass'],'CRC/watchdog/replay/hard-error/diagnostic contract')
    header=read(C/'nucleo/Inc/uart_v3_transport.h');mutations=[]
    for name,a,b in (
        ('old_double_count','if (rx->speculative_prefix==rx->index) {','if (false) {'),
        ('CRC_removed','if (!uv3_crc_ok(rx->frame))','if (false)'),
        ('budget_raised','UV3_NE_BUDGET = 2,','UV3_NE_BUDGET = 3,'),
        ('watchdog_extended','UV3_WATCHDOG_MS = 300,','UV3_WATCHDOG_MS = 900,'),
        ('discard_refreshes_watchdog','rx->last_drop_reason = reason;','rx->last_drop_reason = reason;rx->last_valid_ms=now_ms;'),
        ('replay_guard_removed','advance == 0 || advance > (uint8_t)(rx->recoverable_losses + 1U)','advance == 255')):
        assert header.count(a)==1,name
        folder=work/name;folder.mkdir(exist_ok=True)
        (folder/'uart_v3_transport.h').write_text(header.replace(a,b),encoding='utf-8')
        # Quote-includes search their own header's directory before -I.
        shutil.copyfile(C/'UNOQ_MOTOR/uart_reject_wire.h',folder/'uart_reject_wire.h')
        shutil.copyfile(C/'UNOQ_MOTOR/uart_reject_record.h',folder/'uart_reject_record.h')
        shutil.copyfile(C/'UNOQ_MOTOR/break_wire.h',folder/'break_wire.h')
        cpp=folder/'contract.cpp';shutil.copyfile(T/'contract_test.cpp',cpp)
        binary=folder/'contract.exe'
        run(flags+['-I',str(folder),'-I',str(C/'UNOQ_MOTOR'),str(cpp),'-o',str(binary)],name+'_compile')
        p=subprocess.run([str(binary)],cwd=folder,capture_output=True,text=True)
        (folder/'run.log').write_text(p.stdout+p.stderr,encoding='utf-8')
        detected=p.returncode!=0 and 'FAIL ' in p.stderr
        check(detected,'negative control detected '+name);mutations.append(dict(name=name,detected=detected))
    # Actual BKIN firmware + Uno D2 receiver remain executable with the new pair.
    sim=work/'bkin_sim.exe'
    run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
        '-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR'),'-I',str(ROOT/'tools/bkin_fast_capture'),
        str(ROOT/'tools/bkin_fast_capture/sim.c'),'-o',str(sim)],'bkin_compile')
    bkin=json.loads(run([str(sim)],'bkin_run'));check(bkin['host_cases']==450 and bkin['pass'],'450 BKIN recorder/receiver scenarios preserved')
    spec=importlib.util.spec_from_file_location('uart_resync_hmi',C/'web_hmi/server.py')
    hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
    raw=(work/'fatal.bin').read_bytes()
    decoded=hmi.uart_reject_status(dict(mc_fw_build=2026101806,mc_uart_reject_hex=raw.hex()))
    check(decoded['available'] and decoded['records'][1]['length']==43 and decoded['records'][1]['full_frame_crc_matches'] is False,'HMI independently verifies raw fatal frame CRC')
    parsed=hmi.RpcBridge._parse_status_string('state=SAFE mode=VF pwm=0 fw_build=2026101807 mc_fw_build=2026101806 mc_uart_reject_hex='+raw.hex()+' mc_uart_reject_good_pages=14 mc_uart_reject_bad_pages=0')
    check(parsed['mc_uart_reject_hex']==raw.hex() and parsed['mc_uart_reject_good_pages']==14,'real RPC text parser preserves the complete raw rejection')
    (work/'decoded_fatal.json').write_text(json.dumps(decoded,indent=2)+'\n',encoding='utf-8')
    for offset in (0,4,8,12,16,20,28,40,180,184,188,192,200,204,220,224,228,319):
        bad=bytearray(raw);bad[offset]^=128
        check(not hmi.uart_reject_status(dict(mc_fw_build=2026101806,mc_uart_reject_hex=bad.hex()))['available'],'HMI rejects corrupted metadata '+str(offset))
    check(not hmi.uart_reject_status(dict(mc_fw_build=2026101804,mc_uart_reject_hex=raw.hex()))['available'],'diagnostic from wrong firmware rejected')
    for filename in ('pulse_core.h','pulse_record.h','bkin_wave_capture.h','manual_scalar_control.h'):
        check((BASE/'nucleo/Inc'/filename).read_bytes()==(C/'nucleo/Inc'/filename).read_bytes(),'unchanged '+filename)
    for p in (BASE/'nucleo').rglob('*'):
        if not p.is_file() or any(x in ('Debug','Release','.settings') for x in p.parts):continue
        rel=p.relative_to(BASE)
        if rel.as_posix() in ('nucleo/Src/main.c','nucleo/Inc/uart_v3_transport.h','nucleo/Inc/break_wire.h'):continue
        check(p.read_bytes()==(C/rel).read_bytes(),'unmodified '+str(rel))
    # The exact running motor/control/ISR blocks outside diagnostics are intact.
    def body(source,name):
        match=re.search(r'(?m)^(?:static )?(?:void|bool|uint\d+_t|int\d+_t)\s+'+re.escape(name)+r'\([^;]*?\)\s*\{',source)
        if not match:raise AssertionError('missing function '+name)
        depth=1;end=match.end()
        while depth:depth+=(source[end]=='{')-(source[end]=='}');end+=1
        return source[match.start():end]
    old=read(BASE/'nucleo/Src/main.c');new=read(C/'nucleo/Src/main.c')
    functions=set(re.findall(r'\b(uno_\w+)\([^;\n]*\)\s*\{',old))|{'USART1_IRQHandler'}
    for name in functions:
        check(body(old,name).replace('2026101804','2026101806')==body(new,name),'motor/ISR unchanged '+name)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        header=read(C/folder/'uart_v3_transport.h')
        for text in ('UV3_NE_BUDGET = 2,','UV3_FRAME_DEADLINE_MS = 15,','UV3_WATCHDOG_MS = 300,'):
            check(text in header,'unchanged '+text+' in '+folder)
    for name in ('uart_v3_transport.h','uart_reject_record.h'):
        check((C/'nucleo/Inc'/name).read_bytes()==(C/'UNOQ_MOTOR'/name).read_bytes(),'both MCUs agree '+name)
    oldcal=dict(fw_build=2026101805,mc_fw_build=2026101804,rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    check(hmi._vbus_calibration_identity_matches(oldcal,dict(oldcal,fw_build=2026101807,mc_fw_build=2026101806)),'prior calibration preserved')
    run(['node','--check',str(C/'web_hmi/static/app.js')],'browser_syntax')
    report=dict(pass_=True,checks=len(results),details=results,old_probe=probes[0],fixed_probe=probes[1],
        contract=contract,bkin=bkin,mutations=mutations,hardware_commands=0,physical_crc_cause_proven=False,
        limitations=['Synthetic reproduction proves a parser defect, not the exact physical bytes causing the last stop',
            'The 320-byte trace is sent only OFF; one diagnostic cycle is now 7.2 seconds'])
    report['pass']=report.pop('pass_');(work/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('pass','checks','old_probe','fixed_probe','contract','bkin','hardware_commands')}))
if __name__=='__main__':main()
