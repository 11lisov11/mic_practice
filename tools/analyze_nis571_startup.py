"""Offline NIS 571 audit and sensorless speed-loop admission candidate."""
import ctypes
import difflib
import json
import math
import re
import struct
import subprocess
from pathlib import Path

import numpy as np
from elftools.elf.elffile import ELFFile

import build_observer_nis_admission_release as release
from check_recorded_nis_admission import audit_trace
from replay_start_history import ArmObserver
from run_nis_admission_paged_trial import verify_release
from test_foc_estimate_publish_fix import native_source
from test_observer_current_window import compile_case


ROOT = release.ROOT
BASE = release.OUT
TRIAL = BASE/'FOC_5Hz_NIS_20261121_r1'
DATA = BASE/'FOC_5Hz_NIS_20261121_r1_analysis'
OUT = BASE/'step571_model_audit_r1'
CANDIDATE = OUT/'candidate'
ELF = BASE/'release/nucleo_2026112102_nis_admission.elf'


def verify_inputs():
    _, archive = verify_release()
    for directory, name in ((TRIAL,'saved_files_sha256.json'), (DATA,'sha256.json'),
                             (BASE,'source_hashes.json')):
        for file, expected in release.read_json(directory/name).items():
            archive[(directory/file).relative_to(ROOT).as_posix()] = expected
    release.verify_inventory(archive, ROOT)
    return archive


def reconstruct():
    trace = release.read_json(DATA/'observer_trace_decoded.json')
    a = release.read_json(DATA/'ADC_decoded.json')
    nis = trace['first_nis_replay']
    assert nis['post_steps']==trace['first_loss']['steps']==a['source_observer_step']==571
    arm = ArmObserver(ELF)
    event = audit_trace(trace, arm)
    assert event['bit_exact_ARM_words']==51
    first = next(i for i,r in enumerate(a['samples']) if r['cycles']==a['requested_first_cycles'])
    rows = a['samples'][first-32:first+16]
    assert len(rows)==48 and all(r['pair']==0 and r['quality']==1 for r in rows)
    currents = np.array([r['nominal_currents_a'] for r in rows])
    clarke = np.column_stack([currents[:,0],(currents[:,0]+2*currents[:,1])/math.sqrt(3)])
    windows = clarke.reshape(3,16,2)
    means = windows.mean(axis=1)
    data = bytes.fromhex(nis['raw_hex'])
    before = data[:168]+bytes(28)+data[168:176]
    unpacked = list(struct.unpack_from('<5f',data,228))
    motor = data[176:228]
    counts = struct.unpack_from('<I',data,452)[0]>>8
    assert np.max(np.abs(means[-1]-unpacked[:2]))<1e-7

    def replay(prior=before, profile=motor, inputs=unpacked):
        rc, after, _ = arm.step(prior,profile,struct.pack('<5f',*inputs),nis['fpscr'],counts)
        assert rc==0
        v = struct.unpack_from('<7f',after,168)
        return {'NIS':v[0],'prediction_A':list(v[1:3])}

    # Fixed-prior sensitivity. These cases are not replacements for a complete
    # trajectory, nor grounds for applying a fitted parameter to the drive.
    chosen = (TRIAL/'paged_capture/ADC_peak.bin').read_bytes()
    rebuild = ctypes.CDLL(str(release.ANALYSIS/'rebuild_1810_adc.dll')).rebuild_exact
    rebuild.argtypes = [ctypes.c_char_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_float]
    voltages = {}
    for label,fraction in (('installed_right_endpoint',-1),('centered_interval',.5)):
        bin_data, points = ctypes.create_string_buffer(48),ctypes.create_string_buffer(400)
        assert rebuild(chosen,bin_data,points,fraction)==0
        source = list(struct.unpack_from('<4f',bin_data.raw))
        voltages[label] = dict(inputs=source,**replay(inputs=[*source,unpacked[-1]]))
    vdc,arr = rows[-1]['bus_v'],rows[-1]['timer_arr']
    assert all(r['bus_v']==vdc and r['timer_arr']==arr and
               r['counts_uvw'][0]<0 and r['counts_uvw'][1]<0 and r['counts_uvw'][2]>0 for r in rows)
    dt_loss = vdc*229/(2*arr)
    scenarios = {}
    for label,correction in (('effective_deadtime_0_25us_shorter',-.25e-6*170e6/229),
                              ('effective_deadtime_0_25us_longer',.25e-6*170e6/229),
                              ('omit_half_deadtime_correction',-.5)):
        x=unpacked.copy()
        x[2]+=correction*dt_loss*2/3
        x[3]+=correction*dt_loss*2/math.sqrt(3)
        scenarios[label]=replay(inputs=x)
    x=unpacked.copy()
    scale=3.3/(4095*.04*2.1)
    x[0]+=scale;x[1]+=scale/math.sqrt(3)
    scenarios['phase_U_plus_one_ADC_count']=replay(inputs=x)
    rs=nis['motor']['rs']
    scenarios['Rs_minus_2_ohm']=replay(profile=struct.pack('<f',rs-2)+motor[4:])
    scenarios['prior_currents_from_previous_16_ADC_samples']=replay(
        prior=struct.pack('<2f',*means[1])+before[8:])
    # Lower bound: the gap visible BEFORE this step is not one anomalous sample.
    prior_gap=means[1]-np.array(nis['prior_state'][:2]); assert abs(prior_gap[0])>.08
    return {'step':571,'baseline':event,'previous_window_centers_apart_ms':1,
            'three_ADC_means_A':means.tolist(),'three_ADC_sample_std_A':windows.std(axis=1,ddof=1).tolist(),
            'previous_window_minus_prior_EKF_A':prior_gap.tolist(),
            'sample_source_pairs':'U1/V2','offsets_from_ADC_record':rows[-1]['offsets_adc'],
            'voltage_window_alignment':voltages,'fixed_prior_sensitivity':scenarios,
            'prior_bias_existed_before_window':True,'physical_bias_cause_identified':False,
            'NIS_threshold_changed':False,'hardware_commands':0}


