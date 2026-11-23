"""Seal OFFLINE1611/1612 after host/model/build/evidence checks. Never flashes."""
import json,shutil
import prepare_observer_current_window as p
from analyze_observer_nis import write,sha
def main():
    assert not (p.OUT/'manifest.json').exists(),'Do not overwrite sealed candidates'
    reports={}
    for name in ('core','adapter','model'):
        r=json.loads(p.read(p.OUT/f'verification/{name}_report.json'));assert r['passed'];reports[name]=r
    assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
    assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
    # Every model trace must pass the same firmware/ABI/CRC decoder as the HMI.
    import importlib.util
    spec=importlib.util.spec_from_file_location('seal_window_hmi',p.OUT/'web_hmi/server.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    count=0
    for f in (p.OUT/'verification').glob('candidate_*.bin'):
        d=h.decode_observer_trace_hex(f.read_bytes().hex(),p.NEW[1]);count+=1
        write(f.with_suffix('.json'),d)
    #2.1ms case trips before the first publish/trace push; its first-fault
    # reason is asserted by the actual native adapter simulation instead.
    assert count==8
    hashes={}
    for f in (p.UNO/'preserved_all_hashes.json',p.HMI/'new_capture_hashes.json',p.OUT/'protected_capture_hashes.json'):
        for rel,want in json.loads(p.read(f)).items():
            assert sha(p.ROOT/rel)==want,rel
            hashes[rel]=want
    for folder in ('FOC_trial_r1','FOC_visual_repeat_r1'):
        for f in (p.HMI/folder).iterdir():
            if f.is_file():hashes[f.relative_to(p.ROOT).as_posix()]=sha(f)
    write(p.OUT/'preserved_all_hashes.json',hashes)
    source_hashes={}
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts:source_hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
    write(p.OUT/'source_hashes.json',source_hashes)
    release=p.OUT/'release';release.mkdir()
    native=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin'
    uno=p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'
    artifacts={}
    for src,name in ((native,'nucleo_2026111612_observer_mean16.bin'),(uno,'uno_2026111611_observer_schema3.elf-zsk.bin')):
        dst=release/name;shutil.copy2(src,dst);artifacts[dst.relative_to(p.OUT).as_posix()]=sha(dst)
    baseline=reports['model']['results']['baseline'][5];candidate=reports['model']['results']['candidate'][5]
    write(p.OUT/'manifest.json',dict(pair=p.NEW,built=True,installed=False,hardware_commands=0,
        START=0,CLEAR=0,RESET=0,flash=0,physical_NIS_root_cause_fully_proven=False,
        source_hashes_file='source_hashes.json',artifacts=artifacts,preserved_files_verified=len(hashes),
        control_and_observer_Q_R_math_unchanged=True,raw_trip_A=1.35,ADC_UPDATE_limit_ticks=2048,
        OFF_fast_budget_cycles=4000,RUN_existing_deadline_cycles=5312,estimate_age_limit_ms=2,
        target_CPU_cycles_measured=False,target_OFF_64case_timing_required_before_START=True,
        qualification='OFFLINE model-tested input-window correction; no speed/current-scale qualification',
        host_core_checks=reports['core']['checks'],host_adapter_checks=reports['adapter']['checks'],
        host_OFF_qualification_cases=64,independent_model_cases_per_variant=9,
        baseline_noisy_peak_NIS=baseline['peak_NIS'],candidate_noisy_peak_NIS=candidate['peak_NIS'],
        candidate_noisy_valid_fraction_after1s=candidate['native_valid_fraction_after1s'],
        observation='noise contribution reduced in simulation; parameter/voltage-model and low-speed observability uncertainty remains'))
    print(json.dumps(dict(built=True,installed=False,pair=p.NEW,protected=len(hashes),new_model_traces=count)))
if __name__=='__main__':main()
