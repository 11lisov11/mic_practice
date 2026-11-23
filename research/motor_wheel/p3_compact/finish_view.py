"""Export a legible P3 internal view and correct descriptive properties."""
import json
import pythoncom,win32com.client as com
from calculate import ROOT
from build_cad import call0

def run():
    try:sw=com.GetActiveObject('SldWorks.Application')
    except pythoncom.com_error:sw=com.Dispatch('SldWorks.Application')
    folder=ROOT/'P3_L30_M145/CAD';path=folder/'P3_L30_M145.SLDASM';e=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0);doc=sw.ActivateDoc3(str(path),False,0,e)
    if doc is None:raise RuntimeError('Open the P3 assembly before view export')
    a=json.loads((folder/'cad_audit.json').read_text());fix={'31_PRINTED_BEARING_FIT_COUPON':'Cold fit coupon16/26mm; only geometry/print trial',
      '11_MAIN_AXLE_HARDENED':'Hollow steel axle17/bore6 with keyseat; HK1712 race hardening and grinding required; frame ends unknown',
      '10_FIXED_HEAT_SPREADER':'Fixed Al heat spreader,48fins, integral keyed collar28OD; nominal key5x5x12; strength/fit pending'}
    seen=set();vis=[]
    for c in doc.GetComponents(False):
        d=call0(c,'GetModelDoc2');p=call0(d,'GetPathName')
        if p not in seen:
            cp=d.Extension.CustomPropertyManager('');cp.Add3('STATUS',30,'P3_NOMINAL_DONOR_NOT_MEASURED_NOT_FOR_PRODUCTION',1);cp.Add3('PARAMETRIC_MASTER',30,'p3_compact/calculate.py + rebuild.py; motor OD108/stack30',1)
            for name,text in fix.items():
                if p.endswith(name+'.SLDPRT'):cp.Add3('MATERIAL_INTENT',30,text,1)
            d.SaveAs3(p,0,1);seen.add(p)
        vis.append((c,int(c.Visible)))
        if any('_'+n in c.Name2 for n in ['19_CARRIER_FRONT','20_OUTPUT_NEEDLE','21_OUTPUT_NEEDLE','08_STATOR_AL_JACKET','09_STATOR_FRONT']):c.Visible=0
    doc.ClearSelection2(True);doc.ShowNamedView2('*Isometric',7);call0(doc,'ViewZoomtofit2');call0(doc,'GraphicsRedraw2');doc.SaveAs3(str(folder/'P3_REVIEW.PNG'),0,3)
    for c,v in vis:c.Visible=v
    call0(doc,'ViewZoomtofit2');doc.SaveAs3(str(path),0,1)
    for p in a['parts']:
        if p['part'] in fix:p['material_intent']=fix[p['part']]
    (folder/'cad_audit.json').write_text(json.dumps(a,indent=2),encoding='utf-8');print('P3 view and metadata saved')

if __name__=='__main__':run()