def make_overlay():
    def once(text, original, replacement):
        assert text.count(original)==1,original
        return text.replace(original,replacement)

    changes = {}
    relative = 'nucleo/Inc/motor_control.h'
    original = release.read(BASE/relative)
    text = once(original,'int ma_control_checked(ma_controller*','int ma_control_with_speed_admission(ma_controller*')
    text = once(text,'float bus,float dt,int fresh,ma_output*out,int model_ok){',
                'float bus,float dt,int fresh,ma_output*out,int model_ok,int speed_ready){')
    text = once(text,'  float iqref=0;\n  if(c->time_s<.35f)c->speed_integral=0;',
                '  /* A provisional flux can establish magnetization, but an unqualified\n'
                '   * speed must not command torque or enter speed feed-forward. */\n'
                '  const float omega = speed_ready ? x[4] : 0.f;\n'
                '  float iqref=0;\n  if(c->time_s<.35f||!speed_ready)c->speed_integral=0;')
    text = once(text,'const float speederr=omega_ref-x[4]','const float speederr=omega_ref-omega')
    text = once(text,'if(x[4]>0&&iqref<0)','if(omega>0&&iqref<0)')
    text = once(text,'m->poles*x[4]+ar*m->lm*iq','m->poles*omega+ar*m->lm*iq')
    text = once(text,'res*iq+kr*m->poles*x[4]*flux','res*iq+kr*m->poles*omega*flux')
    text = once(text,'/* General callers validate the model here.',
                'static inline __attribute__((always_inline)) int ma_control_checked(ma_controller*c,\n'
                '    const ma_motor*m,const float*x,const ma_geometry*g,int algorithm,float ia,float ib,\n'
                '    float reference_hz,float bus,float dt,int fresh,ma_output*out,int model_ok){\n'
                '  return ma_control_with_speed_admission(c,m,x,g,algorithm,ia,ib,reference_hz,bus,dt,\n'
                '    fresh,out,model_ok,1);\n}\n'
                '/* General callers validate the model here.')
    changes[relative]=original,text
    relative = 'nucleo/Src/multi_native.c'
    original = release.read(BASE/relative)
    text = once(original,'typedef struct {float x[6];uint32_t stamp;} ma_estimate_slot;',
                'typedef struct {float x[6];uint32_t stamp;uint8_t speed_ready;} ma_estimate_slot;')
    text = once(text,'static int ma_estimate_publish(const float*x,uint32_t stamp){',
                'static int ma_estimate_publish(const float*x,uint32_t stamp,uint8_t speed_ready){')
    text = once(text,' estimate_slot[next].stamp=stamp;',
                ' estimate_slot[next].stamp=stamp;\n estimate_slot[next].speed_ready=speed_ready;')
    text = once(text,'static uint32_t ma_estimate_read(float*x){',
                'static uint32_t ma_estimate_read(float*x,uint8_t*speed_ready){')
    text = once(text,' return estimate_slot[index].stamp;',
                ' *speed_ready=estimate_slot[index].speed_ready;\n return estimate_slot[index].stamp;')
    text = once(text,'  ma_observer_done_cycles=DWT->CYCCNT;',
                '  const uint8_t speed_ready=(uint8_t)(!fault&&observer.steps>=500U&&observer.nis<25.f&&\n'
                '    hypotf(observer.x[2],observer.x[3])>model.flux*.5f);\n'
                '  ma_observer_done_cycles=DWT->CYCCNT;')
    text = once(text,'ma_estimate_publish(endpoint_estimate,stamp);',
                'ma_estimate_publish(endpoint_estimate,stamp,speed_ready);')
    text = once(text,'  float x[6];uint32_t est_cycles=ma_estimate_read(x);',
                '  float x[6];uint8_t speed_ready;uint32_t est_cycles=ma_estimate_read(x,&speed_ready);')
    marker = ('    fault=ma_control_checked(&controller,&fe_control_model,x,&g,selected,ma_amps(sample.counts[0]),\n'
              '    (ma_amps(sample.counts[0])+2.f*ma_amps(sample.counts[1]))*.5773502692f,\n'
              '    reference_hz,VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super),1.f/16000U,fresh,&out,model_ok);')
    text = once(text,marker,marker.replace('ma_control_checked','ma_control_with_speed_admission').replace('out,model_ok);','out,model_ok,speed_ready);'))
    text = once(text,' fe_rc=avrc?avrc:ma_control_checked(&fe_test_controller,',
                ' volatile uint8_t speed_ready=(uint8_t)(fe_case&1U);\n'
                ' fe_rc=avrc?avrc:ma_control_with_speed_admission(&fe_test_controller,')
    text = once(text,'fe_test_bus,1.f/16000U,1,&fe_test_out,model_ok);',
                'fe_test_bus,1.f/16000U,1,&fe_test_out,model_ok,speed_ready);')
    changes[relative]=original,text

    diffs=[]
    for relative,(before,after) in changes.items():
        p=CANDIDATE/relative;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(after,encoding='utf8')
        diffs.extend(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),
                                         'a/'+relative,'b/'+relative))
    (OUT/'source_changes.patch').write_text(''.join(diffs),encoding='utf8')


