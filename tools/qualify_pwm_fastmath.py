"""Run the actual prepared PWM/controller/filter functions with target -Ofast."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import audit_production_pwm_filters as audit

def qualify(package,out):
    out.mkdir(parents=True,exist_ok=False)
    template=(audit.ROOT/'artifacts/live_bench_20261014/pwm_filter_audit_r6/actual_functions.cpp').read_text()
    helper='''static bool mic_float_isfinite(float value) {
 uint32_t bits; memcpy(&bits,&value,sizeof(bits));
 return (bits & 0x7f800000U) != 0x7f800000U;
}
'''
    template=template.replace('using std::isfinite;', '#include <cstring>\n'+helper)
    template=template.replace('PWM_Handle_t *pwmHandle[1];','PWM_Handle_t *pwmHandle[1];\nbool LL_TIM_IsEnabledAllOutputs(TIM_TypeDef *p){return (p->BDTR & 32768U)!=0;}')
    template=template.replace('std::isfinite(', 'mic_float_isfinite(')
    names={audit.PWM:['PWM_SetPhasePWMOutputs','PWM_SwitchOffPWM'],
           audit.VF:['ACIM_VF_Controller'],Path('Src/mc_tasks.c'):['TSK_HighFrequencyTask'],
           audit.FILTER:['RVBS_CheckFaultState','RVBS_CalcAvVbus','RVBS_Init']}
    for relative,functions in names.items():
        source=(package/'nucleo'/relative).read_text(encoding='utf-8-sig')
        for name in functions:
            old=audit.function(template,'candidate_'+name)
            new=audit.function(source,name)
            for n in sum(names.values(),[]):
                new=re.sub(r'\b'+n+r'\b','candidate_'+n,new)
            template=audit.once(template,old,new)
    if json.loads((package/'manifest.json').read_text()).get('inactive_hft_guard'):
        template=template.replace(' unsigned max_old_lag=0,', '''
 h=ACIM_VF_Handle_t{&p};h.fVoutMax_PWM_Mod_V=0;t.BDTR=0;t.update_irq=false;Mci[0].fault=0;writes=0;
 candidate_TSK_HighFrequencyTask();
 assert(t.BDTR==0 && Mci[0].fault==0 && writes==0);++invalid_cases;
 unsigned max_old_lag=0,''')
    unit=out/'actual_functions.cpp';unit.write_text(template)
    exe=out/'actual_functions.exe'
    build=subprocess.run(['g++','-Ofast','-std=c++17','-Wall','-Wextra',str(unit),'-o',str(exe)],capture_output=True,text=True)
    (out/'build.log').write_text(build.stdout+build.stderr);build.check_returncode()
    run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)
    (out/'run.log').write_text(run.stdout+run.stderr);run.check_returncode()
    result=json.loads(run.stdout)
    # A finite-math-optimized isfinite mutant must be detected by the same vectors.
    mutant=template.replace('!mic_float_isfinite(', '!std::isfinite(')
    munit=out/'isfinite_mutant.cpp';munit.write_text(mutant)
    mexe=out/'isfinite_mutant.exe'
    built=subprocess.run(['g++','-Ofast','-std=c++17',str(munit),'-o',str(mexe)],capture_output=True,text=True)
    (out/'mutant_build.log').write_text(built.stdout+built.stderr);built.check_returncode()
    bad=subprocess.run([str(mexe)],capture_output=True,text=True,timeout=60)
    (out/'mutant_run.log').write_text(bad.stdout+bad.stderr)
    if bad.returncode==0:raise RuntimeError('isfinite mutation not detected')
    result.update(target_optimization='-Ofast',isfinite_mutant_detected=True,hardware_commands=0,
                  production_source_sha256={str(p):audit.sha(package/'nucleo'/p) for p in names})
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',required=True,type=Path);p.add_argument('--outdir',required=True,type=Path)
    a=p.parse_args();print(json.dumps(qualify(a.package.resolve(),a.outdir.resolve()),indent=2))
