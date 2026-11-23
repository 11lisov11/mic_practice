"""Replay the stationary-start capture and test a bounded I/f startup on PC."""

import argparse
import csv
import difflib
import json
import math
import struct
import subprocess
from pathlib import Path

import build_foc_stationary_start_release as installed
import check_foc_stationary_start as pc
import run_nis_admission_paged_trial as archive
from replay_start_history import replay
from test_observer_current_window import compile_case


BASE = installed.OUT
DEFAULT_OUT = BASE / 'foc_rotating_start_r2'
TRIAL = BASE / 'FOC_5Hz_stationary_start_r1'
HISTORY = BASE / 'FOC_5Hz_stationary_start_r1_history'
HEADER, NATIVE = pc.HEADER, pc.NATIVE
change = pc.replace_once


def prepare(out):
    header = installed.read(BASE / HEADER)
    header = change(header, '  uint8_t preflux; /* 0 unused, 1 stationary frame, 2 handed over */', '''  uint8_t preflux; /* 0 unused, 1 commanded current frame, 2 handed over */
  float start_cos,start_sin;''')
    start = header.index('  /* Establish rotor flux along a commanded stator axis.')
    end = header.index('  const float id=c0*ia+s*ib', start)
    header = header[:start] + '''  if(!speed_ready&&c->preflux==0U){
    c->start_cos=1.f;c->start_sin=0.f;c->preflux=1U;
  }
  float c0=1.f,s=0.f,start_omega=0.f;
  if(c->preflux==1U){
    /* Magnetize for 100 ms, then follow the bounded electrical reference in
     * a commanded current frame. Rotor speed is not used during I/f. */
    const float start_hz=c->time_s<.10f?0.f:ma_min2(reference_hz,5.f);
    start_omega=6.2831853072f*start_hz;
    const float delta=start_omega*dt;
    const float next_c=c->start_cos-delta*c->start_sin;
    const float next_s=c->start_sin+delta*c->start_cos;
    const float norm=1.5f-.5f*(next_c*next_c+next_s*next_s);
    c0=c->start_cos=next_c*norm;s=c->start_sin=next_s*norm;
    /* An accepted flux alone cannot authorize torque from an implausible
     * speed or a jump to an unrelated field axis. The existing NIS and age
     * checks remain independent and are still applied in I/f. */
    const float projection=c0*x[2]+s*x[3];
    const float estimated_electrical_speed=m->poles*x[4];
    if(speed_ready&&start_hz>=1.f&&projection>=.92f*flux&&
       fabsf(estimated_electrical_speed-start_omega)<=6.2831853072f){
      const float d=projection/flux,q=(c0*x[3]-s*x[2])/flux;
      const float a=c->integral[0],b=c->integral[1];
      c->integral[0]=d*a+q*b;c->integral[1]=-q*a+d*b;
      c->preflux=2U;
    }else speed_ready=0;
  }
  if(c->preflux!=1U&&flux>.0001f){c0=x[2]/flux;s=x[3]/flux;}
''' + header[end:]
    header = change(header, 'const float sync=stationary?0.f:', 'const float sync=c->preflux==1U?start_omega:')
    header = change(header, '''  const float res=m->rs+kr*ar*m->lm;
  const float ff[2]={res*id-kr*ar*flux-sync*l*iq,
    res*iq+kr*m->poles*omega*flux+sync*l*id};''', '''  const float res=m->rs+kr*ar*m->lm;
  /* I/f is a current loop. Its feed-forward uses Rs and the commanded
   * rotation only, leaving flux and back-EMF compensation to closed-loop. */
  const float ff[2]={c->preflux==1U?m->rs*id-sync*l*iq:res*id-kr*ar*flux-sync*l*iq,
    c->preflux==1U?m->rs*iq+sync*l*id:res*iq+kr*m->poles*omega*flux+sync*l*id};''')
    native = installed.read(BASE / NATIVE)
    native = change(native, 'static ow_state observer_window;', '''/* Experimental 5Hz profile: supervision of actual commanded dq-axis rate.
 * Measure over 16 observer windows, outside the PWM IRQ. A biased speed
 * estimate can otherwise be plausible at handover and later accelerate the
 * electrical field above the requested band even while NIS remains low. */
typedef struct {float alpha,beta,elapsed,angle_limit;uint8_t count,ready;} ma_field_rate;
static ma_field_rate field_rate;
static void ma_field_rate_update(ma_field_rate *rate,const float*x,float reference,float dt){
 if(!rate->count){
  rate->alpha=x[2];rate->beta=x[3];
  rate->elapsed=rate->angle_limit=0.f;rate->count=1U;return;
 }
 rate->elapsed+=dt;
 rate->angle_limit+=6.2831853072f*(reference+.75f)*dt;
 if(++rate->count<17U)return;
 const float cross=rate->alpha*x[3]-rate->beta*x[2];
 const float dot=rate->alpha*x[2]+rate->beta*x[3];
 const float angle=fabsf(atan2f(cross,dot));
 rate->ready=(uint8_t)(rate->elapsed>.010f&&rate->elapsed<.030f&&angle<=rate->angle_limit);
 rate->alpha=x[2];rate->beta=x[3];
 rate->elapsed=rate->angle_limit=0.f;rate->count=1U;
}
static ow_state observer_window;''')
    native = change(native, '  memset(ma_irq_last,0,sizeof(ma_irq_last));ma_perf_off=0;ma_reset(&observer,&controller);',
                     '''  memset(ma_irq_last,0,sizeof(ma_irq_last));ma_perf_off=0;ma_reset(&observer,&controller);
  memset(&field_rate,0,sizeof(field_rate));''')
    native = change(native, '''  float endpoint_estimate[6];
  if(!fault)fault=ow_forecast''', '''  if(!fault&&qualification==FE_ESTIMATED){
    ma_field_rate_update(&field_rate,observer.x,trace_ref,dt);
    if(__atomic_load_n(&controller.preflux,__ATOMIC_RELAXED)==2U&&!field_rate.ready){
      fault=MA_OBSERVER;
      ma_fail(MA_OBSERVER);
      ma_observer_record(&sample,stamp,trace_seq,trace_adc,trace_id,trace_iq,
        trace_idref,trace_iqref,trace_ref,va,vb,dt,fault,0,&window);
    }
  }
  float endpoint_estimate[6];
  if(!fault)fault=ow_forecast''')
    native = change(native, '''  const uint8_t speed_ready=(uint8_t)(!fault&&observer.steps>=500U&&observer.nis<25.f&&
    hypotf(observer.x[2],observer.x[3])>model.flux*.5f);''', '''  const uint8_t speed_ready=(uint8_t)(!fault&&observer.steps>=500U&&observer.nis<25.f&&
    hypotf(observer.x[2],observer.x[3])>model.flux*.5f&&
    (qualification!=FE_ESTIMATED||field_rate.ready));''')
    native = change(native, '  fe_test_controller.preflux=(uint8_t)(fe_n%3U);', '''  /* Include the open-loop and qualified handover branches in OFF DWT.
   * Synthetic inputs only. No output-enable, timer or protection writes. */
  fe_test_controller.preflux=(uint8_t)(fe_n%3U);
  fe_test_controller.start_cos=cosf((fe_case%16U)*.3926990817f);
  fe_test_controller.start_sin=sinf((fe_case%16U)*.3926990817f);
  if(fe_test_controller.preflux==1U&&(fe_case&9U)==9U)
    fe_test_x[4]=ma_min2(fe_test_ref,5.f)*6.2831853072f;''')
    native = change(native, '   float probe_forecast[6]={0};', '''   ma_field_rate rate_probe={fe_test_x[2],fe_test_x[3],.015f,.50f,16U,0U};
   ma_field_rate_update(&rate_probe,fe_test_observer.x,5.f,.001f);
   if(!rc&&rate_probe.count!=1U)rc=MA_OBSERVER;
   float probe_forecast[6]={0};''')
    native = change(native, '   fe_applied_a=probe_forecast[0];', '''   fe_applied_a=probe_forecast[0];
   fe_applied_b=rate_probe.ready?1.f:0.f;''')
    candidate = out / 'candidate'
    patch = []
    for name, contents in ((HEADER, header), (NATIVE, native)):
        path = candidate / name
        path.parent.mkdir(parents=True, exist_ok=True)
        installed.write(path, contents)
        before = installed.read(BASE / name)
        patch.extend(difflib.unified_diff(before.splitlines(keepends=True), contents.splitlines(keepends=True),
                                          'a/'+name, 'b/'+name))
    installed.write(out/'foc_rotating_start.patch',''.join(patch))
    return candidate


