"""Prepare only the Uno diagnostic peer identity update, without actuation."""
import argparse
import json
from pathlib import Path
import shutil
from prepare_ipm_break_wifi import source_hashes
from prepare_mcsdk_logic_bench import replace_once

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261012/llext_fix/candidate_r1/UNOQ_MOTOR'
BUILD=2026101205
PEER=2026101204


def sketch(text):return replace_once(text,'FW_BUILD_ID = 2026101108U',f'FW_BUILD_ID = {BUILD}U')
def diagnostics(text):return replace_once(text,'build == 2026101102U;',f'build == 2026101102U || build == {PEER}U;')
def wire(text):return replace_once(text,'BW_NUCLEO_BUILD 2026101102UL',f'BW_NUCLEO_BUILD {PEER}UL')


def prepare(out):
    before=source_hashes(BASE);out.mkdir(parents=True,exist_ok=False)
    target=out/'UNOQ_MOTOR';shutil.copytree(BASE,target)
    for name,fn in (('UNOQ_MOTOR.ino',sketch),('nucleo_fault_diagnostics.h',diagnostics),('break_wire.h',wire)):
        path=target/name;path.write_text(fn(path.read_text()),encoding='utf-8')
    after=source_hashes(target)
    changed={k for k in set(before)|set(after) if before.get(k)!=after.get(k)}
    if changed!={'UNOQ_MOTOR.ino','nucleo_fault_diagnostics.h','break_wire.h'} or source_hashes(BASE)!=before:
        raise RuntimeError('Unexpected Uno changes')
    r=dict(uno_build=BUILD,nucleo_build=PEER,baseline_sha256=before,source_sha256=after,
           changed_files=sorted(changed),control_logic_changed=False,installed=False,
           hardware_commands=0,hv_release_approved=False)
    (out/'manifest.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();r=prepare(a.outdir.resolve())
    print(json.dumps({k:r[k] for k in ('uno_build','nucleo_build','changed_files','installed')}))
