"""Screen winding, reduction and variable rotor flux for scooter duty.

Motor current is phase RMS at the inverter. Battery current is calculated
separately. 9Arms is the conservative case;12/15Arms require board qualification.
"""
import argparse,csv,json,math
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq
from model import ROOT,load,masses,belt
ALPHA=.00393

def road(g,speed,grade=0,acceleration=0):
    v=speed/3.6;r=g['wheel_rolling_d_mm']/2000;m=g['vehicle_and_rider_kg'];theta=math.atan(grade/100)
    force=m*9.81*(math.sin(theta)+.015*math.cos(theta))+.5*1.225*.6*v*v+m*acceleration
    return {'speed_kmh':speed,'grade_pct':grade,'acceleration_m_s2':acceleration,'force_N':force,'wheel_torque_Nm':force*r,'wheel_omega_rad_s':v/r,'wheel_W':force*v}

def fit_model(field):
    f=field['fit'];tau=f['tau_rotor_s'];kb=np.mean([r['Bg_fund_peak_t']*math.sqrt(1+(2*math.pi*r['frequency_hz']*tau)**2)/r['current_peak_A'] for r in field['rows'][:3]])
    return {**f,'Bg_per_Id_peak_ref_T_A':float(kb)}

def wire(g,turns):
    A=(g['slot_shoulder_w_mm']+g['slot_bottom_w_mm'])/2*(g['slot_bottom_r_mm']-g['slot_shoulder_r_mm']);options=[]
    for d in [.5,.55,.6,.65,.7,.75,.8,.85,.9,1,1.1,1.2]:
        for s in range(1,9):
            a=s*math.pi*d*d/4;fill=2*turns*a/A
            if fill<=g['design_screens']['copper_fill_max']:options.append((round(a,10),-s,d,s,fill))
    a,_,d,s,fill=max(options);a=s*math.pi*d*d/4
    meanr=(g['slot_shoulder_r_mm']+g['slot_bottom_r_mm'])/2000
    mlt=2*g['stack_mm']/1000+4*meanr*math.sin(math.pi*g['coil_pitch']/g['stator_slots'])+.012
    coils=g['stator_slots']//3;nph=coils*turns;length=nph*mlt+.3
    return {'turns_per_coil':turns,'coils_series_per_phase':coils,'turns_series_per_phase':nph,'connection':'star','strands':s,'wire_bare_mm':d,'copper_area_mm2':a,
      'bare_slot_fill':fill,'gross_winding_slot_mm2':A,'mean_turn_length_m':mlt,'wire_one_strand_phase_m':length,'total_wire_m':3*length*s,'order_wire_m_15pct':3*length*s*1.15,
      'copper_mass_kg':3*length*a*1e-6*8960,'Rs20_ohm':.01724*length/a,'Rline20_ohm_star':2*.01724*length/a}

