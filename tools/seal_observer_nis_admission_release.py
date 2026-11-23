"""Offline acceptance and readback assets for the matched NIS admission release."""
import json
import runpy
import shutil
import struct
import subprocess

from elftools.elf.elffile import ELFFile

import build_observer_nis_admission_release as release
from check_recorded_nis_admission import audit_trace
from observer_exact_peak_decode import exact_pc_crc
from probe_native_programming_state import programmed_hex_image
from replay_start_history import ArmObserver
from test_rpc_capture_pages import STUBS, RUN


def verify_page_contract(output):
    sketch = release.read(release.OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    begin = sketch.index('static String rpc_capture_page')
    end = sketch.index('static String rpc_get()', begin)
    cpp = output/'page_fixture.cpp'
    release.write(cpp, STUBS+sketch[begin:end]+RUN)
    exe = cpp.with_suffix('.exe')
    subprocess.run([shutil.which('g++'), '-std=c++17', str(cpp), '-o', str(exe)], check=True, timeout=40)
    names = ('ADC_peak.bin', 'observer_trace.bin')
    result = {}
    for name in names:
        raw = bytearray((release.CURRENT/'paged_capture'/name).read_bytes())
        assert struct.unpack_from('<I', raw, 8)[0]==release.OLD[1]
        struct.pack_into('<I', raw, 8, release.NEW[1])
        struct.pack_into('<I', raw, 60, exact_pc_crc(raw))
        (output/name).write_bytes(raw)
        result[name]=bytes(raw)
    pages = subprocess.check_output([str(exe), *(str(output/name) for name in names)],
        timeout=10, text=True).splitlines()
    assert len(pages)==22 and pages[-3:]==['ERR RUN']*3
    assert pages[16:18]==['ERR PAGE', 'ERR NOT_COMPLETE'] and pages[18].startswith('NH 77 1 524 ')
    hmi = runpy.run_path(str(release.OUT/'web_hmi/server.py'))
    def fetch(kind, index):
        part, size = hmi['CAPTURE_PAGES'][kind]
        return hmi['parse_capture_page'](pages[(0 if part==3 else 6)+index], part, index, size)
    for kind, name in zip(('adc', 'observer'), names):
        assert hmi['receive_capture_pages'](fetch, kind)==result[name]
    wrong_fw = pages[0].replace(str(release.NEW[1]), str(release.OLD[1]))
    try:
        hmi['parse_capture_page'](wrong_fw, 3, 0, 1024)
    except ValueError:
        pass
    else:
        raise AssertionError('Stale firmware capture accepted')
    return {'roundtrip_pages':16, 'negative_cases':['RUN', 'outputs_active', 'peer_PWM_active',
        'bad_page', 'record_not_complete', 'stale_firmware'], 'old_files_read_only':True}


def seal():
    out = release.OUT
    release.verify_inventory(release.read_json(out/'source_hashes.json'), out)
    protected = release.read_json(out/'preserved_inputs_sha256.json')
    release.verify_inventory(protected, release.ROOT)
    native = release.read_json(out/'nucleo_build_report.json')
    assert native['passed'] and native['build_id']==release.NEW[1] and native['errors']==native['warnings']==0
    uno_dir = out/'build/uno'
    uno = release.read_json(uno_dir/'unoq_mcsdk_scalar.build-manifest.json')
    assert uno['firmware_build_id']==release.NEW[0]
    assert uno['transport']=='Serial1 / D0-D1, 921600 8N1, protocol v0x03'
    release.verify_inventory({item['file']:item['sha256'].lower() for item in uno['artifacts']}, uno_dir)
    evidence = release.read_json(release.ANALYSIS/'verification.json')
    assert evidence['native']['candidate']['OFF_cases']==64
    assert evidence['native']['candidate']['checks']==21

    db = 'nucleo/STM32CubeIDE/Debug'
    obj = db+'/Application/User/multi_native.o'
    with (release.BASE/obj).open('rb') as before, (out/obj).open('rb') as after:
        original, candidate = ELFFile(before), ELFFile(after)
        same = {name:original.get_section_by_name('.text.'+name).data()==
                candidate.get_section_by_name('.text.'+name).data()
                for name in ('ma_native_fast','mic_observer_step','mic_observer_noise')}
    assert all(same.values()), same
    native_image = out/db/'ACIM-NUCLEOG431RB-IPM15B-VF_OL'
    elf = native_image.with_suffix('.elf')
    arm = ArmObserver(elf)
    trace = release.read_json(release.CURRENT/'observer_trace_decoded.json')
    replay = audit_trace(trace, arm)
    assert replay['bit_exact_ARM_words']==51 and replay['step']==567
    with elf.open('rb') as stream:
        names = {sym.name:int(sym['st_value']) for sym in ELFFile(stream).get_section_by_name('.symtab').iter_symbols()}
    assert names['_estack']-names['__StackLimit']==4096 and names['_end']+512<=names['__StackLimit']

    verification = out/'verification'
    verification.mkdir()
    page_check = verify_page_contract(verification)
    release_images = out/'release'
    release_images.mkdir()
    for ext in ('hex','elf','bin'):
        shutil.copyfile(native_image.with_suffix('.'+ext), release_images/f'nucleo_{release.NEW[1]}_nis_admission.{ext}')
    readback, holes = programmed_hex_image(native_image.with_suffix('.hex'), native_image.with_suffix('.bin').read_bytes())
    (release_images/f'nucleo_{release.NEW[1]}_expected_readback.bin').write_bytes(readback)
    shutil.copyfile(uno_dir/'UNOQ_MOTOR.ino.elf-zsk.bin', release_images/f'uno_{release.NEW[0]}_nis_admission.elf-zsk.bin')

    release.verify_inventory(protected, release.ROOT)
    release.save(verification/'report.json', {'passed':True,'actual_release_ARM_replay':replay,
        'byte_identical_ARM_sections':same,'native_readback_bytes':len(readback),'hex_erased_padding_offsets':holes,
        'stack_reserve':4096,'heap_reserve':512,'page_contract':page_check,'physical_timing_measured':False,
        'protected_files_verified':len(protected),'hardware_commands':0})
    files = [*release_images.iterdir(), out/'web_hmi/server.py', out/'web_hmi/static/app.js', out/'web_hmi/static/index.html']
    manifest = {**release.read_json(out/'preparation.json'), 'built':True, 'offline_acceptance_passed':True,
        'motor_run_tested':False,'NIS_model_error_fixed':False,
        'artifacts':{path.relative_to(out).as_posix():release.digest(path) for path in files}}
    release.save(out/'release_manifest.json', manifest)
    print(json.dumps({'pair':release.NEW, 'passed':True,'protected_files':len(protected),
        'readback_bytes':len(readback),'pages':page_check['roundtrip_pages']}))


if __name__=='__main__':
    seal()
