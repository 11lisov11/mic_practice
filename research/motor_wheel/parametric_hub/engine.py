"""Peak-amplitude inverse-Gamma ACIM model + screening thermal/mechanical model.

FEMM fit identifies an effective inverse-Gamma circuit, NOT a T-equivalent
Lm/Lls/Llr set for direct insertion into MCSDK. Hypotheses remain explicit.
"""
from __future__ import annotations
import csv,json,math
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from geometry import ROOT,geometry,package,belt,stator_slot,rotor_slot

ALPHA=.00393;RHO=.01724

def model_from_femm(path):
    d=json.loads(Path(path).read_text(encoding='utf-8'));f=d['fit'];tau=f['tau_rotor_s']
    kb=float(np.mean([r['Bg_fund_peak_t']*math.sqrt(1+(2*math.pi*r['frequency_hz']*tau)**2) for r in d['rows'][:3]]))
    return {**f,'Bg_per_Id_peak_T_A':kb,'end_leakage_h_assumed':.00015,
      'source_femm_json':str(Path(path).resolve()),'field_current_reference_turns':10}

def polygon_area(points):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2

def masses(g):
    # Includes mouths and wedges as voids. Surface mouth arc area omitted
    # from polygon differs by <0.01 mm2 per slot at the reference geometry.
    sa=polygon_area(stator_slot(g,0));ra=polygon_area(rotor_slot(g,0))
    sv=(math.pi*(g['stator_outer_radius_mm']**2-g['stator_bore_radius_mm']**2)-48*sa)*g['active_length_mm']
    rv=(math.pi*(g['rotor_outer_radius_mm']**2-(g['stator_outer_radius_mm']+g['air_gap_radial_mm'])**2)-50*ra)*g['active_length_mm']
    cage=(50*g['rotor_bar_width_mm']*g['rotor_bar_depth_mm']*g['active_length_mm']+2*2*math.pi*g['ring_mean_radius_mm']*g['ring_cross_section_mm2'])*1e-9*8960
    return {'stator_steel_kg':sv*1e-9*7650*.95,'rotor_steel_kg':rv*1e-9*7650*.95,'cage_copper_kg':cage}

def winding(g,turns):
    slot=g['slot_copper_gross_mm2'];options=[]
    # Two layers. Gross copper fill is a screen; film, enamel and wedge
    # allowances must be checked in a real wound coupon before ordering.
    for d in [.5,.55,.6,.65,.7,.75,.8,.85,.9,1.,1.1,1.2]:
        for n in range(1,13):
            a=n*math.pi*d*d/4;fill=2*turns*a/slot
            if fill<=.42:options.append((a,-n,d,n,fill))
    if not options:return None
    a,_,d,n,fill=max(options)
    rmean=(g['slot_bottom_radius_mm']+g['slot_shoulder_radius_mm'])/2000
    mlt=2*g['active_length_mm']/1000+4*rmean*math.sin(math.pi*5/48)+.012
    nph=16*turns;length=nph*mlt+.4
    kw=math.sin(5*math.pi/12)*math.sin(math.pi/6)/(2*math.sin(math.pi/12))
    return {'turns_per_coil':turns,'coils_series_per_phase':16,'turns_series_per_phase':nph,
      'connection':'star','parallel_phase_paths':1,'winding_factor':kw,'coil_pitch_slots':5,
      'wire_strands_in_hand':n,'wire_bare_diameter_mm':d,'copper_area_mm2':a,'bare_slot_fill':fill,
      'mean_turn_length_m_assumed':mlt,'phase_length_one_strand_m':length,
      'total_wire_m':3*length*n,'order_wire_m_with_15pct_reserve':3*length*n*1.15,
      'winding_copper_kg':3*length*a*1e-6*8960,'Rphase20_ohm':RHO*length/a,
      'Rline20_ohm_star':2*RHO*length/a,'not_wound_or_measured':True}

