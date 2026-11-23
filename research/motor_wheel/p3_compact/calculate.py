"""P3: shorter L30 motor and14mm planetary ring, limited to15A phase peak.

Reuses the already solved L30 CU3 full-circle field, not scaled L40 results.
No firmware, serial port, battery or inverter commands.
"""
import argparse,csv,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;P2=ROOT.parent/'p2_geared';sys.path.insert(0,str(P2))
from model import masses,belt
from planetary import config,load_screen
from optimise import fit_model,wire,road,wheel_op,thermal

def geometry(module=1.45):
    f=json.loads((P2/'C108_L30_G025_R29_CU3/femm/linear.json').read_text());g=f['geometry']
    g['revision']='P3 L30 compact geared hub';g['shaft_d_mm']=17;g['design_screens']['stator_to_ambient_forced_K_W_assumed']=1.5
    gear=config(module);gear.update({'sun_face_mm':10,'planet_face_mm':12,'ring_face_mm':14,'planet_bearing_name':'688VV',
      'planet_bearing_outer_r_mm':8,'planet_bearing_width_mm':5,'planet_bearing_rear_offset_mm':1.5,'planet_bearing_axial_step_mm':6,
      'needle_name':'HK1712','needle_width_mm':12,'needle_outer_r_mm':11.5,'needle_start_after_G0_mm':10.5,'pin_span_mm':17.75,
      'output_bearing':'HK1712,17x23x12; hardened/ground shaft17mm required','gear_design_torque_Nm':9,
      'temperature_target_for_printed_gears_C':60,'gear_material_service_qualified':False,'keyed_reaction_collar':True})
    g['transmission']={'kind':'planetary_inside_wheel',**gear};return f,g,gear

def run(module=1.45):
    f,g,gear=geometry(module);m=fit_model(f);w=wire(g,8);tag=f'{module*100:.5f}'.rstrip('0').rstrip('.').replace('.','p')
    out=ROOT/('P3_L30_M'+tag);out.mkdir(exist_ok=True)
    names=[('flat15',15,0,0),('flat20',20,0,0),('flat25',25,0,0),('hill5_10',10,5,0),('start03',0,0,.3)]
    roads={n:road(g,s,h,a) for n,s,h,a in names}
    points={str(V):{n:wheel_op(g,m,w,r,6,V,10.5,.8 if n=='start03' else .65,ripple_peak_ceiling=15) for n,r in roads.items()} for V in [30,36,42]}
    curves=[]
    for s in np.arange(0,30.01,.5):
        row={'speed_kmh':float(s),'road_T_Nm':road(g,float(s))['wheel_torque_Nm']}
        for V in [30,36,42]:
            lo,hi=0,9
            for _ in range(21):
                T=(lo+hi)/2;r=road(g,float(s));r.update({'wheel_torque_Nm':T,'wheel_W':T*r['wheel_omega_rad_s']})
                # Blend the short launch flux ceiling into the continuous
                # ceiling. An abrupt switch at10km/h creates a false torque step.
                flux_limit=.8-.15*min(1.,max(0.,(float(s)-8)/4))
                if wheel_op(g,m,w,r,6,V,10.5,flux_limit,ripple_peak_ceiling=15):lo=T
                else:hi=T
            row[f'Tmax_{V}V_Nm']=lo
        curves.append(row)
    accels={}
    for allowance in [1.,.9]:
        v=0.;t=0.;trace=[]
        for k in range(2400):
            s=v*3.6
            if s>=20:break
            T=allowance*np.interp(s,[x['speed_kmh'] for x in curves],[x['Tmax_30V_Nm'] for x in curves]);r=road(g,s)
            a=max(0,(T/.127-r['force_N'])/122.5);t+=.05;v+=a*.05;trace.append({'time_s':t,'speed_kmh':v*3.6,'accel_m_s2':a,'T_wheel_Nm':float(T)})
            if a<1e-5:break
        accels[str(allowance)]={'time_20kmh_s':t if v*3.6>=20 else None,'torque_allowance_factor':allowance,'trace':trace}
    th={str(V):thermal(g,w,points[str(V)]['flat20']) for V in [30,36,42]}
    sensitivity={}
    for R in [1.1,1.5,2,2.5,3]:
        gg=json.loads(json.dumps(g));gg['design_screens']['stator_to_ambient_forced_K_W_assumed']=R
        sensitivity[str(R)]=thermal(gg,w,points['30']['flat20'])['steady_C']
    start=points['30']['start03'];a={'status':'P3_NOMINAL_DONOR_UNMEASURED_NO_PRODUCTION_RELEASE','date':'2026-11-18',
      'geometry':g,'gear':gear,'model':m,'winding':w,'roads':roads,'points':points,'curves':curves,'acceleration':accels,
      'thermal':th,'thermal_sensitivity_Rsa':sensitivity,'active_masses':{**masses(g),'winding_kg':w['copper_mass_kg']},
      'gear_load_screen':load_screen(9,module,gear),'gear_12Nm_overload_screen':load_screen(12,module,gear),
      'field_source':str(P2/'C108_L30_G025_R29_CU3/femm/linear.json'),
      'nonlinear_start_test_input':{'current_peak_ref10turn_A':start['I_peak_A']*.8,'frequency_Hz':start['slip_Hz'],'cage_temperature_C':85},
      'notes':['Phase current peak including estimated ripple <=15A; board rating convention unverified',
       'Heat transfer target is assumed and must be measured','9Nm mechanical design torque; higher-current research cases are excluded',
       'Dimensions of Max Pro donor remain unmeasured','All bench firmware and hardware unchanged']}
    (out/'results.json').write_text(json.dumps(a,indent=2),encoding='utf-8')
    with (out/'winding_24_coils.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        wr=csv.writer(fh);wr.writerow(['coil','phase','sign_top','slot_top','slot_return','turns','strands','wire_bare_mm'])
        for j in range(24):ph,sign=belt(j);wr.writerow([j+1,ph,sign,j+1,(j+5)%24+1,8,w['strands'],w['wire_bare_mm']])
    print(json.dumps({'case':out.name,'active_mass_kg':sum(a['active_masses'].values()),'winding':w,'cruise30':points['30']['flat20'],
      'start':start,'nonlinear_input':a['nonlinear_start_test_input'],'thermal30':th['30']['steady_C'],'time20_10pct_allowance':accels['0.9']['time_20kmh_s']}),flush=True)
    return a,out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--module',type=float,default=1.45);p.add_argument('--cad',action='store_true');p.add_argument('--nonlinear',action='store_true');p.add_argument('--nonlinear-adjusted',action='store_true');a=p.parse_args();data,out=run(a.module)
    if a.nonlinear:
        from field import run as field_run
        gg=data['geometry'];gg['cage_temperature_C']=85;n=data['nonlinear_start_test_input'];field_run(gg,out/'femm_start_hot',n['current_peak_ref10turn_A'],nonlinear_freq=n['frequency_Hz'])
    if a.nonlinear_adjusted:
        from field import run as field_run
        gg=data['geometry'];gg['cage_temperature_C']=85;field_run(gg,out/'femm_launch_adjusted_hot',11.06,nonlinear_freq=4.1)
    if a.cad:
        from build_cad import Hub
        Hub(a.module,data['geometry'],out,data['gear']).build_hub()
