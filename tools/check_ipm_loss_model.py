"""Check an explicit, configurable IPM voltage model on saved captures and a PC plant."""
import ctypes
import csv
import difflib
import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np

import analyze_nis571_startup as startup
from observer_exact_peak_decode import decode_exact_adc_peak_hex
from replay_start_history import ArmObserver
from test_observer_current_window import compile_case


release=startup.release
ROOT=startup.ROOT
BASE=startup.BASE
OUT=BASE/'step571_ipm_model_r1'
MODEL=OUT/'candidate'
HISTORY=OUT/'startup_history'

LOSS=r'''
/* Inferred voltage affects the model and PWM feed-forward only. Neither
 * the programmed TIM1 dead time nor the ADC aperture uses these offsets.
 * Zero values are the uncalibrated board default. Characterization inputs
 * for another inverter must come from its own measurements. */
#ifndef MA_IPM_DEVICE_DROP_MV
#define MA_IPM_DEVICE_DROP_MV 0
#endif
#ifndef MA_IPM_ON_MILLIOHMS
#define MA_IPM_ON_MILLIOHMS 0
#endif
#ifndef MA_IPM_EDGE_ADJUST_HALF_TICKS
#define MA_IPM_EDGE_ADJUST_HALF_TICKS 0
#endif
#if MA_IPM_DEVICE_DROP_MV < 0 || MA_IPM_ON_MILLIOHMS < 0
#error Inverter conduction losses must be nonnegative
#endif

static inline void ma_voltage_loss_ab(const ma_geometry*g,float bus,float ia,float ib,
                                      float*loss_a,float*loss_b){
#if MA_IPM_EDGE_ADJUST_HALF_TICKS != 0
  const float edge_adjust=(float)MA_IPM_EDGE_ADJUST_HALF_TICKS*.5f;
  /* With a calibrated, signed edge correction, zero effective time is the
   * lower bound of this term. Conduction loss is independent. */
  const float ticks=ma_max2(0.f,(float)g->deadtime_ticks+edge_adjust);
#else
  const uint32_t ticks=g->deadtime_ticks;
#endif
  const float switching=bus*ticks/(2.f*g->arr);
#if MA_IPM_DEVICE_DROP_MV != 0
  const float threshold=switching+(float)MA_IPM_DEVICE_DROP_MV*.001f;
#else
  const float threshold=switching;
#endif
  const float u=threshold*ma_current_polarity(ia);
  const float v=threshold*ma_current_polarity(-.5f*ia+.8660254038f*ib);
  const float w=threshold*ma_current_polarity(-.5f*ia-.8660254038f*ib);
  *loss_a=(2.f*u-v-w)/3.f;
  *loss_b=(v-w)*.5773502692f;
#if MA_IPM_ON_MILLIOHMS != 0
  const float r=(float)MA_IPM_ON_MILLIOHMS*.001f;
  *loss_a+=r*ia;
  *loss_b+=r*ib;
#endif
}
'''


def prepare_model():
    inc=MODEL/'nucleo/Inc';inc.mkdir(parents=True)
    source=MODEL/'nucleo/Src';source.mkdir()
    dd=[]
    def save(rel,old,new):
        release.write(MODEL/rel,new)
        dd.extend(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),
                                      'a/'+rel,'b/'+rel))

    path='nucleo/Inc/motor_control.h'
    old=release.read(startup.CANDIDATE/path)
    mark='static inline int ma_motor_valid('
    assert old.count(mark)==1
    code=old.replace(mark,LOSS+'\n'+mark)
    a=code.index('  const float loss=bus*g->deadtime_ticks/(2.f*g->arr);')
    b=code.index('  float aperture_scale=1;',a)
    code=code[:a]+'  float loss_a,loss_b;ma_voltage_loss_ab(g,bus,ia,ib,&loss_a,&loss_b);\n'+code[b:]
    save(path,old,code)
    path='nucleo/Inc/observer_applied_voltage.h'
    old=release.read(BASE/path)
    a=old.index(' const float loss=(float)bus*g->deadtime_ticks/(2.f*arr);')
    b=old.index(' return MA_OK;',a)
    new=old[:a]+''' float loss_a,loss_b;
 ma_voltage_loss_ab(g,(float)bus,ia,ib,&loss_a,&loss_b);
 *va=((float)ccr[0]-average)*factor-loss_a;
 *vb=((float)ccr[1]-ccr[2])*factor*.5773502692f-loss_b;
'''+old[b:]
    new=new.replace(' * or motor identification is claimed. The existing dead-time model is retained.',
                    ' * or motor identification is claimed. Loss parameters are explicit.')
    save(path,old,new)
    shutil.copyfile(startup.CANDIDATE/'nucleo/Src/multi_native.c',source/'multi_native.c')
    release.write(OUT/'voltage_model.patch',''.join(dd))


