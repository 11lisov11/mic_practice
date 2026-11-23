"""Prepare a separate all-three-leg ADC window candidate; no device access."""
import json
import os
import shutil
from pathlib import Path
import prepare_current_shunt_monitor as u
from audit_production_pwm_filters import function

ROOT=u.ROOT
BASE=ROOT/'artifacts/live_bench_20261024/current_zero_noise_r1'
OUT=BASE.parent/'current_adc_window_fix_r1'
OLD=(2026102505,2026102506)
NEW=(2026102507,2026102508)

def main():
    assert not OUT.exists()
    old=json.loads(u.read(BASE/'manifest.json'))
    assert old['installed'] and old['installation_flash_verified']
    for rel,digest in old['source_sha256'].items():assert u.sha(BASE/rel)==digest,rel
    for name in ('nucleo','UNOQ_MOTOR','web_hmi'):
        def copy(src,dst):
            rel=Path(src).relative_to(BASE/name)
            if name=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/name,OUT/name,copy_function=copy,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                a=u.read(f);b=a.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if a!=b:u.write(f,b)
    shutil.copyfile(ROOT/'tools/current_adc_window_plan.h',OUT/'nucleo/Inc/current_adc_window_plan.h')
    f=OUT/'nucleo/Src/current_shunt.c';s=u.read(f)
    s=u.once(s,'#include "peak_core.h"','#include "peak_core.h"\n#include "current_adc_window_plan.h"')
    s=u.once(s,'CM_SETTLE_TICKS=TW_AFTER+TNOISE+32U','CM_SETTLE_TICKS=TW_AFTER+TNOISE+32U, CM_ACQUIRE_TICKS=112U')
    s=u.once(s,'static uint16_t peak_active_ccr[4],peak_update_cnt,peak_update_cr1;',
        'static volatile uint16_t peak_active_ccr[4],peak_update_cnt,peak_update_cr1;')
    s=u.once(s,'  if(peak.frozen)return;\n','')
    s=u.once(s,'  LL_TIM_OC_SetCompareCH4(TIM1,TIM1->ARR-CM_BEFORE_TOP);',
        '  LL_TIM_OC_EnablePreload(TIM1,LL_TIM_CHANNEL_CH4);\n  LL_TIM_OC_SetCompareCH4(TIM1,TIM1->ARR-CM_BEFORE_TOP);')
    s=s.replace(function(s,'mic_current_adc_irq'),u.read(ROOT/'tools/current_adc_window_fix/window_irq.c').rstrip())
    u.write(f,s)
    f=OUT/'web_hmi/server.py';s=u.read(f)
    # Keep predecessor identities in command/calibration compatibility lists.
    s=u.once(s,'        (2026102505, 2026102506),','        (2026102505, 2026102506),\n        (2026102507, 2026102508),')
    s=u.once(s,'(2026102505,2026102506)) and','(2026102505,2026102506),(2026102507,2026102508)) and')
    s=''.join(line.replace(',2026102506)',',2026102506,2026102508)').replace(', 2026102506)',', 2026102506, 2026102508)')
        if (('not in (' in line and 'not in ((' not in line) or ('mc_fw_build' in line and ' in (2026' in line)) else line
        for line in s.splitlines(keepends=True))
    a=s.index('# Imported as source into the HMI;');b=s.index('def with_motor_controller_aliases',a)
    s=s[:a]+s[a:b].replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))+s[b:]
    s=u.once(s,'            accepted_by_existing_monitor=bool(s[25]&64),queue_overflow_observed=bool(s[25]&256),',
        '''            accepted_by_existing_monitor=bool(s[25]&64),accepted_by_monitor=bool(s[25]&64),
            three_leg_window_rejected=bool(s[25]&1024),queue_overflow_observed=bool(s[25]&256),''')
    s=u.once(s,"'Недостоверное окно: насыщение АЦП или пропуски выборки'",
        "'Недостоверное окно АЦП: недостаточное покрытие, фронты ШИМ, рассинхронизация или насыщение; смотрите флаги и долю принятых отсчётов'")
    u.write(f,s)
    for name in ('build/uno','build/nucleo'):(OUT/name).mkdir(parents=True)
    m={k:v for k,v in old.items() if not k.startswith(('source_sha','build_sha','verification_',
        'installation','completion','images_written','adc_idle_','zero_history_hmi_'))}
    m.update(pair_compatibility_ids=list(NEW),predecessor=str(BASE),built=False,selftest_pass=False,installed=False,
        hardware_commands=0,rpc_pending=False,adc_trigger_changed=True,
        adc_trigger='TIM1_OC4REF dynamic CH4 preload, all3leg guard, bound to ADC context/update epoch',
        adc_trigger_preload_required=True,adc_guard_all_three_legs=True,adc_acquisition_guard_ticks=112,
        adc_settling_guard_ticks=771,current_raw_spikes_retained=True,current_window_rejection_explicit=True,
        zero_acceptance_unchanged=True,current_active_samples_filter_changed=True,
        current_amplitude_filter_changed=False,current_window_quality_thresholds_unchanged=True,
        physical_window_fix_verified=False,adc_idle_zero_verified=False,physical_current_qualified=False)
    u.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
