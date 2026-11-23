"""Seal late-upstroke sampling and bottom-epoch queue; retain95% RMS gate."""
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path
import prepare_current_adc_apex_fix as p
import prepare_current_shunt_monitor as u
from audit_production_pwm_filters import function
from collect_current_peak import decoder
from current_adc_apex_fix.update import apply_irq

def main():
    c=p.OUT;m=json.loads(u.read(c/'manifest.json'))
    assert not m['built'] and not m['installed']
    tests=('apex_selftest_r1','window_sweep_r2','zero_selftest_r1','display_selftest_r1')
    results={n:json.loads(u.read(c/n/'report.json')) for n in tests}
    for n,r in results.items():assert r.get('passed',r.get('host_reproduction_passed')),n
    out=c/'verification';out.mkdir(exist_ok=True)
    ui=subprocess.run(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],capture_output=True,text=True,check=True,timeout=20)
    frontend=json.loads(ui.stdout);assert frontend['passed']
    u.write(out/'frontend.json',json.dumps(frontend,indent=2)+'\n')
    for f in (c/'web_hmi/server.py',p.ROOT/'tools/install_current_adc_apex_fix.py',p.ROOT/'tools/current_zero_quality.py'):
        ast.parse(u.read(f),filename=str(f))
    previous=json.loads(u.read(p.BASE/'manifest.json'));changes=[]
    for rel,digest in previous['source_sha256'].items():
        assert u.sha(p.BASE/rel)==digest,'Installed predecessor changed: '+rel
        if (p.BASE/rel).read_bytes()==(c/rel).read_bytes():continue
        old=u.read(p.BASE/rel).replace(str(p.OLD[0]),str(p.NEW[0])).replace(str(p.OLD[1]),str(p.NEW[1]))
        if old!=u.read(c/rel):changes.append(rel)
    allowed={'nucleo/Src/current_shunt.c','web_hmi/server.py','nucleo/STM32CubeIDE/.settings/language.settings.xml'}
    assert set(changes)<=allowed,changes
    for rel in ('nucleo/Inc/current_core.h','nucleo/Inc/peak_core.h','nucleo/Src/stm32g4xx_mc_it.c',
        'nucleo/Src/mc_tasks.c','web_hmi/static/app.js','web_hmi/static/index.html','web_hmi/static/style.css'):
        assert (c/rel).read_bytes()==(p.BASE/rel).read_bytes(),rel
    new=u.read(c/'nucleo/Src/current_shunt.c');old=u.read(p.BASE/'nucleo/Src/current_shunt.c')
    for name in ('mic_current_packet','mic_zero_record','mic_zero_packet','mic_current_peak_packet','queue_pair'):
        assert function(new,name)==function(old,name),name
    assert 'LL_TIM_OC_EnablePreload(TIM1,LL_TIM_CHANNEL_CH4)' in function(new,'mic_current_init')
    assert 'if(peak.frozen)return;' not in function(new,'mic_current_update_epoch')
    irq=function(new,'mic_current_adc_irq')
    assert irq.index('LL_TIM_OC_SetCompareCH4')<irq.index('queue_pair(pair)')<irq.index('cm_sample(')
    assert not re.search(r'CCR[123]\s*=|CCER\s*=|BDTR\s*=',irq)
    assert (c/'nucleo/Inc/current_adc_window_plan.h').read_bytes()==(p.ROOT/'tools/current_adc_window_plan.h').read_bytes()
    assert (c/'nucleo/Inc/current_adc_window_plan.h').read_bytes()==(p.BASE/'nucleo/Inc/current_adc_window_plan.h').read_bytes()
    assert (c/'nucleo/Inc/current_adc_deadline.h').read_bytes()==(p.ROOT/'tools/current_adc_apex_fix/deadline.h').read_bytes()
    assert irq==apply_irq(function(old,'mic_current_adc_irq'))
    assert 'CM_BEFORE_TOP=128U, CM_IDLE_BEFORE_TOP=384U' in new
    assert 'pending_epoch=epoch0+1U' in irq
    assert 'adc_flags_must_be_one_byte' in new and 'static uint32_t pending_epoch' in new
    h=decoder(c);fixture=json.loads(u.read(c/'zero_selftest_r1/decoded.json'))
    line=('DATA state=SAFE mode=VF pwm=0 fw_build=2026102509 bp_fw_build=2026102510 '
        'bp_mcsdk_telemetry=1 bp_age_ms=20 bp_rsp_age_ms=20 bp_status=0 '
        'mc_current_age_ms=10 mc_current_detail_age_ms=10 mc_current_quality_age_ms=10 ')
    line+=' '.join(k+'='+fixture[k] for k in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex','mc_zero_history_hex'))
    from current_zero_quality import ready
    parsed=h.RpcBridge._parse_status_string(line)
    assert ready(parsed) and parsed['mc_zero_history_valid']==1
    assert not ready(dict(parsed,mc_current_flags=17))
    before=dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(before,dict(before,fw_build=p.NEW[0],mc_fw_build=p.NEW[1]))
    for pair in (p.OLD,p.NEW):
        assert h.manual_scalar_supported(dict(parsed,manual_scalar_capable=1,fw_build=pair[0],mc_fw_build=pair[1]))
    assert not h.manual_scalar_supported(dict(parsed,manual_scalar_capable=1,fw_build=0))
    # Missing geometry coverage is NEVER made valid to satisfy a runner.
    damaged=bytearray.fromhex(fixture['mc_current_packet_hex'])
    damaged[3]=(damaged[3]|64)&~2
    damaged[5]=89;damaged[39:43]=h.current_crc32c(damaged[:39]).to_bytes(4,'little')
    invalid=h.with_shunt_currents(dict(fixture,mc_current_packet_hex=damaged.hex()))
    assert invalid['mc_current_telemetry_valid']==0 and invalid['mc_current_rms_a'] is None
    assert 'фронты ШИМ' in invalid['mc_current_status']
    debug=c/'nucleo/STM32CubeIDE/Debug'
    for f in debug.iterdir():
        if f.is_file() and (f.name.startswith('ACIM-NUCLEOG431RB-IPM15B-VF_OL.') or f.name=='mcsdk_release_preflight.json'):
            shutil.copyfile(f,c/'build/nucleo'/f.name)
    for name,folder,build in (('unoq_mcsdk_scalar','uno',p.NEW[0]),('ACIM-NUCLEOG431RB-IPM15B-VF_OL','nucleo',p.NEW[1])):
        b=json.loads(u.read(c/'build'/folder/(name+'.build-manifest.json')))
        assert b['firmware_build_id']==build
        if folder=='nucleo':assert b['build_errors']==b['build_warnings']==0
        for item in b['artifacts']:assert u.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
    assert json.loads(u.read(c/'build/uno/llext-check.json'))['pass']
    text=u.read(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map')
    end=int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',text)[1],16)
    margin=0x20008000-end-0x600;assert margin>=4096
    stack=u.read(debug/'Application/User/current_shunt.su')
    irq_stack=int(re.search(r':mic_current_adc_irq\s+(\d+)\s',stack)[1]);assert irq_stack<=384
    sweep=results['window_sweep_r2']['proposed_planner']
    assert sweep['safe_windows']==5410800 and sweep['no_safe_window']==0 and sweep['geometry_failures']==0
    summary=dict(passed=True,hardware_commands=0,installed=False,physical_peak_fix_verified=False,
        exact_captured_frames_replayed=24,old_2508_no_safe_frames_recovered_in_planning=2,
        old_bad_raw_samples_remain_rejected=True,new_trigger_currents_not_measured=True,raw_peak_preserved=True,
        actual_irq_checks=results['apex_selftest_r1']['checks'],
        raw_zero_statistics_and_95percent_coverage_gate_unchanged=True,
        sweep=sweep,
        incomplete_coverage_remains_invalid=True,zero_history_rpc_roundtrip=True,
        previous_calibration_identity_compatible=True,source_changes_beyond_identity=changes+['nucleo/Inc/current_adc_deadline.h'],
        nucleo_ram_above_min_heap_stack_bytes=margin,adc_irq_stack_bytes=irq_stack,
        uno_logic_unchanged_except_pair_identity=True,hardware_isr_wcet_verified=False,
        latest_trigger_ticks=5184,analog_settling_guard_ticks=771,acquisition_guard_ticks=112,
        min_queue_publish_budget_ticks=2048,full32bit_context_stamp=True,
        modeled_rms_valid_45_50=True,modeled_accepted_samples_per16000=15999,
        limitation='Saved raw replay validates rejection at ORIGINAL timestamps. Geometric retiming and synthetic40/45/50Hz current tests restore>=95% software coverage without changing thresholds; actual newly timed ADC currents, ISR WCET, current scale and physical RMS qualification remain pending.',
        sources=['https://www.st.com/resource/en/reference_manual/dm00355726-stm32g4-series-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf'])
    u.write(out/'report.json',json.dumps(summary,indent=2)+'\n')
    def hashes(files):return {str(f.relative_to(c)).replace('\\','/'):u.sha(f) for f in sorted(files) if f.is_file()}
    m.update(built=True,selftest_pass=True,installed=False,verification_summary=summary,
        zero_acceptance_unchanged=True,current_active_samples_filter_changed=True,
        current_amplitude_filter_changed=False,current_window_quality_thresholds_unchanged=True)
    m['source_sha256']=hashes(f for name in ('nucleo','UNOQ_MOTOR','web_hmi') for f in (c/name).rglob('*')
        if not any(x in f.relative_to(c).parts for x in ('Debug','Release','__pycache__')))
    m['build_sha256']=hashes((c/'build').rglob('*'))
    m['verification_sha256']=hashes(f for name in tests+('verification',) for f in (c/name).rglob('*'))
    u.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(summary))

if __name__=='__main__':main()