def arguments(drop_mv=0,resistance_mohm=0,edges_half_ticks=0):
    return [f'-DMA_IPM_DEVICE_DROP_MV={drop_mv}',f'-DMA_IPM_ON_MILLIOHMS={resistance_mohm}',
            f'-DMA_IPM_EDGE_ADJUST_HALF_TICKS={edges_half_ticks}']


PARAMETERS={'stock':(0,0,0),'drop_2V':(2000,0,0),'edges_minus_250ns':(0,0,-85),
            'drop_2V_edges_minus_250ns':(2000,0,-85),'ron_1ohm':(0,1000,0)}


def fixture():
    # Reuse the previously checked independent motor/bridge plant. The
    # real plant owns drop, loss and timing, separately from the new model.
    old_file=startup.OUT/'PC_verification/candidate_plant.cpp'
    old=release.read(old_file)
    end=old.index('\n')
    new='#include "'+(MODEL/'nucleo/Inc/motor_control.h').as_posix()+'"'+old[end:]
    old_line='#include "observer_applied_voltage.h"'
    assert new.count(old_line)==1
    new=new.replace(old_line,'#include "'+(MODEL/'nucleo/Inc/observer_applied_voltage.h').as_posix()+'"')
    marker='static float max_prequalification_iq;'
    assert new.count(marker)==1
    new=new.replace(marker,marker+'\nstatic FILE* focus_stream;')
    marker=' setup();'
    assert new.count(marker)==1
    new=new.replace(marker,marker+'\n if(argc>=6){focus_stream=fopen(argv[5],"w");assert(focus_stream);}')
    marker='     peak_nis=fmax(peak_nis,observer.nis);'
    assert new.count(marker)==1
    new=new.replace(marker,'''     if(focus_stream&&observer.steps<=650U){
       fprintf(focus_stream,"%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\\n",observer.steps,
         (double)bin_window.ia,(double)observer.predicted_i[0],(double)observer.x[0],
         (double)bin_va,(double)bin_vb,(double)observer.nis);
     }
'''+marker)
    marker=' bool completed=fe_trial_done'
    assert new.count(marker)==1
    return new.replace(marker,' if(focus_stream)fclose(focus_stream);\n'+marker)