def saved_evidence(out, elf):
    with (TRIAL.with_name(TRIAL.name+'_analysis')/'observer_NIS_currents.csv').open(encoding='utf-8-sig') as stream:
        rows=list(csv.DictReader(stream))
    motor=struct.unpack_from('<7fI5f',(HISTORY/'meta.bin').read_bytes(),64)
    rotor_rate=motor[1]/motor[3]
    data=[]
    for row in rows:
        ia,iv,iw=(float(row['phase_'+phase+'_A']) for phase in 'uvw')
        ib=(iv-iw)/math.sqrt(3.)
        rpm=float(row['rpm_est'])
        expected=rotor_rate*motor[4]*math.hypot(ia,ib)/math.hypot(rotor_rate,motor[7]*rpm*math.pi/30.)
        data.append(dict(step=int(row['steps']),NIS=float(row['nis']),flux_Wb=float(row['flux_wb']),
                         estimated_speed_rpm=rpm,measured_current_alpha_beta_A=[ia,ib],
                         steady_flux_from_estimated_speed_Wb=expected,iq_reference_A=float(row['iq_ref_A']),
                         reason_mask=int(row['reason_mask'])))
    assert all(row['reason_mask']==16 and row['iq_reference_A']==0 for row in data)
    history=replay(HISTORY,elf,installed.NEW[1],out/'ARM_history.jsonl')
    result={'saved_decimated_rows':data,'full_history_before_first_crossing':history,
            'observability':'The constant-axis current and the biased estimated omega are compatible with a small inferred rotor flux; this does not measure rotor motion or terminal voltage.'}
    installed.save(out/'saved_evidence.json',result)
    return result


