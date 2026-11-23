"""Remove redundant PWM-IRQ work and check the 2106 handover offline."""

import difflib
import json
import math
import struct
import subprocess

from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_CODE

import build_foc_rotating_start_release as release
import check_foc_rotating_start as rotating
from replay_start_history import ArmObserver
from test_observer_current_window import compile_case
from build_multi_native import BIN


BASE = release.OUT
OUT = BASE / 'foc_handover_budget_r4'
HEADER, NATIVE = rotating.HEADER, rotating.NATIVE


def prepare():
    original = release.read(BASE / HEADER)
    start = original.index('  float c0=1.f,s=0.f,start_omega=0.f;')
    end = original.index('  const float id=c0*ia+s*ib', start)
    header = original[:start] + '''  float c0=1.f,s=0.f,start_omega=0.f;
  if(c->preflux==1U){
    const float start_hz=c->time_s<.10f?0.f:ma_min2(reference_hz,5.f);
    start_omega=6.2831853072f*start_hz;
    c0=c->start_cos;s=c->start_sin;
    /* At handover the PI integral is still in the currently applied frame.
     * Check that frame against the estimate, without advancing an oscillator
     * which will no longer be used. Keep the same admission criteria. */
    const float projection=c0*x[2]+s*x[3];
    if(speed_ready&&start_hz>=1.f&&flux>.0001f&&projection>=.92f*flux&&
       fabsf(m->poles*x[4]-start_omega)<=6.2831853072f){
      const float inv_flux=1.f/flux;
      const float d=projection*inv_flux,q=(c0*x[3]-s*x[2])*inv_flux;
      const float a=c->integral[0],b=c->integral[1];
      c->integral[0]=d*a+q*b;c->integral[1]=-q*a+d*b;
      c0=x[2]*inv_flux;s=x[3]*inv_flux;
      c->preflux=2U;
    }else{
      const float delta=start_omega*dt;
      const float next_c=c0-delta*s,next_s=s+delta*c0;
      const float norm=1.5f-.5f*(next_c*next_c+next_s*next_s);
      c0=c->start_cos=next_c*norm;s=c->start_sin=next_s*norm;
      speed_ready=0;
    }
  }else if(flux>.0001f){c0=x[2]/flux;s=x[3]/flux;}
''' + original[end:]
    header = rotating.change(header, '''  unsigned exponent=bits>>23;
  if(exponent<126U)return 0;
  unsigned shift=150U-exponent;
  uint32_t mantissa=(bits&0x7fffffU)|0x800000U;
  return (mantissa+(1U<<(shift-1U)))>>shift;''', '''  /* The unsigned truncation fits 16 bits. Its conversion back to float is
   * exact, as is subtraction of the integer part. This avoids the double
   * rounding of adding 0.5f, and uses the M4's fixed-point conversion. */
  const uint32_t whole=(uint32_t)value;
  return whole+(uint32_t)(value-(float)whole>=.5f);''')
    header = rotating.change(header,
        '  for(unsigned i=0;i<3;i++){out->ccr[i]=cc[i];out->duty[i]=(float)cc[i]/g->arr;}',
        '''  /* The timer counts and ADC aperture are already fixed. Reuse the
   * scale solely for float duty telemetry and anti-windup feedback. */
  const float inv_arr=1.f/(float)g->arr;
  for(unsigned i=0;i<3;i++){out->ccr[i]=cc[i];out->duty[i]=(float)cc[i]*inv_arr;}''')
    header = rotating.change(header, 'static inline int ma_motor_valid(const ma_motor*m){', '''static inline float ma_voltage_scale(float d,float q,float limit){
  /* Skip the norm only when rounding cannot change the already-unity scale.
   * Near or above saturation, keep the original norm, divide and clamp. */
  const float mag2=d*d+q*q;
  if(mag2<(limit*limit)*.99f)return 1.f;
  return ma_min2(1.f,limit/ma_max2(ma_control_norm(d,q),1.e-9f));
}
static inline int ma_motor_valid(const ma_motor*m){''')
    header = rotating.change(header, '''  const float limit=.90f*bus*.5773502692f,mag=ma_control_norm(dq[0],dq[1]);
  const float scale=ma_min2(1,limit/ma_max2(mag,1.e-9f));''', '''  const float limit=.90f*bus*.5773502692f;
  const float scale=ma_voltage_scale(dq[0],dq[1],limit);''')
    candidate = OUT / 'candidate'
    for path, text in ((HEADER, header), (NATIVE, release.read(BASE / NATIVE))):
        dest = candidate / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        release.write(dest, text)
    patch = difflib.unified_diff(original.splitlines(keepends=True), header.splitlines(keepends=True),
                                 'a/' + HEADER, 'b/' + HEADER)
    release.write(OUT / 'handover_budget.patch', ''.join(patch))
    return candidate


