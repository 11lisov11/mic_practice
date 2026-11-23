"""Seal offline observer diagnostics, preserving all earlier evidence."""
import hashlib,json,re,shutil,subprocess
from elftools.elf.elffile import ELFFile
from build_multi_native import BIN
import prepare_observer_trace as p


def sha(f):
    with f.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
    tests=json.loads(p.read(p.OUT/'verification/selftest.json'));model=json.loads(p.read(p.OUT/'verification/model_report.json'))
    assert tests['passed'] and model['passed'] and model['baseline_candidate_model_trajectories_identical']
    assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
    assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
    assert json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))['firmware_build_id']==p.NEW[0]
    for rel,digest in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert sha(p.BASE/rel)==digest,rel
    preserved=json.loads(p.read(p.BASE/'verification/preserved_captures_sha256.json'))
    for rel,digest in preserved.items():assert sha(p.ROOT/rel)==digest,rel
    for folder in p.BASE.iterdir():
        if folder.is_dir() and folder.name not in ('nucleo','UNOQ_MOTOR','libraries','web_hmi','build','release'):
            for f in folder.rglob('*'):
                if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=sha(f)
    # Validate the post-install and successful powered run's own sealed records.
    for name in ('post_install_readback_r1','powered_FOC_boot_capture_20261030_r1'):
        directory=p.BASE/name
        for rel,digest in json.loads(p.read(directory/'saved_files_sha256.json')).items():assert sha(directory/rel)==digest,rel
    p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2)+'\n')
    elf_path=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    with elf_path.open('rb') as stream:
        e=ELFFile(stream);symbols={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
        def raw(name,size):
            s=symbols[name];section=e.get_section(s['st_shndx']);off=s['st_value']-section['sh_addr'];return section.data()[off:off+size]
        from configure_multi_algorithm import load
        _,profile,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
        assert raw('model',52)==profile and raw('qualification',1)==bytes([128])
        ram=sum(e.get_section_by_name(s)['sh_size'] for s in ('.data','.bss','.noinit','._user_heap_stack'))
        assert ram<32768 and e.get_section_by_name('.noinit')['sh_size']==32
        trace_size=symbols['observer_trace']['st_size'];assert trace_size<1900
        units=[]
        for cu in e.get_dwarf_info().iter_CUs():
            a=cu.get_top_DIE().attributes.get('DW_AT_name')
            if a and 'live_bench_' in a.value.decode(errors='replace'):
                name=a.value.decode().replace('\\','/');assert (p.OUT/'nucleo').as_posix() in name,name;units.append(name)
    for name in ('ma_native_fast','ma_native_service','ma_observer_trace_packet','SystemInit'):
        asm=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d','--disassemble='+name,str(elf_path)],text=True)
        assert '<'+name+'>:' in asm
        if name!='SystemInit':assert 'cpsid' not in asm.lower() and 'primask' not in asm.lower()
        p.write(p.OUT/'verification'/('ARM_'+name+'.txt'),asm)
    stack=p.OUT/'nucleo/STM32CubeIDE/Debug/Application/User/multi_native.su'
    stack_text=p.read(stack);p.write(p.OUT/'verification/native_stack_usage.txt',stack_text)
    release=p.OUT/'release';release.mkdir(exist_ok=True)
    for name,src in [('nucleo_2026103016_observer_trace.bin',elf_path.with_suffix('.bin')),
                     ('unoq_2026103015_observer_trace.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')]:shutil.copy2(src,release/name)
    hashes={}
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts:hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
    rel='nucleo/STM32CubeIDE/STM32G431RBTX_FLASH.ld';hashes[rel]=sha(p.OUT/rel)
    p.write(p.OUT/'source_hashes.json',json.dumps(hashes,indent=2)+'\n')
    m.update(built=True,installed=False,selftests_passed=True,model_checks_passed=True,
        model_scientific_speed_qualification=False,model_parameter_mismatch_detected=True,
        RAM_allocated=ram,RAM_unallocated=32768-ram,recorder_state_bytes=trace_size,
        exact_calculated_profile=True,preserved_files_verified=len(preserved),source_files_hashed=len(hashes),
        target_diagnostic_timing_not_measured=True,first_powered_trial_not_authorized=True,
        artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pair=list(p.NEW),installed=False,RAM_allocated=ram,
        RAM_unallocated=32768-ram,recorder_bytes=trace_size,preserved_files=len(preserved),artifacts=m['artifacts'])))


if __name__=='__main__':main()
