"""Prepare2509/2510 late-aperture and bottom-update context fix; no hardware."""
import json
import os
import shutil
from pathlib import Path
import prepare_current_shunt_monitor as u
from audit_production_pwm_filters import function
from current_adc_apex_fix.update import FLAGS,apply_irq

ROOT=u.ROOT
BASE=ROOT/'artifacts/live_bench_20261024/current_adc_window_fix_r1'
OUT=BASE.parent/'current_adc_apex_fix_r1'
OLD=(2026102507,2026102508)
NEW=(2026102509,2026102510)

def main():
    assert not OUT.exists()
    m=json.loads(u.read(BASE/'manifest.json'))
    assert m['installed'] and m['installation_flash_verified']
    for rel,digest in m['source_sha256'].items():assert u.sha(BASE/rel)==digest,rel
    for name in ('nucleo','UNOQ_MOTOR','web_hmi'):
        def copy(src,dst):
            rel=Path(src).relative_to(BASE/name)
            if name=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/name,OUT/name,copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                a=u.read(f);b=a.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if a!=b:u.write(f,b)
    shutil.copyfile(ROOT/'tools/current_adc_apex_fix/deadline.h',OUT/'nucleo/Inc/current_adc_deadline.h')
    f=OUT/'nucleo/Src/current_shunt.c';s=u.read(f)
    s=u.once(s,'#include "current_adc_window_plan.h"','#include "current_adc_window_plan.h"\n#include "current_adc_deadline.h"')
    s=u.once(s,'CM_BEFORE_TOP=384U,','CM_BEFORE_TOP=128U, CM_IDLE_BEFORE_TOP=384U,')
    s=u.once(s,'static uint8_t pending_pair,pending_valid,pending_active,initialized,lost_sync;',FLAGS)
    s=u.once(s,'LL_TIM_OC_SetCompareCH4(TIM1,TIM1->ARR-CM_BEFORE_TOP);',
        'LL_TIM_OC_SetCompareCH4(TIM1,TIM1->ARR-CM_IDLE_BEFORE_TOP);')
    s=u.once(s,'  queue_pair(0);pending_valid=0;', '  pending_epoch=peak_epoch+1U;\n  queue_pair(0);pending_valid=0;')
    irq=function(s,'mic_current_adc_irq');s=s.replace(irq,apply_irq(irq));u.write(f,s)
    f=OUT/'web_hmi/server.py';s=u.read(f)
    s=u.once(s,'        (2026102507, 2026102508),','        (2026102507, 2026102508),\n        (2026102509, 2026102510),')
    s=u.once(s,'(2026102507,2026102508)) and','(2026102507,2026102508),(2026102509,2026102510)) and')
    s=''.join(line.replace(',2026102508)',',2026102508,2026102510)').replace(', 2026102508)',', 2026102508, 2026102510)')
        if (('not in (' in line and 'not in ((' not in line) or ('mc_fw_build' in line and ' in (2026' in line)) else line
        for line in s.splitlines(keepends=True))
    a=s.index('# Imported as source into the HMI;');b=s.index('def with_motor_controller_aliases',a)
    s=s[:a]+s[a:b].replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))+s[b:]
    s=u.once(s,'            three_leg_window_rejected=bool(s[25]&1024),queue_overflow_observed=bool(s[25]&256),',
        '''            three_leg_window_rejected=bool(s[25]&1024),queue_overflow_observed=bool(s[25]&256),
            publish_deadline_missed=bool(s[25]&2048),pending_epoch_mismatch=bool(s[25]&4096),injected_queue_not_empty=bool(s[25]&8192),
            timer_phase_entry_ticks=(2*s[17]-s[16]) if s[18]&16 else s[16],''')
    u.write(f,s)
    for name in ('build/uno','build/nucleo'):(OUT/name).mkdir(parents=True)
    m={k:v for k,v in m.items() if not k.startswith(('source_sha','build_sha','verification_',
        'installation','completion','images_written','adc_idle_','physical_','powerbank_','zero_history_hmi_'))}
    m.update(pair_compatibility_ids=list(NEW),predecessor=str(BASE),built=False,selftest_pass=False,installed=False,
        hardware_commands=0,rpc_pending=False,adc_active_before_top_ticks=128,adc_idle_before_top_ticks=384,
        adc_queue_publish_margin_ticks=2048,adc_pending_epoch_bits=32,
        adc_trigger='TIM1_OC4REF CH4 preload, all3leg guards, JEOS allowed after apex before bottom UEV deadline',
        adc_settling_guard_ticks=771,adc_acquisition_guard_ticks=112,zero_acceptance_unchanged=True,
        current_window_quality_thresholds_unchanged=True,current_amplitude_filter_changed=False,
        physical_current_scale_qualified=False,full_current_rms_coverage_verified=False)
    u.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