def model_source(candidate, variant):
    header = candidate / HEADER
    text=pc.simulation_source(candidate, variant)
    text=change(text, 'static unsigned first_torque_step;', '''static unsigned first_torque_step,handover_step;
static double maximum_plant_rpm;''')
    text=change(text, ' last_iq=bin_iqref;', ''' last_iq=bin_iqref;
 if(controller.preflux==2U&&!handover_step)handover_step=observer.steps;
 maximum_plant_rpm=fmax(maximum_plant_rpm,plant.x[4]*9.5492965855);''')
    # This exact signature is only a plant test hook. Keep the true observer
    # state, covariance, current, buses and NIS path, and suppress admission.
    text=change(text, '*speed_ready=estimate_slot[index].speed_ready;',
        '*speed_ready=force_unavailable?0U:estimate_slot[index].speed_ready;')
    text=change(text, '#define MIC_NATIVE_BUILD', 'static bool force_unavailable;\n#define MIC_NATIVE_BUILD')
    text=change(text, ' setup();', ' force_unavailable=scenario==23;\n setup();')
    text=change(text,r'\"peak_hold_speed_error_rpm\":%.9g}',
        r'\"peak_hold_speed_error_rpm\":%.9g,\"handover_step\":%u,\"maximum_plant_rpm\":%.9g}')
    text=change(text,'reference_max,peak_hold_speed_error);','reference_max,peak_hold_speed_error,handover_step,maximum_plant_rpm);')
    assert header.as_posix() in text
    return text