def test_kernel():
    out=OUT/'PC_verification';out.mkdir()
    header=(CANDIDATE/'nucleo/Inc/motor_control.h').as_posix()
    source=f'#include "{header}"\n'+r'''
#include <cassert>
#include <cstdio>
#include "foc_experiment.h"
int main(){
  const ma_motor motor=FE_ESTIMATED_MOTOR;
  const ma_geometry g={5312,5184,771,112,240,229};
  const float ia=-.2596263f,ib=-.7377065f,reference=.9f,dt=1.f/16000.f;
  const float x[6]={-.1684476f,-.6725104f,-.199377f,-.08908632f,-14.100735f,.13949648f};
  float alternative[6];memcpy(alternative,x,sizeof(alternative));alternative[4]=90.f;
  ma_controller before={};before.time_s=.4f;before.speed_integral=.02f;
  ma_controller ready=before,warm=before,changed=before;
  ma_output original,qualification,provisional,alternate;
  assert(ma_control_checked(&before,&motor,x,&g,MA_FOC,ia,ib,reference,322.f,dt,1,&original,1)==MA_OK);
  assert(fabsf(original.iq_ref)>.1f);
  assert(ma_control_with_speed_admission(&ready,&motor,x,&g,MA_FOC,ia,ib,reference,322.f,dt,1,&qualification,1,1)==MA_OK);
  assert(!memcmp(&ready,&before,sizeof(ready))&&!memcmp(&qualification,&original,sizeof(qualification)));
  assert(ma_control_with_speed_admission(&warm,&motor,x,&g,MA_FOC,ia,ib,reference,322.f,dt,1,&provisional,1,0)==MA_OK);
  assert(ma_control_with_speed_admission(&changed,&motor,alternative,&g,MA_FOC,ia,ib,reference,322.f,dt,1,&alternate,1,0)==MA_OK);
  assert(provisional.iq_ref==0.f&&warm.speed_integral==0.f);
  assert(!memcmp(&warm,&changed,sizeof(warm))&&!memcmp(provisional.ccr,alternate.ccr,sizeof(provisional.ccr)));
  assert(provisional.id_ref==original.id_ref);
  for(int flag:{0,1}){
    assert(ma_control_with_speed_admission(&warm,&motor,x,&g,MA_FOC,1.36f,0,reference,322.f,dt,1,&provisional,1,flag)==MA_CURRENT);
    assert(ma_control_with_speed_admission(&warm,&motor,x,&g,MA_FOC,ia,ib,reference,322.f,dt,0,&provisional,1,flag)==MA_STALE);
    assert(ma_control_with_speed_admission(&warm,&motor,x,&g,MA_FOC,ia,ib,reference,0.f,dt,1,&provisional,1,flag)==MA_BUS);
  }
  printf("{\"unqualified_speed_torque_A_before\":%.9g,\"unqualified_speed_torque_A_candidate\":0,"
         "\"qualified_path_bit_identical\":true,\"raw_current_age_and_bus_guards_preserved\":true}\n",original.iq_ref);
}
'''
    source='#include <initializer_list>\n'+source
    program=compile_case(out,'speed_admission_kernel',source,BASE)
    return json.loads(subprocess.check_output([str(program)],text=True,timeout=30))


