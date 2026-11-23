"""Exercise production SD encoding and display using real archived records."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
C = ROOT/'artifacts/live_bench_20261018/sd_live_diagnostics_r1'
BASE = ROOT/'artifacts/live_bench_20261018/uart_resync_fix_r1'


def read(p):
    return p.read_text(encoding='utf-8-sig')


def main():
    work = C/'selftest'
    work.mkdir(exist_ok=True)
    checks = []

    def check(value, name):
        checks.append({'name':name, 'pass':bool(value)})
        if not value:
            raise AssertionError(name)

    def run(cmd, label):
        p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding='utf-8', errors='replace')
        (work/(label+'.log')).write_text(p.stdout+p.stderr, encoding='utf-8')
        if p.returncode:
            raise RuntimeError(label+': '+(p.stderr or p.stdout)[-2000:])
        return p.stdout

    main_source = read(C/'nucleo/Src/main.c')
    a = main_source.index('  const bool sd_config_ok =')
    b = main_source.index('\n  if ((mcsdk_faults & MC_OVER_TEMP)', a)
    actual_encode = main_source[a:b]
    fixture = r'''
#include <cstdio>
#include <cstring>
#include <cassert>
#include "sd_live_status.h"
struct Gpio { unsigned MODER,OTYPER,PUPDR,AFR[2],IDR; } gpio;
struct Timer { unsigned AF1,BDTR,DIER; } tim;
#define GPIOA (&gpio)
#define TIM1 (&tim)
enum {GPIO_PIN_6=64,TIM1_AF1_BKINE=1,TIM1_AF1_BKINP=512,
 TIM_BDTR_BKE=4096,TIM_BDTR_BKP=8192,TIM_BDTR_BKBID=268435456,
 TIM_DIER_BIE=128,MIC_BKIN_RUNNING=1};
unsigned mic_bkin_capture_state,mic_bkin_record_ready;
unsigned char encode() {unsigned char reply[43]={};
ACTUAL
return reply[21];}
int main(){
 gpio={2u<<12,64,1u<<12,{6u<<24,0},0};tim={513,12288,0};
 for(unsigned mask=0;mask<16;++mask){
   gpio.IDR=(mask&1)?64:0;tim.DIER=(mask&2)?128:0;
   mic_bkin_capture_state=(mask&4)?1:2;mic_bkin_record_ready=!!(mask&8);
   Gpio beforeG=gpio;Timer beforeT=tim;
   unsigned result=encode();
   assert(!memcmp(&beforeG,&gpio,sizeof(gpio))&&!memcmp(&beforeT,&tim,sizeof(tim)));
   assert((result&3)==0);
   printf("%u\n",result);
 }
 // Wrong mode, output type, pull, AF, polarity, enable, bidirectional mode.
 unsigned *fields[]={&gpio.MODER,&gpio.OTYPER,&gpio.PUPDR,&gpio.AFR[0],&tim.AF1,&tim.AF1,&tim.BDTR,&tim.BDTR,&tim.BDTR};
 unsigned changes[]={1u<<12,64,1u<<12,1u<<24,1,512,4096,8192,268435456};
 for(unsigned i=0;i<9;++i){unsigned old=*fields[i];*fields[i]^=changes[i];assert(!(encode()&128));*fields[i]=old;}
 assert(encode()&128);
}
'''.replace('ACTUAL', actual_encode)
    cpp = work/'sd_encode.cpp'
    cpp.write_text(fixture, encoding='utf-8')
    exe = work/'sd_encode.exe'
    run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(C/'nucleo/Inc'),str(cpp),'-o',str(exe)], 'sd_encode_compile')
    flags = list(map(int,run([str(exe)], 'sd_encode_run').split()))
    check(len(flags)==16, 'actual GPIO/timer encoding covers levels and capture states without register writes')
    spec = importlib.util.spec_from_file_location('sd_live_candidate', C/'web_hmi/server.py')
    hmi = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = hmi
    spec.loader.exec_module(hmi)
    for mask, flag in enumerate(flags):
        for temp in range(4):
            data = hmi.RpcBridge._parse_status_string(f'state=SAFE mode=VF pwm=0 fw_build=2026101809 bp_fw_build=2026101808 bp_temp_flags={flag|temp} bp_temp_valid={temp&1} bp_temp_fault={int(bool(temp&2))} bp_age_ms=20')
            result = hmi.sd_live_status(data)
            check(result['available'] and result['level']==('HIGH' if mask&1 else 'LOW') and result['config_ok'], f'live SD through actual RPC parser mask {mask} temp {temp}')
            check(result['break_irq_enabled']==bool(mask&2) and result['capture_running']==bool(mask&4) and result['first_record_ready']==bool(mask&8), f'capture state mask {mask} temp {temp}')
            check(data['bp_temp_valid']==(temp&1) and data['bp_temp_fault']==bool(temp&2), f'temperature bits preserved mask {mask} temp {temp}')
    baseline = dict(mc_fw_build=2026101808, bp_temp_flags=141, mc_age_ms=20)
    for key,value in [('mc_fw_build',2026101806),('mc_age_ms',300),('mc_age_ms',-1),('bp_temp_flags',1),('bp_temp_flags',256),('bp_temp_flags',None)]:
        check(not hmi.sd_live_status(dict(baseline,**{key:value}))['available'], 'unknown is never HIGH: '+str((key,value)))
    historical = json.loads(read(ROOT/'artifacts/live_bench_20261018/uart_resync_j4_after_reset_r2/final_status.json'))
    old_wave = hmi.bkin_wave_status(historical)
    live_data = dict(historical, mc_fw_build=2026101808, bp_temp_flags=205, mc_age_ms=20)
    wave = hmi.bkin_wave_status(live_data)
    check(old_wave['available'] and not old_wave['live_sd']['available'], 'old pair explicitly reports unknown current SD')
    check(wave['reason']=='timeout_low_unfinished' and wave['live_sd']['level']=='HIGH' and wave['pulse_width_us'] is None, 'past LOW and present HIGH coexist without inventing a pulse end')
    check(wave['runs']==old_wave['runs'] and wave['flags']==old_wave['flags'], 'historical record is unchanged')
    # Rebuild the actual recorder excerpt, rather than an old copied simulation.
    a = main_source.index('static bool mic_bkin_dma_initialized;')
    b = main_source.index('\n\nstatic void mic_bkin_wave_packet',a)
    (work/'firmware.inc').write_text(main_source[a:b], encoding='utf-8')
    sim_source = read(ROOT/'tools/bkin_fast_capture/sim.c')
    (work/'sim.c').write_text(sim_source, encoding='utf-8')
    sim = work/'bkin.exe'
    run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR'),str(work/'sim.c'),'-o',str(sim)], 'bkin_compile')
    bkin = json.loads(run([str(sim)], 'bkin_run'))
    check(bkin['pass'] and bkin['host_cases']==450, '450 actual recorder/receiver scenarios preserved')
    contract = work/'uart_contract.exe'
    run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR'),str(ROOT/'tools/uart_resync_fix/contract_test.cpp'),'-o',str(contract)], 'uart_compile')
    uart = json.loads(run([str(contract)], 'uart_run'))
    check(uart['pass'], 'UART CRC/watchdog/replay/D3 contracts retained')
    raw = (work/'fatal.bin').read_bytes()
    check(hmi.uart_reject_status(dict(mc_fw_build=2026101808,mc_uart_reject_hex=raw.hex()))['available'], 'D3 new identity decoded')
    check(not hmi.uart_reject_status(dict(mc_fw_build=2026101806,mc_uart_reject_hex=raw.hex()))['available'], 'D3 rejects cross-peer record substitution')
    # Frontend render test against the actual saved timeout record.
    js = read(C/'web_hmi/static/app.js')
    a = js.index('function describeBkinTrace(trace) {')
    b = js.index('\n\nasync function loadBkinTrace()',a)
    harness = js[a:b]+'\nconst assert=require("assert");\nconst wave='+json.dumps(wave,ensure_ascii=False)+';\n'
    harness += '''const s=describeBkinTrace(wave);assert(s.includes("SD сейчас HIGH"));assert(!s.includes("undefined"));assert(!s.includes("NaN"));assert(!s.includes("1 мкс"));assert(!s.includes("не обнаружен"));assert(s.includes("0,2 мкс"));assert(s.includes("полная длительность неизвестна"));console.log(JSON.stringify({pass:true,text:s}));'''
    (work/'display_test.js').write_text(harness,encoding='utf-8')
    display=json.loads(run(['node',str(work/'display_test.js')],'display_run'))
    check(display['pass'], 'real long-LOW record renders correct schema and live HIGH without false no-pulse text')
    run(['node','--check',str(C/'web_hmi/static/app.js')], 'browser_syntax')
    # Unchanged protection code, GPIO setup, IRQs and transport; only identities
    # and the reply flag observation are allowed to differ in firmware.
    for tree in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for path in (BASE/tree).rglob('*'):
            if not path.is_file():continue
            rel=path.relative_to(BASE)
            expected=read(path).replace('2026101807','2026101809').replace('2026101806','2026101808')
            actual=read(C/rel)
            if rel.as_posix()=='nucleo/Src/main.c':
                actual=actual.replace('#include "sd_live_status.h"\n','')
                start=actual.index('  /* Additive status only:')
                end=actual.index('\n  if ((mcsdk_faults & MC_OVER_TEMP)',start)
                actual=actual[:start]+actual[end+1:]
            check(actual==expected, 'unchanged protection/control file '+str(rel))
    oldcal=dict(fw_build=2026101807,mc_fw_build=2026101806,rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    check(hmi._vbus_calibration_identity_matches(oldcal,dict(oldcal,fw_build=2026101809,mc_fw_build=2026101808)), 'existing calibration identity remains compatible')
    report=dict(pass_=True, checks=len(checks), details=checks, bkin=bkin, uart=uart, hardware_commands=0,
                physical_sd_cause_proven=False, active_motor_test=False)
    report['pass']=report.pop('pass_')
    (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('pass','checks','bkin','uart','hardware_commands')}))


if __name__=='__main__':
    main()
