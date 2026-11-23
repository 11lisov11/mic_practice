"""Selected wheel-integrated alternative, separate from the belt candidates."""
import csv,json,math
from pathlib import Path
import numpy as np
from model import ROOT,belt,masses
from optimise import fit_model,wire,wheel_op,thermal,road
from planetary import config,load_screen

def run():
    source=ROOT/'C108_L40_G025_R29_CU3/femm/linear.json';field=json.loads(source.read_text());g=field['geometry'];m=fit_model(field);gear=config()
    g['transmission']={'kind':'planetary_inside_wheel',**gear};g['design_screens']['stator_to_ambient_forced_K_W_assumed']=1.1
    g['revision']='P2 inner rotor induction motor, wheel-integrated planetary reduction';g['shaft_d_mm']=17
    w=wire(g,7);ratio=6;out=ROOT/'P2_HUB';out.mkdir(exist_ok=True)
    roads={n:road(g,s,h,a) for n,s,h,a in [('flat15',15,0,0),('flat20',20,0,0),('flat25',25,0,0),('hill5_10',10,5,0),('start04',0,0,.4)]}
    points={str(V):{n:{str(I):wheel_op(g,m,w,r,ratio,V,I,.8 if n=='start04' else .65,ripple_peak_ceiling=15 if I in [9,10,10.5] else None) for I in [9,10,10.5,12,15]} for n,r in roads.items()} for V in [30,36,42]}
    curves=[]
    for speed in np.arange(0,30.1,.5):
        base=road(g,float(speed))
        row={'speed_kmh':float(speed),'road_torque_Nm':base['wheel_torque_Nm']}
        for I in [9,10.5,12]:
            lo,hi=0.,15.
            for _ in range(22):
                t=(lo+hi)/2;r={**base,'wheel_torque_Nm':t,'wheel_W':t*base['wheel_omega_rad_s']}
                if wheel_op(g,m,w,r,ratio,30,I,.8 if speed<10 else .65,ripple_peak_ceiling=15 if I in [9,10.5] else None):lo=t
                else:hi=t
            row[f'max_wheel_T_I{I}_Nm']=lo
        curves.append(row)
    q30=points['30']['flat20']['10'];q36=points['36']['flat20']['9']
    temperatures={'flat20_30V':thermal(g,w,q30),'flat20_36V':thermal(g,w,q36)}
    # A ramp simulation uses the electrical torque envelope, plus the rolling
    # and aerodynamic loads. It is conditional on flux pre-magnetisation and
    # current-loop operation; no bench START command is sent.
    speed=0.;time=0.;trace=[];radius=g['wheel_rolling_d_mm']/2000
    for k in range(900):
        kmh=speed*3.6
        if kmh>=20:break
        T=float(np.interp(kmh,[x['speed_kmh'] for x in curves],[x['max_wheel_T_I10.5_Nm'] for x in curves]))
        T=min(T,12);load=road(g,kmh);a=max(0,(T/radius-load['force_N'])/(g['vehicle_and_rider_kg']+2.5))
        speed+=a*.05;time+=.05;trace.append({'time_s':time,'speed_kmh':speed*3.6,'acceleration_m_s2':a,'wheel_torque_Nm':T})
        if a<1e-5:break
    # Keep a distinct practical allowance; the full nonlinear torque-speed
    # envelope is not known from a single hot locked-rotor point.
    speed_allow=0.;time_allow=0.;trace_allow=[]
    for k in range(1800):
        kmh=speed_allow*3.6
        if kmh>=20:break
        T=.9*float(np.interp(kmh,[x['speed_kmh'] for x in curves],[x['max_wheel_T_I10.5_Nm'] for x in curves]));load=road(g,kmh)
        a=max(0,(T/radius-load['force_N'])/(g['vehicle_and_rider_kg']+2.5));speed_allow+=a*.05;time_allow+=.05
        trace_allow.append({'time_s':time_allow,'speed_kmh':speed_allow*3.6,'acceleration_m_s2':a,'wheel_torque_Nm':T})
        if a<1e-5:break
    data={'status':'P2_CALCULATED_INSERT_NOT_VERIFIED_NINEBOT_FIT','geometry':g,'gear':gear,'model':m,'field_source':str(source),'winding':w,
      'masses_active':{**masses(g),'winding_copper_kg':w['copper_mass_kg']},'roads':roads,'points':points,'torque_speed_30V':curves,'thermal':temperatures,
      'gear_load_screen':load_screen(),'acceleration_30V_15Apeak_envelope':trace,
      'time_to20kmh_s_electrical_screen':time if speed*3.6>=20 else None,
      'acceleration_10pct_torque_allowance':trace_allow,'time_to20kmh_s_with10pct_torque_allowance':time_allow if speed_allow*3.6>=20 else None,
      'note':['100W in P1 was the15km/h road load, not a measured motor nominal rating',
        'Planetary6:1, motor inside wheel is the priority. Belt arrangement is only an alternative comparison.',
        '9Arms cruise screen,10Arms design,10.5Arms launch capped15A peak+ripple;12/15Arms cases need board qualification',
        'Current firmware1.35A peak trip and all drive hardware remain unchanged',
        'Flattened12mm end turn overhang is a packaging target requiring a formed coil coupon',
        'Motor wheel donor dimensions, rim interface and frame clearance remain unmeasured']}
    (out/'results.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    (out/'parameters.json').write_text(json.dumps({'geometry':g,'gear':gear},indent=2),encoding='utf-8')
    with (out/'winding_24_coils.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.writer(f);wr.writerow(['coil','phase','sign_top','slot_top','slot_return','turns','strands','wire_bare_mm'])
        for j in range(24):ph,s=belt(j);wr.writerow([j+1,ph,s,j+1,(j+5)%24+1,w['turns_per_coil'],w['strands'],w['wire_bare_mm']])
    print(json.dumps({'active_mass':sum(data['masses_active'].values()),'winding':w,'q30':q30,'q36':q36,'thermal30':temperatures['flat20_30V']['steady_C'],'time20':data['time_to20kmh_s_electrical_screen']}),flush=True)
    return data

if __name__=='__main__':run()
