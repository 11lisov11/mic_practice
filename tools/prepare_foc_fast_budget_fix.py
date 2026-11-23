"""Equivalent, bounded work reduction; no hardware access or relaxed limits."""
import json, os, shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT, read, write, once

BASE=ROOT/'artifacts/live_bench_20261029/foc_runtime_fix_r1'
OUT=ROOT/'artifacts/live_bench_20261029/foc_fast_budget_fix_r1'
NEW=(2026103001,2026103002)

def main():
    assert not OUT.exists(), 'Never overwrite a package or capture'
    for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        def cp(src,dst):
            rel=Path(src).relative_to(BASE/folder)
            if folder=='libraries' or (folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full')):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                s=read(f);n=s.replace('2026102971','2026103001').replace('2026102972','2026103002')
                n=n.replace('2971-foc-runtime','3001-fast-budget')
                if n!=s:write(f,n)
    f=OUT/'nucleo/Inc/motor_control.h';s=read(f)
    s=once(s,'#include <math.h>','#include <math.h>\n#include <float.h>')
    anchor='static inline int ma_modulate('
    helper='''/* CCR inputs are nonnegative binary32 values bounded by the16-bit timer.
 * Exact halfway-away-from-zero rounding, including the float below0.5:
 * adding0.5 before conversion would double-round that boundary. Invalid input
 * fails closed; every caller rejects the sentinel before aperture planning. */
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || FLT_MAX_EXP != 128
#error "CCR rounding requires IEEE binary32"
#endif
typedef char ma_float_is_32_bits[(sizeof(float)==4)?1:-1];
static inline uint32_t ma_round_ccr(float value){
  uint32_t bits;memcpy(&bits,&value,sizeof(bits));
  if(bits==0x80000000U)return 0; /* negative zero */
  if(bits>0x477fff00U)return UINT32_MAX; /* negative, NaN, Inf, or >65535 */
  unsigned exponent=bits>>23;
  if(exponent<126U)return 0;
  unsigned shift=150U-exponent;
  uint32_t mantissa=(bits&0x7fffffU)|0x800000U;
  return (mantissa+(1U<<(shift-1U)))>>shift;
}
'''
    s=once(s,anchor,helper+anchor)
    for expr in ('(base[i]+candidates[n])*g->arr','(base[i]+shift)*g->arr'):
        s=once(s,'for(unsigned i=0;i<3;i++)cc[i]=(uint32_t)lroundf('+expr+');',
            'for(unsigned i=0;i<3;i++){cc[i]=ma_round_ccr('+expr+');if(cc[i]>g->arr)return MA_WINDOW;}')
    s=once(s,'static inline int ma_control(ma_controller*c,','static inline int ma_control_checked(ma_controller*c,')
    s=once(s,'float bus,float dt,int fresh,ma_output*out){\n  memset(out,0,sizeof(*out));',
        'float bus,float dt,int fresh,ma_output*out,int model_ok){\n  memset(out,0,sizeof(*out));')
    s=once(s,'if(!ma_motor_valid(m)||!isfinite(ia)||!isfinite(ib)||!isfinite(reference_hz)||',
        'if(!model_ok||!isfinite(ia)||!isfinite(ib)||!isfinite(reference_hz)||')
    wrapper='''/* General callers validate the model here. The native IRQ uses the result
 * of the identical validation already performed in that SAME IRQ invocation;
 * no result is cached between frames and no foreground mutation can intervene. */
static inline int ma_control(ma_controller*c,const ma_motor*m,const float*x,
    const ma_geometry*g,int algorithm,float ia,float ib,float reference_hz,
    float bus,float dt,int fresh,ma_output*out){
  return ma_control_checked(c,m,x,g,algorithm,ia,ib,reference_hz,bus,dt,fresh,out,ma_motor_valid(m));
}
'''
    s=once(s,'#ifdef __cplusplus\n}\n#endif\n#endif',wrapper+'#ifdef __cplusplus\n}\n#endif\n#endif')
    write(f,s)
    f=OUT/'nucleo/Inc/foc_experiment.h';s=once(read(f),' const ma_motor expected=FE_ESTIMATED_MOTOR;',
        ' static const ma_motor expected=FE_ESTIMATED_MOTOR;');write(f,s)
    f=OUT/'nucleo/Src/multi_native.c';s=read(f)
    s=once(s,'  ma_current_sample sample={0};int got=mic_current_fast(&sample);',
        '  ma_current_sample sample;int got=mic_current_fast(&sample);')
    s=once(s,'ma_fail_at(MA_STALE,why,begin,&sample,est_cycles,bin_cycles,0);',
        'ma_fail_at(MA_STALE,why,begin,got?&sample:NULL,est_cycles,bin_cycles,0);')
    s=once(s,'  int fault=ma_control(&controller,&model,x,&g,selected,ma_amps(sample.counts[0]),',
        '''  /* fe_profile_allowed has just validated the exact calculated model.
   * TIM1 has the highest configurable IRQ priority; no foreground profile write
   * can occur here. Other qualifications retain their own per-frame validation. */
  const int model_ok=qualification==FE_ESTIMATED||ma_motor_valid(&model);
  int fault=ma_control_checked(&controller,&model,x,&g,selected,ma_amps(sample.counts[0]),''')
    s=once(s,'reference_hz,VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super),1.f/16000U,fresh,&out);',
        'reference_hz,VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super),1.f/16000U,fresh,&out,model_ok);')
    write(f,s)
    write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.foc_fast_budget_fix.v1',pair=list(NEW),
        base_pair=[2026102971,2026102972],built=False,installed=False,
        current_model_changed=False,ADC_source_changed=False,thresholds_changed=False,
        age_limits_changed=False,IRQ_priorities_changed=False,IRQ_masking_added=False,
        observer_math_changed=False,control_equivalence_test_required=True,
        target_timing_qualification_pending=True,native_autostop_seconds=5,experimental_max_hz=5,
        start_commands=0,clear_commands=0,flash_commands=0),indent=2)+'\n')
    print('Prepared3001/3002 offline; no hardware commands')

if __name__=='__main__':main()