def test_plant():
    out=OUT/'PC_verification'
    template = release.read(ROOT/'artifacts/live_bench_20261117/observer_pair_noise_r1/verification/pair_plant_candidate.cpp')
    prefix=template.split('#define MIC_NATIVE_BUILD',1)[0]
    assert 'static void mic_current_request_observer_capture(){}' in prefix
    prefix=prefix.replace('static void mic_current_request_observer_capture(){}',
                          'static void mic_current_request_observer_capture(uint32_t,uint32_t,uint32_t){}')
    tail=template[template.index('#undef ma_observe_noise'):]
    prefix='#include "observer_start_history.h"\n'+prefix+'\nstatic float max_prequalification_iq;\n'
    tail=tail.replace(' int rc=ma_native_fast(reference);',
        ' int rc=ma_native_fast(reference);\n'
        ' if(observer.steps<500U)max_prequalification_iq=fmaxf(max_prequalification_iq,fabsf(bin_iqref));')
    tail=tail.replace('if(scenario==17){','if(scenario==17&&frames==4800U){')
    tail=tail.replace('\\\"peak_NIS\\\":%.9g}', '\\\"peak_NIS\\\":%.9g,\\\"prequalification_Iq_ref_max_A\\\":%.9g}')
    tail=tail.replace(',peak_nis);', ',peak_nis,max_prequalification_iq);')
    cases=((0,'nominal'),(1,'Rs_plus20pct'),(2,'Rr_plus20pct'),(3,'Lm_minus5pct'),
           (4,'ADC_1count'),(5,'ADC_16counts'),(8,'IGBT_drop_0_5V'),(9,'IGBT_drop_1V'),
           (10,'IGBT_drop_1_5V'),(11,'IGBT_drop_2V'),(12,'deadtime_plus0_25us'),
           (13,'deadtime_plus0_50us'),(14,'deadtime_minus0_25us'),(15,'Ron_1ohm'),
           (16,'ADC_offset8counts'),(17,'raw_overcurrent'),(18,'current_scale_minus10pct'),
           (19,'current_scale_plus10pct'),(0,'observer_2_1ms'))
    result={}
    for name,folder in (('baseline',BASE),('candidate',CANDIDATE)):
        h=(folder/'nucleo/Inc/motor_control.h').as_posix()
        pre='#include "'+h+'"\n'+prefix
        program=compile_case(out,name+'_plant',pre+native_source(folder)+'\n'+tail,BASE)
        for code,label in cases:
            stale=label=='observer_2_1ms'
            wall,queue=('357000','0') if stale else ('95737','17000')
            run=subprocess.run([str(program),wall,queue,str(code),str(out/f'{name}_{label}.bin')],
                               check=True,capture_output=True,text=True,timeout=30)
            result.setdefault(label,{})[name]=json.loads(run.stdout)
    assert all(r['candidate']['prequalification_Iq_ref_max_A']==0 for r in result.values())
    assert result['nominal']['baseline']['prequalification_Iq_ref_max_A']>0
    for name in ('baseline','candidate'):
        assert result['observer_2_1ms'][name]['fault']==3
        assert result['raw_overcurrent'][name]['fault']==2
    return result


