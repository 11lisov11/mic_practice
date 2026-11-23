"""Reproducible offline hub-ACIM design, operating points and lumped thermal model.

Electromagnetic parameters come from the actual linear FEMM sweep, not a
claimed manufactured motor. dq quantities are amplitude invariant, peak units.
No firmware, network, or hardware operations are performed by this module.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results'
P = 4
ZS = 48
ZR = 50
NC = 6
PITCH = 5
NPH = 16*NC
AREA = 8*math.pi*.8**2/4  # mm2, bare copper
RHO = .01724
ALPHA = .00393
GAP = .0004
MEAN_COIL_R = .071
END_SPAN = 2*MEAN_COIL_R*math.sin(math.pi*PITCH/ZS)
MLT = 2*.04 + 2*END_SPAN + .012
R20 = RHO*(NPH*MLT+.4)/AREA  # includes 0.4 m total phase leads
KW = math.sin(math.pi*5/12)*math.sin(math.pi/6)/(2*math.sin(math.pi/12))
SLOT_AREA = (3.5+6.8)/2*22  # excludes neck, approximate rounded polygon
FILL = 2*NC*AREA/SLOT_AREA
CU_MASS = 3*(NPH*MLT+.4)*AREA*1e-6*8960
STAT_MASS = (math.pi*(.085**2-.045**2)-ZS*SLOT_AREA*1e-6)*.04*7650*.95
ROT_MASS = (math.pi*(.105**2-.0854**2)-ZR*4.8*10e-6)*.04*7650*.95
CAGE_MASS = (ZR*48e-6*.04+2*2*math.pi*.095*120e-6)*8960
CASE_MASS = 2.0
C = np.array([CU_MASS*385, STAT_MASS*460, ROT_MASS*460+CAGE_MASS*385, CASE_MASS*900])
CASE_AREA = math.pi*.22*.08+2*math.pi*(.11**2-.015**2)
THERMAL_ASSUMPTIONS = {'R_winding_stator_K_W': .18, 'R_stator_case_K_W': 2.,
    'R_rotor_case_K_W': .04, 'air_conductivity_W_m_K': .026,
    'case_area_m2': CASE_AREA, 'h_convection_W_m2_K': '5+6*sqrt(vehicle_speed_m_s)',
    'h_radiation_linearized_W_m2_K': 4., 'ambient_C': 25.,
    'winding_limit_C': 100., 'rotor_limit_C': 110.,
    'case_convection_multipliers': [.6, 1., 1.4]}


def load_model():
    data = json.loads((ROOT/'femm'/'sweep.json').read_text(encoding='utf-8'))
    fit = data['fit']
    rows = data['rows']
    tau = fit['tau_rotor_s']
    # A travelling space wave has one complex Fourier coefficient at its
    # temporal peak amplitude; do NOT double it as for a real cosine snapshot.
    bg_per_id = float(np.mean([r['Bg_fund_peak_t']*math.sqrt(1+(2*math.pi*r['frequency_hz']*tau)**2)
                              for r in rows[:3]]))
    return {'M_h': fit['M_effective_h'], 'L_leak_2d_h': fit['L_leak_total_2d_h'],
            'L_end_assumed_h': .0001, 'Rr20_ohm': fit['Rr_effective_20_ohm'],
            'tau20_s': tau, 'Bg_per_Id_peak_T_A': bg_per_id,
            'Bg_limit_peak_T': .60, 'I_limit_peak_A': 45., 'Rs20_ohm': R20,
            'status': 'linear_FEA_estimate_not_identified_hardware'}


def road(speed_kmh, grade_pct=0, acceleration=0):
    v = speed_kmh/3.6
    angle = math.atan(grade_pct/100)
    force = 120*9.81*(.015*math.cos(angle)+math.sin(angle))+.5*1.225*.6*v*v+120*acceleration
    return {'speed_kmh': speed_kmh, 'grade_pct': grade_pct, 'force_n': force,
            'omega_rad_s': v/.254, 'rpm': v/.254*30/math.pi,
            'torque_nm': force*.254, 'shaft_w': force*v}


def operating_point(model, torque, omega, tw=80., tr=70., vdc=36., forced_id=None,
                    enforce=True, core_factor=1., joint_factor=1.):
    """Steady inverse-Gamma motor + explicit approximate iron-loss branch.

    Minimize MOTOR input loss at equal useful torque/speed. This is a model
    optimum for a candidate LUT, not measured AI savings. Imposed current and
    voltage limits are constraints, not clipped promises of delivered torque.
    """
    m, ll = model['M_h'], model['L_leak_2d_h']+model['L_end_assumed_h']
    rs = R20*(1+ALPHA*(tw-20))
    rr = model['Rr20_ohm']*(1+ALPHA*(tr-20))*joint_factor
    idmax = model['Bg_limit_peak_T']/model['Bg_per_Id_peak_T_A']
    ids = np.array([forced_id]) if forced_id is not None else np.linspace(.3, idmax, 450)
    # Bearing/seal/windage assumption, separate from useful wheel torque.
    friction_torque = (.15+.001*abs(omega))*math.tanh(abs(omega)/.5)
    te = torque+friction_torque
    iq = te/(1.5*P*m*ids)
    ws = rr/m*iq/ids
    we = P*omega+ws
    bg = model['Bg_per_Id_peak_T_A']*ids
    freq = np.abs(we)/(2*math.pi)
    slip_hz = np.abs(ws)/(2*math.pi)
    # Unidentified steel, assumed 3.5 W/kg at 1.5T/50Hz, split 60/40.
    # Use sampled tooth/yoke representative induction; not material loss data.
    bstat = 2.1*bg
    brot = 2.3*bg
    def core(mass, b, f):
        return core_factor*mass*3.5*(.6*(f/50)*(b/1.5)**1.6+.4*(f/50)**2*(b/1.5)**2)
    ps = core(STAT_MASS, bstat, freq)
    pr = core(ROT_MASS, brot, slip_hz)
    psi = m*ids
    pcage = 1.5*rr*iq**2
    pfric = friction_torque*abs(omega)
    # PWM/stray reserve; not measured. An equivalent internal loss branch
    # consumes ALL extra losses, so phase electrical power remains balanced.
    pstray = 5.+.015*(torque*omega+pcage)
    icq = (ps+pr+pstray)/(1.5*np.maximum(np.abs(we*psi), 1e-9))
    iqs = iq+icq
    ipk = np.sqrt(ids**2+iqs**2)
    vd = rs*ids-we*ll*iqs
    vq = rs*iqs+we*(ll+m)*ids
    upk = np.sqrt(vd*vd+vq*vq)
    pcu = 1.5*rs*ipk**2
    total_loss = pcu+pcage+ps+pr+pfric+pstray
    valid = (ipk <= model['I_limit_peak_A']) & (upk <= .9*vdc/math.sqrt(3)) & (bg <= .600001)
    objective = np.where(valid if enforce else np.ones_like(valid, dtype=bool), total_loss, np.inf)
    index = int(np.argmin(objective))
    if not np.isfinite(objective[index]):
        return None
    def at(x):
        return float(np.asarray(x)[index])
    pmech = torque*omega
    pmotor = pmech+at(total_loss)
    battery = pmotor/.95+15
    result = {'torque_useful_nm': torque, 'omega_rad_s': omega, 'rpm': omega*30/math.pi,
        'Tw_C': tw, 'Tr_C': tr, 'Vdc_V': vdc, 'Id_peak_A': at(ids),
        'Iq_torque_peak_A': at(iq), 'Iq_stator_peak_A': at(iqs),
        'I_phase_rms_A': at(ipk)/math.sqrt(2), 'I_phase_peak_A': at(ipk),
        'U_phase_peak_V': at(upk), 'U_line_rms_V': at(upk)*math.sqrt(1.5),
        'U_phase_available_peak_V': .9*vdc/math.sqrt(3),
        'frequency_hz': at(freq), 'slip_hz': at(slip_hz), 'Bg_peak_T': at(bg),
        'psi_inverse_gamma_Wb': at(psi), 'Rs_ohm': rs, 'Rr_ohm': rr,
        'shaft_W': pmech, 'copper_W': at(pcu), 'cage_W': at(pcage),
        'stator_iron_W': at(ps), 'rotor_iron_W': at(pr),
        'friction_W': pfric, 'stray_PWM_assumed_W': at(pstray),
        'motor_loss_W': at(total_loss), 'motor_input_W': pmotor,
        'motor_efficiency': pmech/pmotor if pmotor else 0.,
        'battery_W_including_15W_aux': battery, 'battery_A': battery/vdc,
        'phase_electrical_input_W': at(1.5*(vd*ids+vq*iqs)),
        'power_balance_residual_W': pmotor-at(1.5*(vd*ids+vq*iqs)),
        'torque_loss_identity_error_W': abs(at(pcage)-te*at(ws)/P),
        'feasible': bool(valid[index])}
    return result


def thermal_matrix(speed_kmh, cooling=1.):
    v = speed_kmh/3.6
    gws, gsc, grc = 1/.18, 1/2., 1/.04
    gsr = .026*2*math.pi*.0852*.04/GAP
    ga = CASE_AREA*((5+6*math.sqrt(v))*cooling+4)
    k = np.zeros((4, 4))
    for i, j, g in [(0,1,gws), (1,2,gsr), (1,3,gsc), (2,3,grc)]:
        k[i,i] += g
        k[j,j] += g
        k[i,j] -= g
        k[j,i] -= g
    k[3,3] += ga
    return k


def heat_sources(point):
    return np.array([point['copper_W'], point['stator_iron_W']+point['stray_PWM_assumed_W'],
                     point['cage_W']+point['rotor_iron_W'], point['friction_W']])


def transient(model, speed, torque, cooling=1., ambient=25., duration=7200., start=None):
    k = thermal_matrix(speed, cooling)
    omega = speed/3.6/.254
    def rhs(t, temp):
        # Losses beyond the thermal operating limit are evaluated only to locate
        # a threshold. Infeasible demanded torque is not silently delivered.
        pt = operating_point(model, torque, omega, tw=temp[0], tr=temp[2])
        if pt is None:
            pt = operating_point(model, torque, omega, tw=temp[0], tr=temp[2], enforce=False)
        return (heat_sources(pt)-k@(temp-ambient))/C
    def stop(t, temp):
        return min(100-temp[0], 110-temp[2])
    stop.terminal = True
    stop.direction = -1
    def electrical_stop(t, temp):
        return 1. if operating_point(model,torque,omega,tw=temp[0],tr=temp[2]) is not None else -1.
    electrical_stop.terminal=True
    electrical_stop.direction=-1
    initial = np.full(4, ambient) if start is None else np.array(start)
    sol = solve_ivp(rhs, (0,duration), initial, events=[stop,electrical_stop], rtol=1e-5, atol=1e-6, max_step=10, dense_output=True)
    times = np.linspace(0,sol.t[-1],300)
    temps = sol.sol(times).T
    pt_end = operating_point(model, torque, omega, tw=temps[-1,0], tr=temps[-1,2])
    return {'time_s': times.tolist(), 'temperatures_C': temps.tolist(),
            'stop_time_s': float(sol.t[-1]), 'thermal_limit_reached': bool(len(sol.t_events[0])),
            'electrical_limit_reached': bool(len(sol.t_events[1])),
            'electrically_feasible_at_end': pt_end is not None,
            'speed_kmh': speed, 'torque_nm': torque, 'cooling_multiplier': cooling,
            'ambient_C': ambient, 'initial_C': initial.tolist()}


def equilibrium(model, speed, torque, cooling=1., ambient=25.):
    k = thermal_matrix(speed, cooling)
    temp = np.full(4, ambient+30)
    for _ in range(250):
        pt = operating_point(model, torque, speed/3.6/.254, tw=temp[0], tr=temp[2])
        if pt is None:
            return None
        newtemp = ambient+np.linalg.solve(k,heat_sources(pt))
        if not np.all(np.isfinite(newtemp)) or max(newtemp)>300:
            return None
        if max(abs(newtemp-temp))<.0005:
            return {'temperatures_C': newtemp.tolist(), 'point': pt}
        temp = .7*temp+.3*newtemp
    return None


def continuous_torque(model, speed, cooling=1., ambient=25.):
    low, high = 0., 25.
    for _ in range(22):
        mid = (low+high)/2
        eq = equilibrium(model,speed,mid,cooling,ambient)
        ok = eq is not None and eq['temperatures_C'][0]<=100 and eq['temperatures_C'][2]<=110
        if ok:
            low=mid
        else:
            high=mid
    return low


def flat_thermal_speed(model):
    low,high=1.,25.
    for _ in range(20):
        mid=(low+high)/2
        if road(mid)['torque_nm']<=continuous_torque(model,mid):
            low=mid
        else:
            high=mid
    return low


def cage_currents(point):
    rb=RHO*.04/48*(1+ALPHA*(point['Tr_C']-20))
    re=RHO*(2*math.pi*.095/50)/120*(1+ALPHA*(point['Tr_C']-20))
    factor=1+re/(2*rb*math.sin(math.pi*P/50)**2)
    ib=math.sqrt(point['cage_W']/(50*rb*factor))
    iring=ib/(2*math.sin(math.pi*P/50))
    return {'bar_R_rms_A':ib,'ring_segment_RMS_A':iring,
            'bar_current_density_A_mm2':ib/48,'ring_current_density_A_mm2':iring/120,
            'bar_active_loss_W':50*ib*ib*rb,'both_ring_loss_W':100*iring*iring*re,
            'additional_loss_1uohm_each_joint_W':100*ib*ib*1e-6}


def make_winding():
    rows=[]
    for j in range(ZS):
        phase, sign = [('A',1),('C',-1),('B',1),('A',-1),('C',1),('B',-1)][((j+1)//2)%6]
        rows.append({'coil':j+1,'phase':phase,'top_slot':j+1,'return_slot':(j+PITCH)%ZS+1,
                     'top_direction':sign,'turns':NC,'parallel_strands':8,'strand_bare_mm':.8})
    return rows


def main():
    OUT.mkdir(exist_ok=True)
    model=load_model()
    points=[]
    for name,v,g,a in [('flat_25',25,0,0),('hill_5pct_10',10,5,0),('hill_5pct_25',25,5,0),
                        ('accel_flat_5',5,0,.5),('standstill_25Nm',0,0,0)]:
        r=road(v,g,a)
        if name=='standstill_25Nm': r['torque_nm']=25.
        pt=operating_point(model,r['torque_nm'],r['omega_rad_s'])
        points.append({'name':name,'road':r,'point':pt,
                       'unconstrained_point_if_infeasible':None if pt else operating_point(model,r['torque_nm'],r['omega_rad_s'],enforce=False)})
    flat=road(25)
    hill=road(10,5)
    trajectories={name:transient(model,v,t) for name,v,t in [
        ('flat25_cold',25,flat['torque_nm']),('hill10_cold',10,hill['torque_nm']),
        ('hill10_warm',10,hill['torque_nm'])]}
    warm=equilibrium(model,25,flat['torque_nm'])
    if warm and warm['temperatures_C'][0]<100:
        trajectories['hill10_warm']=transient(model,10,hill['torque_nm'],start=warm['temperatures_C'])
    else:
        trajectories['hill10_warm']=transient(model,10,hill['torque_nm'],start=[80,75,70,50])
    sensitivity=[]
    for amb in [25.,35.]:
        for cool in [.6,1.,1.4]:
            sensitivity.append({'ambient_C':amb,'cooling_multiplier':cool,
                'Tcont_10kmh_Nm':continuous_torque(model,10,cool,amb),
                'Tcont_25kmh_Nm':continuous_torque(model,25,cool,amb),
                'hill_cold_limit_s':transient(model,10,hill['torque_nm'],cool,amb)['stop_time_s']})
    supply=[]
    for vdc in [30.,36.,42.]:
        for name,r in [('flat25',flat),('hill10',hill)]:
            supply.append({'case':name,'Vdc':vdc,'point':operating_point(model,r['torque_nm'],r['omega_rad_s'],vdc=vdc)})
    fixed_id=model['Bg_limit_peak_T']/model['Bg_per_Id_peak_T_A']
    comparison={}
    for name,r in [('flat25',flat),('hill10',hill)]:
        comparison[name]={'fixed_flux':operating_point(model,r['torque_nm'],r['omega_rad_s'],forced_id=fixed_id),
            'optimized_flux':operating_point(model,r['torque_nm'],r['omega_rad_s'])}
    p300=operating_point(model,300/(25/3.6/.254),25/3.6/.254,tw=100,tr=70)
    internal_min=25+np.linalg.solve(thermal_matrix(25)[:3,:3],heat_sources(p300)[:3])
    # Case clamped at ambient is an optimistic physical lower bound, not a
    # proposed passive cooler. Estimate maximum case-to-ambient R at Tw=100.
    r_case_budget=(100-internal_min[0])/p300['motor_loss_W']
    cooling_requirement={'point_300W_25kmh_Tw100_Tr70':p300,
        'temperature_with_ideal_25C_case_C':internal_min.tolist(),
        'maximum_case_ambient_R_K_W_at_given_losses':float(r_case_budget),
        'requires_internal_path_change_if_budget_negative':bool(r_case_budget<0)}
    uncertainty=[]
    for factor in [1.,1.2,1.5]:
        p=operating_point(model,hill['torque_nm'],hill['omega_rad_s'],joint_factor=factor)
        uncertainty.append({'rotor_resistance_multiplier':factor,'hill_point':p})
    data={'status':'preliminary_design_with_actual_linear_2D_FEA_not_hardware_validation',
        'cage_currents':{'flat25':cage_currents(points[0]['point']),
                         'hill10':cage_currents(points[1]['point'])},
        'cooling_requirement_300W':cooling_requirement,
        'rotor_resistance_sensitivity':uncertainty,
        'flat_thermal_speed_kmh':flat_thermal_speed(model),
        'flat25_steady_state':equilibrium(model,25,flat['torque_nm']),
        'model':model,'winding':{'slots':ZS,'poles':2*P,'coil_pitch_slots':PITCH,'coils':48,
        'coils_series_per_phase':16,'turns_per_coil':NC,'turns_series_per_phase':NPH,
        'kw1':KW,'connection':'star, isolated neutral','parallel_paths':1,
        'parallel_wire_strands':8,'strand_bare_diameter_mm':.8,'effective_copper_mm2':AREA,
        'slot_area_usable_approx_mm2':SLOT_AREA,'bare_fill_fraction':FILL,
        'mean_turn_length_m':MLT,'copper_length_each_strand_all_phases_m':3*(NPH*MLT+.4),
        'Rs20_ohm':R20,'Rs100_ohm':R20*(1+ALPHA*80)},
        'masses_kg':{'winding_copper':CU_MASS,'stator_steel':STAT_MASS,'rotor_steel':ROT_MASS,
                     'cage_copper':CAGE_MASS,'case_and_axle_assumed':CASE_MASS},
        'thermal_capacities_J_K':C.tolist(),'thermal_assumptions':THERMAL_ASSUMPTIONS,
        'points':points,'supply_sensitivity':supply,'cooling_sensitivity':sensitivity,
        'trajectories':trajectories,'flux_comparison':comparison}
    (OUT/'design_results.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    (OUT/'winding_48_coils.json').write_text(json.dumps(make_winding(),indent=2),encoding='utf-8')
    fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for name,tr in trajectories.items():
        temp=np.asarray(tr['temperatures_C'])
        axs[0].plot(np.asarray(tr['time_s'])/60,temp[:,0],label=name)
    axs[0].axhline(100,color='black',ls='--',lw=1)
    axs[0].set(xlabel='Time, min',ylabel='Winding temperature, C',title='Lumped model: assumed cooling, 25 C ambient')
    axs[0].legend(fontsize=7)
    speeds=np.linspace(1,25,25)
    tcont=[continuous_torque(model,float(v)) for v in speeds]
    axs[1].plot(speeds,tcont,label='Thermal + electrical, 36 V')
    axs[1].plot(speeds,[min(22,300/(v/3.6/.254)) for v in speeds],ls='--',label='Previous 300 W / 22 Nm target')
    axs[1].set(xlabel='Speed, km/h',ylabel='Continuous useful torque, Nm',title='100 C winding / 110 C rotor limits')
    axs[1].legend(fontsize=7)
    fig.savefig(OUT/'thermal_and_envelope.png',dpi=170)
    plt.close(fig)
    print(json.dumps({k:data[k] for k in ['model','winding','masses_kg','points','cooling_sensitivity']},indent=2))


if __name__=='__main__':
    main()