def check_rounding(candidate):
    source = '#include "' + (candidate / HEADER).as_posix() + '"\n' + r'''
#include <cassert>
#include <cstdio>
static uint32_t baseline(float value){
 uint32_t bits;memcpy(&bits,&value,4);
 if(bits==0x80000000U)return 0;
 if(bits>0x477fff00U)return UINT32_MAX;
 unsigned exponent=bits>>23;
 if(exponent<126U)return 0;
 unsigned shift=150U-exponent;
 uint32_t mantissa=(bits&0x7fffffU)|0x800000U;
 return (mantissa+(1U<<(shift-1U)))>>shift;
}
int main(){
 unsigned tested=0;
 for(unsigned i=0;i<=65535U;++i){
  float a=(float)i,b=a+.5f;
  float samples[]={a,b,nextafterf(a,-INFINITY),nextafterf(a,INFINITY),
                     nextafterf(b,-INFINITY),nextafterf(b,INFINITY)};
  for(float v:samples){assert(ma_round_ccr(v)==baseline(v));++tested;}
 }
 uint32_t seed=12345;
 for(unsigned n=0;n<1000000U;++n){
  seed=1664525U*seed+1013904223U;float v;memcpy(&v,&seed,4);
  assert(ma_round_ccr(v)==baseline(v));++tested;
 }
 unsigned scale_cases=0;
 for(float lim:{15.588f,129.904f,181.865f})for(int i=-320;i<=320;++i){
  const float d=lim*(float)i/256.f;
  for(int j=-320;j<=320;++j){
   const float q=lim*(float)j/256.f;
   const float expected=ma_min2(1.f,lim/ma_max2(ma_control_norm(d,q),1.e-9f));
   assert(ma_voltage_scale(d,q,lim)==expected);++scale_cases;
  }
 }
 printf("%u %u\n",tested,scale_cases);
}
'''
    source='#include <initializer_list>\n'+source
    tool=compile_case(OUT,'rounding_equivalence',source,BASE)
    return tuple(map(int,subprocess.check_output([str(tool)],text=True,timeout=20).split()))


def instruction_probe(elf, recorded, *, retain_handover_speed=False):
    """Run compiled OFF IRQ on emulated M4. Instruction counts, never DWT cycles."""
    emu = ArmObserver(elf)
    uc = emu.uc
    uc.mem_map(0x40012000, 0x1000)  # TIM1, BDTR.MOE=0
    uc.mem_map(0xe0001000, 0x1000)  # DWT registers (no clock simulation)
    with elf.open('rb') as stream:
        symbols = {s.name: (int(s['st_value']), s['st_size'])
                   for s in ELFFile(stream).get_section_by_name('.symtab').iter_symbols()}

    def set_value(name, fmt, *values):
        uc.mem_write(symbols[name][0], struct.pack(fmt, *values))

    def seed(name):
        raw = recorded[name]
        assert len(raw) == symbols[name][1], name
        uc.mem_write(symbols[name][0], raw)

    active_count = 0
    divisions = 0
    disassembly = subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d',str(elf)],text=True,timeout=20)
    division_addresses = {int(line.split(':',1)[0],16) for line in disassembly.splitlines()
                          if '\tvdiv.f32\t' in line}

    def on_instruction(_, address, size, user_data):
        nonlocal active_count,divisions
        active_count += 1
        divisions += address in division_addresses

    uc.hook_add(UC_HOOK_CODE, on_instruction)
    seed('model')
    seed('fe_test_geometry')
    data = []
    for case in range(64):
        theta = (case % 16) * .3926990817
        c, s = math.cos(theta), math.sin(theta)
        current = .75 if case & 16 else .2
        ia, ib = current * c, current * s
        ref = 50. if case & 2 else 5.
        set_value('fe_test_bus', '<f', 250. if case & 4 else 350.)
        set_value('fe_test_ref', '<f', ref)
        set_value('fe_test_ia', '<f', ia)
        set_value('fe_test_ib', '<f', ib)
        set_value('fe_window_seed', '<8f6I', 15*ia, 15*ib, 0., 0., 0., 0., 0., 0.,
                  159360, 0, 10624, 90304, 15, 15 << (5*(case % 3)))
        controller_size = symbols['fe_test_controller'][1]
        assert controller_size in (48,56), controller_size
        set_value('fe_test_controller', '<7f2IB3x2f', 0., 0., 0., 1. if case & 8 else .05,
                  0., 0., 0., 0, 0, 0, c, s)
        if controller_size == 56:
            uc.mem_write(symbols['fe_test_controller'][0]+48, struct.pack('<2f', ia, ib))
        set_value('fe_case', '<B', case)
        initial_omega = 314.1592654 if case & 32 else 31.41592654
        omega = initial_omega
        for n in range(8):
            phase = n % 3
            if phase == 1 and case & 9 == 9:
                omega = min(ref, 5.) * math.tau
            elif not retain_handover_speed:
                omega = initial_omega
            set_value('fe_test_x', '<6f', ia, ib, .25*c, .25*s, omega, 0.)
            uc.mem_write(symbols['fe_test_controller'][0]+36, struct.pack('<B3x2f', phase, c, s))
            set_value('fe_pending', '<B', 1)
            active_count = divisions = 0
            emu.call('ma_native_profile_tick', [])
            count = active_count
            rc = struct.unpack('<i', uc.mem_read(symbols['fe_rc'][0],4))[0]
            finished = uc.mem_read(symbols['fe_finished'][0],1)[0]
            branch = uc.mem_read(symbols['fe_test_controller'][0]+36,1)[0]
            assert rc == 0 and finished == 1 and count > 100, (case, n, rc, finished)
            data.append({'case':case,'iteration':n,'instructions':count,'floating_divisions':divisions,
                         'handover':phase==1 and branch==2})
    return data


