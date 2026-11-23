"""Seal the built diagnostic/display package after offline checks. No device access."""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess

import prepare_current_peak_capture as p
import prepare_current_shunt_monitor as util
from audit_production_pwm_filters import function
from collect_current_peak import decoder, fresh_off


def main():
    c = p.OUT
    m = json.loads(util.read(c/'manifest.json'))
    assert not m['installed'] and not m['built'], 'Preserve sealed package'
    reports = {}
    for name in ('peak_selftest_r4','display_selftest_r1','collector_selftest_r1',
                 'core_selftest_r1','zero_selftest_r2'):
        report = json.loads(util.read(c/name/'report.json'))
        assert report['passed'], name
        reports[name] = report
    out = c/'verification'
    out.mkdir(exist_ok=False)
    ui = subprocess.run(['node', str(p.ROOT/'tools/current_shunt_ui_selftest.js'),
                         str(c/'web_hmi/static/app.js')], capture_output=True,text=True,check=True,timeout=20)
    frontend = json.loads(ui.stdout)
    assert frontend['passed']
    util.write(out/'frontend.json',json.dumps(frontend,indent=2)+'\n')
    for script in (c/'web_hmi/server.py',p.ROOT/'tools/collect_current_peak.py',
                   p.ROOT/'tools/install_current_peak_capture.py'):
        ast.parse(util.read(script), filename=str(script))

    # Full production parser -> current aliases -> new trace decoder, not only
    # an isolated Python decoder test. No RouterClient is instantiated.
    module = decoder()
    raw = (c/'peak_selftest_r4/trace.bin').read_bytes()
    text = ('DATA state=SAFE mode=VF pwm=0 fw_build=2026102501 bp_fw_build=2026102502 '
            'bp_mcsdk_telemetry=1 bp_age=20 bp_rsp_age_ms=20 bp_status=0 '
            'mc_adc_peak_hex='+raw.hex()+' mc_adc_peak_complete=1 mc_adc_peak_good=35 mc_adc_peak_bad=0')
    parsed = module.RpcBridge._parse_status_string(text)
    assert parsed and parsed['mc_adc_peak_valid']==1 and parsed['mc_adc_peak_hex']==raw.hex()
    assert parsed['mc_adc_peak']['sample_count']==12
    assert fresh_off(dict(parsed,mc_age_ms=20))
    assert not fresh_off(dict(parsed,pwm=1,mc_age_ms=20))
    assert not fresh_off(dict(parsed,mc_age_ms=300))
    assert not fresh_off(dict(parsed,mc_age_ms=float('nan')))
    assert module.with_adc_peak(dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],mc_adc_peak_hex=raw.hex()))['mc_adc_peak_valid']==0
    util.write(out/'rpc_parser.json',json.dumps(dict(passed=True,production_parser=True,
        trace_hex_preserved=True,off_freshness_negative_controls=True,hardware_commands=0),indent=2)+'\n')

    old_manifest=json.loads(util.read(p.BASE/'manifest.json'))
    allowed={'nucleo/Inc/current_shunt.h','nucleo/Src/current_shunt.c','nucleo/Src/main.c',
             'nucleo/Src/stm32g4xx_mc_it.c','nucleo/STM32CubeIDE/.settings/language.settings.xml',
             'UNOQ_MOTOR/UNOQ_MOTOR.ino','web_hmi/server.py','web_hmi/static/app.js'}
    changed=[]
    for rel,digest in old_manifest['source_sha256'].items():
        assert util.sha(p.BASE/rel)==digest, 'Installed predecessor altered: '+rel
        assert (c/rel).is_file(), rel
        if (p.BASE/rel).read_bytes()!=(c/rel).read_bytes():
            before=util.read(p.BASE/rel).replace(str(p.OLD[0]),str(p.NEW[0])).replace(str(p.OLD[1]),str(p.NEW[1]))
            if before!=util.read(c/rel):
                assert rel in allowed, 'Unreviewed change: '+rel
                changed.append(rel)
    # Current filter, zero, timing predicate, context queue, ADC setup, power
    # timer and all vendor modulation/transport implementations stay exact.
    old=util.read(p.BASE/'nucleo/Src/current_shunt.c')
    new=util.read(c/'nucleo/Src/current_shunt.c')
    for name in ('queue_pair','mic_current_packet'):
        assert function(old,name)==function(new,name), name
    irq=util.read(c/'nucleo/Src/stm32g4xx_mc_it.c')
    assert irq.replace('    mic_current_update_epoch();\n','')==util.read(p.BASE/'nucleo/Src/stm32g4xx_mc_it.c')
    assert (c/'nucleo/Inc/current_core.h').read_bytes()==(p.BASE/'nucleo/Inc/current_core.h').read_bytes()
    uno=util.read(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    assert '#define USE_ROUTER_BRIDGE 1' in uno and 's.reserve(8192);' in uno
    # Diagnostic string construction is outside the short timing snapshot lock.
    rpc=function(uno,'rpc_get')
    assert rpc.index('irq_unlock(timing_key)')<rpc.index('mc_adc_peak_hex=')

    debug=c/'nucleo/STM32CubeIDE/Debug'
    for item in debug.iterdir():
        if item.is_file() and (item.name.startswith('ACIM-NUCLEOG431RB-IPM15B-VF_OL.') or item.name=='mcsdk_release_preflight.json'):
            shutil.copyfile(item,c/'build/nucleo'/item.name)
    for folder,name,build in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
        build_manifest=json.loads(util.read(c/'build'/folder/(name+'.build-manifest.json')))
        assert build_manifest['firmware_build_id']==build
        if folder=='nucleo':
            assert build_manifest['build_errors']==0 and build_manifest['build_warnings']==0
        for item in build_manifest['artifacts']:
            assert util.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
    assert json.loads(util.read(c/'build/uno/llext-check.json'))['pass']
    map_text=util.read(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map')
    end=int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',map_text)[1],16)
    margin=0x20008000-end-0x600
    assert margin>=4096
    stack=util.read(debug/'Application/User/current_shunt.su')
    irq_stack=int(re.search(r':mic_current_adc_irq\s+(\d+)\s',stack)[1])
    assert irq_stack<=384
    summary=dict(passed=True,hardware_commands=0,installed=False,
        physical_measurements_verified=False,physical_display_verified=False,hardware_irq_timing_verified=False,
        capture_irq_checks=reports['peak_selftest_r4']['checks'],
        core_checks=reports['core_selftest_r1']['core']['checks'],
        display_checks=reports['display_selftest_r1']['checks'],frontend_checks=frontend['checks'],
        production_rpc_parser_roundtrip=True,source_predecessor_hashes_verified=len(old_manifest['source_sha256']),
        changed_files_beyond_identity=changed,nucleo_ram_above_min_heap_stack_bytes=margin,
        adc_irq_stack_bytes=irq_stack,scale_qualified=False,
        limitations=['Raw ADC is not an independent measurement of actual current.',
          'CCR-at-update is a software latch; epoch races are recorded.',
          'First threshold crossing only; STOP may freeze a shorter/no-peak record.',
          'Host checks do not qualify actual ISR execution time or motor current scale.',
          'Build preflight remains non-gating and is not an HV release approval.'])
    util.write(out/'report.json',json.dumps(summary,indent=2)+'\n')
    m.update(built=True,selftest_pass=True,installed=False,verification_summary=summary,
        zero_acceptance_unchanged=True,display_inverted_mount_fixed=True,
        display_axis_mapping='raw_x=logical_x, raw_y=7-logical_y; 180 degrees relative to previous frame',
        display_physical_verification_pending=True,peak_capture_hardware_verified=False)
    def hashes(paths):
        return {str(path.relative_to(c)).replace('\\','/'):util.sha(path)
                for path in sorted(paths) if path.is_file()}
    sources=[]
    for folder in ('nucleo','UNOQ_MOTOR','web_hmi'):
        sources.extend(path for path in (c/folder).rglob('*') if path.is_file()
            and not any(part in ('Debug','Release','__pycache__') for part in path.relative_to(c).parts))
    m['source_sha256']=hashes(sources)
    m['build_sha256']=hashes((c/'build').rglob('*'))
    folders=list(reports)+['verification']
    m['verification_sha256']=hashes(path for folder in folders for path in (c/folder).rglob('*'))
    util.write(c/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':
    main()
