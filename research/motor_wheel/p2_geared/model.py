"""P2 geometry shared by field solver, calculation, drawings and native CAD."""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def load():return json.loads((ROOT/'inputs.json').read_text(encoding='utf-8'))

def xy(r,a):return r*math.cos(a),r*math.sin(a)

def pt(r,t,a,circle=False):
    x=math.sqrt(r*r-t*t) if circle else r
    return x*math.cos(a)-t*math.sin(a),x*math.sin(a)+t*math.cos(a)

def profile(a,levels):
    return [pt(r,-w/2,a,i==0) for i,(r,w) in enumerate(levels)]+[pt(r,w/2,a,i==0) for i,(r,w) in reversed(list(enumerate(levels)))]

def stator_slot(g,j,extend=0):
    r=g['stator_bore_mm']/2;a=2*math.pi*j/g['stator_slots'];b=g['slot_bottom_r_mm'];s=g['slot_shoulder_r_mm'];q=g['slot_split_r_mm']
    wq=g['slot_shoulder_w_mm']+(g['slot_bottom_w_mm']-g['slot_shoulder_w_mm'])*(q-s)/(b-s)
    return profile(a,[(r-extend,g['slot_mouth_w_mm']),(g['slot_neck_r_mm'],g['slot_mouth_w_mm']),
      (s,g['slot_shoulder_w_mm']),(q,wq),(b,g['slot_bottom_w_mm'])])

def rotor_slot(g,j,extend=0):
    r=g['stator_bore_mm']/2-g['gap_mm'];a=2*math.pi*(j+.31)/g['rotor_bars'];o=g['rotor_bar_outer_r_mm'];i=g['rotor_bar_inner_r_mm'];w=g['rotor_bar_w_mm']
    return profile(a,[(r+extend,g['rotor_opening_w_mm']),(o,g['rotor_opening_w_mm']),(o,w),(i,w)])

def cage_bar(g,j):
    a=2*math.pi*(j+.31)/g['rotor_bars'];i=g['rotor_bar_inner_r_mm'];o=g['rotor_bar_outer_r_mm'];w=g['rotor_bar_w_mm']
    return [pt(i,-w/2,a),pt(o,-w/2,a),pt(o,w/2,a),pt(i,w/2,a)]

def belt(j):return [('A',1),('C',-1),('B',1),('A',-1),('C',1),('B',-1)][((j+1)//2)%6]

def area(points):return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2

def masses(g):
    L=g['stack_mm'];si=g['stator_bore_mm']/2;so=g['stator_OD_mm']/2;ri=g['rotor_bore_r_mm'];ro=si-g['gap_mm']
    stat=(math.pi*(so*so-si*si)-g['stator_slots']*area(stator_slot(g,0)))*L*7.65e-6*g['steel_fill']
    rot=(math.pi*(ro*ro-ri*ri)-g['rotor_bars']*area(rotor_slot(g,0)))*L*7.65e-6*g['steel_fill']
    cage=(g['rotor_bars']*(g['rotor_bar_outer_r_mm']-g['rotor_bar_inner_r_mm'])*g['rotor_bar_w_mm']*L+4*math.pi*g['endring_mean_r_mm']*g['endring_axial_mm']*g['endring_radial_mm'])*8.96e-6
    return {'stator_steel_kg':stat,'rotor_steel_kg':rot,'cage_copper_kg':cage}
