"""Rebuild the SAME parameterised geometry as CAD in FEMM 4.2.

Only an offline field solver is used. No serial/network drive access.
"""
import argparse,importlib.util,json,math
from pathlib import Path
import numpy as np
from geometry import ROOT,parameters,geometry

def run(p,out,nonlinear=False,refine=False):
    spec=importlib.util.spec_from_file_location('compact_femm',ROOT.parent/'ipm15_battery_20261117'/'femm_candidate.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    g=geometry(p);m.G=g;m.L=g['active_length_mm'];m.RS=g['stator_outer_radius_mm'];m.RB=g['stator_bore_radius_mm']
    m.RO=g['rotor_outer_radius_mm'];m.RG=m.RS+g['air_gap_radial_mm']
    m.BAR0=g['rotor_bar_inner_radius_mm'];m.BW=g['rotor_bar_width_mm'];m.BD=g['rotor_bar_depth_mm']
    bar_r=.01724*(m.L/1000)/(m.BW*m.BD)
    ring_r=.01724*(2*math.pi*g['ring_mean_radius_mm']/1000/50)/g['ring_cross_section_mm2']
    m.END=1+ring_r/(2*bar_r*math.sin(math.pi*4/50)**2)
    # Original helper uses 1 mm cage openings; for changed diameters make
    # the opening fixed 1 mm in the parameter record too (no hidden mismatch).
    g['rotor_slot_opening_mm']=1.0
    tag='nonlinear' if nonlinear else ('refined' if refine else 'linear')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    data={'status':'unvalidated_material_and_geometry_hypothesis','geometry':g,'end_factor':m.END,'rows':[]}
    m.f.openfemm(1)
    try:
        m.build(out/(tag+'.fem'),.7 if refine else 1.,nonlinear)
        for freq in ([2.] if nonlinear else ([1.,4.] if refine else [.5,1,2,4,8,16])):
            row=m.evaluate(freq,9*math.sqrt(2) if nonlinear else 1.,nonlinear)
            data['rows'].append(row)
            data['fit']=m.b.fit(data['rows']) if len(data['rows'])>=4 else None
            (out/(tag+'.json')).write_text(json.dumps(data,indent=2),encoding='utf-8')
            print(json.dumps({'case':out.parent.name,'mode':tag,**row}),flush=True)
        m.f.mi_saveas(str(out/(tag+'.fem')))
    finally:m.f.closefemm()
    return data

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--diameter',type=float,default=130);a.add_argument('--length',type=float,default=30)
    a.add_argument('--out',required=True);a.add_argument('--nonlinear',action='store_true');a.add_argument('--refine',action='store_true')
    v=a.parse_args();run(parameters(diameter=v.diameter,length=v.length),v.out,v.nonlinear,v.refine)