def road(p,speed,grade=0,accel=0):
    v=speed/3.6;r=p['wheel_rolling_diameter_mm_assumed']/2000;m=p['total_vehicle_and_rider_mass_kg_assumed'];theta=math.atan(grade/100)
    f=m*9.81*(math.sin(theta)+.015*math.cos(theta))+.5*1.225*.6*v*v+m*accel
    return {'speed_kmh':speed,'grade_pct':grade,'force_N':f,'torque_Nm':f*r,'omega_rad_s':v/r,'shaft_W':f*v,'rpm':v/r*30/math.pi}

def operating(p,g,model,w,torque,omega,vdc,current_limit=None,tw=80,tr=70,forced_id=None):
    inv=p['inverter'];ratio=w['turns_per_coil']/10
    lm=model['M_effective_h']*ratio**2
    # End leakage is an unmeasured length-dependent estimate.
    ll=(model['L_leak_total_2d_h']+model['end_leakage_h_assumed']*(g['stator_outer_radius_mm']/65))*ratio**2
    rr20=model['Rr_effective_20_ohm']*ratio**2
    rr=rr20*(1+ALPHA*(tr-20));rs=w['Rphase20_ohm']*(1+ALPHA*(tw-20))
    kb=model['Bg_per_Id_peak_T_A']*ratio
    ids=np.array([forced_id]) if forced_id is not None else np.linspace(.15,.5/kb,700)
    tf=.10+.0005*abs(omega);te=torque+tf
    iq=te/(1.5*4*lm*ids);wsl=rr/lm*iq/ids;we=4*omega+wsl;bg=kb*ids;psi=lm*ids
    mass=masses(g)
    def iron(kg,b,f):return kg*3.5*(.6*(f/50)*(b/1.5)**1.6+.4*(f/50)**2*(b/1.5)**2)
    ps=iron(mass['stator_steel_kg'],2.3*bg,abs(we)/(2*math.pi));pr=iron(mass['rotor_steel_kg'],2.5*bg,abs(wsl)/(2*math.pi))
    cage=1.5*rr*iq**2;fric=tf*abs(omega);stray=3+.015*(torque*omega+cage)
    ic=(ps+pr)/(1.5*np.maximum(abs(we*psi),1e-9));iqs=iq+ic;ip=np.hypot(ids,iqs)
    vd=rs*ids-we*ll*iqs;vq=rs*iqs+we*(lm+ll)*ids
    # MOSFET drop proportional to current, plus deadtime sign(current)
    # fundamental error. No fictitious IGBT 1.5V drop on this MOSFET board.
    rd=inv['mosfet_Rds_hot_ohm_assumed'];dt=4/math.pi*vdc*inv['PWM_Hz']*inv['deadtime_s_assumed']
    extra=rd*ip+dt;ud=vd+extra*ids/ip;uq=vq+extra*iqs/ip
    u=np.hypot(ud,uq);vlim=.9*vdc/math.sqrt(3);ripple=vdc/(8*inv['PWM_Hz']*ll)
    imax=current_limit or inv['phase_current_limit_rms_A_assumed']
    cu=1.5*rs*ip**2;loss=cu+cage+ps+pr+fric+stray
    valid=(ip<=imax*math.sqrt(2))&(ip+ripple<=inv['current_peak_design_ceiling_A_assumed'])&(u<=vlim-1)&(bg<=.5+1e-9)
    opt=np.where(valid,loss,np.inf);k=int(np.argmin(opt))
    if not np.isfinite(opt[k]):return None
    def at(a):return float(np.asarray(a)[k])
    shaft=torque*omega;pin=shaft+at(loss);irms=at(ip)/math.sqrt(2)
    cond=3*irms**2*rd;shunt=1.5*irms**2*inv['shunt_ohm_inferred_not_measured']
    # Bounds, not a board temperature qualification or switch energy fit.
    battery=[pin+cond+shunt+sw+3 for sw in [2,8]]
    return {'useful_torque_Nm':torque,'rpm':omega*30/math.pi,'shaft_W':shaft,'Vdc_V':vdc,
      'I_phase_rms_A':irms,'I_phase_peak_A':at(ip),'Id_peak_A':at(ids),'Iq_torque_peak_A':at(iq),
      'Iq_total_peak_A':at(iqs),'Bg_peak_T':at(bg),'frequency_hz':at(we)/(2*math.pi),'slip_hz':at(wsl)/(2*math.pi),
      'U_phase_motor_peak_V':at(np.hypot(vd,vq)),'U_line_motor_rms_V':at(np.hypot(vd,vq))*math.sqrt(1.5),
      'U_pwm_required_phase_peak_V':at(u),'U_pwm_limit_phase_peak_V':vlim,'voltage_margin_peak_V':vlim-at(u),
      'Rs_hot_ohm':rs,'Rr_hot_ohm':rr,'Lm_effective_h':lm,'Lleak_effective_h':ll,
      'copper_W':at(cu),'cage_W':at(cage),'stator_iron_W_assumed':at(ps),'rotor_iron_W_assumed':at(pr),
      'stray_PWM_W_assumed':at(stray),'friction_W_assumed':fric,'motor_loss_W':at(loss),'motor_input_W':pin,
      'motor_efficiency_model':shaft/pin,'power_factor_fundamental':(pin-at(stray))/(1.5*at(np.hypot(vd,vq))*at(ip)),
      'power_balance_error_W':pin-at(stray)-at(1.5*(vd*ids+vq*iqs)),
      'rotor_slip_balance_error_W':at(cage)-te*at(wsl)/4,
      'inverter_conduction_W_assumed':cond,'inverter_shunts_W_inferred':shunt,
      'inverter_switching_W_bounds_assumed':[2,8],'battery_W_bounds_assumed':battery,'battery_current_A_bounds_assumed':[x/vdc for x in battery],
      'ripple_half_pp_A_estimate':ripple,'current_peak_with_ripple_A_estimate':at(ip)+ripple,'copper_current_density_A_mm2':irms/w['copper_area_mm2']}

