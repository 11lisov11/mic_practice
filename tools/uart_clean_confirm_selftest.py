"""Replay saved UART bytes through old/new actual C parsers and retain contracts."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import prepare_uart_clean_confirm as package
from uart_tx_dma_selftest import body

C,BASE,ROOT=package.OUT,package.BASE,package.ROOT
def main():
    work=C/'selftest';work.mkdir(exist_ok=True);checks=[]
    def check(value,name):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    def run(cmd,label):
        p=subprocess.run(cmd,cwd=work,capture_output=True,text=True,encoding='utf-8',errors='replace')
        (work/(label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        if p.returncode:raise RuntimeError(label+': '+(p.stderr or p.stdout)[-2500:])
        return p.stdout
    trace=json.loads((ROOT/'artifacts/live_bench_20261021/sd_dual_motor_to_25_r1/after_uart_reject.json').read_text(encoding='utf-8'))['data']['records']
    def array(name,raw):return 'static const uint8_t '+name+'[]={' + ','.join(str(b) for b in bytes.fromhex(raw))+'};\n'
    inc=array('captured_recovered',trace[0]['raw_hex'])+array('captured_fatal',trace[1]['raw_hex'])+array('captured_fatal_marks',trace[1]['marks_hex'])
    (work/'captured.inc').write_text(inc,encoding='utf-8')
    flags=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(work)]
    results={}
    for label,source in [('old',BASE),('fixed',C)]:
        exe=work/(label+'_replay.exe')
        run(flags+(['-DSOURCE_OLD'] if label=='old' else [])+['-I',str(source/'nucleo/Inc'),
            str(ROOT/'tools/uart_clean_confirm_test.cpp'),'-o',str(exe)],label+'_compile')
        results[label]=json.loads(run([str(exe)],label+'_run'))
    check(results['old']['old_fatal_reproduced'],'actual old parser reproduces saved failure under captured receiver state')
    check(results['fixed']['pass'] and results['fixed']['two_NE_position_pairs']==903,'new path withholds all 903 possible two-NE byte pairs until a clean command')
    exe=work/'contract.exe'
    run(flags+['-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR'),
        str(ROOT/'tools/uart_resync_fix/contract_test.cpp'),'-o',str(exe)],'contract_compile')
    contract=json.loads(run([str(exe)],'contract_run'));check(contract['pass'],'existing CRC/sequence/timeout/diagnostic transport contracts')
    source=package.read(C/'nucleo/Src/main.c');old=package.read(BASE/'nucleo/Src/main.c')
    check(body(source,'uno_transport_result')==body(old,'uno_transport_result'),'owner ignores withheld packet via existing DROPPED result')
    check('if (result == UV3_WAIT || result == UV3_DROPPED) return;' in body(source,'uno_transport_result'),'no motor call from withheld packet')
    allowed={'nucleo/Inc/uart_v3_transport.h','UNOQ_MOTOR/uart_v3_transport.h','web_hmi/server.py'}
    changed=[]
    manifest=json.loads(package.read(BASE/'manifest.json'))
    for rel in manifest['source_sha256']:
        if (BASE/rel).read_bytes()==(C/rel).read_bytes():continue
        expected=package.read(BASE/rel)
        if not rel.startswith('web_hmi/'):
            expected=expected.replace(str(package.OLD[0]),str(package.NEW[0])).replace(str(package.OLD[1]),str(package.NEW[1]))
        if package.read(C/rel)!=expected:changed.append(rel)
    check(set(changed)==allowed,'only UART header and HMI identity allowlists change beyond build identities')
    check((C/'nucleo/Inc/uart_v3_transport.h').read_bytes()==(C/'UNOQ_MOTOR/uart_v3_transport.h').read_bytes(),'shared wire/transport header identical')
    # Negative controls must invalidate the new confirmation tests.
    header=package.read(C/'nucleo/Inc/uart_v3_transport.h')
    mutations=[('publish_noisy','return UV3_DROPPED;\n  }\n  if (rx->ne_bytes','return UV3_READY;\n  }\n  if (rx->ne_bytes'),
        ('refresh_deadline','rx->confirm_started_ms=now_ms;','rx->confirm_started_ms=now_ms;rx->last_valid_ms=now_ms;'),
        ('erase_crc_budget','rx->confirm_pending=true;','rx->confirm_pending=true;rx->noise_used=0;'),
        ('accept_replayed_confirm','advance == 0 || advance > (uint8_t)(losses + 1U)','advance > (uint8_t)(losses + 1U)'),
        ('remove_pending_deadline','(uint32_t)(now_ms-rx->confirm_started_ms)>UV3_CONFIRM_MS','false'),
        ('second_noisy_confirms','rx->confirm_pending && rx->ne_bytes)','false)'),
        ('CRC_removed','if (!uv3_crc_ok(rx->frame))','if (false)')]
    for name,a,b in mutations:
        assert header.count(a)==1,(name,header.count(a))
        folder=work/name;folder.mkdir(exist_ok=True)
        (folder/'uart_v3_transport.h').write_text(header.replace(a,b),encoding='utf-8')
        exe=folder/'test.exe'
        run(flags+['-I',str(folder),str(ROOT/'tools/uart_clean_confirm_test.cpp'),'-o',str(exe)],name+'_compile')
        p=subprocess.run([str(exe)],cwd=folder,capture_output=True,text=True)
        (folder/'run.log').write_text(p.stdout+p.stderr,encoding='utf-8')
        check(p.returncode!=0 and 'FAIL ' in p.stderr,'negative control detected '+name)
    spec=importlib.util.spec_from_file_location('clean_confirm_hmi',C/'web_hmi/server.py')
    hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
    pair=package.NEW
    check(hmi.manual_scalar_supported(dict(fw_build=pair[0],mc_fw_build=pair[1],manual_scalar_capable=1)),'new exact pair supports manual scalar')
    check(not hmi.manual_scalar_supported(dict(fw_build=pair[0],mc_fw_build=package.OLD[1],manual_scalar_capable=1)),'mixed old/new pair rejected')
    cal=dict(fw_build=package.OLD[0],mc_fw_build=package.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    check(hmi._vbus_calibration_identity_matches(cal,dict(cal,fw_build=pair[0],mc_fw_build=pair[1])),'existing calibration identity preserved')
    check(hmi.sd_live_status(dict(mc_fw_build=pair[1],mc_age_ms=20,bp_temp_flags=189))['available'],'SD diagnostics accept new image')
    # Execute the existing dual recorder and decoder tests against this new pair.
    # The dual tests intentionally use exact source/identity literals. Instead
    # use their already sealed actual C simulation with the unchanged recorder.
    firmware_start=source.index('static bool mic_bkin_dma_initialized;')
    firmware_end=source.index('static void mic_bkin_wave_packet(',firmware_start)
    (work/'firmware.inc').write_text(source[firmware_start:firmware_end]+body(source,'mic_bkin_wave_packet'),encoding='utf-8')
    sim=package.read(BASE/'selftest/sim.c').replace(str(package.OLD[1]),str(package.NEW[1]))
    (work/'sim.c').write_text(sim,encoding='utf-8')
    exe=work/'dual.exe'
    run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
         '-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR'),str(work/'sim.c'),'-o',str(exe)],'dual_compile')
    host=json.loads(run([str(exe)],'dual_run'));check(host['pass'] and host['host_cases']>=1149,'unchanged actual dual SD recorder and Uno receiver')
    raw=(work/'equal_3_0.bin').read_bytes()
    check(hmi.bkin_wave_status(dict(mc_fw_build=pair[1],mc_break_wave_hex=raw.hex(),mc_break_wave_age_ms=0,mc_age_ms=20))['available'],'new pair dual waveform HMI decode')
    check(hmi.uart_reject_status(dict(mc_fw_build=pair[1],mc_uart_reject_hex=(work/'fatal.bin').read_bytes().hex()))['available'],'new pair raw UART diagnostic decoder')
    run(['node','--check',str(C/'web_hmi/static/app.js')],'browser_syntax')
    report=dict(passed=True,checks=len(checks),details=checks,replay=results,contract=contract,host=host,
        negative_controls=len(mutations),hardware_commands=0,
        limitations=['Captured fatal frame/state replayed; next clean confirming frame is a synthetic follow-up, not recorded physical traffic',
                     'No physical noise-source identification or motor operation to 50 Hz established'])
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('passed','checks','replay','contract','host','negative_controls','hardware_commands')}))

if __name__=='__main__':main()