CASES=(('nominal',0),('unknown_speed_admission',23),('Rs_plus20pct',1),('Rr_plus20pct',2),
       ('Lm_minus5pct',3),('ADC_1count',4),('ADC_16counts',5),('phase_current_offset',16),
       ('voltage_model_1V',9),('voltage_model_2V',11),('effective_edge_minus250ns',14),
       ('raw_overcurrent',17),('estimate_age_2_1ms',0),('NIS_25',21),('NIS_just_below_25',22))


def simulate(out,candidate):
    dest=out/'PC';dest.mkdir()
    results={name:{} for name,_ in CASES}
    for variant,folder in (('stationary',BASE),('I_f',candidate)):
        executable=compile_case(dest,variant,model_source(folder,variant),BASE)
        for name,scenario in CASES:
            timing=['357000','0'] if name=='estimate_age_2_1ms' else ['95737','17000']
            run=subprocess.run([str(executable),*timing,str(scenario),str(dest/f'{variant}_{name}.bin'),'.443'],
                               check=True,capture_output=True,text=True,timeout=25)
            results[name][variant]=json.loads(run.stdout)
    installed.save(dest/'cases.json',results)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,default=DEFAULT_OUT)
    out=parser.parse_args().outdir.resolve()
    archive.release=installed
    _,preserved=archive.verify_release()
    for folder,name in ((TRIAL,'saved_files_sha256.json'),(HISTORY,None),
                        (BASE/'one_CLEAR_powered_r1','sha256.json')):
        inventory=installed.read_json(folder/name) if name else installed.read_json(folder/'download.json')['sha256']
        installed.verify_inventory(inventory,folder)
        preserved.update({(folder/rel).relative_to(installed.ROOT).as_posix():sha for rel,sha in inventory.items()})

    out.mkdir()
    candidate=prepare(out)
    results=simulate(out,candidate)
    prior_base=pc.previous.BASE
    try:
        pc.previous.BASE=BASE
        timing=pc.previous.arm_compile(output=out/'ARM_linkcheck',source=candidate)
    finally:
        pc.previous.BASE=prior_base
    evidence=saved_evidence(out,out/'ARM_linkcheck/speed_admission_linkcheck_DO_NOT_FLASH.elf')
    installed.verify_inventory(preserved,installed.ROOT)
    nominal=results['nominal']['I_f']
    quiet=results['unknown_speed_admission']
    bad_voltage=results['effective_edge_minus250ns']
    assertions={
        'nominal_reached_5Hz_with_handover': nominal['completed_5s'] and nominal['handover_step']>0
                                             and abs(nominal['rpm_true_end']-300)<15,
        'rotating_current_reaches_5Hz_without_using_bad_speed': quiet['I_f']['completed_5s']
                                   and quiet['I_f']['handover_step']==0 and abs(quiet['I_f']['rpm_true_end']-300)<15
                                   and abs(quiet['stationary']['rpm_true_end'])<5,
        'field_rate_guard_stops_model_overspeed': bad_voltage['stationary']['rpm_true_end']>500
                           and bad_voltage['I_f']['handover_step']>0 and bad_voltage['I_f']['fault']==5
                           and bad_voltage['I_f']['maximum_plant_rpm']<330 and bad_voltage['I_f']['peak_NIS']<25,
        'NIS_25_stops': results['NIS_25']['I_f']['fault']==5 and results['NIS_25']['I_f']['observer_calls']==571,
        'NIS_just_below_25_is_accepted': results['NIS_just_below_25']['I_f']['completed_5s'],
        'raw_current_trip': results['raw_overcurrent']['I_f']['fault']==2,
        'estimate_age_trip': results['estimate_age_2_1ms']['I_f']['fault']==3,
    }
    summary={'passed':all(assertions.values()),'checks':assertions,'nominal':nominal,'unavailable':quiet,
             'model_voltage_error_overspeed_test':bad_voltage,
             'archive_files_verified':len(preserved),'ARM':timing,'hardware_commands':0,
             'history_read_only_RPC':True,
             'observed_early_NIS_step':evidence['full_history_before_first_crossing']['first_NIS_ge25'],
             'NIS_trip':25,'OFF_cycles_limit':4000,'estimate_age_ms':2}
    installed.save(out/'verification.json',summary)
    print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
