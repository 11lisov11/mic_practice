"""Seal verified offline reset diagnostics; no board access."""
import hashlib
import json
import re
import shutil
import subprocess
from elftools.elf.elffile import ELFFile
from build_multi_native import BIN
import prepare_boot_reset_capture as p


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
    tests=json.loads(p.read(p.OUT/'verification/selftest.json'));assert tests['passed']
    assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
    uno=json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    assert uno['firmware_build_id']==p.NEW[0]
    assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
    for rel,digest in json.loads(p.read(p.BASE/'source_hashes.json')).items():
        assert sha(p.BASE/rel)==digest,rel
    preserved=json.loads(p.read(p.BASE/'verification/preserved_captures_sha256.json'))
    for folder in p.BASE.iterdir():
        if folder.is_dir() and folder.name not in ('nucleo','UNOQ_MOTOR','libraries','web_hmi','build','release'):
            for f in folder.rglob('*'):
                if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=sha(f)
    for rel,digest in preserved.items():assert sha(p.ROOT/rel)==digest,rel
    p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2)+'\n')
    ef=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    assembly={}
    for name in ('Reset_Handler','SystemInit','mic_boot_capture_early','mic_boot_note_software_reset','mic_send_boot_page'):
        asm=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d','--disassemble='+name,str(ef)],text=True)
        p.write(p.OUT/'verification'/('ARM_'+name+'.txt'),asm);assembly[name]=asm
    init=assembly['SystemInit']
    # CPACR write, barriers, then call: GCC emits VFP struct-copy instructions.
    assert init.index('str.w')<init.index('dsb')<init.index('isb')<init.index('<mic_boot_capture_early>')
    assert not re.search(r'\bblx?\s',assembly['mic_boot_capture_early'])
    assert '<SystemInit>' in assembly['Reset_Handler']
    with ef.open('rb') as stream:
        elf=ELFFile(stream);syms={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
        r=syms['mic_boot_retained'];noinit=elf.get_section_by_name('.noinit')
        assert r['st_size']==32 and r['st_value']==noinit['sh_addr']
        def raw(name,n):
            s=syms[name];section=elf.get_section(s['st_shndx']);off=s['st_value']-section['sh_addr']
            return section.data()[off:off+n]
        from configure_multi_algorithm import load
        _,model,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
        assert raw('model',52)==model and raw('qualification',1)==bytes([128])
        # Cross-check linker/startup evidence against ELF symbols.
        assert syms['_ebss']['st_value']<=noinit['sh_addr']
        flash=sum(seg['p_filesz'] for seg in elf.iter_segments() if seg['p_type']=='PT_LOAD')
    release=p.OUT/'release';release.mkdir(exist_ok=True)
    for name,source in [('nucleo_2026103014_boot_capture.bin',ef.with_suffix('.bin')),
                        ('unoq_2026103013_boot_capture.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')]:
        shutil.copy2(source,release/name)
    hashes={}
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts:hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
    hashes['nucleo/STM32CubeIDE/STM32G431RBTX_FLASH.ld']=sha(p.OUT/'nucleo/STM32CubeIDE/STM32G431RBTX_FLASH.ld')
    p.write(p.OUT/'source_hashes.json',json.dumps(hashes,indent=2)+'\n')
    m.update(built=True,installed=False,selftests_passed=True,ARM_startup_verified=True,
        profile_unchanged=True,RAM_allocated=tests['RAM_allocated'],RAM_unallocated=32768-tests['RAM_allocated'],
        source_files_hashed=len(hashes),preserved_files_verified=len(preserved),
        artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()},
        hardware_reset_classification_not_yet_validated=True,
        documentation=dict(reference='RM0440 rev9, 7.4.28, RCC_CSR',url='https://www.st.com/resource/en/reference_manual/rm0440-stm32g4-series-advanced-armbased-32bit-mcus-stmicroelectronics.pdf'))
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pair=m['pair'],built=True,installed=False,
        preserved_files=m['preserved_files_verified'],RAM_allocated=m['RAM_allocated'],artifacts=m['artifacts'])))


if __name__=='__main__':main()