def thermal(p,g,w,q):
    t=p['thermal'];amb=t['ambient_C'];mass=masses(g)
    cw=w['winding_copper_kg']*385;cs=mass['stator_steel_kg']*460;cr=mass['rotor_steel_kg']*460+mass['cage_copper_kg']*385
    rws=t['winding_to_stator_K_W_assumed'];rsa=t['stator_to_ambient_K_W_assumed'];rra=t['rotor_to_ambient_K_W_assumed'];rsr=4.
    cu20=q['copper_W']/(1+ALPHA*60);ca20=q['cage_W']/(1+ALPHA*50)
    def fun(_,y):
        tw,ts,tr=y;hws=(tw-ts)/rws;hsr=(ts-tr)/rsr
        return [(cu20*(1+ALPHA*(tw-20))+q['stray_PWM_W_assumed']-hws)/cw,
          (q['stator_iron_W_assumed']+hws-(ts-amb)/rsa-hsr)/cs,
          (ca20*(1+ALPHA*(tr-20))+q['rotor_iron_W_assumed']+q['friction_W_assumed']+hsr-(tr-amb)/rra)/cr]
    times=np.arange(0,7201,10);sol=solve_ivp(fun,(0,7200),[amb]*3,t_eval=times,rtol=1e-7,atol=1e-8)
    crossed=np.where(sol.y[0]>=t['winding_limit_C_screen'])[0]
    y0=np.ones(3)*amb;f0=np.asarray(fun(0,y0));jac=np.column_stack([np.asarray(fun(0,y0+np.eye(3)[i]))-f0 for i in range(3)])
    stable=bool(max(np.linalg.eigvals(jac).real)<0)
    steady=y0-np.linalg.solve(jac,f0)
    return {'method':'3 lumped nodes; fixed Id/Iq, approximate positive copper feedback, unmeasured thermal resistances',
      'time_to_90C_s':float(times[crossed[0]]) if len(crossed) else None,
      'temperatures_at_60min_C':{n:float(sol.y[i,360]) for i,n in enumerate(['winding','stator','rotor'])},
      'times_s':times.tolist(),'winding_C':sol.y[0].tolist(),'stator_C':sol.y[1].tolist(),'rotor_C':sol.y[2].tolist(),
      'steady_state_C_if_stable':dict(zip(['winding','stator','rotor'],steady.tolist())) if stable else None,'linearised_network_stable':stable,
      'heat_capacities_J_K':[cw,cs,cr],'continuous_rating_established':False}

