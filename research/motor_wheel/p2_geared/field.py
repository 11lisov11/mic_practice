"""Offline 360deg FEMM AC identification of a conventional inner rotor ACIM."""
import argparse,importlib.util,json,math,os,sys,time
from pathlib import Path
import numpy as np
from model import ROOT,load,stator_slot,rotor_slot,belt,xy
sys.path.insert(0,str(Path(os.environ['LOCALAPPDATA'])/'mic_motor_wheel_tools/python'))
import femm as f
spec=importlib.util.spec_from_file_location('prior_helpers',ROOT.parent/'design_v1/femm_motor.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

def run(g,out,nonlinear_amp=None,refine=False,nonlinear_freq=2.):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);tag='nonlinear' if nonlinear_amp else ('refined' if refine else 'linear')
    p=g['pole_pairs'];Z=g['stator_slots'];ZR=g['rotor_bars'];L=g['stack_mm'];si=g['stator_bore_mm']/2;so=g['stator_OD_mm']/2;ro=si-g['gap_mm']
    bw=g['rotor_bar_w_mm'];bd=g['rotor_bar_outer_r_mm']-g['rotor_bar_inner_r_mm'];rho=.01724*(1+.00393*(g.get('cage_temperature_C',20)-20))
    rb=rho*(L/1000)/(bw*bd);re=rho*(2*math.pi*g['endring_mean_r_mm']/1000/ZR)/(g['endring_axial_mm']*g['endring_radial_mm'])
    end=1+2*g.get('cage_end_clearance_mm',0)/L+re/(2*rb*math.sin(math.pi*p/ZR)**2)
    mesh=.65 if refine else 1.
    f.openfemm(1)
    try:
        f.newdocument(0);f.mi_probdef(1,'millimeters','planar',1e-7,L,25,1 if nonlinear_amp else 0)
        f.mi_addmaterial('Air',1,1,0,0,0)
        f.mi_addmaterial('Steel_linear',2000,2000,0,0,0,g['lamination_mm'],0,g['steel_fill'])
        steel='Steel_linear'
        if nonlinear_amp:
            steel='M-19 Steel';f.mi_getmaterial(steel);f.mi_modifymaterial(steel,5,0);f.mi_modifymaterial(steel,6,g['lamination_mm']);f.mi_modifymaterial(steel,8,g['steel_fill'])
        f.mi_addmaterial('Winding',1,1,0,0,0)
        f.mi_addmaterial('Cage_end_corrected',1,1,0,0,(1/rho)/end)
        f.mi_addboundprop('A0',0,0,0,0,0,0,0,0,0)
        for ph,ang in [('A',0),('B',-2*math.pi/3),('C',2*math.pi/3)]:f.mi_addcircprop(ph,complex(math.cos(ang),math.sin(ang)),1)
        h.circle(g['rotor_bore_r_mm']);h.circle(so);h.circle(so+15,boundary='A0')
        angles=[]
        for j in range(Z):
            a=2*math.pi*j/Z;pts=stator_slot(g,j);h.poly(pts)
            f.mi_addsegment(*pts[2],*pts[-3]);f.mi_addsegment(*pts[3],*pts[-4])
            h.label((si+g['slot_shoulder_r_mm'])/2,a,'Air',.35*mesh,3)
            ph,sign=belt(j);h.label((g['slot_shoulder_r_mm']+g['slot_split_r_mm'])/2,a,'Winding',.65*mesh,1,ph,sign*g['reference_turns'])
            ph,sign=belt((j-g['coil_pitch'])%Z);h.label((g['slot_split_r_mm']+g['slot_bottom_r_mm'])/2,a,'Winding',.65*mesh,1,ph,-sign*g['reference_turns'])
            da=math.asin(g['slot_mouth_w_mm']/(2*si));angles.extend([a-da,a+da])
        h.circle(si,angles)
        angles=[]
        for j in range(ZR):
            a=2*math.pi*(j+.31)/ZR;pts=rotor_slot(g,j);h.poly(pts);f.mi_addsegment(*pts[2],*pts[-3])
            h.label((g['rotor_bar_inner_r_mm']+g['rotor_bar_outer_r_mm'])/2,a,'Cage_end_corrected',.45*mesh,2)
            h.label((ro+g['rotor_bar_outer_r_mm'])/2,a,'Air',.2*mesh,3)
            da=math.asin(g['rotor_opening_w_mm']/(2*ro));angles.extend([a-da,a+da])
        h.circle(ro,angles)
        h.label(g['rotor_bore_r_mm']/2,.11,'Air',2)
        h.label((g['rotor_bore_r_mm']+g['rotor_bar_inner_r_mm'])/2,.11,steel,.8*mesh,2)
        h.label((si+ro)/2,.11,'Air',g['gap_mm']*.38*mesh,3)
        h.label((g['slot_bottom_r_mm']+so)/2,.11,steel,1.0*mesh,4)
        h.label(so+8,.11,'Air',3)
        path=out/(tag+'.fem');f.mi_saveas(str(path));rows=[]
        for freq in ([nonlinear_freq] if nonlinear_amp else ([1.,4.] if refine else [.5,1.,2.,4.,8.,16.])):
            amp=nonlinear_amp or 1.;f.mi_probdef(freq,'millimeters','planar',1e-7,L,25,1 if nonlinear_amp else 0)
            for ph,a in [('A',0),('B',-2*math.pi/3),('C',2*math.pi/3)]:f.mi_modifycircprop(ph,1,amp*complex(math.cos(a),math.sin(a)))
            start=time.time();f.mi_analyze(1);f.mi_loadsolution();c=f.mo_getcircuitproperties('A')
            f.mo_groupselectblock(2);loss=float(f.mo_blockintegral(4).real);torque=float(f.mo_blockintegral(22).real);f.mo_clearblock()
            angles=np.arange(720)*2*math.pi/720;bs=[]
            for a in angles:
                bx,by=f.mo_getb(*xy((si+ro)/2,float(a)));bs.append(bx*math.cos(a)+by*math.sin(a))
            bs=np.asarray(bs);bg=max(abs(np.mean(bs*np.exp(1j*p*angles))),abs(np.mean(bs*np.exp(-1j*p*angles))))
            maxsteel=0
            for radius,n,off in [((g['slot_bottom_r_mm']+so)/2,180,.5),((g['rotor_bore_r_mm']+g['rotor_bar_inner_r_mm'])/2,180,.5),((si+g['slot_bottom_r_mm'])/2,Z,.5)]:
                for j in range(n):
                    bx,by=f.mo_getb(*xy(radius,2*math.pi*(j+off)/n));maxsteel=max(maxsteel,math.sqrt(abs(bx)**2+abs(by)**2))
            row={'frequency_hz':freq,'current_peak_A':amp,'L_real_h':float((c[2]/c[0]).real),'L_imag_h':float((c[2]/c[0]).imag),
              'cage_loss_W':loss,'torque_signed_Nm':torque,'torque_mst_Nm':abs(torque),'torque_from_cage_Nm':loss*p/(2*math.pi*freq),
              'Bg_fund_peak_t':float(bg),'steel_sample_max_T':maxsteel,'nodes':f.mo_numnodes(),'elements':f.mo_numelements(),'elapsed_s':time.time()-start}
            # Common helper fit consumes only the frequency and inductance keys.
            rows.append(row);result={'status':'UNVALIDATED_REFERENCE_STEEL_AND_END_RING_CORRECTION','geometry':g,'end_factor':end,'rows':rows,'fit':h.fit(rows) if len(rows)>=4 else None}
            (out/(tag+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'case':out.parent.name,'tag':tag,**row}),flush=True);f.mo_close()
        f.mi_saveas(str(path))
        return result
    finally:f.closefemm()

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--length',type=float);ap.add_argument('--gap',type=float);ap.add_argument('--out',required=True);ap.add_argument('--nonlinear-amp',type=float);ap.add_argument('--nonlinear-freq',type=float,default=2.);ap.add_argument('--cage-temperature',type=float,default=20);ap.add_argument('--refine',action='store_true')
    a=ap.parse_args();g=load()
    if a.length:g['stack_mm']=a.length
    if a.gap:g['gap_mm']=a.gap
    g['cage_temperature_C']=a.cage_temperature
    run(g,a.out,a.nonlinear_amp,a.refine,a.nonlinear_freq)