def run_plant():
    out=OUT/'PC_plant';out.mkdir()
    corr=fixture()
    cases=(('nominal',0),('Rs_plus20pct',1),('Rr_plus20pct',2),('Lm_minus5pct',3),
           ('ADC_1count',4),('ADC_16counts',5),('drop_0_5V',8),('drop_1V',9),('drop_1_5V',10),
           ('drop_2V',11),('edges_plus_250ns',12),('edges_plus_500ns',13),('edges_minus_250ns',14),
           ('ron_1ohm',15),('offset_8counts',16),('raw_overcurrent',17),('gain_minus10pct',18),
           ('gain_plus10pct',19),('observer_stale_2_1ms',0))
    results={}
    for name,params in PARAMETERS.items():
        source=''.join(f'#define {x[2:].replace("="," ",1)}\n' for x in arguments(*params))+corr
        exe=compile_case(out,name,source,BASE)
        # The stock profile exercises the full previous set. Other profiles
        # are characterized on matched, mismatched and negative controls.
        wanted=cases if name=='stock' else [x for x in cases if x[0] in
            ('nominal','drop_2V','edges_minus_250ns','ron_1ohm','raw_overcurrent','observer_stale_2_1ms')]
        for label,scenario in wanted:
            timing=('357000','0') if label=='observer_stale_2_1ms' else ('95737','17000')
            args=[str(exe),*timing,str(scenario),str(out/(name+'_'+label+'.bin'))]
            if label=='drop_2V' and name in ('stock','drop_2V'):
                args.append(str(out/(name+'_2V_warmup.csv')))
            r=subprocess.run(args,check=True,capture_output=True,text=True,timeout=30)
            results.setdefault(label,{})[name]=json.loads(r.stdout)
    previous=release.read_json(startup.OUT/'PC_verification/independent_plant_final.json')
    assert results['drop_2V']['stock']==previous['IGBT_drop_2V']['candidate']
    assert results['drop_2V']['drop_2V']['completed_5s']
    assert results['nominal']['stock']['completed_5s']
    assert results['edges_minus_250ns']['edges_minus_250ns']['completed_5s']
    assert results['ron_1ohm']['ron_1ohm']['completed_5s']
    for model in PARAMETERS:
        assert results['raw_overcurrent'][model]['fault']==2
        assert results['observer_stale_2_1ms'][model]['fault']==3
    release.save(out/'cases.json',results)
    return results


def capture_inputs():
    prior=ROOT/'artifacts/live_bench_20261118/exact_nis_input_release_r1'
    return {'571':(startup.DATA/'observer_trace_decoded.json',startup.TRIAL/'paged_capture/ADC_peak.bin',startup.ELF,2026112102),
            '659':(prior/'FOC_5Hz_r2/observer_trace_decoded.json',prior/'FOC_5Hz_r2/ADC_peak.bin',
                   prior/'release/nucleo_2026111802_exact_source.elf',2026111802)}


def compare_captures():
    out=OUT/'saved_capture_replay';out.mkdir()
    dlls={}
    for name,params in PARAMETERS.items():
        dll=out/(name+'.dll')
        cmd=[shutil.which('g++'),'-std=c++17','-O2','-ffp-contract=off','-shared',*arguments(*params),
             '-I',str(MODEL/'nucleo/Inc'),'-I',str(BASE/'nucleo/Inc'),str(ROOT/'tools/rebuild_exact_adc_source.cpp'),'-o',str(dll)]
        subprocess.run(cmd,check=True,capture_output=True,timeout=30)
        fn=ctypes.CDLL(str(dll)).rebuild_exact
        fn.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_float]
        dlls[name]=fn
    results={}
    for step,(trace,adc,elf,fw) in capture_inputs().items():
        a=adc.read_bytes(); window=decode_exact_adc_peak_hex(a.hex(),fw)
        event=release.read_json(trace)['first_nis_replay']
        assert int(step)==window['source_observer_step']==event['post_steps']
        payload=bytes.fromhex(event['raw_hex']); prior=payload[:168]+bytes(28)+payload[168:176]
        counts=struct.unpack_from('<I',payload,452)[0]>>8
        original=struct.unpack_from('<5f',payload,228)
        targets={}; arm=ArmObserver(elf)
        for model,rebuild in dlls.items():
            bin_data,points=ctypes.create_string_buffer(48),ctypes.create_string_buffer(400)
            assert rebuild(a,bin_data,points,-1)==0
            inp=struct.unpack_from('<4f',bin_data.raw)
            assert inp[:2]==original[:2],(step,model,inp[:2],original[:2])
            rc,post,_=arm.step(prior,payload[176:228],struct.pack('<5f',*inp,original[-1]),event['fpscr'],counts)
            assert rc==0
            nis,pu,pb=struct.unpack_from('<3f',post,168)
            targets[model]={'NIS':nis,'U_alpha_beta_volts':inp[2:4],
                            'predicted_current_alpha_beta_A':[pu,pb]}
        assert abs(targets['stock']['NIS']-event['nis'])<2e-5
        results[step]=targets
    release.save(out/'report.json',results)
    return results


