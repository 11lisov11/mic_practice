"""Single geometry source for CAD, FEMM and winding calculations; millimetres.

Fixed 48-slot / 8-pole winding topology. Diameter scales transverse geometry;
airgap, shaft and purchased bearings remain independently specified.
"""
from __future__ import annotations
import json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def parameters(path=None,diameter=None,length=None):
    p=json.loads(Path(path or ROOT/'parameters.json').read_text(encoding='utf-8'))
    if diameter is not None:p['stator_diameter_mm']=float(diameter)
    if length is not None:p['stack_length_mm']=float(length)
    if not 110<=p['stator_diameter_mm']<=170:raise ValueError('P1 supported stator diameter: 110..170 mm')
    if not 20<=p['stack_length_mm']<=50:raise ValueError('P1 supported stack length: 20..50 mm')
    if not .3<=p['radial_airgap_mm']<=.8:raise ValueError('P1 radial airgap: 0.3..0.8 mm')
    return p

def geometry(p):
    s=p['stator_diameter_mm']/130
    rs=p['stator_diameter_mm']/2; gap=p['radial_airgap_mm']
    g={
      'status':p['status'],'phases':3,'pole_pairs':4,'stator_slots':48,'rotor_bars':50,
      'reference_turns_per_coil':10,'coil_pitch_slots':5,
      'active_length_mm':p['stack_length_mm'],'stator_outer_radius_mm':rs,
      'stator_bore_radius_mm':35*s,'slot_bottom_radius_mm':46*s,
      'slot_shoulder_radius_mm':62.5*s,'slot_bottom_width_mm':2.5*s,
      'slot_shoulder_width_mm':4.5*s,'slot_layer_split_radius_mm':55.4*s,
      'slot_mouth_width_mm':1.8*s,'slot_mouth_base_radius_mm':63.5*s,
      'air_gap_radial_mm':gap,'rotor_outer_radius_mm':rs+gap+14.6*s,
      'rotor_bar_inner_radius_mm':rs+gap+.8*s,'rotor_bar_width_mm':3.2*s,
      'rotor_bar_depth_mm':7*s,'rotor_slot_opening_mm':1.0,
      'ring_axial_mm':5*s,'ring_radial_mm':16*s,
      'ring_mean_radius_mm':rs+gap+6.6*s,'ring_cross_section_mm2':80*s*s,
      'steel_lamination_mm':.5,'packing_factor':.95,
      'wheel_rolling_diameter_m_assumed':p['wheel_rolling_diameter_mm_assumed']/1000,
      'total_mass_kg_assumed':p['total_vehicle_and_rider_mass_kg_assumed']}
    g['slot_copper_gross_mm2']=(g['slot_bottom_width_mm']+g['slot_shoulder_width_mm'])/2*(g['slot_shoulder_radius_mm']-g['slot_bottom_radius_mm'])
    g['lamination_count_nominal']=round(g['active_length_mm']/g['steel_lamination_mm'])
    g['lamination_stack_note']='Geometric stack / 0.5 mm; actual coated sheet stack must be measured. FEMM fill factor 0.95.'
    return g

def point(r,t,angle,on_circle=False):
    x=math.sqrt(r*r-t*t) if on_circle else r
    return (x*math.cos(angle)-t*math.sin(angle),x*math.sin(angle)+t*math.cos(angle))

def profile(angle,levels):
    return [point(r,-w/2,angle,i==0) for i,(r,w) in enumerate(levels)]+[point(r,w/2,angle,i==0) for i,(r,w) in reversed(list(enumerate(levels)))]

def stator_slot(g,j,extend=0):
    return profile(2*math.pi*j/48,[(g['stator_outer_radius_mm']+extend,g['slot_mouth_width_mm']),
      (g['slot_mouth_base_radius_mm'],g['slot_mouth_width_mm']),
      (g['slot_shoulder_radius_mm'],g['slot_shoulder_width_mm']),
      (g['slot_bottom_radius_mm'],g['slot_bottom_width_mm'])])

def rotor_slot(g,j,extend=0):
    r=g['stator_outer_radius_mm']+g['air_gap_radial_mm']; b=g['rotor_bar_inner_radius_mm']; w=g['rotor_bar_width_mm']
    return profile(2*math.pi*(j+.31)/50,[(r-extend,g['rotor_slot_opening_mm']),(b,g['rotor_slot_opening_mm']),(b,w),(b+g['rotor_bar_depth_mm'],w)])

def bar_profile(g,j):
    a=2*math.pi*(j+.31)/50;r=g['rotor_bar_inner_radius_mm'];w=g['rotor_bar_width_mm'];d=g['rotor_bar_depth_mm']
    return [point(r,-w/2,a),point(r+d,-w/2,a),point(r+d,w/2,a),point(r,w/2,a)]

def belt(j):return [('A',1),('C',-1),('B',1),('A',-1),('C',1),('B',-1)][((j+1)//2)%6]

def package(p,g):
    m=p['mechanical'];L=g['active_length_mm'];over=m['endwinding_overhang_mm_assumed']
    cover_z=L/2+over+m['cover_clearance_mm']
    outer=g['rotor_outer_radius_mm']+m['housing_wall_mm']
    return {'rotor_iron_OD_mm':2*g['rotor_outer_radius_mm'],'housing_OD_mm':2*outer,
      'cover_inner_z_mm':cover_z,'cover_outer_z_mm':cover_z+m['cover_web_thickness_mm'],
      'bearing_center_z_mm':cover_z+m['cover_web_thickness_mm']-m['bearing_width_mm']/2,
      'total_housing_width_mm':2*(cover_z+m['cover_web_thickness_mm']),
      'outer_housing_radius_mm':outer,'shaft_total_length_mm':m['shaft_total_length_mm'],
      'endring_inner_radius_mm':g['ring_mean_radius_mm']-g['ring_radial_mm']/2,
      'endring_outer_radius_mm':g['ring_mean_radius_mm']+g['ring_radial_mm']/2,
      'endturn_envelope_outer_radius_mm':g['slot_mouth_base_radius_mm']-0.6,
      'endturn_ring_radial_clearance_mm':g['ring_mean_radius_mm']-g['ring_radial_mm']/2-(g['slot_mouth_base_radius_mm']-0.6),
      'status':'concept_envelopes; end winding bend/forming and donor fit require physical verification'}
