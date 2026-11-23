"""Prepare a new identity for the measured fix: skip inactive HFT calculations."""
import argparse,json,shutil
from pathlib import Path
from prepare_pwm_filter_pair import sha,write,change
from prepare_ipm_break_wifi import source_hashes
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r3'

def prepare(out):
    assert json.loads((BASE/'qualification/report.json').read_text())['pass']
    out.mkdir(parents=True,exist_ok=False)
    pairs={'production':((2026101405,2026101404),(2026101407,2026101406)),
           'fixture':((2026101498,2026101499),(2026101496,2026101497))}
    for name,(old,new) in pairs.items():
        before=json.loads((BASE/name/'manifest.json').read_text())
        assert source_hashes(BASE/name/'nucleo')==before['nucleo_source_sha256']
        assert source_hashes(BASE/name/'UNOQ_MOTOR')==before['uno_source_sha256']
        p=out/name
        shutil.copytree(BASE/name/'nucleo',p/'nucleo',ignore=shutil.ignore_patterns('Debug','Release','.metadata'))
        shutil.copytree(BASE/name/'UNOQ_MOTOR',p/'UNOQ_MOTOR')
        shutil.copytree(BASE/name/'web_hmi',p/'web_hmi',ignore=shutil.ignore_patterns('__pycache__'))
        change(p/'nucleo/Src/main.c',f'MIC_NUCLEO_FW_BUILD_ID {old[1]}UL',f'MIC_NUCLEO_FW_BUILD_ID {new[1]}UL')
        change(p/'nucleo/Inc/break_wire.h',f'BW_NUCLEO_BUILD {old[1]}UL',f'BW_NUCLEO_BUILD {new[1]}UL')
        change(p/'UNOQ_MOTOR/UNOQ_MOTOR.ino',f'FW_BUILD_ID = {old[0]}U',f'FW_BUILD_ID = {new[0]}U')
        change(p/'UNOQ_MOTOR/break_wire.h',f'BW_NUCLEO_BUILD {old[1]}UL',f'BW_NUCLEO_BUILD {new[1]}UL')
        if name=='production':
            change(p/'UNOQ_MOTOR/nucleo_fault_diagnostics.h','build == 2026101404U;',
                   'build == 2026101404U || build == 2026101406U;')
        else:
            change(p/'UNOQ_MOTOR/nucleo_fault_diagnostics.h','build == 2026101499U;',
                   'build == 2026101499U || build == 2026101406U || build == 2026101497U;')
        change(p/'nucleo/Src/mc_tasks.c','  uint8_t bMotorNbr = 0;\n\n  ACIM_VF_CalcAngle',
          '''  uint8_t bMotorNbr = 0;

  /* An off output needs no modulation calculation. A pending update at boot
     or after a hardware break must not evaluate an uninitialized normalizer.
     Active outputs still execute all validity guards and fault processing. */
  if (0U == LL_TIM_IsEnabledAllOutputs(pwmHandle[M1]->TIMx))
  {
    return bMotorNbr;
  }

  ACIM_VF_CalcAngle''')
        web=p/'web_hmi/server.py';text=web.read_text()
        text=text.replace('(2026101102, 2026101204, 2026101404, 2026101499)',
                          '(2026101102, 2026101204, 2026101404, 2026101499, 2026101406, 2026101497)')
        text=text.replace('in (2026101404, 2026101499):','in (2026101404, 2026101499, 2026101406, 2026101497):')
        if name=='fixture':text=text.replace('(2026101498, 2026101499)','(2026101496, 2026101497)')
        write(web,text)
        assert (p/'nucleo/Inc/break_wire.h').read_bytes()==(p/'UNOQ_MOTOR/break_wire.h').read_bytes()
        manifest=dict(before,pair=list(new),nucleo_source_sha256=source_hashes(p/'nucleo'),
          uno_source_sha256=source_hashes(p/'UNOQ_MOTOR'),hmi_sha256=sha(web),inactive_hft_guard=True)
        write(p/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    write(out/'manifest.json',json.dumps(dict(production_pair=[2026101407,2026101406],fixture_pair=[2026101496,2026101497],
       predecessor_pair=[2026101405,2026101404],predecessor_hmi_sha256=sha(BASE/'production/web_hmi/server.py'),
       hardware_commands=0,hv_release_approved=False),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True);a=p.parse_args();prepare(a.outdir.resolve())