def mechanical(p,g,torque_screen=20):
    pk=package(p,g);m=p['mechanical'];d=m['shaft_diameter_mm']/1000
    load=p['total_vehicle_and_rider_mass_kg_assumed']*9.81*.6*3
    support_half=.065;bearing_half=pk['bearing_center_z_mm']/1000
    moment=load/2*max(0,support_half-bearing_half)
    bend=32*moment/(math.pi*d**3);shear=16*torque_screen/(math.pi*d**3);vm=math.hypot(bend,math.sqrt(3)*shear)
    # Solid smooth shaft only, no cable bore/flats/keyway/thread concentrations.
    e=210e9;second=math.pi*d**4/64;a=max(0,support_half-bearing_half);span=2*support_half
    deflection=(load/2)*a*(3*span**2-4*a*a)/(24*e*second)
    nominal_bearing_load=load/2
    c=12810.;rpm=road(p,25)['rpm'];life=(c/nominal_bearing_load)**3*1e6/(60*rpm)
    # thin free ring hoop stress under rotational inertia; wheel/impact fit
    # stress and bolt/spoke deformation not contained in this check.
    omega=road(p,25)['omega_rad_s'];hoop=7650*(omega*g['rotor_outer_radius_mm']/1000)**2
    return {'load_case':'120kg or parameter mass, 60% rear axle, 3g shock, support span130mm ASSUMED',
      'radial_total_N':load,'bearing_radial_each_N':nominal_bearing_load,'shaft_bending_moment_Nm':moment,
      'shaft_bending_MPa_smooth_solid':bend/1e6,'shaft_torsion_MPa_smooth_solid':shear/1e6,
      'shaft_von_Mises_MPa_smooth_solid':vm/1e6,'shaft_yield_safety_at_235MPa_no_notches':235e6/vm,
      'shaft_center_deflection_mm_ideal':deflection*1000,'bearing_L10h_screen_at25kmh':life,
      'rotor_centrifugal_hoop_MPa_at25kmh':hoop/1e6,'torque_design_Nm':torque_screen,
      'airgap_budget_mm':{'radial_gap':g['air_gap_radial_mm'],'rotor_runout_allowance':.08,'stator_eccentricity_allowance':.06,
        'bearing_play_allowance':.03,'thermal_growth_reserve':.04,'shaft_deflection_ideal':deflection*1000,
        'remaining_for_cover_flex_and_assembly':g['air_gap_radial_mm']-.21-deflection*1000},
      'not_verified':['cover/retainer strength and distortion','thread/keyway/cable hole stress','torque arm/frame/dropout','bearing fits and lubrication','cage joints, balancing, fretting','wheel donor interface']}

