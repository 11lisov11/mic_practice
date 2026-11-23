"""Local CAD API probe, only new project documents are modified."""
from pathlib import Path
import pythoncom,win32com.client as w
NULL=w.VARIANT(pythoncom.VT_DISPATCH,None)
s=w.GetActiveObject('SldWorks.Application')
d=s.ActiveDoc
if d is None: d=s.NewDocument(r'C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2020\templates\gost-part.prtdot',0,0,0)
plane=d.FirstFeature
while plane is not None and plane.GetTypeName2!='RefPlane':plane=plane.GetNextFeature
print('plane',plane.Name,flush=True)
plane.Select2(False,0)
sm=d.SketchManager;sm.InsertSketch(True)
sm.CreateCircleByRadius(0,0,0,.065);sm.CreateCircleByRadius(0,0,0,.035)
sm.InsertSketch(True)
f=d.FeatureManager.FeatureExtrusion3(True,False,False,6,0,.03,0,False,False,False,False,0,0,False,False,False,False,True,True,True,0,0,False)
print('extrusion',f,flush=True)
if f is None:raise RuntimeError('Extrusion failed')
f.Name='Stator_blank'
d.ClearSelection2(True);plane.Select2(False,0);sm.InsertSketch(True)
for a,b in [((.046,-.00125),(.0625,-.00225)),((.0625,-.00225),(.067,-.0009)),((.067,-.0009),(.067,.0009)),((.067,.0009),(.0625,.00225)),((.0625,.00225),(.046,.00125)),((.046,.00125),(.046,-.00125))]:sm.CreateLine(a[0],a[1],0,b[0],b[1],0)
sm.InsertSketch(True)
c=d.FeatureManager.FeatureCut3(True,False,False,6,0,.04,0,False,False,False,False,0,0,False,False,False,False,False,True,True,False,False,False,0,0,False)
print('cut',c,flush=True)
if c:c.Name='Slot_cut_test'
print('bodies',len(d.GetBodies2(0,False)),flush=True)
print('save',d.SaveAs3(str(Path(__file__).resolve().parent/'sw_probe.SLDPRT'),0,2),flush=True)
d.ShowNamedView2('*Isometric',7);d.ViewZoomtofit2()