def clarke_polarity(ia,ib):
    phases=(ia,-.5*ia+.8660254037844386*ib,-.5*ia-.8660254037844386*ib)
    u,v,w=(max(-1.,min(1.,i/.05)) for i in phases)
    return (2*u-v-w)/3.,(v-w)/math.sqrt(3.)


def history_replay():
    folder=HISTORY
    chunks=(folder/'rows.bin').read_bytes()
    witness=release.read_json(folder/'ARM_exact_replay.json')
    assert witness['rows']==83 and witness['terminal_51_words_bit_exact']
    meta=(folder/'meta.bin').read_bytes()
    from replay_start_history import pair_counts

    inputs=[chunks[i:i+22] for i in range(0,len(chunks),22)]
    original=[struct.unpack_from('<5f',row) for row in inputs]
    arm=ArmObserver(startup.ELF)
    a,b=0.,0.
    basis=[]
    for ia,ib,*_ in original:
        c,d=clarke_polarity(ia,ib)
        basis.append(((a+c)/2.,(b+d)/2.))
        a,b=c,d

    def evaluation(loss):
        prior=meta[116:320]
        nis_history=[]
        event=None
        for number,(r,v,(a,b)) in enumerate(zip(inputs,original,basis),1):
            x=[v[0],v[1],v[2]-loss*a,v[3]-loss*b,v[4]]
            rc,post,_=arm.step(prior,meta[64:116],struct.pack('<5f',*x),(r[21]>>3)<<22,pair_counts(r[20]))
            result=struct.unpack_from('<7f',post,168)
            if rc!=0:
                return {'correction_V':loss,'numeric_kernel_result':rc,'stopped_at_step':number}
            nis_history.append(result[0])
            if number==83:
                event={'predicted_alpha_beta_A':list(result[1:3]),'conditional_residual_A':list(result[3:5]),
                       'conditional_NIS_terms':[e*e/s for e,s in zip(result[3:5],result[5:7])],
                       'nis':result[0],'measured_alpha_beta_A':list(v[:2])}
            prior=post
        if loss==0:
            assert prior==meta[320:524]
        return {'correction_V':loss,'training_mean_NIS_steps16_55':float(np.mean(nis_history[15:55])),
                'held_out_mean_NIS_steps56_83':float(np.mean(nis_history[55:83])),
                'held_out_max_NIS_steps56_83':max(nis_history[55:83]),'event83':event}

    grid=[evaluation(n/4.) for n in range(-8,9)]
    used=[r for r in grid if 'training_mean_NIS_steps16_55' in r]
    # The 0.25 V grid is only a sensitivity study. It uses averaged current
    # polarity for early bins because their raw PWM-frame history is absent.
    fit=min(used,key=lambda r:r['training_mean_NIS_steps16_55'])
    result={'records':83,'first_crossing_before_speed_loop':True,'window_time_s':sum(x[4] for x in original),
            'score_grid':grid,'training_best':fit,'fixed_2V':grid[-1],
            'first_failed_step_baseline':83,'baseline':grid[8],
            'model_voltage_required_for_physical_calibration':True,
            'limitations':'early 83 mean-current windows only. The between-window polarity is approximate and step 84..570 is missing.'}
    release.save(OUT/'startup_model_sensitivity.json',result)
    return result


def check_identifiability():
    frame_coefficients=[]
    group=[]
    for trace,adc,elf,fw in capture_inputs().values():
        record=decode_exact_adc_peak_hex(adc.read_bytes().hex(),fw)
        rows=record['source_voltage_history']
        group.append(sorted({r['bus_v'] for r in rows}))
        coeff=[]
        for row in rows:
            # Rescale to compare one volt to 250ns at the actual PWM clock.
            switching_scale=42.5*row['bus_v']/(2*row['timer_arr'])
            coeff.append([1.,switching_scale])
        frame_coefficients.extend(coeff)
        assert np.linalg.matrix_rank(np.array(coeff))==1
    singular=np.linalg.svd(np.array(frame_coefficients),compute_uv=False)
    result={'bus_voltages_per_capture':group,'individual_capture_rank':1,'joint_condition_number':float(singular[0]/singular[1]),
            'columns':'threshold volts and effective edge time in units of 250 ns, before common polarity projection',
            'physically_distinguishable_from_current_alone':False}
    release.save(OUT/'ipm_identifiability.json',result)
    return result


