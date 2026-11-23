"""Seal offline1601/1602 with evidence and explicit unresolved-observer limits."""
import inspect,json,re,subprocess
import prepare_observer_adc_delivery as p
import seal_observer_input_epoch as generic
from build_multi_native import BIN


def main():
    t=json.loads(p.read(p.OUT/'verification/report.json'))
    model=json.loads(p.read(p.OUT/'model_verification/model_report.json'))
    assert t['passed'] and model['passed'] and model['baseline_candidate_model_trajectories_identical']
    unchanged=[];modified=[]
    expected_modified={'nucleo/Inc/peak_core.h','nucleo/Inc/current_shunt.h',
        'nucleo/Src/main.c','nucleo/Src/current_shunt.c','nucleo/Src/multi_native.c','web_hmi/server.py'}
    for rel,digest in json.loads(p.read(p.BASE/'source_hashes.json')).items():
        a=p.read(p.BASE/rel).replace('2026111503',str(p.NEW[0])).replace('2026111504',str(p.NEW[1]))
        b=p.read(p.OUT/rel)
        if a==b:unchanged.append(rel)
        else:modified.append(rel)
    assert set(modified)==expected_modified,modified
    assert p.read(p.BASE/'nucleo/Inc/foc_experiment.h')==p.read(p.OUT/'nucleo/Inc/foc_experiment.h')
    arm={}
    for label,folder in [('baseline',p.BASE),('candidate',p.OUT)]:
        elf=folder/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
        asm=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d',str(elf)],text=True)
        p.write(p.OUT/f'verification/ARM_{label}.txt',asm)
        scopes={}
        for name in ('ma_native_fast','ma_native_profile_tick'):
            match=re.search(r'^\w+ <'+re.escape(name)+r'>:\n(.*?)(?=^\w+ <|\Z)',asm,re.M|re.S)
            assert match,name
            scopes[name]=re.findall(r'\bbl(?:\.w)?\s+[^<\n]+<([^>]+)>',match[1])
            assert 'mic_current_request_observer_capture' not in scopes[name]
        arm[label]=scopes
    assert arm['baseline']==arm['candidate'],'New calls in fast/profiling path'
    arm.update(passed=True,unchanged_FAST_call_scope=True,fast_cycle_claim=False,
        native_profiling_and_all_protection_headers_unchanged=True,unchanged_source_files=len(unchanged),
        intentionally_modified_source_files=modified)
    p.write(p.OUT/'verification/ARM_scope.json',json.dumps(arm,indent=2)+'\n')
    source=inspect.getsource(generic.main).replace('_observer_input.hex','_observer_adc_delivery.hex').replace('_observer_trace.elf-zsk.bin','_observer_adc_delivery.elf-zsk.bin')
    scope=dict(generic.__dict__,p=p);exec(compile(source,__file__,'exec'),scope);scope['main']()
    m=json.loads(p.read(p.OUT/'manifest.json'))
    m.update(verification_reports={rel:p.sha(p.OUT/rel) for rel in (
        'verification/report.json','verification/ARM_scope.json','model_verification/model_report.json',
        'nucleo_build_report.json','build/uno/unoq_mcsdk_scalar.build-manifest.json')},
        qualified=False,OFF_CPU_qualified=False,FOC_start_ready=False,
        observer_validity_problem_solved=False,observer_physical_root_cause_proven=False,
        target_timing_requalification_required=True,hardware_commands=0,installed=False)
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pair=list(p.NEW),installed=False,hardware_commands=0,
        preserved_files_verified=m['preserved_files_verified'],RAM_unallocated=m['RAM_unallocated'])))


if __name__=='__main__':main()