def main():
    release.verify_inventory(release.read_json(BASE/'preserved_inputs_sha256.json'),release.ROOT)
    off = BASE/'post_install_idle_r1'
    release.verify_inventory(release.read_json(off/'saved_files_sha256.json'),off)
    native = release.read_json(BASE/'OFF_budget_audit.json')
    assert native['fe_case']==9 and native['fe_n']==1 and native['fe_elapsed']==4076
    ram = (off/'native_SRAM_0.bin').read_bytes()
    base_elf = BASE/'release/nucleo_2026112106_if_start.elf'
    with base_elf.open('rb') as stream:
        symbols={s.name: (int(s['st_value']), s['st_size'])
                 for s in ELFFile(stream).get_section_by_name('.symtab').iter_symbols()}
    recorded = {k:ram[address-0x20000000:address-0x20000000+size]
                for k,(address,size) in symbols.items() if k in ('model','fe_test_geometry')}

    OUT.mkdir()
    candidate=prepare()
    rounding_cases, scale_cases=check_rounding(candidate)
    results=rotating.simulate(OUT,candidate)
    original_base=rotating.pc.previous.BASE
    try:
        rotating.pc.previous.BASE=BASE
        timing=rotating.pc.previous.arm_compile(output=OUT/'ARM_linkcheck',source=candidate)
    finally:
        rotating.pc.previous.BASE=original_base
    elf=OUT/'ARM_linkcheck/speed_admission_linkcheck_DO_NOT_FLASH.elf'
    before,after = instruction_probe(base_elf,recorded),instruction_probe(elf,recorded)
    release.save(OUT/'ARM_OFF_instruction_counts.json',{'installed':before,'candidate':after,'unicorn_instruction_counts_not_DWT':True})
    failure_index = 9*8+1
    assert before[failure_index]['handover'] and after[failure_index]['handover']
    old, new = before[failure_index]['instructions'],after[failure_index]['instructions']
    assert new < old,(old,new)
    nominal=results['nominal']['I_f']
    checks = {
        'nominal_completes_5s_at_5Hz':nominal['completed_5s'] and nominal['maximum_reference_Hz']==5 and nominal['handover_step']>0 and abs(nominal['rpm_true_end']-300)<15,
        'without_admitted_speed':results['unknown_speed_admission']['I_f']['completed_5s'] and results['unknown_speed_admission']['I_f']['handover_step']==0,
        'NIS_25_stop':results['NIS_25']['I_f']['fault']==5 and results['NIS_25']['I_f']['observer_calls']==571,
        'NIS_just_below_25_allowed':results['NIS_just_below_25']['I_f']['completed_5s'],
        'raw_current_trip':results['raw_overcurrent']['I_f']['fault']==2,
        'estimate_age_trip':results['estimate_age_2_1ms']['I_f']['fault']==3,
        'field_rate_guard':results['effective_edge_minus250ns']['I_f']['fault']==5 and results['effective_edge_minus250ns']['I_f']['peak_NIS']<25,
    }
    report = {'passed':all(checks.values()),'checks':checks,'nominal':nominal,
              'CCR_rounding_equivalence_cases':rounding_cases,
              'voltage_scale_equivalence_cases':scale_cases,
              'recorded_DWT_cycles_before':native['fe_elapsed'],'instruction_count_replay_before_after':[old,new],
              'floating_divisions_replay_before_after':[rows[failure_index]['floating_divisions'] for rows in (before,after)],
              'max_OFF_instructions_before_after':[max(d['instructions'] for d in rows) for rows in (before,after)],
              'nested_IRQ_or_wait_states_emulated':False,'target_DWT_after_measured':False,
              'ARM':timing,'hardware_commands':0}
    release.verify_inventory(release.read_json(BASE/'preserved_inputs_sha256.json'),release.ROOT)
    release.save(OUT/'verification.json',report)
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
