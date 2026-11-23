"""Seal equivalent fast-path candidate and preserved evidence, offline only."""
import hashlib,json,re,shutil,subprocess
from elftools.elf.elffile import ELFFile
import prepare_foc_fast_budget_fix as p
from build_multi_native import BIN

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
    m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed']
    for rel in ('verification/selftest.json','verification/path_tests.json','nucleo_build_report.json'):
        assert json.loads(p.read(p.OUT/rel))['passed'],rel
    assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
    assert json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))['firmware_build_id']==p.NEW[0]
    model=json.loads(p.read(p.OUT/'model_verification/report.json'))
    old_model=p.ROOT/'artifacts/live_bench_20261029/estimated_foc_trial_r5/model_verification_final/report.json'
    assert model['scenarios']==json.loads(p.read(old_model))['scenarios']
    assert model['actual_c_kernel_sha256']==sha(p.OUT/'nucleo/Inc/motor_control.h')
    assert sum(r['passed'] for r in model['scenarios'])==54
    assert all(r['passed'] for r in model['scenarios'] if r['label']=='central')
    from configure_multi_algorithm import load
    _,raw,_=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
    ef=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    with ef.open('rb') as stream:
        elf=ELFFile(stream);syms={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
        def symbol_data(name,n):
            x=syms[name];sec=elf.get_section(x['st_shndx']);offset=x['st_value']-sec['sh_addr'];return sec.data()[offset:offset+n]
        assert symbol_data('model',52)==raw and symbol_data('qualification',1)==bytes([128])
        for name in ('mic_foc_irq_meter','ma_perf','ma_first_runtime','ma_observer_active','fe_trial_done','fe_trial_begin'):
            assert name in syms,name
        units=[]
        for cu in elf.get_dwarf_info().iter_CUs():
            a=cu.get_top_DIE().attributes.get('DW_AT_name')
            if a and 'live_bench_20261029' in a.value.decode(errors='replace'):
                n=a.value.decode(errors='replace').replace('\\','/')
                assert (p.OUT/'nucleo').as_posix() in n,n
                units.append(n)
        assert any(n.endswith('multi_native.c') for n in units)
        default=int(syms['Default_Handler']['st_value'])&~1
        vectors=elf.get_section_by_name('.isr_vector').data();active={}
        for i in range(2,len(vectors)//4):
            addr=int.from_bytes(vectors[4*i:4*i+4],'little')&~1
            if not addr or addr==default:continue
            active[i]=[s.name for s in syms.values() if (int(s['st_value'])&~1)==addr and s['st_size']]
        expected={'ADC1_2_IRQHandler','TIM1_UP_TIM16_IRQHandler','TIM1_BRK_TIM15_IRQHandler',
            'USART2_IRQHandler','SysTick_Handler','EXTI15_10_IRQHandler',
            'DMA2_Channel1_IRQHandler','DMA1_Channel1_IRQHandler','USART1_IRQHandler'}
        found={name for group in active.values() for name in group}
        assert expected <= found and found <= expected|{'HardFault_Handler'}
        ram=int(elf.get_section_by_name('.bss')['sh_size'])+int(elf.get_section_by_name('.data')['sh_size'])
        assert ram+1536<32768
    disassembly=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d','--disassemble=ma_native_fast',str(ef)],text=True)
    assert '<ma_native_fast>:' in disassembly and '<lroundf>' not in disassembly
    p.write(p.OUT/'verification/fast_control_disassembly.txt',disassembly)
    p.write(p.OUT/'verification/elf_identity.json',json.dumps(dict(passed=True,profile_bytes_exact=True,
        qualification=128,source_units=units,actual_vector_handlers=active,
        all_returning_handlers_instrumented=True,static_RAM_bytes=ram,RAM_after_static_bytes=32768-ram,
        fast_path_lroundf_call_removed=True,target_cycles_measured=False),indent=2)+'\n')
    # Source-level equality with baseline after ID substitution: every ADC,
    # SD/Break, stop, UART scheduling, IRQ-accounting and observer operation.
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for f in (p.OUT/folder).rglob('*'):
            if not f.is_file() or f.suffix not in ('.c','.h','.ino'):continue
            rel=f.relative_to(p.OUT)
            if rel.as_posix() in ('nucleo/Inc/motor_control.h','nucleo/Inc/foc_experiment.h','nucleo/Src/multi_native.c'):continue
            old=p.read(p.BASE/rel).replace('2026102971','2026103001').replace('2026102972','2026103002')
            assert p.read(f)==old,rel
    from audit_production_pwm_filters import function
    old=p.read(p.BASE/'nucleo/Inc/motor_control.h');new=p.read(p.OUT/'nucleo/Inc/motor_control.h')
    for name in ('ma_motor_valid','ma_observe','ma_derivative','ma_reset','ma_margin'):
        assert function(old,name)==function(new,name),name
    native_old=p.read(p.BASE/'nucleo/Src/multi_native.c');native_new=p.read(p.OUT/'nucleo/Src/multi_native.c')
    for name in ('ma_native_service','ma_native_prepare','fe_profile_allowed','fe_profile_service'):
        assert function(native_old,name)==function(native_new,name),name
    for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert sha(p.BASE/rel)==h,rel
    preserved={}
    for name in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json'):
        preserved.update(json.loads(p.read(p.BASE/name)))
    for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
    for dirname in ('autonomous_20261030_before_FOC_r1','powered_FOC_CPU_IRQ_20261030_r1'):
        for f in (p.BASE/dirname).rglob('*'):
            if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=sha(f)
    p.write(p.OUT/'verification/preserved_captures_sha256.json',json.dumps(preserved,indent=2)+'\n')
    release=p.OUT/'release';release.mkdir(exist_ok=True)
    for name,src in [('unoq_2026103001_fast_budget.elf-zsk.bin',p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'),
                     ('nucleo_2026103002_fast_budget.bin',ef.with_suffix('.bin'))]:
        shutil.copy2(src,release/name)
    source_hashes={}
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.log'):
                source_hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
    p.write(p.OUT/'source_hashes.json',json.dumps(source_hashes,indent=2)+'\n')
    m.update(built=True,installed=False,selftests_passed=True,control_equivalence_verified=True,
        target_timing_qualification_pending=True,target_timing_measured=False,
        original_5312_cycle_and_2ms_ADC_guards_unchanged=True,
        model_study=dict(rerun=True,central_passed=4,central_total=4,sensitivity_passed=54,sensitivity_total=60,
            scenarios_identical_to_prior=True,report='model_verification/report.json',sha256=sha(p.OUT/'model_verification/report.json')),
        preserved_files_verified=len(preserved),artifacts={f.relative_to(p.OUT).as_posix():sha(f) for f in release.iterdir() if f.is_file()})
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps({k:m[k] for k in ('pair','built','installed','preserved_files_verified','artifacts')}))

if __name__=='__main__':main()
