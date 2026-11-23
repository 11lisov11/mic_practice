"""Nominal involute planetary geometry and independent mesh/load screens.

Functional flank equations are derived, not copied CAD. Root transition is
nominal; fatigue qualification and production fillets remain necessary.
"""
import math,json
from pathlib import Path
import numpy as np

def involute(r,rb):
    if r<=rb:return 0.
    a=math.acos(rb/r);return math.tan(a)-a

def gear_outline(z,module,internal=False,backlash=.12,phase=0.,steps=8):
    rp=z*module/2;rb=rp*math.cos(math.radians(20));invp=math.tan(math.radians(20))-math.radians(20)
    half=math.pi/(2*z)-backlash/(2*rp);points=[]
    def add(r,a):
        p=(r*math.cos(a),r*math.sin(a))
        if not points or math.dist(points[-1],p)>1e-7:points.append(p)
    if not internal:
        ra=rp+module;rf=rp-1.25*module;rs=max(rf,rb)
        def width(r):return half+invp-involute(r,rb)
        ab=width(rs);at=width(ra)
        for j in range(z):
            c=phase+2*math.pi*j/z
            add(rf,c-ab)
            for r in np.linspace(rs,ra,steps):add(float(r),c-width(float(r)))
            for a in np.linspace(c-at,c+at,4):add(ra,float(a))
            for r in np.linspace(ra,rs,steps):add(float(r),c+width(float(r)))
            add(rf,c+ab)
            for a in np.linspace(c+ab,c+2*math.pi/z-ab,4)[1:]:add(rf,float(a))
    else:
        ra=rp-module;rf=rp+1.25*module
        def width(r):return half-invp+involute(r,rb)
        at=width(ra);af=width(rf)
        for j in range(z):
            c=phase+2*math.pi*j/z
            for r in np.linspace(rf,ra,steps):add(float(r),c-width(float(r)))
            for a in np.linspace(c-at,c+at,4):add(ra,float(a))
            for r in np.linspace(ra,rf,steps):add(float(r),c+width(float(r)))
            for a in np.linspace(c+af,c+2*math.pi/z-af,4)[1:]:add(rf,float(a))
    if math.dist(points[0],points[-1])<1e-6:points.pop()
    return points

def config(module=1.6):
    rr=50*module+10;ri=max(62,rr-15)
    return {'sun_teeth':20,'planet_teeth':40,'ring_teeth':100,'planets':4,'module_mm':module,'pressure_angle_deg':20,
      'planet_face_mm':18,'ring_face_mm':20,'sun_face_mm':20 if module<1.59 else 12,'backlash_per_gear_mm':.12,'ring_outer_r_mm':rr,
      'ratio':6,'efficiency_assumed':.94,'planet_pin_d_mm':8,'main_axle_d_mm':17,
      'output_bearing':'NK17/16,17x25x16, hardened shaft race required',
      'plastic_gear_material':'Purchased POM or qualified printed PA. PETG is for cold fit trials until endurance/temperature qualification.',
      'endturn_overhang_mm_assumed':12,'case_inner_r_mm':ri,'case_outer_r_mm':ri+2,
      'donor_rim_inner_r_mm_ASSUMED':rr+3,'donor_rim_outer_r_mm_ASSUMED':rr+6,
      'donor_fit_verified':False}

def load_screen(torque_wheel=12,module=1.6,gear=None):
    p=gear or config(module);eta=p['efficiency_assumed'];ts=torque_wheel/(p['ratio']*eta);rp=p['sun_teeth']*p['module_mm']/2000
    ft=ts/rp/p['planets'];Kshare=1.5;Kdynamic=1.2;y=.154-.912/p['planet_teeth'];b=min(p['sun_face_mm'],p['planet_face_mm']);m=p['module_mm']
    stress=ft*Kshare*Kdynamic/(b*math.pi*m*y)
    pinload=2*ft*Kshare*Kdynamic;span=p.get('pin_span_mm',23)/1000;diam=p['planet_pin_d_mm']/1000;moment=pinload*span/4
    return {'wheel_design_torque_Nm':torque_wheel,'sun_torque_Nm':ts,'Ft_per_mesh_nominal_N':ft,'load_sharing_factor':Kshare,'dynamic_factor':Kdynamic,
      'planet_root_MPa_Lewis_screen':stress,'screen_allowable_MPa_assumed_not_fatigue_data':10,
      'root_safety_to_assumed10MPa':10/stress,'planet_pin_force_N_screen':pinload,'pin_bending_MPa':32*moment/(math.pi*diam**3)/1e6,
      'planet_neighbour_tip_clearance_mm':2*(p['sun_teeth']+p['planet_teeth'])*m/2*math.sin(math.pi/p['planets'])-(p['planet_teeth']+2)*m,
      'assembly_tooth_condition':(p['ring_teeth']+p['sun_teeth'])/p['planets'],
      'limitations':['Lewis is not ISO6336/VDI2736 gear life rating','FDM root quality, anisotropy, wear, moisture and temperature require tests','Nominal root transitions require production rounding']}