def arm_compile(*, output=None, source=None, definitions=()):
    from build_multi_native import BIN
    out=output if output is not None else OUT/'ARM_verification'
    out.mkdir(exist_ok=True)
    source=source if source is not None else CANDIDATE
    debug=BASE/'nucleo/STM32CubeIDE/Debug'
    gcc=BIN/'arm-none-eabi-gcc.exe'
    makefile=release.read(debug/'Application/User/subdir.mk')
    recipe=next(line for line in makefile.split('Application/User/multi_native.o:',1)[1].splitlines()
                if 'arm-none-eabi-gcc' in line)
    flags=recipe.split('"$<" ',1)[1].split(' -o "$@"',1)[0].split()
    flags=[f for f in flags if not f.startswith(('-MMD','-MP','-MF','-MT'))]
    obj=out/'candidate.o'
    command=[str(gcc),str(source/'nucleo/Src/multi_native.c'),'-I'+str(source/'nucleo/Inc'),
             *definitions,*flags,'-o',str(obj)]
    result=subprocess.run(command,cwd=debug,capture_output=True,timeout=30)
    (out/'compile.log').write_bytes(result.stdout+result.stderr);result.check_returncode()
    assert b'warning:' not in result.stderr
    old=debug/'Application/User/multi_native.o'
    with old.open('rb') as f, obj.open('rb') as g:
        eb,ec=ELFFile(f),ELFFile(g)
        same={k:eb.get_section_by_name('.text.'+k).data()==ec.get_section_by_name('.text.'+k).data()
              for k in ('mic_observer_step','mic_observer_noise')}
        assert all(same.values())
        sizes={k:[e.get_section_by_name('.text.'+k).data_size for e in (eb,ec)]
               for k in ('ma_native_fast','ma_native_service','ma_native_profile_tick')}
    objects=release.read(debug/'objects.list')
    assert objects.count('"./Application/User/multi_native.o"')==1
    response=out/'objects.list'
    release.write(response,objects.replace('"./Application/User/multi_native.o"',f'"{obj.as_posix()}"'))
    line=next(line for line in release.read(debug/'makefile').splitlines() if 'arm-none-eabi-gcc -o' in line)
    flags=[i.strip('"') for i in re.findall(r'(?:[^\s"]|"[^"]*")+',line.split('$(LIBS) ',1)[1])
           if not i.startswith(('-T','-Wl,-Map='))]
    elf=out/'speed_admission_linkcheck_DO_NOT_FLASH.elf'
    result=subprocess.run([str(gcc),'-o',str(elf),'@'+str(response),'-T'+str(debug.parent/'STM32G431RBTX_FLASH.ld'),*flags],
                          cwd=debug,capture_output=True,timeout=30)
    (out/'link.log').write_bytes(result.stdout+result.stderr);result.check_returncode()
    return {'linked':True,'byte_identical_observer_NIS_and_noise':same,'code_sizes_bytes':sizes,
            'measured_target_cycles':False,'compiled_OFF_gate_cycles':4000,'age_limit_ms':2}


def main():
    import argparse

    global OUT, CANDIDATE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,default=OUT)
    OUT=parser.parse_args().outdir.resolve()
    CANDIDATE=OUT/'candidate'
    old=verify_inputs();OUT.mkdir()
    release.save(OUT/'preserved_inputs_sha256.json',old)
    result=reconstruct();release.save(OUT/'ADC_and_model_evidence.json',result)
    make_overlay()
    kernel=test_kernel();release.save(OUT/'PC_verification/kernel.json',kernel)
    sim=test_plant();release.save(OUT/'PC_verification/independent_plant.json',sim)
    arm=arm_compile();release.save(OUT/'ARM_verification/report.json',arm)
    release.verify_inventory(old,ROOT)
    release.save(OUT/'summary.json',{'tested_speed_feedback_admission':True,'step571_NIS':result['baseline']['NIS'],
        'physical_NIS_root_cause_proven':False,'real_step_571_NIS_removed':False,
        'installed':False,'target_timing_measured':False,'candidate_ready_to_flash':False,
        'protected_files':len(old),'hardware_commands':0,
        'simulated_baseline_successes':sum(r['baseline']['completed_5s'] for r in sim.values()),
        'simulated_candidate_successes':sum(r['candidate']['completed_5s'] for r in sim.values()),
        'candidate_regressions':[name for name,r in sim.items()
                                 if r['baseline']['completed_5s'] and not r['candidate']['completed_5s']],
        'limits':[25,4000,2]})
    print(json.dumps({'kernel':kernel,'simulations':len(sim),'arm':arm}))


if __name__=='__main__':
    main()
