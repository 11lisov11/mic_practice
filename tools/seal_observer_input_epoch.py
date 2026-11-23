"""Seal host-checked candidate, retain all old captures, never contact boards."""
import json
import subprocess
from elftools.elf.elffile import ELFFile
import prepare_observer_input_epoch as p
from probe_native_programming_state import programmed_hex_image


def main():
    manifest=json.loads(p.read(p.OUT/'manifest.json'))
    assert not manifest['installed'] and not manifest['built']
    assert json.loads(p.read(p.OUT/'verification/report.json'))['passed']
    assert json.loads(p.read(p.OUT/'model_verification/model_report.json'))['passed']
    assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
    u=json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    assert u['firmware_build_id']==p.NEW[0]
    assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
    for a in u['artifacts']:
        assert p.sha(p.OUT/'build/uno'/a['file'])==a['sha256'].lower()
    preserved=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
    preserved.update(json.loads(p.read(p.BASE/'preserved_capture_hashes.json')))
    for rel,digest in preserved.items():assert p.sha(p.ROOT/rel)==digest,rel
    p.write(p.OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2)+'\n')
    for rel,digest in json.loads(p.read(p.BASE/'source_hashes.json')).items():
        assert p.sha(p.BASE/rel)==digest,rel
    native=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL'
    image,holes=programmed_hex_image(native.with_suffix('.hex'),native.with_suffix('.bin').read_bytes())
    ram={}
    with native.with_suffix('.elf').open('rb') as f:
        elf=ELFFile(f)
        for section in elf.iter_sections():
            if section['sh_flags']&2 and 0x20000000<=section['sh_addr']<0x20008000:
                ram[section.name]=int(section['sh_size'])
    assert sum(ram.values())<32768
    release=p.OUT/'release';release.mkdir(exist_ok=False)
    copies=[(native.with_suffix('.hex'),f'nucleo_{p.NEW[1]}_observer_input.hex'),
        (p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',f'uno_{p.NEW[0]}_observer_trace.elf-zsk.bin')]
    for source,name in copies:(release/name).write_bytes(source.read_bytes())
    (release/f'nucleo_{p.NEW[1]}_expected_readback.bin').write_bytes(image)
    sources={}
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts:
                sources[f.relative_to(p.OUT).as_posix()]=p.sha(f)
    p.write(p.OUT/'source_hashes.json',json.dumps(sources,indent=2)+'\n')
    manifest.update(built=True,installed=False,hardware_commands=0,
        hardware_validated=False,host_tests_passed=True,model_tests_passed=True,
        native_flash_bytes=len(image),hex_padding_offsets=holes,
        artifacts={f.relative_to(p.OUT).as_posix():p.sha(f) for f in release.iterdir()},
        RAM_sections=ram,RAM_allocated=sum(ram.values()),RAM_unallocated=32768-sum(ram.values()),
        preserved_files_verified=len(preserved),source_files=len(sources),
        target_timing_measured=False)
    p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))


if __name__=='__main__':main()
