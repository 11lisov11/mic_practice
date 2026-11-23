"""Prepare1801/1802 from the tested exact-input overlay; no device access."""
import json,os,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
from analyze_observer_nis import sha

BASE=ROOT/'artifacts/live_bench_20261117/observer_pair_noise_r1'
DIAG=ROOT/'artifacts/live_bench_20261118/nis_input_window_r1'
OUT=ROOT/'artifacts/live_bench_20261118/exact_nis_input_release_r1'
NEW=(2026111801,2026111802)


def verify_inputs():
    for name,base in [('source_hashes.json',BASE),('release/sha256.json',BASE/'release')]:
        for rel,h in json.loads(read(BASE/name)).items():assert sha(base/rel)==h,rel
    for rel,h in json.loads(read(DIAG/'saved_files_sha256.json')).items():assert sha(DIAG/rel)==h,rel
    for rel,h in json.loads(read(DIAG/'protected_inputs_final_sha256.json')).items():assert sha(ROOT/rel)==h,rel


def main():
    verify_inputs();assert not OUT.exists(),'Never replace a candidate or records'
    for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        def copy(src,dst):
            parts=Path(src).relative_to(BASE/folder).parts
            if folder=='libraries' or folder=='nucleo' and parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log','backups'))
    changes=json.loads(read(DIAG/'overlay_manifest.json'))['changed']
    for rel in changes:shutil.copy2(DIAG/'overlay'/rel,OUT/rel)
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for path in (OUT/folder).rglob('*'):
            if path.is_file():
                a=read(path);b=a.replace('2026111715',str(NEW[0])).replace('2026111716',str(NEW[1]))
                if a!=b:write(path,b)
    protected=json.loads(read(DIAG/'protected_inputs_final_sha256.json'))
    for path in DIAG.rglob('*'):
        if path.is_file():protected[path.relative_to(ROOT).as_posix()]=sha(path)
    for path in BASE.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.o','.d','.su','.cyclo'):
            # Preserve the installed candidate, actual RAM/SD/ADC/NIS and recovery
            # records as inputs, including files added after its original seal.
            protected[path.relative_to(ROOT).as_posix()]=sha(path)
    write(OUT/'preserved_inputs_sha256.json',json.dumps(protected,indent=2)+'\n')
    write(OUT/'preparation.json',json.dumps(dict(pair=NEW,predecessor_pair=[2026111715,2026111716],
        built=False,installed=False,hardware_commands=0,START=0,CLEAR=0,RESET=0,
        change='Exact ADC source16 plus previous voltage history, first-NIS replay latch, explicit GAP; schema3 ADC and schema5 observer',
        NIS_algorithm_fixed=False,physical_NIS_root_cause_proven=False,
        current_trip_A=1.35,OFF_fast_limit_cycles=4000,estimate_age_ms=2,ADC_UPDATE_ticks=2048,
        full_RUN_existing_limit_cycles=5312,NIS_limits=[25,50],
        no_protection_or_model_change=True,protected_files=len(protected)),indent=2)+'\n')
    print(json.dumps(dict(prepared=True,pair=NEW,hardware_commands=0,protected_files=len(protected))))


if __name__=='__main__':main()
