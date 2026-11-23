"""Seal the zero-estimator/history pair after actual-code offline checks."""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import prepare_current_zero_noise as p
import prepare_current_shunt_monitor as u
from audit_production_pwm_filters import function
from collect_current_peak import decoder


def main():
    c=p.OUT;m=json.loads(u.read(c/'manifest.json'))
    assert not m['built'] and not m['installed']
    test_names=('zero_noise_selftest_r6','peak_selftest_r2','display_selftest_r2','collector_selftest_r1')
    tests={name:json.loads(u.read(c/name/'report.json')) for name in test_names}
    assert all(r['passed'] for r in tests.values())
    out=c/'verification';out.mkdir(exist_ok=True)
    ui=subprocess.run(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],
        capture_output=True,text=True,check=True,timeout=20)
    frontend=json.loads(ui.stdout);assert frontend['passed']
    u.write(out/'frontend.json',json.dumps(frontend,indent=2)+'\n')
    for f in (c/'web_hmi/server.py',p.ROOT/'tools/current_zero_quality.py',p.ROOT/'tools/install_current_zero_noise.py'):
        ast.parse(u.read(f),filename=str(f))
    h=decoder(c)
    fixture=json.loads(u.read(c/'zero_noise_selftest_r6/decoded.json'))
    line=('DATA state=SAFE mode=VF pwm=0 fw_build=2026102505 bp_fw_build=2026102506 '
          'bp_mcsdk_telemetry=1 bp_age_ms=20 bp_rsp_age_ms=20 bp_status=0 '
          'mc_current_age_ms=10 mc_current_detail_age_ms=10 mc_current_quality_age_ms=10 ')
    line+=' '.join(key+'='+fixture[key] for key in ('mc_current_packet_hex','mc_current_detail_hex',
        'mc_current_quality_hex','mc_zero_history_hex'))
    parsed=h.RpcBridge._parse_status_string(line)
    from current_zero_quality import ready
    assert parsed and ready(parsed) and parsed['mc_zero_history_valid']==1
    assert not ready(dict(parsed,mc_current_flags=17))
    assert not ready(dict(parsed,fw_build=0))
    before=dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(before,dict(before,fw_build=p.NEW[0],mc_fw_build=p.NEW[1]))
    assert h.manual_scalar_supported(dict(parsed,manual_scalar_capable=1))
    assert not h.manual_scalar_supported(dict(parsed,manual_scalar_capable=1,fw_build=0))

    # Protect installed predecessors, including hard-linked immutable vendor code.
    permitted_nuc={'nucleo/Inc/current_core.h','nucleo/Inc/current_shunt.h','nucleo/Src/current_shunt.c',
        'nucleo/Src/main.c','nucleo/STM32CubeIDE/.settings/language.settings.xml'}
    changed=[]
    for base,names in ((p.BASE,('nucleo',)),(p.UNO_BASE,('UNOQ_MOTOR','web_hmi'))):
        old_manifest=json.loads(u.read(base/'manifest.json'))
        for rel,digest in old_manifest['source_sha256'].items():
            assert u.sha(base/rel)==digest,'Installed source altered: '+rel
            if rel.split('/')[0] not in names:continue
            if (base/rel).read_bytes()==(c/rel).read_bytes():continue
            old=u.read(base/rel).replace(str(p.OLD[0]),str(p.NEW[0])).replace(str(p.OLD[1]),str(p.NEW[1]))
            if old!=u.read(c/rel):
                if rel.startswith('nucleo/'):assert rel in permitted_nuc,rel
                changed.append(rel)
    old_core=u.read(p.BASE/'nucleo/Inc/current_core.h');new_core=u.read(c/'nucleo/Inc/current_core.h')
    for name in ('cm_sample','cm_window_valid','cm_publish','cm_choose_pair','cm_pair_window'):
        assert function(old_core,name)==function(new_core,name),name
    old_adc=u.read(p.BASE/'nucleo/Src/current_shunt.c');new_adc=u.read(c/'nucleo/Src/current_shunt.c')
    assert function(old_adc,'queue_pair')==function(new_adc,'queue_pair')
    irq=function(new_adc,'mic_current_adc_irq')
    assert irq.index('queue_pair(pair)')<irq.index('cm_sample(')
    assert 'if(!peak.frozen && (active || peak.running))' in irq
    assert (c/'nucleo/Src/stm32g4xx_mc_it.c').read_bytes()==(p.BASE/'nucleo/Src/stm32g4xx_mc_it.c').read_bytes()
    for rel in ('uart_v3_transport.h','peak_wire.h'):
        assert u.read(c/'UNOQ_MOTOR'/rel)==u.read(p.UNO_BASE/'UNOQ_MOTOR'/rel)
    # The actual display implementation and MCU power/service code are exact.
    old_uno=u.read(p.UNO_BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    new_uno=u.read(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    for name in ('matrix_set_pixel','matrix_draw_digit','control_step','manual_watchdog_tick','hard_stop','request_normal_stop'):
        assert function(old_uno,name)==function(new_uno,name),name
    assert 'if(g_zero_history.complete)' in new_uno
    assert '!g_pwm_enabled' not in new_uno[new_uno.index('if(g_zero_history.complete)'):new_uno.index('if(g_zero_history.complete)')+50]
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
    packet_stack=int(re.search(r':mic_current_packet\s+(\d+)\s',stack)[1]);assert packet_stack<=512
    summary=dict(passed=True,hardware_commands=0,installed=False,
        physical_noise_source_identified=False,physical_zero_verified=False,
        synthetic_old_failure_reproduced=True,actual_raw_time_series_available=False,
        zero_checks=tests['zero_noise_selftest_r6']['checks'],independent_long_double_variance_trials=3000,
        actual_irq_and_peak_checks=tests['peak_selftest_r2']['checks'],display_checks=tests['display_selftest_r2']['checks'],
        frontend_checks=frontend['checks'],production_rpc_parser_roundtrip=True,
        nucleo_ram_above_min_heap_stack_bytes=margin,adc_irq_stack_bytes=irq_stack,current_packet_stack_bytes=packet_stack,
        control_and_running_current_math_unchanged=True,adc_queue_published_before_statistics=True,
        source_changes_beyond_identity=changed,
        limitation='Mean uncertainty is an engineering estimate using raw and64-sample-group variances plus three-block consistency; hardware calibration/current scale and actual ISR timing still require measurement.',
        sources=['https://www.st.com/resource/en/application_note/cd00211314-how-to-optimize-the-adc-accuracy-in-the-stm32-mcus-stmicroelectronics.pdf',
                 'https://www.st.com/resource/en/application_note/an5346-stm32g4-adc-use-tips-and-recommendations-stmicroelectronics.pdf'])
    u.write(out/'report.json',json.dumps(summary,indent=2)+'\n')
    m.update(built=True,selftest_pass=True,verification_summary=summary,
        zero_quality_method='max(raw-sample and four64-sample-group estimated mean variance):3sigma<=2counts; three consecutive block means drift<=2counts',
        installed=False,zero_span_limit_counts=None,zero_per_block_limits_unchanged=False)
    def hashes(files):
        return {str(f.relative_to(c)).replace('\\','/'):u.sha(f) for f in sorted(files) if f.is_file()}
    m['source_sha256']=hashes(f for name in ('nucleo','UNOQ_MOTOR','web_hmi') for f in (c/name).rglob('*')
        if not any(x in f.relative_to(c).parts for x in ('Debug','Release','__pycache__')))
    m['build_sha256']=hashes((c/'build').rglob('*'))
    m['verification_sha256']=hashes(f for name in test_names+('verification',) for f in (c/name).rglob('*'))
    u.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(summary))


if __name__=='__main__':main()
