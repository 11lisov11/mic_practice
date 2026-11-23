"""Exercise the actual dual recorder, wire packets, Uno receiver and HMI offline."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import struct
import subprocess
import sys
import prepare_sd_dual_capture as package
from uart_tx_dma_selftest import body

ROOT,C,BASE,T=package.ROOT,package.OUT,package.BASE,package.T
def read(p):return p.read_text(encoding='utf-8-sig')
def main():
    work=C/'selftest'; checks=[]
    def check(value,name):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    def run(cmd,label):
        p=subprocess.run(cmd,cwd=work,capture_output=True,text=True,encoding='utf-8',errors='replace')
        (work/(label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        if p.returncode:raise RuntimeError(label+': '+(p.stderr or p.stdout)[-3000:])
        return p.stdout
    source=read(C/'nucleo/Src/main.c');old=read(BASE/'nucleo/Src/main.c')
    a=source.index('static bool mic_bkin_dma_initialized;');b=source.index('static void mic_bkin_wave_packet(',a)
    (work/'firmware.inc').write_text(source[a:b]+body(source,'mic_bkin_wave_packet'),encoding='utf-8')
    stubs=read(ROOT/'tools/bkin_fast_capture/sim.c').split('static unsigned cases;')[0]
    stubs=stubs.replace('uint32_t IDR;','uint32_t IDR,MODER,PUPDR;')
    stubs=stubs.replace('GPIO_PIN_6=64','GPIO_PIN_6=64,GPIO_PIN_4=16,GPIO_MODE_INPUT=0,GPIO_NOPULL=0')
    anchor='#include "firmware.inc"'
    stubs=stubs.replace(anchor,'''typedef struct {uint32_t Pin,Mode,Pull;} GPIO_InitTypeDef;
static bool sim_bad_gpio;
static void HAL_GPIO_Init(gpio_t *g,GPIO_InitTypeDef *p) {
  assert(g==GPIOA && p->Pin==16 && p->Mode==0 && p->Pull==0);
  g->MODER=sim_bad_gpio?256:0;g->PUPDR=0;
}
'''+'#define MIC_NUCLEO_FW_BUILD_ID 2026102102UL\n'+anchor)
    (work/'sim.c').write_text(stubs+read(T/'sim_tests.inc'),encoding='utf-8')
    flags=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
           '-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR')]
    exe=work/'dual.exe';run(flags+[str(work/'sim.c'),'-o',str(exe)],'dual_compile')
    host=json.loads(run([str(exe)],'dual_run'));check(host['pass'],'actual C recorder and Uno receiver')
    firmware=(work/'firmware.inc').read_text(encoding='utf-8')
    for name,before,after in [('missing_tp23','GPIO_PIN_4|GPIO_PIN_6','GPIO_PIN_6'),
                              ('probe_not_passive','probe.Mode=GPIO_MODE_INPUT','probe.Mode=1U')]:
        folder=work/name;folder.mkdir(exist_ok=True)
        (folder/'firmware.inc').write_text(firmware.replace(before,after),encoding='utf-8')
        (folder/'sim.c').write_text(read(work/'sim.c'),encoding='utf-8')
        mutant=folder/'mutant.exe';run(flags+[str(folder/'sim.c'),'-o',str(mutant)],name+'_compile')
        p=subprocess.run([str(mutant)],cwd=folder,capture_output=True,text=True)
        check(p.returncode!=0 and 'Assertion' in p.stderr,'negative control detected '+name)
    spec=importlib.util.spec_from_file_location('sd_dual_hmi',C/'web_hmi/server.py')
    hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
    def decode(raw,**fields):return hmi.bkin_wave_status(dict(mc_fw_build=2026102102,
        mc_break_wave_hex=raw.hex(),mc_break_wave_age_ms=86400000,mc_age_ms=20,**fields))
    for p in work.glob('equal_*.bin'):
        width=int(p.stem.split('_')[1]);d=decode(p.read_bytes())
        check(d['available'] and d['schema']==5 and d['post_complete'] and d['mismatch_samples']==0,p.stem+' simultaneous complete window')
        for channel in d['channels'].values():
            pulse=channel['selected_pulse'];check(pulse['pulse_complete'] and pulse['width_samples']==width,p.stem+' complete width per channel')
    for name,active,quiet in [('sink_only','pa6_bkin','tp23_pa4'),('source_only','tp23_pa4','pa6_bkin')]:
        d=decode((work/(name+'.bin')).read_bytes())
        check(d['channels'][active]['selected_pulse']['width_samples']==3 and not d['channels'][quiet]['low_observed'] and d['mismatch_samples']==3,name+' independent channel distinction')
    for name,delta in [('skew_source_first',-2),('skew_sink_first',2),('late_source',200),('late_source_100us',500)]:
        d=decode((work/(name+'.bin')).read_bytes());ch=d['channels']
        check(ch['tp23_pa4']['selected_pulse']['fall_sample']-ch['pa6_bkin']['selected_pulse']['fall_sample']==delta,name+' edge delay retained')
    d=decode((work/'source_long.bin').read_bytes())
    check(d['post_complete'] and d['channels']['tp23_pa4']['selected_pulse']['width_samples']==100000,'source recovery not truncated by sink recovery')
    for name,reason in [('timeout','timeout_incomplete'),('overflow','run_capacity_exceeded'),('overrun','sampling_overrun'),('dma_error','dma_error'),('stalled','dma_error')]:
        d=decode((work/(name+'.bin')).read_bytes());check(d['available'] and d['reason']==reason and not d['post_complete'],name+' explicit incomplete status')
        if name!='timeout':check(all(not x['pulse_complete'] for ch in d['channels'].values() for x in ch['low_intervals']),name+' no unqualified pulse widths')
    d=decode((work/'left.bin').read_bytes())
    check(d['channels']['tp23_pa4']['selected_pulse']['left_censored'] and d['channels']['tp23_pa4']['selected_pulse']['width_us'] is None,'missing falling edge not called complete')
    d=decode((work/'no_low.bin').read_bytes());check(all(not ch['low_observed'] for ch in d['channels'].values()),'Break without observed LOW remains explicit')
    raw=(work/'equal_3_0.bin').read_bytes()
    check(not decode(raw[:-1])['available'],'truncated record rejected')
    for offset,value in [(0,0),(4,4),(8,160),(16,1000),(20,0),(24,2049),(28,502049),(32,33),(36,0x40),(40,1),(44,1),(48,1),(52,16),(56,8193),(60,0),(64,4),(68,0),(312,1)]:
        bad=bytearray(raw);struct.pack_into('<I',bad,offset,value)
        check(not decode(bad)['available'],f'invalid record field {offset} rejected')
    # Actual record validator in the Uno must reject the same malformed fields,
    # independently of a transport CRC. Compile it as a tiny binary utility.
    validate=work/'validate.c';validate.write_text('''#include <stdio.h>
#include "pulse_record.h"
int main(void){unsigned char p[320];if(fread(p,1,320,stdin)!=320)return 2;return bp_record_valid(p)?0:1;}
''',encoding='utf-8')
    binary=work/'validate.exe';run(flags+[str(validate),'-o',str(binary)],'validate_compile')
    check(subprocess.run([str(binary)],input=raw).returncode==0,'real C validator accepts actual dual record')
    for offset,value in [(4,4),(20,2),(32,33),(36,0),(40,1),(44,1),(48,1),(60,0),(64,4),(68,0),(312,1)]:
        bad=bytearray(raw);struct.pack_into('<I',bad,offset,value)
        check(subprocess.run([str(binary)],input=bad).returncode==1,'real C validator rejects offset '+str(offset))
    # Archived schema-4 evidence is still decoded; never relabel it as dual.
    archive=ROOT/'artifacts/live_bench_20261020/sd_break_filter_to_50_r1/bkin_wave.bin'
    old_data={'mc_fw_build':2026102002,'mc_break_wave_hex':archive.read_bytes().hex(),'mc_break_wave_age_ms':20,'mc_age_ms':20}
    check(hmi.bkin_wave_status(old_data)['schema']==4,'old real schema-4 record stays readable')
    check(not hmi.bkin_wave_status(dict(old_data,mc_fw_build=2026102102))['available'],'old record rejected for dual peer')
    check(not hmi.bkin_wave_status(dict(old_data,mc_fw_build=999))['available'],'unknown peer rejected')
    old_id=dict(fw_build=2026102001,mc_fw_build=2026102002,rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    new_id=dict(old_id,fw_build=2026102101,mc_fw_build=2026102102)
    check(hmi._vbus_calibration_identity_matches(old_id,new_id),'saved calibration identity retained without rewriting points')
    check(hmi.manual_scalar_supported({'fw_build':2026102101,'mc_fw_build':2026102102,'manual_scalar_capable':1}),'manual scalar exact pair accepted')
    # No changes to the Break IRQ, motor algorithms, TX/RX, or their watchdogs.
    for name in ('mic_bkin_capture_trigger_from_break','mic_bkin_freeze','mic_bkin_wave_packet','MX_TIM1_Init','MX_GPIO_Init'):
        check(body(source,name)==body(old,name),'unchanged critical function '+name)
    for tree in ('nucleo/Inc','nucleo/Src','nucleo/Drivers','nucleo/MCSDK_v6.4.2-Full','UNOQ_MOTOR'):
        for p in (BASE/tree).rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(BASE);target=C/rel
            if rel.as_posix() in ('nucleo/Src/main.c','nucleo/Inc/pulse_core.h','nucleo/Inc/pulse_record.h','nucleo/Inc/bkin_wave_capture.h','UNOQ_MOTOR/pulse_core.h','UNOQ_MOTOR/pulse_record.h'):continue
            before=p.read_bytes()
            if tree in ('nucleo/Drivers','nucleo/MCSDK_v6.4.2-Full'):
                check(target.read_bytes()==before,'unchanged library '+rel.as_posix())
            else:
                expected=read(p).replace('2026102001','2026102101').replace('2026102002','2026102102')
                check(read(target)==expected,'unchanged source '+rel.as_posix())
    # Exact outside-recorder source equality catches accidental control edits.
    strip=lambda s:s[:s.index('static bool mic_bkin_dma_initialized;')]+s[s.index('static void mic_bkin_wave_packet('):]
    check(strip(source)==strip(old).replace('2026102002','2026102102'),'all main.c changes confined to recorder and identity')
    run(['node','--check',str(C/'web_hmi/static/app.js')],'browser_syntax')
    report=dict(passed=True,checks=len(checks),host=host,mutation_controls=2,details=checks,
                hardware_commands=0,hardware_validated=False)
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('passed','checks','host','hardware_commands','hardware_validated')}))
if __name__=='__main__':main()
