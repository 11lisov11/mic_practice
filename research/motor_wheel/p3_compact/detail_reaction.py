"""Add the same keyed reaction detail to the first already generated P3 set.

Future full builds include it directly through keyed_reaction_collar.
Only the named P3 documents are edited; geometry and results P2 are preserved.
"""
import json,sys
from pathlib import Path
from calculate import ROOT,P2,geometry
from build_cad import Hub,call0
import pythoncom,win32com.client as com

def run():
    folder=ROOT/'P3_L30_M145';out=folder/'CAD';audit=json.loads((out/'cad_audit.json').read_text());data=json.loads((folder/'results.json').read_text())
    _,g,gear=geometry();h=Hub(1.45,g,folder,gear);z0=-30;z1=-17.5
    asm=out/'P3_L30_M145.SLDASM';doc=h.sw.GetOpenDocumentByName(str(asm));err=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
    for name in ['10_FIXED_HEAT_SPREADER','11_MAIN_AXLE_HARDENED']:
        path=out/('P3_L30_M145_'+name+'.SLDPRT');d=h.sw.ActivateDoc3(str(path),False,0,err)
        if d is None:raise RuntimeError('P3 part not loaded:'+name)
        h.doc=d;h.sk=d.SketchManager;h.name=name;h.plane=call0(d,'FirstFeature')
        while h.plane is not None and call0(h.plane,'GetTypeName2')!='RefPlane':h.plane=call0(h.plane,'GetNextFeature')
        # Re-entry is harmless: do not duplicate named native features.
        exists=d.FeatureByName('Collar_keyway' if name.startswith('10') else 'Axle_keyway')
        if exists is None:
            if name.startswith('10'):h.annulus(8.5,14,z0,z1,'Keyed_reaction_collar')
            h.begin('Keyway_profile');h.poly([(5.5,-2.5),(10.5,-2.5),(10.5,2.5),(5.5,2.5)]);h.finish();h.cut_at(z0,z1,'Collar_keyway' if name.startswith('10') else 'Axle_keyway')
        call0(d,'EditRebuild3');d.SaveAs3(str(path),0,1);d.SaveAs3(str(path.with_suffix('.STEP')),0,3)
        for row in audit['parts']:
            if row['part']==name:row['solid_volume_mm3']=float(call0(d.Extension,'CreateMassProperty').Volume)*1e9
    name='28_REACTION_KEY_5X5';path=out/('P3_L30_M145_'+name+'.SLDPRT')
    if not path.exists():
        h.new(name,(.5,.54,.58),'Steel5x5x12 reaction key, nominal geometry; fit and end treatment pending');h.begin('Reaction_key_profile');h.poly([(5.5,-2.5),(10.5,-2.5),(10.5,2.5),(5.5,2.5)]);h.finish();h.extrude(-29.75,-17.75,'Reaction_key');h.keep()
        audit['parts'].append(h.audit[-1])
    doc=h.sw.ActivateDoc3(str(asm),False,0,err)
    if not any(name in c.Name2 for c in doc.GetComponents(False)):
        warn=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0);h.sw.OpenDoc6(str(path),1,1,'',err,warn)
        doc=h.sw.ActivateDoc3(str(asm),False,0,err);c=doc.AddComponent5(str(path),0,'',False,'',0,0,0)
        if c is None:raise RuntimeError('Cannot insert reaction key')
        c.Select4(False,com.VARIANT(pythoncom.VT_DISPATCH,None),False);call0(doc,'FixComponent');doc.ClearSelection2(True)
        audit['placements'].append({'name':name,'x_mm':0,'y_mm':0,'z_mm':0,'angle_rad':0})
    # AddComponent5 positions a component's box centre at its insertion point.
    # Our parts use assembly coordinates, so an explicit identity is required.
    key=next(c for c in doc.GetComponents(False) if name in c.Name2)
    key.Select4(False,com.VARIANT(pythoncom.VT_DISPATCH,None),False);call0(doc,'UnfixComponent');doc.ClearSelection2(True)
    mu=call0(h.sw,'GetMathUtility');mu._FlagAsMethod('CreateTransform')
    key.Transform2=mu.CreateTransform(com.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,[1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0]))
    key.Select4(False,com.VARIANT(pythoncom.VT_DISPATCH,None),False);call0(doc,'FixComponent');doc.ClearSelection2(True)
    audit['gear']=gear;audit['assembly_components']=len(doc.GetComponents(False));call0(doc,'EditRebuild3');doc.SaveAs3(str(asm),0,1)
    vis=[(c,int(c.Visible)) for c in doc.GetComponents(False)]
    for c,_ in vis:c.Visible=1
    doc.SaveAs3(str(out/'P3_L30_M145_COMPLETE.STEP'),0,3)
    for c,v in vis:c.Visible=v
    doc.ShowNamedView2('*Isometric',7);call0(doc,'ViewZoomtofit2');call0(doc,'GraphicsRedraw2');doc.SaveAs3(str(asm),0,1)
    (out/'cad_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print('P3 keyed reaction collar and steel key saved',flush=True)

if __name__=='__main__':run()