def op(g,m,w,Tshaft,omega,Vdc,Irms=9,Bmax=.65,Tw=100,Tr=85,ripple_peak_ceiling=None,rr_factor=1.,Lend_factor=1.,fixed_id=None):
    r=w['turns_per_coil']/g['reference_turns'];lm=m['M_effective_h']*r*r
    ll=(m['L_leak_total_2d_h']+g['design_screens']['end_leakage_reference_H_assumed']*Lend_factor)*r*r
    rr=m['Rr_effective_20_ohm']*r*r*(1+ALPHA*(Tr-20))*rr_factor;rs=w['Rs20_ohm']*(1+ALPHA*(Tw-20));kb=m['Bg_per_Id_peak_ref_T_A']*r;p=g['pole_pairs']
    ids=np.array([fixed_id]) if fixed_id is not None else np.linspace(.1,Bmax/kb,450)
    tf=.008+.00002*abs(omega);te=Tshaft+tf;iq=te/(1.5*p*lm*ids);ws=rr/lm*iq/ids;we=p*omega+ws;bg=kb*ids;psi=lm*ids
    kg=masses(g)
    # Reference generic loss law. High frequency is included explicitly;
    # no claim that changing speed makes core losses disappear.
    def iron(mass,b,f):return mass*3.5*(.6*(f/50)*(b/1.5)**1.6+.4*(f/50)**2*(b/1.5)**2)
    stat_factor=max((2*math.pi*(g['stator_bore_mm']/2)/g['stator_slots'])/((2*math.pi*g['slot_shoulder_r_mm']/g['stator_slots'])-g['slot_shoulder_w_mm']),
      (g['stator_bore_mm']/2)/(p*(g['stator_OD_mm']/2-g['slot_bottom_r_mm'])))
    rot_factor=(g['stator_bore_mm']/2-g['gap_mm'])/(p*(g['rotor_bar_inner_r_mm']-g['rotor_bore_r_mm']))
    ps=iron(kg['stator_steel_kg'],stat_factor*bg,abs(we)/(2*math.pi));pr=iron(kg['rotor_steel_kg'],rot_factor*bg,abs(ws)/(2*math.pi))
    cage=1.5*rr*iq**2;stray=2+.02*(Tshaft*omega+cage);fric=tf*abs(omega)
    ic=(ps+pr)/(1.5*np.maximum(abs(we*psi),1e-9));iqs=iq+ic;ipk=np.hypot(ids,iqs)
    vd=rs*ids-we*ll*iqs;vq=rs*iqs+we*(lm+ll)*ids
    inv=g['inverter'];drop=inv['MOS_Rds_hot_ohm_assumed']*ipk+4/math.pi*Vdc*inv['PWM_Hz']*inv['deadtime_s_assumed']
    upwm=np.hypot(vd+drop*ids/ipk,vq+drop*iqs/ipk);ulim=.9*Vdc/math.sqrt(3)-.75
    ripple=Vdc/(8*inv['PWM_Hz']*ll);ceiling=ripple_peak_ceiling or {9:15.,12:20.,15:25.}.get(Irms,1.5*Irms+2)
    cu=1.5*rs*ipk**2;loss=cu+cage+ps+pr+stray+fric
    valid=(ipk<=math.sqrt(2)*Irms)&(ipk+ripple<=ceiling)&(upwm<=ulim)&(bg<=Bmax+1e-9)
    obj=np.where(valid,loss,np.inf);k=int(np.argmin(obj))
    if not np.isfinite(obj[k]):return None
    def at(x):return float(np.asarray(x)[k])
    cur=at(ipk)/math.sqrt(2);shaft=Tshaft*omega;pin=shaft+at(loss)
    inverter=3*cur*cur*inv['MOS_Rds_hot_ohm_assumed']+1.5*cur*cur*inv['shunt_ohm_inferred']+5
    return {'Tshaft_Nm':Tshaft,'motor_rpm':omega*30/math.pi,'shaft_W':shaft,'Vdc_V':Vdc,'I_rms_A':cur,'I_peak_A':at(ipk),'I_peak_with_ripple_A':at(ipk)+ripple,
      'Id_peak_A':at(ids),'Iq_torque_peak_A':at(iq),'Iq_total_peak_A':at(iqs),'Bg_T':at(bg),'electrical_Hz':at(we)/(2*math.pi),'slip_Hz':at(ws)/(2*math.pi),
      'M_effective_H':lm,'Lleak_effective_H':ll,'Rr_hot_ohm':rr,'Rs_hot_ohm':rs,
      'U_motor_phase_peak_V':at(np.hypot(vd,vq)),'U_pwm_phase_peak_V':at(upwm),'U_pwm_screen_V':ulim,'voltage_margin_V':ulim-at(upwm),
      'copper_W':at(cu),'cage_W':at(cage),'stator_iron_W':at(ps),'rotor_iron_W':at(pr),'stray_W':at(stray),'friction_W':fric,
      'motor_loss_W':at(loss),'motor_input_W':pin,'motor_efficiency':shaft/pin if pin>0 else 0,
      'inverter_loss_W_assumed':inverter,'battery_W_with_10W_aux':pin+inverter+10,'battery_A':(pin+inverter+10)/Vdc,
      'fundamental_PF':(pin-at(stray))/(1.5*at(np.hypot(vd,vq))*at(ipk)),
      'energy_error_W':pin-at(stray)-at(1.5*(vd*ids+vq*iqs)),'slip_energy_error_W':at(cage)-te*at(ws)/p,
      'J_A_mm2':cur/w['copper_area_mm2'],'current_limit_rms_A_screen':Irms,'Bg_limit_T_screen':Bmax,
      'current_rating_status':'conservative_assumed' if Irms==9 else 'BOARD_THERMAL_AND_RATING_QUALIFICATION_REQUIRED'}

def wheel_op(g,m,w,r,ratio,Vdc,I,Bmax=.65,**kwargs):
    eta=g['transmission']['efficiency_assumed'];T=r['wheel_torque_Nm']/(ratio*eta);omega=r['wheel_omega_rad_s']*ratio
    q=op(g,m,w,T,omega,Vdc,I,Bmax,**kwargs)
    if q:q.update({'ratio':ratio,'wheel_torque_Nm':r['wheel_torque_Nm'],'wheel_speed_kmh':r['speed_kmh'],'wheel_W':r['wheel_W'],'transmission_loss_W':q['shaft_W']-r['wheel_W']})
    return q

