"""Conditional winding and inverter study. Offline; no firmware or hardware IO.

dq quantities use amplitude-invariant, phase-peak convention. Inverter drops
are a documented screening assumption, NOT low-voltage device qualification.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
G=json.loads((ROOT/'geometry_candidate.json').read_text(encoding='utf-8'))
P=G['pole_pairs']
NT0=G['reference_turns_per_coil']
NCOILS_PHASE=G['stator_slots']//3
KW=math.sin(5*math.pi/12)*math.sin(math.pi/6)/(2*math.sin(math.pi/12))
HEIGHT=G['slot_shoulder_radius_mm']-G['slot_bottom_radius_mm']
SLOT=(G['slot_bottom_width_mm']+G['slot_shoulder_width_mm'])/2*HEIGHT
MLT=2*G['active_length_mm']/1000+4*.054*math.sin(math.pi*5/48)+.012
RHO=.01724
ALPHA=.00393
MU=.95
PWM=16000
DEAD=1.35e-6
BG_MAX=.5


def load_model():
    data=json.loads((ROOT/'femm'/'linear.json').read_text(encoding='utf-8'))
    fit=data['fit']
    tau=fit['tau_rotor_s']
    kbg=float(np.mean([r['Bg_fund_peak_t']*math.sqrt(1+(2*math.pi*r['frequency_hz']*tau)**2) for r in data['rows'][:3]]))
    return {**fit,'Bg_per_Id_peak_T_A':kbg,'end_leakage_h_assumed':.00015}


def wire(turns):
    options=[]
    for diameter in [.5,.55,.6,.65,.7,.75,.8,1.0]:
        for strands in range(1,13):
            area=strands*math.pi*diameter**2/4
            fill=2*turns*area/SLOT
            if fill <=.42:
                options.append((area,-strands,diameter,strands,fill))
    area,_,d,s,fill=max(options)
    nph=NCOILS_PHASE*turns
    length=nph*MLT+.4
    return {'turns_per_coil':turns,'coils_series_per_phase':NCOILS_PHASE,
            'turns_series_per_phase':nph,'parallel_phase_paths':1,'connection':'star',
            'wire_strands_in_hand':s,'wire_bare_diameter_mm':d,'conductor_copper_area_mm2':area,
            'bare_slot_fill':fill,'mean_turn_length_m_assumed':MLT,'phase_length_one_strand_m':length,
            'total_wire_m_without_reserve':3*length*s,'copper_mass_kg':3*length*area*1e-6*8960,
            'Rs20_ohm':RHO*length/area,'Rs80_ohm':RHO*length/area*(1+ALPHA*60),
            'line_resistance20_ohm_star':2*RHO*length/area,
            'insulation_enamel_and_winding_trial_not_verified':True}


def road(speed,grade=0.,accel=0.):
    v=speed/3.6
    theta=math.atan(grade/100)
    m=G['total_mass_kg_assumed']
    radius=G['wheel_rolling_diameter_m_assumed']/2
    force=m*9.81*(math.sin(theta)+.015*math.cos(theta))+.5*1.225*.6*v*v+m*accel
    return {'speed_kmh':speed,'grade_pct':grade,'acceleration_m_s2':accel,'force_N':force,
            'torque_Nm':force*radius,'omega_rad_s':v/radius,'shaft_W':force*v,
            'rpm':v/radius*30/math.pi}


def operating(model,w,torque,omega,vdc,current_rms=6.,drop=1.5,tw=80.,tr=70.,forced_id=None):
    ratio=w['turns_per_coil']/NT0
    lm=model['M_effective_h']*ratio**2
    ll=(model['L_leak_total_2d_h']+model['end_leakage_h_assumed'])*ratio**2
    rr=model['Rr_effective_20_ohm']*ratio**2*(1+ALPHA*(tr-20))
    rs=w['Rs20_ohm']*(1+ALPHA*(tw-20))
    kbg=model['Bg_per_Id_peak_T_A']*ratio
    ids=np.asarray([forced_id]) if forced_id is not None else np.linspace(.15,BG_MAX/kbg,650)
    tf=.10+.0005*abs(omega)
    te=torque+tf
    iq=te/(1.5*P*lm*ids)
    wsl=rr/lm*iq/ids
    we=P*omega+wsl
    bg=kbg*ids
    psi=lm*ids
    statkg=(math.pi*((.065)**2-(.035)**2)-48*SLOT*1e-6)*.03*7650*.95
    rotkg=(math.pi*(.080**2-.0654**2)-50*3.2*7*1e-6)*.03*7650*.95
    def iron(mass,b,freq):
        return mass*3.5*(.6*(freq/50)*(b/1.5)**1.6+.4*(freq/50)**2*(b/1.5)**2)
    # Unmeasured generic iron-loss law; reserve, not measured efficiency.
    ps=iron(statkg,2.3*bg,abs(we)/(2*math.pi))
    pr=iron(rotkg,2.5*bg,abs(wsl)/(2*math.pi))
    pcage=1.5*rr*iq**2
    pfric=tf*abs(omega)
    pstray=3.+.015*(torque*omega+pcage)
    # Only iron loss belongs in this fundamental parallel branch. The PWM
    # allowance is separate harmonic heat, not fictitious torque current at
    # low speed (which would distort starting torque).
    icq=(ps+pr)/(1.5*np.maximum(abs(we*psi),1e-9))
    iqs=iq+icq
    ipk=np.hypot(ids,iqs)
    vd=rs*ids-we*ll*iqs
    vq=rs*iqs+we*(lm+ll)*ids
    # Fundamental voltage error from sign(current) IGBT/diode and dead time.
    # Added along the CURRENT vector, not subtracted as a fictitious DC bus.
    verr=4/math.pi*(drop+vdc*PWM*DEAD)
    vd_pwm=vd+verr*ids/ipk
    vq_pwm=vq+verr*iqs/ipk
    vlim=.9*vdc/math.sqrt(3)
    upwm=np.hypot(vd_pwm,vq_pwm)
    pcu=1.5*rs*ipk**2
    loss=pcu+pcage+ps+pr+pfric+pstray
    # Additional 1 V phase-peak reserve avoids selecting a winding exactly on
    # the estimated voltage boundary. It does not replace prototype tests.
    valid=(ipk <=current_rms*math.sqrt(2))&(upwm <=vlim-1.)&(bg <=BG_MAX+1e-10)
    objective=np.where(valid,loss,np.inf)
    index=int(np.argmin(objective))
    if not np.isfinite(objective[index]):
        return None
    def at(x):return float(np.asarray(x)[index])
    irms=at(ipk)/math.sqrt(2)
    shaft=torque*omega
    pin=shaft+at(loss)
    pcond=6/math.pi*drop*at(ipk)
    shunts={str(r):1.5*r*irms**2 for r in [.04,.08]}
    # Switching-loss allowance deliberately not a device prediction: datasheet
    # switching energies are specified at 300 V, not this low-voltage bus.
    switching_bounds=[3.,12.]
    aux=15.
    battery_bounds=[pin+pcond+shunts['0.04']+s+aux for s in switching_bounds]
    return {'useful_torque_Nm':torque,'rpm':omega*30/math.pi,'shaft_W':shaft,
            'Vdc_V':vdc,'current_limit_rms_A_assumed':current_rms,'I_phase_rms_A':irms,
            'I_phase_peak_A':at(ipk),'Id_peak_A':at(ids),'Iq_torque_peak_A':at(iq),
            'Iq_total_peak_A':at(iqs),'Bg_peak_T':at(bg),'frequency_hz':at(we)/(2*math.pi),
            'slip_hz':at(wsl)/(2*math.pi),'U_phase_motor_peak_V':at(np.hypot(vd,vq)),
            'U_line_motor_rms_V':at(np.hypot(vd,vq))*math.sqrt(1.5),
            'U_phase_pwm_required_peak_V':at(upwm),'U_phase_pwm_limit_peak_V':vlim,
            'voltage_margin_peak_V':vlim-at(upwm),'Rs_hot_ohm':rs,'Rr_hot_ohm':rr,
            'copper_W':at(pcu),'cage_W':at(pcage),'stator_iron_W_assumed':at(ps),
            'rotor_iron_W_assumed':at(pr),'stray_PWM_W_assumed':at(pstray),'friction_W_assumed':pfric,
            'motor_loss_W':at(loss),'motor_input_W':pin,'motor_efficiency_model':shaft/pin,
            'power_factor_fundamental':pin/(1.5*at(np.hypot(vd,vq))*at(ipk)),
            'motor_power_balance_error_W':pin-at(pstray)-at(1.5*(vd*ids+vq*iqs)),
            'torque_rotor_loss_identity_error_W':at(pcage)-te*at(wsl)/P,
            'inverter_conduction_W_assumed':pcond,'shunt_losses_W':shunts,
            'inverter_switching_W_allowance_not_prediction':switching_bounds,
            'battery_W_with_15W_aux_range':battery_bounds,
            'battery_current_A_range':[x/vdc for x in battery_bounds],
            'phase_current_peak_including_ripple_estimate_A':at(ipk)+vdc/(8*PWM*ll),
            'conductor_current_density_A_mm2':irms/w['conductor_copper_area_mm2']}


def max_torque(model,w,vdc,limit_rms,speed=1.):
    omega=speed/3.6/(G['wheel_rolling_diameter_m_assumed']/2)
    lo,hi=0.,20.
    for _ in range(30):
        mid=(lo+hi)/2
        if operating(model,w,mid,omega,vdc,limit_rms) is None:hi=mid
        else:lo=mid
    return lo


def run():
    model=load_model()
    points={'flat10':road(10),'flat15':road(15),'flat20':road(20),'flat25':road(25),'hill5_10':road(10,5)}
    buses=[{'name':'36V_10S','nominal':36.,'minimum_assumed':30.,'full':42.,'series':10},
           {'name':'48V_13S','nominal':48.,'minimum_assumed':39.,'full':54.6,'series':13},
           {'name':'60V_16S','nominal':59.2,'minimum_assumed':48.,'full':67.2,'series':16},
           {'name':'72V_20S','nominal':72.,'minimum_assumed':60.,'full':84.,'series':20}]
    windings=[wire(n) for n in range(6,25,2)]
    records=[]
    for bus in buses:
        for w in windings:
            for limit in [6.,9.]:
                pts={}
                for state in ['minimum_assumed','nominal','full']:
                    pts[state]={name:operating(model,w,p['torque_Nm'],p['omega_rad_s'],bus[state],limit) for name,p in points.items()}
                records.append({'bus':bus,'winding':w,'current_limit_rms_A_assumed':limit,'points':pts,
                                'launch_torque_1kmh_Nm':max_torque(model,w,bus['minimum_assumed'],limit)})
    sensing=[]
    for voltage in [30,36,39,42,48,54.6,59.2,60,67.2,72,84]:
        divider=7.5/947.5
        sensing.append({'Vdc_V':voltage,'ADC_pin_V':voltage*divider,'ADC_12bit_count':voltage*divider/3.3*4095,
                        'ideal_Ull_rms_SVPWM_V':voltage/math.sqrt(2)})
    shunts=[]
    for resistance in [.04,.08]:
        oc=(.51*(1000+4700)/4700+.18)/resistance
        shunts.append({'R_ohm':resistance,'OCP_peak_A_typical_circuit_estimate':oc,
                       'ADC_bipolar_peak_A_ideal':1.65/(resistance*2.1),
                       'ADC_A_per_12bit_count':3.3/(4095*resistance*2.1),
                       'three_shunt_total_W_at_6Arms':1.5*resistance*36,
                       'three_shunt_total_W_at_9Arms':1.5*resistance*81})
    data={'status':'conditional_offline_screening_not_release_for_winding_or_battery_purchase',
          'geometry':G,'model':model,'winding_factor':KW,'slot_body_area_mm2':SLOT,
          'assumptions':{'Bg_limit_peak_T':BG_MAX,'Tw_C':80,'Tr_C':70,'PWM_Hz':PWM,
                         'deadtime_s':DEAD,'switch_drop_V_assumed':1.5,'SVPWM_utilization':.9,
                         'current_limits_A_rms_are_study_scenarios_not_hardware_authorization':[6,9],
                         'current_live_bench_trip_A_peak_unchanged':1.35,
                         'thermal_continuous_rating_not_validated':True,
                         'road_parameters':'120kg, Crr .015, CdA .6, rho 1.225, no wind; 0.254m rolling diameter assumed'},
          'roads':points,'winding_candidates':windings,'sensing':sensing,'shunt_cases':shunts,'records':records}
    selected=[]
    for bus in buses:
        for limit in [6.,9.]:
            recs=[r for r in records if r['bus']['name']==bus['name'] and r['current_limit_rms_A_assumed']==limit]
            # Favor flat 15 km/h at depleted voltage, then flat 20, then starting
            # torque. This is explicitly a small transport demonstrator objective.
            def rank(r):
                q=r['points']['minimum_assumed']
                robust=operating(model,r['winding'],points['flat15']['torque_Nm'],points['flat15']['omega_rad_s'],r['bus']['minimum_assumed'],limit,drop=2.1)
                return (robust is not None,q['flat15'] is not None,q['flat20'] is not None,q['flat25'] is not None,q['flat10'] is not None,r['launch_torque_1kmh_Nm'])
            best=max(recs,key=rank)
            selected.append(best)
    data['selected_by_bus_and_current']=selected
    (ROOT/'results.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    for r in selected:
        print(json.dumps({'bus':r['bus']['name'],'limit_rms_A':r['current_limit_rms_A_assumed'],
                          'turns':r['winding']['turns_per_coil'],'wire':r['winding'],
                          'launch_Nm':r['launch_torque_1kmh_Nm'],
                          'min_bus_points':{k:None if v is None else {x:round(v[x],3) for x in ['I_phase_rms_A','voltage_margin_peak_V','motor_loss_W','battery_current_A_range'] if x!='battery_current_A_range'} for k,v in r['points']['minimum_assumed'].items()}}))


if __name__=='__main__':run()