def verification():
    OUT.mkdir(parents=True,exist_ok=True)
    protected=protected_inputs()
    release.save(OUT/'preserved_inputs_sha256.json',protected)
    prepare_model()
    run_plant()
    compare_captures()
    history_replay()
    check_identifiability()
    arm_path=OUT/'ARM_model_verification';arm_path.mkdir()
    model2=startup.arm_compile(output=arm_path/'drop_2V',source=MODEL,definitions=arguments(2000))
    stock=startup.arm_compile(output=arm_path/'stock',source=MODEL,definitions=arguments())
    release.save(arm_path/'report.json',{'drop_2V':model2,'stock':stock})
    return summarize()


def protected_inputs():
    protected=startup.verify_inputs()
    for path in (startup.OUT,HISTORY):
        for f in path.rglob('*'):
            if f.is_file():protected[f.relative_to(ROOT).as_posix()] = release.digest(f)
    for elements in capture_inputs().values():
        for f in elements[:3]:protected[f.relative_to(ROOT).as_posix()] = release.digest(f)
    release.verify_inventory(protected,ROOT)
    return protected


def summarize():
    protected=protected_inputs()
    release.save(OUT/'preserved_inputs_sha256.json',protected)
    sim=release.read_json(OUT/'PC_plant/cases.json')
    observed=release.read_json(OUT/'saved_capture_replay/report.json')
    history=release.read_json(OUT/'startup_model_sensitivity.json')
    info=release.read_json(OUT/'ipm_identifiability.json')
    arm=release.read_json(OUT/'ARM_model_verification/report.json')
    assert all(r['linked'] and all(r['byte_identical_observer_NIS_and_noise'].values()) for r in arm.values())
    gains={}
    for model in ('stock','drop_2V'):
        with (OUT/'PC_plant'/(model+'_2V_warmup.csv')).open(newline='') as f:
            rows=np.array(list(csv.reader(f)),dtype=float)
        g=rows[(rows[:,0]>=400)&(rows[:,0]<=500)]
        endpoint=rows[rows[:,0]==500][0]
        gains[model]={'step500_nis':float(endpoint[-1]),'rms_U_prediction_error_400_500_A':float(np.sqrt(np.mean((g[:,1]-g[:,2])**2)))}
    assert gains['stock']['step500_nis']>25>gains['drop_2V']['step500_nis']
    assert observed['571']['drop_2V']['NIS']>observed['571']['stock']['NIS']
    report={'simulation_2V_cause_verified':True,
        'source_model_with_explicit_calibration':True,'simulation_2V_completed_5s':sim['drop_2V']['drop_2V']['completed_5s'],
        'synthetic_2V_window_metrics':gains,'synthetic_0V_speed_with_mismatched_2V_model_rpm':sim['nominal']['drop_2V']['rpm_true_end'],
        'step571_2V_does_not_explain_real_failure':observed['571']['drop_2V']['NIS']>observed['571']['stock']['NIS'],
        'real_model_validated_for_installation':False,'installed':False,'hardware_enable_commands':0,
        'early_steps_replayed':history['records'],'physical_edge_drop_cross_correlation':info['joint_condition_number'],
        'NIS':25,'OFF_fast_budget_cycles':4000,'estimate_age_ms':2,
        'protection_mathematics_unchanged':True,'target_time_measured':False,'archived_inputs_verified':len(protected)}
    release.save(OUT/'summary.json',report)
    return report


if __name__=='__main__':
    import argparse

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,default=OUT)
    parser.add_argument('--startup-history',type=Path,default=HISTORY)
    options=parser.parse_args()
    OUT=options.outdir.resolve()
    HISTORY=options.startup_history.resolve()
    MODEL=OUT/'candidate'
    print(json.dumps(verification()))
