"""Correct descriptive metadata and export review views of existing solids."""
import json,sys
import pythoncom,win32com.client as com
from model import ROOT,load
sys.path.insert(0,str(ROOT.parent/'parametric_hub'))
from solidworks import call0

def run():
    sw=com.GetActiveObject('SldWorks.Application')
    err=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
    for tag,asm in [('P2_HUB_SMALL','P2_HUB_SMALL'),('P2_HUB','P2_GEARED_HUB')]:
        folder=ROOT/tag/'CAD';p=folder/(asm+'.SLDASM');doc=sw.ActivateDoc3(str(p),False,0,err)
        if doc is None:raise RuntimeError(p)
        audit=json.loads((folder/'cad_audit.json').read_text());cfg=audit['gear'];mod=cfg['module_mm'];dc=30*mod;bolt=2*(dc+2)
        updates={'12_METAL_SUN_20T':f'Steel sun m{mod:g} z20; production root fillet and fits pending',
          '18_CARRIER_REAR_AL':f'Aluminium rear carrier,8mm pins on{dc*2:g}mm PCD',
          '19_CARRIER_FRONT_AL':f'Aluminium front carrier;6xPCD{bolt:g}mm ASSUMED output interface',
          '91_DONOR_RIM_REFERENCE':f'ASSUMED rim OD{2*cfg["donor_rim_outer_r_mm_ASSUMED"]:g}; NOT measured Max Pro',
          '92_DONOR_FRONT_COVER_REFERENCE':f'ASSUMED cover;6xPCD{bolt:g}mm adapter, not measured Max Pro'}
        audit['geometry']=load();seen=set()
        for c in doc.GetComponents(False):
            d=call0(c,'GetModelDoc2');path=call0(d,'GetPathName');name=next((r['part'] for r in audit['parts'] if path.endswith(r['part']+'.SLDPRT')),None)
            if path not in seen:
                cp=d.Extension.CustomPropertyManager('')
                cp.Add3('PARAMETRIC_MASTER',30,'p2_geared/inputs.json + build_cad.py --gear-module; new motor diameter needs new FEMM',1)
                if name in updates:cp.Add3('MATERIAL_INTENT',30,updates[name],1)
                d.SaveAs3(path,0,1);seen.add(path)
        for r in audit['parts']:
            if r['part'] in updates:r['material_intent']=updates[r['part']]
        (folder/'cad_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
        components=doc.GetComponents(False);vis=[(c,int(c.Visible)) for c in components]
        for c in components:
            if any('_'+s in c.Name2 for s in ['19_CARRIER_FRONT','20_OUTPUT','21_OUTPUT','08_STATOR_AL_JACKET','09_STATOR_FRONT']):c.Visible=0
        doc.ClearSelection2(True);doc.ShowNamedView2('*Isometric',7);call0(doc,'ViewZoomtofit2');call0(doc,'GraphicsRedraw2')
        doc.SaveAs3(str(folder/'P2_REVIEW.PNG'),0,3)
        for c,v in vis:c.Visible=v
        doc.ClearSelection2(True);call0(doc,'ViewZoomtofit2');doc.SaveAs3(str(p),0,1)
        print(tag,'metadata and view complete',flush=True)
    return True

if __name__=='__main__':run()
