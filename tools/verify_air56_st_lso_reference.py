"""Verify the ARM artifact, test bench limits, and model the adapted ST LSO."""

import argparse
import cmath
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from elftools.elf.elffile import ELFFile

from build_multi_native import BIN
from prepare_air56_st_lso_reference import NAME, OUT, ROOT
from install_foc_handover_feedback_release import read_json, sha, release

sys.path.insert(0,str(ROOT))
from motor_identification.model import MotorParameters, MotorState, _step


def verify_limits(out):
    source = out/'limit_checks.c'
    source.write_text(r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "air56_st_lso_limits.h"

int main(void) {
    unsigned checked = 0;
    const int64_t limit = AIR56_LSO_CURRENT_TRIP;
    for (int ia = -2300; ia <= 2300; ++ia) {
        for (int ib = -2300; ib <= 2300; ++ib) {
            const int64_t ic = -ia - ib;
            const bool expected = 2 * ((int64_t)ia * ia + (int64_t)ib * ib + ic * ic)
                                  > 3 * limit * limit;
            assert(air56_lso_overcurrent((int16_t)ia,(int16_t)ib) == expected);
            ++checked;
        }
    }
    assert(!air56_lso_overcurrent(2252,-1126));
    assert(air56_lso_overcurrent(2253,-1126));
    assert(air56_lso_overcurrent(1400,1000));
    assert(air56_lso_overcurrent(INT16_MIN,INT16_MIN));
    assert(air56_lso_overcurrent(INT16_MAX,INT16_MAX));
    uint32_t stamp = UINT32_MAX - 4;
    unsigned limits[] = {AIR56_LSO_ADC_AGE_CYCLES,AIR56_LSO_LINK_MS,AIR56_LSO_RUN_MS};
    for (unsigned i=0;i<sizeof limits/sizeof limits[0];++i) {
        assert(!air56_lso_stale(stamp+limits[i]-1, stamp, limits[i]));
        assert(air56_lso_stale(stamp+limits[i], stamp, limits[i]));
        assert(air56_lso_stale(stamp+limits[i]+1, stamp, limits[i]));
    }
    printf("%u\n",checked);
}
''',encoding='utf-8')
    exe = out/'limit_checks.exe'
    subprocess.run([shutil.which('gcc'),'-std=c11','-Wall','-Wextra','-Werror','-O2',
                    '-I',str(out/'Inc'),str(source),'-o',str(exe)],check=True,timeout=25)
    return int(subprocess.check_output([str(exe)],text=True,timeout=15))


def plant_model(profile, *, rs_scale=1., rr_scale=1., shunt_gain=1.):
    """Independent stationary-flux plant, with the configured ST dq observer/PI.

    The test uses averaged applied voltage and no load. It is a numerical model,
    not STM32 timing, a switching model, or a proof of the physical motor.
    """
    m,settings = profile['motor'],profile['applied']
    dt = 1/16000
    conversion = 65536*.04*2.1/3.3
    lm = 1.5*m['Lms']
    ls,lr = lm+m['Lls'],lm+m['Llr']
    sigma = 1-lm**2/(ls*lr)
    inv_ts,inv_tr = m['Rs']/ls,m['Rr']/lr
    k = 1.15
    leak_res = (inv_ts+(1-sigma)*inv_tr)/sigma
    k1 = -(k-1)*(inv_tr+inv_ts)/sigma
    k3 = (k-1)*(inv_tr-k*inv_ts)/(1-sigma)
    im = settings['ACIM_DEFAULT_FLUX_COMPONENT']/conversion
    iq_limit = settings['ACIM_IQMAX']
    nominal = MotorParameters(m['Rs'],m['Rr'],m['Lls'],lm,m['inertia']/1e6,m['friction']/1e6,
                              m['polesPairs'],1.35,.01)
    plant = replace(nominal,Rs=nominal.Rs*rs_scale,Rr=nominal.Rr*rr_scale)
    state = MotorState()
    current = voltage = observed = 0j
    angle = i_flux = omega = field = omega_int = 0.
    id_integral = iq_integral = speed_integral = iq_ref = 0
    peak = 0.
    stage_entered = None
    magnetized = 0
    rad_to_rpm = 60/math.tau
    omega_limit = 1.5*m['maxSpeed']*math.tau/60
    goal_units = field_frames = 0
    field_sum = permitted_sum = 0.

    def pi(error, integrator, axis, divider, limit):
        kp,ki = (settings[f'ACIM_PID_{axis}_{part}_DEFAULT'] for part in ('KP','KI'))
        p_div,i_div = (settings[f'{divider}_{part}DIV'] for part in ('KP','KI'))
        integrator = min(max(integrator+ki*error,-limit*i_div),limit*i_div)
        output = kp*error//p_div+integrator//i_div
        limited = min(max(output,-limit),limit)
        # ST's output clamp also discharges the integrator on saturation.
        integrator = min(max(integrator+(limited-output),-limit*i_div),limit*i_div)
        return limited,integrator

    for index in range(80000):
        previous_omega = omega
        previous_i = observed
        qd_error = current-previous_i  # d + jq space
        speed_error = -qd_error.imag*i_flux
        omega_int += settings['LSO_KI']*speed_error*dt
        omega = min(max(omega_int+settings['LSO_KP']*speed_error,-omega_limit),omega_limit)
        divisor = i_flux if i_flux else im
        field = omega+inv_tr*previous_i.imag/divisor
        angle = math.remainder(angle+field*dt,math.tau)
        k2 = (k-1)*previous_omega
        k4 = k2*sigma/(1-sigma)
        inverse_leakage = 1/(sigma*ls)
        cross_flux = (1-sigma)*i_flux/sigma
        dd = (-leak_res*previous_i.real+field*previous_i.imag+cross_flux*inv_tr
              +voltage.real*inverse_leakage+k1*qd_error.real-k2*qd_error.imag)
        dq = (-field*previous_i.real-leak_res*previous_i.imag-cross_flux*previous_omega
              +voltage.imag*inverse_leakage+k2*qd_error.real+k1*qd_error.imag)
        observed += complex(dd,dq)*dt
        excitation = previous_i.real if previous_i.real else im
        i_flux += ((excitation-i_flux)*inv_tr+k3*qd_error.real-k4*qd_error.imag)*dt
        frame = cmath.rect(1,angle)
        feedback = 1j*complex(ialpha,ibeta)/frame*shunt_gain if index else 0j
        current = complex(round(feedback.real*conversion),round(feedback.imag*conversion))/conversion
        peak = max(peak,abs(current))
        if not math.isfinite(peak) or abs(current)>1.35:
            return dict(completed=False,stop_ms=index*dt*1000,peak_current_A=peak,
                        simulated_trip='current_limit',rpm=state.omega_m*rad_to_rpm)
        if index%32 == 0:
            if stage_entered is None:
                magnetized = magnetized+1 if .7*im<=current.real<=1.3*im else 0
                if magnetized>=10:
                    stage_entered = index*dt
            if stage_entered is not None:
                elapsed = index*dt-stage_entered
                goal_units = round(50*min(1.,elapsed))
                estimated_units = math.trunc(10*omega/math.tau)
                iq_ref,speed_integral = pi(goal_units-estimated_units,speed_integral,'SPEED','ACIM_SP',iq_limit)
                iq_ref = max(0,iq_ref)
        if stage_entered is not None:
            field_frames += 1
            field_sum += field
            permitted_sum += (goal_units/10 + .75)*math.tau
            if field_frames == 256:
                if abs(field_sum)>permitted_sum:
                    return dict(completed=False,stop_ms=index*dt*1000,peak_current_A=peak,
                                simulated_trip='field_rate',rpm=state.omega_m*rad_to_rpm)
                field_frames = 0
                field_sum = permitted_sum = 0.
        vd,id_integral = pi(settings['ACIM_DEFAULT_FLUX_COMPONENT']-round(current.real*conversion),
                           id_integral,'FLUX','F',32767)
        vq,iq_integral = pi(iq_ref-round(current.imag*conversion),iq_integral,'TORQUE','T',32767)
        voltage = complex(vd,vq)*325/math.sqrt(3)/32767
        physical_v = -1j*voltage*frame
        state,ialpha,ibeta = _step(plant,state,physical_v.real,physical_v.imag,0.,dt,False)
    return dict(completed=True,stop_ms=5000,magnetized_ms=None if stage_entered is None else stage_entered*1000,
                peak_current_A=peak,rpm=state.omega_m*rad_to_rpm,rpm_estimated=omega*rad_to_rpm,
                field_frequency_Hz=field/math.tau)


def verify(out):
    profile = read_json(out/'AIR56B2_profile.json')
    settings = profile['applied']
    image = out/'STM32CubeIDE/Debug'/NAME
    elf = image.with_suffix('.elf')
    assert elf.exists()
    log = (out/'build_verified.log').read_text(encoding='utf-8',errors='replace')
    assert not re.search(r'\b(error|warning):',log,re.I)
    page = lambda name: (out/name).read_text(encoding='utf-8-sig')
    assert 'Code generation completed' in page('generation.log')
    assert '#define RSHUNT                               0.04' in page('Inc/power_stage_parameters.h')
    assert '#define AMPLIFICATION_GAIN                   2.1' in page('Inc/power_stage_parameters.h')
    for token in ('BreakState = TIM_BREAK_ENABLE','BreakFilter = 9',
                  'Polarity = TIM_BREAKINPUTSOURCE_POLARITY_LOW','AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE'):
        assert token in page('Src/main.c'),token
    for key,value in {'OV_VOLTAGE_THRESHOLD_V':350,'UD_VOLTAGE_THRESHOLD_V':250,
                      'MAX_APPLICATION_SPEED_RPM':300,'IQMAX':settings['ACIM_IQMAX'],
                      'DEFAULT_FLUX_COMPONENT_A':settings['ACIM_DEFAULT_FLUX_COMPONENT']}.items():
        assert re.search(rf'^#define\s+{key}\s+{value}\b',page('Inc/drive_parameters.h'),re.M),key
    with elf.open('rb') as f:
        symbols = {symbol.name for symbol in ELFFile(f).get_section_by_name('.symtab').iter_symbols()}
    assert {'ACIM_LSO_CalcAngle','R3_2_GetPhaseCurrents','TIM1_BRK_TIM15_IRQHandler',
            'ADC1_2_IRQHandler','AIR56_LsoWatchAdc'} <= symbols
    assert 'ma_native_fast' not in symbols
    assert 'AIR56_FieldReady() ? FOC_CurrControllerM1() : MC_SPEED_FDBK' in page('Src/mc_tasks.c')
    protected = read_json(out/'preserved_inputs_sha256.json')
    release.base.verify_inventory(protected,ROOT)
    checked = verify_limits(out)
    models = {name:plant_model(profile,**opts) for name,opts in
              (('nominal',{}),('Rs_plus20',{'rs_scale':1.2}),('Rr_plus20',{'rr_scale':1.2}),
               ('shunt_plus5',{'shunt_gain':1.05}))}
    write_json(out/'PC_model.json',models)
    nominal = models['nominal']
    assert nominal['completed'] and nominal['magnetized_ms'] is not None and abs(nominal['rpm']-300)<15,nominal
    folder = out/'image'
    folder.mkdir(exist_ok=True)
    shutil.copyfile(elf,folder/elf.name)
    for fmt,ext in (('binary','bin'),('ihex','hex')):
        subprocess.run([str(BIN/'arm-none-eabi-objcopy.exe'),'-O',fmt,str(elf),str(folder/f'{NAME}.{ext}')],
                       check=True,timeout=20)
    write_json(out/'verification.json',dict(passed=True,build_errors=0,build_warnings=0,
         profile=profile['profile'],run_on_target=False,installed=False,hardware_commands=0,
         present='ST LSO, R3_2 and Break; 5 s, 300 ms link, 1.35 A, 4000 cycles, 2 ms ADC limits',
         field_supervision='16 ms mean field rate, speed reference plus 0.75 Hz',
         current_pairs_checked=checked,PC_model=models,preserved_files_verified=len(protected),
         serial='ST ASPEP/Motor Pilot on USART2; bench client must poll every <300 ms',
         old_NIS_policy='2202 remains installed with NIS 25; ST LSO does not compute NIS',
         images_sha256={file.name:sha(file) for file in folder.iterdir()}))
    print(json.dumps(models))


def write_json(path, value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    verify(parser.parse_args().output.resolve())