def thermal(g,w,q):
    # Three nodes; air stream and heat sink have explicit assumed values.
    mass=masses(g);amb=g['design_screens']['ambient_design_C'];rws=g['design_screens']['winding_to_stator_K_W_assumed'];rsa=g['design_screens']['stator_to_ambient_forced_K_W_assumed']
    # Active airgap conduction plus end space in parallel, screening only.
    gapR=(g['gap_mm']/1000)/(.026*2*math.pi*(g['stator_bore_mm']/2000)*(g['stack_mm']/1000))
    rsr=1/(1/gapR+1/4.);rra=3.0
    C=np.array([w['copper_mass_kg']*385,mass['stator_steel_kg']*460+.16*900,mass['rotor_steel_kg']*460+mass['cage_copper_kg']*385])
    c20=q['copper_W']/(1+ALPHA*80);r20=q['cage_W']/(1+ALPHA*65)
    def fun(_,y):
        tw,ts,tr=y;h=(tw-ts)/rws;hr=(tr-ts)/rsr
        return np.array([c20*(1+ALPHA*(tw-20))+q['stray_W']-h,
          q['stator_iron_W']+h+hr-(ts-amb)/rsa,
          r20*(1+ALPHA*(tr-20))+q['rotor_iron_W']+q['friction_W']-hr-(tr-amb)/rra])/C
    y0=np.ones(3)*amb;f0=fun(0,y0);J=np.column_stack([fun(0,y0+e)-f0 for e in np.eye(3)]);stable=max(np.linalg.eigvals(J).real)<0
    steady=y0-np.linalg.solve(J,f0) if stable else np.full(3,np.inf)
    times=np.arange(0,3601,15);sol=solve_ivp(fun,(0,3600),y0,t_eval=times,rtol=1e-6,atol=1e-7)
    return {'model':'fixed Id/Iq, temperature-dependent copper; assumed air and contact resistances','ambient_C':amb,'Rws_K_W':rws,'Rstator_ambient_K_W':rsa,'Rrotor_stator_K_W':rsr,
      'steady_C':dict(zip(['winding','stator','rotor'],steady.tolist())),'times_s':times.tolist(),'winding_C':sol.y[0].tolist(),'stator_C':sol.y[1].tolist(),'rotor_C':sol.y[2].tolist(),
      'passes_winding120C_screen':bool(stable and steady[0]<=120),'continuous_rating_measured':False}

def run(field_path,out):
    field=json.loads(Path(field_path).read_text(encoding='utf-8'));g=field['geometry'];m=fit_model(field);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    roads={n:road(g,s,h,a) for n,s,h,a in [('flat15',15,0,0),('flat20',20,0,0),('flat25',25,0,0),('hill5_10',10,5,0),('start04',0,0,.4)]}
    trials=[]
    for turns in range(5,21):
        w=wire(g,turns)
        for ratio in [4,5,6,7,8]:
            points={n:{str(I):wheel_op(g,m,w,r,ratio,30.,I,.8 if n=='start04' else .65) for I in [9,12,15]} for n,r in roads.items()}
            trials.append({'winding':w,'ratio':ratio,'points_30V':points})
    valid=[r for r in trials if r['points_30V']['flat20']['9'] and r['points_30V']['start04']['9']]
    tier='9Arms_cruise_and_start'
    if not valid:
        valid=[r for r in trials if r['points_30V']['flat20']['9'] and r['points_30V']['start04']['12']];tier='9Arms_cruise_12Arms_start'
    if not valid:
        valid=[r for r in trials if r['points_30V']['flat20']['12'] and r['points_30V']['start04']['12']];tier='12Arms_cruise_and_start_requires_board_qualification'
    if not valid:
        result={'status':'NO_FEASIBLE20KMH_AND0.4MS2_WITHIN12ARMS','geometry':g,'model':m,'trials':trials}
    else:
        # Avoid arbitrary rewards for a very large reduction: gears7/8 exceed
        # our preferred wheel-side pulley diameter with a20T pinion.
        preferred=[r for r in valid if r['ratio']<=6]
        best=min(preferred or valid,key=lambda r:(r['points_30V']['flat20']['9'] or r['points_30V']['flat20']['12'])['motor_loss_W'])
        w=best['winding'];ratio=best['ratio'];refI=9 if best['points_30V']['flat20']['9'] else 12
        ref=best['points_30V']['flat20'][str(refI)];therm=thermal(g,w,ref)
        points={str(V):{name:{str(I):wheel_op(g,m,w,r,ratio,V,I,.8 if name=='start04' else .65) for I in [9,12,15]} for name,r in roads.items()} for V in [30,36,42]}
        result={'status':'CALCULATED_CANDIDATE_NOT_HARDWARE_VALIDATION','capability_tier':tier,'geometry':g,'model':m,'roads':roads,'masses':{**masses(g),'winding_copper_kg':w['copper_mass_kg']},
          'selected':{'winding':w,'ratio':ratio,'reference_current_limit_rms_A':refI,'points':points,'thermal_flat20_30V':therm},'trials':trials}
        with (out/'winding_24_coils.csv').open('w',newline='',encoding='utf-8-sig') as f:
            wr=csv.writer(f);wr.writerow(['coil','phase','sign_top','slot_top','slot_return','turns','strands','wire_mm'])
            for j in range(24):ph,s=belt(j);wr.writerow([j+1,ph,s,j+1,(j+g['coil_pitch'])%24+1,w['turns_per_coil'],w['strands'],w['wire_bare_mm']])
    (out/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'case':out.name,'status':result['status'],'tier':result.get('capability_tier'),'selected':None if not result.get('selected') else {k:result['selected'][k] for k in ['winding','ratio','reference_current_limit_rms_A']}}),flush=True)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('field');ap.add_argument('--out',required=True);a=ap.parse_args();run(a.field,a.out)
