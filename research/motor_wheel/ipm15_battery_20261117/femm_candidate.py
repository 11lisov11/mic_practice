"""Offline AC FEMM screening of an ASSUMED compact hub, not a Ninebot fit.

Reuses geometric helpers and inverse-Gamma fit from the prior offline model.
Only new files in this study are written; no drive hardware is accessed.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
from pathlib import Path
import time
import numpy as np

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prior_femm_helpers', ROOT.parent/'design_v1'/'femm_motor.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
f = b.f
G = json.loads((ROOT/'geometry_candidate.json').read_text(encoding='utf-8'))
P, Z, ZR = G['pole_pairs'], G['stator_slots'], G['rotor_bars']
L, NT = G['active_length_mm'], G['reference_turns_per_coil']
RS, RB, RO = G['stator_outer_radius_mm'], G['stator_bore_radius_mm'], G['rotor_outer_radius_mm']
RG = RS+G['air_gap_radial_mm']
BAR0, BW, BD = G['rotor_bar_inner_radius_mm'], G['rotor_bar_width_mm'], G['rotor_bar_depth_mm']
rho = .01724
bar_r = rho*(L/1000)/(BW*BD)
ring_r = rho*(2*math.pi*G['ring_mean_radius_mm']/1000/ZR)/G['ring_cross_section_mm2']
END = 1+ring_r/(2*bar_r*math.sin(math.pi*P/ZR)**2)


def build(path, mesh=1., nonlinear=False):
    f.newdocument(0)
    f.mi_probdef(1, 'millimeters', 'planar', 1e-6, L, 20, 0)
    f.mi_addmaterial('Air', 1, 1, 0, 0, 0, 0, 0, 1)
    f.mi_addmaterial('Steel_assumed', 2000, 2000, 0, 0, 0, .5, 0, .95)
    steel='Steel_assumed'
    if nonlinear:
        steel='M-19 Steel'
        f.mi_getmaterial(steel)
        f.mi_modifymaterial(steel, 5, 0)
        f.mi_modifymaterial(steel, 6, .5)
        f.mi_modifymaterial(steel, 8, .95)
    f.mi_addmaterial('Winding', 1, 1, 0, 0, 0)
    f.mi_addmaterial('Cage_Cu_end_corrected', 1, 1, 0, 0, (1/rho)/END)
    f.mi_addboundprop('A0', 0, 0, 0, 0, 0, 0, 0, 0, 0)
    for phase, angle in [('A',0),('B',-2*math.pi/3),('C',2*math.pi/3)]:
        f.mi_addcircprop(phase, complex(math.cos(angle),math.sin(angle)), 1)
    b.circle(RB)
    b.circle(RO)
    b.circle(RO+15, boundary='A0')
    split=G['slot_layer_split_radius_mm']
    bottom=G['slot_bottom_radius_mm']
    shoulder=G['slot_shoulder_radius_mm']
    split_w=G['slot_bottom_width_mm']+(G['slot_shoulder_width_mm']-G['slot_bottom_width_mm'])*(split-bottom)/(shoulder-bottom)
    levels=[(RS,G['slot_mouth_width_mm']),(G['slot_mouth_base_radius_mm'],G['slot_mouth_width_mm']),
            (shoulder,G['slot_shoulder_width_mm']),(split,split_w),(bottom,G['slot_bottom_width_mm'])]
    angles=[]
    for j in range(Z):
        theta=2*math.pi*j/Z
        pts=b.slot_points(theta,levels)
        b.poly(pts)
        f.mi_addsegment(*pts[3],*pts[-4])
        ph,sgn=b.belt(j)
        b.label((split+shoulder)/2,theta,'Winding',.8*mesh,1,ph,sgn*NT)
        ph,sgn=b.belt((j-G['coil_pitch_slots'])%Z)
        b.label((bottom+split)/2,theta,'Winding',.8*mesh,1,ph,-sgn*NT)
        da=math.asin(G['slot_mouth_width_mm']/(2*RS))
        angles.extend([theta-da,theta+da])
    b.circle(RS,angles)
    angles=[]
    for j in range(ZR):
        theta=2*math.pi*(j+.31)/ZR
        pts=b.slot_points(theta,[(RG,1),(BAR0,1),(BAR0,BW),(BAR0+BD,BW)])
        b.poly(pts)
        f.mi_addsegment(*pts[2],*pts[-3])
        b.label(BAR0+BD/2,theta,'Cage_Cu_end_corrected',.7*mesh,2)
        b.label((RG+BAR0)/2,theta,'Air',.2*mesh,3)
        da=math.asin(1/(2*RG))
        angles.extend([theta-da,theta+da])
    b.circle(RG,angles)
    b.label(RB*.65,.1,'Air',4)
    b.label((RB+bottom)/2,.1,steel,1.4*mesh,4)
    b.label((RS+RG)/2,.1,'Air',.14*mesh,3)
    b.label((BAR0+BD+RO)/2,.1,steel,1.2*mesh,2)
    b.label(RO+8,.1,'Air',3)
    f.mi_saveas(str(path))


def evaluate(freq, amp=1., nonlinear=False):
    f.mi_probdef(freq,'millimeters','planar',1e-6,L,20,1 if nonlinear else 0)
    for ph,ang in [('A',0),('B',-2*math.pi/3),('C',2*math.pi/3)]:
        f.mi_modifycircprop(ph,1,amp*complex(math.cos(ang),math.sin(ang)))
    started=time.time()
    f.mi_analyze(1)
    f.mi_loadsolution()
    props=f.mo_getcircuitproperties('A')
    f.mo_groupselectblock(2)
    loss=float(f.mo_blockintegral(4).real)
    torque=float(f.mo_blockintegral(22).real)
    f.mo_clearblock()
    ts=np.arange(720)*2*math.pi/720
    samples=[]
    for theta in ts:
        bx,by=f.mo_getb(*b.xy((RS+RG)/2,float(theta)))
        samples.append(bx*math.cos(theta)+by*math.sin(theta))
    samples=np.asarray(samples)
    bg=max(abs(np.mean(samples*np.exp(1j*P*ts))),abs(np.mean(samples*np.exp(-1j*P*ts))))
    steel=[]
    for radius,n in [(bottom_radius:=G['slot_bottom_radius_mm']-1,240),((BAR0+BD+RO)/2,240),(60,48)]:
        for j in range(n):
            a=2*math.pi*(j+.5)/n
            bx,by=f.mo_getb(*b.xy(radius,a))
            steel.append(math.sqrt(abs(bx)**2+abs(by)**2))
    row={'frequency_hz':freq,'current_peak_a':amp,'L_real_h':float((props[2]/props[0]).real),
         'L_imag_h':float((props[2]/props[0]).imag),'effective_cage_loss_w':loss,
         'torque_mst_nm':torque,'torque_from_rotor_loss_nm':loss*P/(2*math.pi*freq),
         'Bg_fund_peak_t':float(bg),'steel_sample_max_t':max(steel),
         'nodes':f.mo_numnodes(),'elements':f.mo_numelements(),'elapsed_s':time.time()-started}
    f.mo_close()
    return row


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--refine',action='store_true')
    parser.add_argument('--nonlinear',action='store_true')
    a=parser.parse_args()
    out=ROOT/'femm'
    out.mkdir(exist_ok=True)
    tag='nonlinear' if a.nonlinear else ('refined' if a.refine else 'linear')
    result={'status':'assumed_geometry_not_identified_motor','geometry':G,'end_factor':END,'rows':[]}
    f.openfemm(1)
    try:
        build(out/(tag+'.fem'),.7 if a.refine else 1.,a.nonlinear)
        for freq in ([2] if a.nonlinear else ([1,4] if a.refine else [.5,1,2,4,8,16])):
            row=evaluate(freq,9*math.sqrt(2) if a.nonlinear else 1,a.nonlinear)
            result['rows'].append(row)
            result['fit']=b.fit(result['rows']) if len(result['rows'])>=4 else None
            (out/(tag+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(row),flush=True)
        f.mi_saveas(str(out/(tag+'.fem')))
    finally:
        f.closefemm()


if __name__=='__main__':
    main()
