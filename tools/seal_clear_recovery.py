"""Seal1605/1606 offline; keep previous captures and all physical checks pending."""
import ast,inspect,json,re,subprocess
import prepare_clear_recovery as p
import seal_observer_input_epoch as generic
from build_multi_native import BIN


def main():
    checks=json.loads(p.read(p.OUT/'verification/report.json'))
    telemetry=json.loads(p.read(p.OUT/'verification/telemetry/report.json'))
    model=json.loads(p.read(p.OUT/'model_verification/model_report.json'))
    assert checks['passed'] and telemetry['passed'] and model['passed']
    assert model['baseline_candidate_model_trajectories_identical']
    ast.parse(p.read(p.OUT/'web_hmi/server.py'))
    modified=[]
    for rel in json.loads(p.read(p.BASE/'source_hashes.json')):
        baseline=p.read(p.BASE/rel).replace('2026111603',str(p.NEW[0])).replace('2026111604',str(p.NEW[1]))
        if baseline!=p.read(p.OUT/rel):modified.append(rel)
    assert set(modified)=={'nucleo/Src/main.c','UNOQ_MOTOR/UNOQ_MOTOR.ino','web_hmi/server.py'},modified
    scopes={}
    for label,folder in [('baseline',p.BASE),('candidate',p.OUT)]:
        elf=folder/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
        asm=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d',str(elf)],text=True)
        p.write(p.OUT/f'verification/ARM_{label}.txt',asm)
        scopes[label]={}
        for name in ('ma_native_fast','ma_native_profile_tick'):
            m=re.search(r'^\w+ <'+name+r'>:\n(.*?)(?=^\w+ <|\Z)',asm,re.M|re.S);assert m,name
            scopes[label][name]=re.findall(r'\bbl(?:\.w)?\s+[^<\n]+<([^>]+)>',m[1])
    assert scopes['baseline']==scopes['candidate']
    p.write(p.OUT/'verification/ARM_scope.json',json.dumps(dict(passed=True,scopes=scopes,
        modified_source_files=modified,FAST_call_scope_unchanged=True,target_cycles_measured=False),indent=2)+'\n')
    manifest=json.loads(p.read(p.OUT/'manifest.json'))
    # Installed predecessor's measurements/receipts are not candidate evidence.
    remove=('installed_reports','installation_acceptance_SHA256','manual_RESET','programming_resets_per_recipe',
        'nucleo_flash_commands','uno_flash_commands','hardware_validation_scope','hardware_commands_scope')
    for key in list(manifest):
        if key in remove or key.startswith('measured_'):manifest.pop(key)
    manifest.update(previous_measured_OFF_fast_cycles=3618,previous_measurement_is_candidate_measurement=False,
        diagnostic_mask_scope='first_retained_not_live',ordinary_receiver_freshness_unchanged=True,
        target_timing_measured=False,target_timing_measured_OFF=False,target_timing_requalification_required=True,
        observer_validity_problem_solved=False)
    p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    source=inspect.getsource(generic.main).replace('_observer_input.hex','_clear_recovery.hex').replace('_observer_trace.elf-zsk.bin','_clear_recovery.elf-zsk.bin')
    scope=dict(generic.__dict__,p=p);exec(compile(source,__file__,'exec'),scope);scope['main']()
    manifest=json.loads(p.read(p.OUT/'manifest.json'))
    manifest.update(verification_reports={rel:p.sha(p.OUT/rel) for rel in (
        'verification/report.json','verification/telemetry/report.json','verification/ARM_scope.json',
        'model_verification/model_report.json','nucleo_build_report.json','build/uno/unoq_mcsdk_scalar.build-manifest.json')},
        qualified=False,OFF_CPU_qualified=False,FOC_start_ready=False,hardware_validated=False,
        physical_CLEAR_recovery_verified=False,full_stack_high_water_measured=False)
    p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pair=list(p.NEW),built=True,installed=False,
        preserved_files_verified=manifest['preserved_files_verified'],RAM_unallocated=manifest['RAM_unallocated'],
        target_CPU_qualification_required=True,hardware_commands=0)))


if __name__=='__main__':main()
