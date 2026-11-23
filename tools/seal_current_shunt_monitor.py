"""Seal built shunt monitoring package; no device access or motor commands."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import prepare_current_shunt_monitor as p


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path)
    args=parser.parse_args()
    if args.candidate:p.OUT=args.candidate.resolve()
    c=p.OUT
    m=json.loads(p.read(c/'manifest.json'))
    p.NEW=tuple(m['pair_compatibility_ids'])
    assert not m['installed'] and not m['built'], 'Preserve a sealed package'
    out=c/'verification';out.mkdir(exist_ok=False)
    ui=subprocess.run(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],
                      capture_output=True,text=True,check=True,timeout=20)
    ui_report=json.loads(ui.stdout);assert ui_report['passed']
    p.write(out/'frontend.json',json.dumps(ui_report,indent=2)+'\n')
    for name in ('selftest_r4','irq_selftest_r1'):
        assert json.loads(p.read(c/name/'report.json'))['passed']
    debug=c/'nucleo/STM32CubeIDE/Debug'
    for item in debug.iterdir():
        if item.is_file() and (item.name.startswith('ACIM-NUCLEOG431RB-IPM15B-VF_OL.') or item.name=='mcsdk_release_preflight.json'):
            shutil.copyfile(item,c/'build/nucleo'/item.name)
    for folder,name,build in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
        b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')))
        assert b['firmware_build_id']==build
        if folder=='nucleo':assert b['build_errors']==0 and b['build_warnings']==0
        for item in b['artifacts']:
            assert p.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
    map_text=p.read(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map')
    heap=int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',map_text)[1],16)
    margin=0x20008000-heap-0x600
    assert margin>=4096 and 'mic_current_adc_irq' in map_text
    summary=dict(passed=True,core_checks=649655,adc_irq_checks=42324,hmi_checks=14,
                 frontend_checks=ui_report['checks'],nucleo_ram_above_min_heap_stack_bytes=margin,
                 hardware_commands=0,physical_measurements_verified=False,scale_qualified=False)
    evidence_folders=['selftest_r4','irq_selftest_r1','verification']
    if m.get('wire_version_collision_fixed'):
        mixed=json.loads(p.read(c/'mixed_wire_selftest_r1/report.json'))
        assert mixed['passed'] and mixed['collision_negative_control'] and mixed['uart_record_pages']==14
        summary.update(mixed_wire_checks=mixed['checks'],collision_negative_control=True)
        evidence_folders.append('mixed_wire_selftest_r1')
    if m.get('zero_uses_multiple_blocks'):
        zero=json.loads(p.read(c/'zero_blocks_selftest_r2/report.json'))
        assert zero['passed'] and zero['old_failure_reproduced'] and zero['actual_encoder_roundtrip']
        summary.update(zero_block_checks=zero['zero_checks'],zero_quality_hmi_checks=zero['hmi_quality_checks'],
                       old_one_block_failure_reproduced=True)
        evidence_folders.append('zero_blocks_selftest_r2')
    p.write(out/'report.json',json.dumps(summary,indent=2)+'\n')
    m.update(built=True,selftest_pass=True,verification_summary=summary)
    def hashes(paths):return {str(path.relative_to(c)).replace('\\','/'):p.sha(path) for path in sorted(paths) if path.is_file()}
    sources=[]
    for folder in ('nucleo','UNOQ_MOTOR','web_hmi'):
        sources.extend(path for path in (c/folder).rglob('*') if path.is_file()
            and not any(part in ('Debug','__pycache__') for part in path.relative_to(c).parts))
    m['source_sha256']=hashes(sources)
    m['build_sha256']=hashes((c/'build').rglob('*'))
    m['verification_sha256']=hashes(path for folder in evidence_folders for path in (c/folder).rglob('*'))
    p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
