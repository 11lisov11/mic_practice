"""Seal the offline exact-predicate candidate; never contact hardware."""
import inspect,json,re
import seal_observer_input_epoch as old
import prepare_exact_profile_budget as p


def normalized_instructions(path):
    # Remove relocated addresses but retain actual opcode mnemonics/operands.
    result=[]
    for line in p.read(path).splitlines():
        match=re.match(r'\s*[0-9a-f]+:\s+(?:[0-9a-f]{4}\s+)+(.+)',line)
        if match:
            text=re.sub(r'\b[0-9a-f]{7,8}\b','ADDR',match[1])
            result.append(text)
    assert result,path
    return result


def main():
    tests=json.loads(p.read(p.OUT/'verification/report.json'))
    model=json.loads(p.read(p.OUT/'model_verification/model_report.json'))
    arm=json.loads(p.read(p.OUT/'verification/ARM_call_scope.json'))
    assert tests['passed'] and model['passed']
    assert model['baseline_candidate_model_trajectories_identical']
    assert arm['candidate']['fe_profile_allowed']['calls']==[]
    assert arm['candidate']['fe_profile_allowed']['vdiv']==0
    for name in ('ma_native_profile_tick','ma_native_fast'):
        calls=arm['candidate'][name]['calls']
        assert '__ieee754_hypotf' in calls and 'hypotf' in calls
    # The release still links the original library core AND public fallback.
    for name in ('hypotf','__ieee754_hypotf','__ieee754_sqrtf'):
        a=normalized_instructions(p.OUT/f'verification/baseline_{name}.txt')
        b=normalized_instructions(p.OUT/f'verification/candidate_{name}.txt')
        assert a==b,name
    assert arm['no_math_override_symbol'] and arm['original_sqrt_already_hardware']
    arm.update(passed=True,library_math_instructions_identical=True,
               protection_current_hypot_call_preserved=True,
               target_cycle_claim=False)
    p.write(p.OUT/'verification/ARM_call_scope.json',json.dumps(arm,indent=2)+'\n')
    m=json.loads(p.read(p.OUT/'manifest.json'))
    m.update(numeric_tests=tests['numeric'],unchanged_source_files=tests['unchanged_source_files'])
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    source=inspect.getsource(old.main)
    source=source.replace('_observer_input.hex','_exact_profile_budget.hex').replace('_observer_trace.elf-zsk.bin','_exact_profile_budget.elf-zsk.bin')
    scope=dict(old.__dict__,p=p)
    exec(compile(source,__file__,'exec'),scope)
    scope['main']()
    m=json.loads(p.read(p.OUT/'manifest.json'))
    m.update(verification_reports={rel:p.sha(p.OUT/rel) for rel in (
        'verification/report.json','verification/ARM_call_scope.json',
        'model_verification/model_report.json','nucleo_build_report.json',
        'build/uno/unoq_mcsdk_scalar.build-manifest.json')})
    assert m['CPU_probe_budget_cycles']==4000 and m['estimate_limit_ms']==2
    assert m['trip_A']==1.35 and m['ADC_guard_ticks']==2048
    assert m['installed']==False and m['hardware_commands']==0
    assert not m['OFF_CPU_qualified'] and not m['target_timing_measured']
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pair=m['pair'],built=m['built'],
        installed=False,preserved_files_verified=m['preserved_files_verified'],
        RAM_unallocated=m['RAM_unallocated'],native_flash_bytes=m['native_flash_bytes'],
        target_cycles_measured=False)))


if __name__=='__main__':main()
