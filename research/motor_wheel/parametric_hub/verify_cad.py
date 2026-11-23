"""SOLIDWORKS kernel check, placement and assembly interference verification."""
import argparse,json
from pathlib import Path
import pythoncom,win32com.client as com
from solidworks import call0
from geometry import ROOT

def verify(path):
    path=Path(path).resolve()
    try:sw=com.GetActiveObject('SldWorks.Application')
    except pythoncom.com_error:sw=com.Dispatch('SldWorks.Application')
    err=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
    doc=sw.GetOpenDocumentByName(str(path))
    if doc is None:
        warn=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
        doc=sw.OpenDoc6(str(path),2,1,'',err,warn)
    else:doc=sw.ActivateDoc3(str(path),False,0,err)
    if doc is None:raise RuntimeError('Cannot activate assembly:'+str(err.value))
    rows=[];components=doc.GetComponents(False)
    visibility=[(c,int(c.Visible)) for c in components]
    for c in components:
        d=call0(c,'GetModelDoc2');bodies=d.GetBodies2(0,False) or []
        faults=[int(call0(b,'Check3').Count) for b in bodies]
        mp=call0(d.Extension,'CreateMassProperty')
        rows.append({'component':c.Name2,'path':str(call0(d,'GetPathName')),'body_count':len(bodies),
          'kernel_fault_counts':faults,'volume_mm3':float(mp.Volume)*1e9,
          'bbox_mm':[float(x)*1000 for x in d.GetPartBox(True)],'transform':list(call0(c.Transform2,'ArrayData'))})
    mgr=doc.InterferenceDetectionManager
    mgr.TreatCoincidenceAsInterference=False;mgr.IncludeMultibodyPartInterferences=False;mgr.IgnoreHiddenBodies=False
    try:
        inter=call0(mgr,'GetInterferences') or []
        overlaps=[{'components':[x.Name2 for x in r.Components],'volume_mm3':float(r.Volume)*1e9} for r in inter]
    finally:
        call0(mgr,'Done')
        for comp,visible in visibility:comp.Visible=visible
        doc.ClearSelection2(True);call0(doc,'GraphicsRedraw2')
        doc.SaveAs3(str(path),0,1)
    data={'assembly':str(path),'component_count':len(rows),'solid_body_count':sum(r['body_count'] for r in rows),
      'kernel_faults_total':sum(sum(r['kernel_fault_counts']) for r in rows),'interferences':overlaps,
      'coincident_contact_ignored':True,'hidden_components_included':True,'parts':rows,
      'scope':'Nominal solids only; no bearing fits, threads, tolerance stack or strength validation'}
    (path.parent/'cad_verification.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k!='parts'}),flush=True)
    return data

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('assembly');v=a.parse_args();verify(v.assembly)