def calculate(p,femm_json,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);g=geometry(p);g['rotor_slot_opening_mm']=1.
    model=model_from_femm(femm_json);roads={n:road(p,s,h) for n,s,h in [('flat10',10,0),('flat15',15,0),('flat20',20,0),('flat25',25,0),('hill5_10',10,5)]}
    trials=[]
    for n in range(4,23):
        w=winding(g,n)
        if not w:continue
        pts={name:{str(v):operating(p,g,model,w,r['torque_Nm'],r['omega_rad_s'],v) for v in [30.,36.,42.]} for name,r in roads.items()}
        start=operating(p,g,model,w,roads['flat15']['torque_Nm'],0,30.)
        trials.append({'winding':w,'points':pts,'standstill_flat15_torque':start})
    valid=[r for r in trials if all(r['points']['flat15'][str(v)] for v in [30.,36.,42.]) and r['standstill_flat15_torque']]
    if not valid:
        data={'status':'INFEASIBLE_15KMH_WITH_SELECTED_BOARD_LIMITS','parameters':p,'geometry':g,'package':package(p,g),
          'model':model,'masses':masses(g),'roads':roads,'winding_candidates':trials,'selected':None,'mechanical':mechanical(p,g),
          'reason':'No winding4..22 turns reaches flat15km/h at30..42V within9Arms/15Apeak+estimated ripple and0.5T'}
        (out/'results.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
        (out/'parameters_used.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
        print(json.dumps({'case':out.name,'status':data['status']}),flush=True)
        return data
    # Prefer energy; keep minimum 2 V voltage headroom at lowest supply to
    # avoid a paper optimum immediately against the modulation boundary.
    reserve=[r for r in valid if r['points']['flat15']['30.0']['voltage_margin_peak_V']>=2.]
    chosen=min(reserve or valid,key=lambda r:r['points']['flat15']['30.0']['motor_loss_W'])
    w=chosen['winding'];q=chosen['points']['flat15']['36.0']
    thermal_result=thermal(p,g,w,q)
    sweep=[]
    for speed in np.arange(0,30.1,.5):
        omega=float(speed)/3.6/(g['wheel_rolling_diameter_m_assumed']/2)
        lo,hi=0.,25.
        for _ in range(25):
            mid=(lo+hi)/2
            if operating(p,g,model,w,mid,omega,30.) is None:hi=mid
            else:lo=mid
        sweep.append({'speed_kmh':float(speed),'max_torque_Nm_electrical_screen_30V':lo,'shaft_W_at_limit':lo*omega})
    data={'status':'P1_OFFLINE_SCREEN_NOT_PROTOTYPE_VALIDATION','parameters':p,'geometry':g,'package':package(p,g),
      'model':model,'masses':{**masses(g),'winding_copper_kg':w['winding_copper_kg']},'roads':roads,
      'winding_candidates':trials,'selected':chosen,'thermal_flat15_36V':thermal_result,'mechanical':mechanical(p,g),'torque_speed':sweep,
      'limitations':['No measured donor dimensions','Linear 2D field fit + reference M19 nonlinear check, not identified manufactured steel',
        'End winding leakage and thermal network assumed','Cage end ring resistance uses fundamental correction, joints not modelled',
        'No skew, PWM FE loss, NVH, rotor dynamics or stress FE validation','Board current15A ambiguous; conservative design peak ceiling used; transient bus clamp not designed',
        'No motor tests, inverter thermal qualification or MCSDK firmware generated']}
    (out/'results.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    with (out/'winding_48_coils.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.writer(f);wr.writerow(['coil','phase','sign_top','slot_top','slot_return','turns','strands','bare_wire_mm'])
        for j in range(48):ph,sgn=belt(j);wr.writerow([j+1,ph,sgn,j+1,(j+5)%48+1,w['turns_per_coil'],w['wire_strands_in_hand'],w['wire_bare_diameter_mm']])
    (out/'parameters_used.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
    print(json.dumps({'case':out.name,'turns_per_coil':w['turns_per_coil'],'wire':f'{w["wire_strands_in_hand"]}x{w["wire_bare_diameter_mm"]:g}mm',
      'flat15_shaft_W':q['shaft_W'],'flat15_current_rms_A':q['I_phase_rms_A'],'flat15_loss_W':q['motor_loss_W'],
      'thermal90_s':thermal_result['time_to_90C_s']}),flush=True)
    return data
