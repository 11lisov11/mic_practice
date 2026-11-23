"""Native SOLIDWORKS 2020 feature generation, no UI scripting.

JSON/Python is the parametric master. Each generated part contains editable
native sketches/extrusions. Diameter changes regenerate the family, rather
than scaling an imported STEP or falsely preserving the magnetic gap.
"""
from __future__ import annotations
import argparse,json,math,time
from pathlib import Path
import pythoncom,win32com.client as com
from geometry import ROOT,parameters,geometry,package,stator_slot,rotor_slot,bar_profile,profile,belt

NULL=com.VARIANT(pythoncom.VT_DISPATCH,None)
TEMPLATES=Path(r'C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2020\templates')

def call0(obj,name):
    v=getattr(obj,name)
    return v() if callable(v) and not hasattr(v,'_oleobj_') else v

class CAD:
    def __init__(self,p,out):
        self.p=p;self.g=geometry(p);self.pk=package(p,self.g)
        self.out=Path(out).resolve();self.out.mkdir(parents=True,exist_ok=True)
        try:self.sw=com.GetActiveObject('SldWorks.Application')
        except pythoncom.com_error:self.sw=com.Dispatch('SldWorks.Application')
        self.sw.Visible=True;self.sw.UserControl=True
        self.parts=[];self.audit=[]
        self.tag=f'D{self.p["stator_diameter_mm"]:g}_L{self.g["active_length_mm"]:g}'
    def new(self,name,color,material):
        self.doc=self.sw.NewDocument(str(TEMPLATES/'gost-part.prtdot'),0,0,0)
        if self.doc is None:raise RuntimeError('SOLIDWORKS part template missing')
        self.name=name;self.color=color;self.material=material
        self.plane=call0(self.doc,'FirstFeature')
        while self.plane is not None and call0(self.plane,'GetTypeName2')!='RefPlane':self.plane=call0(self.plane,'GetNextFeature')
        self.sk=self.doc.SketchManager
        eq=call0(self.doc,'GetEquationMgr')
        for text in [f'"D_STATOR_mm" = {self.p["stator_diameter_mm"]}mm',f'"L_STACK_mm" = {self.g["active_length_mm"]}mm',f'"AIRGAP_mm" = {self.g["air_gap_radial_mm"]}mm']:
            eq.Add2(-1,text,True)
        cp=self.doc.Extension.CustomPropertyManager('')
        for k,v in {'STATUS':'P1_CONCEPT_NOT_FOR_MANUFACTURE','PARAMETRIC_MASTER':'parameters.json + rebuild.py','MATERIAL_INTENT':material,'DIAMETER_MM':str(self.p['stator_diameter_mm'])}.items():cp.Add3(k,30,v,1)
        return self.doc
    def begin(self,name):
        self.doc.ClearSelection2(True);self.plane.Select2(False,0);self.sk.InsertSketch(True)
        self.sk.AddToDB=True;self.sk.DisplayWhenAdded=False
        self.skname=name
    def circle(self,r):return self.sk.CreateCircleByRadius(0,0,0,r/1000)
    def poly(self,pts):
        for a,b in zip(pts,pts[1:]+pts[:1]):self.sk.CreateLine(a[0]/1000,a[1]/1000,0,b[0]/1000,b[1]/1000,0)
    def finish(self):
        self.sk.AddToDB=False;self.sk.DisplayWhenAdded=True
        self.sk.InsertSketch(True)
    def extrude(self,z0,z1,name,merge=True):
        feat=self.doc.FeatureManager.FeatureExtrusion3(True,False,False,0,0,(z1-z0)/1000,0,
          False,False,False,False,0,0,False,False,False,False,merge,True,True,3 if z0 else 0,abs(z0)/1000,z0<0)
        if feat is None:raise RuntimeError(f'{self.name}/{name}: failed native extrusion')
        feat.Name=name;return feat
    def cut(self,depth,name):
        feat=self.doc.FeatureManager.FeatureCut3(True,False,False,6,0,depth/1000,0,
          False,False,False,False,0,0,False,False,False,False,False,True,True,False,False,False,0,0,False)
        if feat is None:raise RuntimeError(f'{self.name}/{name}: failed native cut')
        feat.Name=name;return feat
    def annulus(self,ri,ro,z0,z1,name,merge=True):
        self.begin(name+'_profile');self.circle(ro)
        if ri:self.circle(ri)
        self.finish();return self.extrude(z0,z1,name,merge)
    def save(self,stl=False):
        self.doc.ClearSelection2(True);call0(self.doc,'EditRebuild3')
        bodies=self.doc.GetBodies2(0,False)
        if not bodies:raise RuntimeError(f'{self.name}: no solid bodies')
        self.doc.MaterialPropertyValues=com.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,[*self.color,0.6,0.5,0.3,0.25,0.0,0.0])
        box=[float(x)*1000 for x in self.doc.GetPartBox(True)]
        mass=call0(self.doc.Extension,'CreateMassProperty')
        volume=float(mass.Volume)*1e9
        native=self.out/(self.tag+'_'+self.name+'.SLDPRT')
        errors=self.doc.SaveAs3(str(native),0,1)
        if errors or not native.exists():raise RuntimeError(f'{native}: save code{errors}')
        step=self.out/(self.tag+'_'+self.name+'.STEP');err=self.doc.SaveAs3(str(step),0,2)
        if err or not step.exists():raise RuntimeError(f'STEP export failed:{err}')
        if stl:
            err=self.doc.SaveAs3(str(self.out/(self.tag+'_'+self.name+'.STL')),0,2)
            if err:raise RuntimeError(f'STL export failed:{err}')
        self.parts.append((str(native),self.name))
        row={'part':self.name,'bodies':len(bodies),'bbox_mm':box,'solid_volume_mm3':volume,'material_intent':self.material}
        self.audit.append(row);print(json.dumps(row),flush=True)
        self.sw.CloseDoc(call0(self.doc,'GetTitle'))
        self.doc=None
        return native
    def build(self):
        g=self.g;p=self.p;pk=self.pk;m=p['mechanical'];h=g['active_length_mm']/2;s=p['stator_diameter_mm']/130
        rs=g['stator_outer_radius_mm'];rg=rs+g['air_gap_radial_mm'];ro=g['rotor_outer_radius_mm'];rb=g['stator_bore_radius_mm']
        steel=(.40,.43,.47);cu=(.83,.40,.12);al=(.68,.72,.77)
        self.new('01_STATOR_LAMINATED',steel,'0.5mm electrical steel insulated laminations; M19 reference curve only')
        self.annulus(rb,rs,-h,h,'Stator_stack')
        self.begin('48_slot_profiles')
        for j in range(48):self.poly(stator_slot(g,j,1.))
        self.finish();self.cut(g['active_length_mm']+2,'Stator_48_slots');self.save()
        self.new('02_ROTOR_LAMINATED',steel,'0.5mm electrical steel insulated laminations; open rotor slots')
        self.annulus(rg,ro,-h,h,'Rotor_stack')
        self.begin('50_cage_slot_profiles')
        for j in range(50):self.poly(rotor_slot(g,j,.8))
        self.finish();self.cut(g['active_length_mm']+2,'Rotor_50_slots');self.save()
        self.new('03_COPPER_CAGE',cu,'Copper cage; 50 bars plus 2 end rings, joint resistance not modelled')
        self.begin('50_bar_profiles')
        for j in range(50):self.poly(bar_profile(g,j))
        self.finish();self.extrude(-h-.1,h+.1,'Cage_50_bars',False)
        ri=pk['endring_inner_radius_mm'];re=pk['endring_outer_radius_mm'];a=g['ring_axial_mm']
        self.annulus(ri,re,h,h+a,'Cage_ring_right')
        self.annulus(ri,re,-h-a,-h,'Cage_ring_left');self.save()
        self.new('04_STATOR_HEAT_CARRIER',al,'Aluminium carrier; torque keys, thermal interface and wire outlet to be detailed')
        self.annulus(m['shaft_diameter_mm']/2,rb,-h,h,'Carrier');self.save()
        self.new('05_SHAFT_METAL',(.45,.47,.5),'Steel solid shaft envelope; thread/flats/keys/cable outlet NOT detailed')
        self.annulus(0,m['shaft_diameter_mm']/2,-m['shaft_total_length_mm']/2,m['shaft_total_length_mm']/2,'Shaft_envelope');self.save()
        self.new('06_ROTOR_SHELL_METAL',(.28,.32,.38),'Aluminium rotor retaining shell; donor rim and retention NOT detailed')
        z=pk['cover_inner_z_mm'];self.annulus(ro,pk['outer_housing_radius_mm'],-z,z,'Rotor_shell');self.save()
        for side,sign in [('RIGHT',1),('LEFT',-1)]:
            self.new('07_COVER_'+side+'_METAL',al,'Aluminium cover; bearing seat47 nominal; bolt/fit/tolerance detail pending')
            z0,z1=sorted((sign*z,sign*pk['cover_outer_z_mm']))
            self.annulus(m['bearing_OD_mm']/2,pk['outer_housing_radius_mm'],z0,z1,'Cover_web')
            b0,b1=sorted((sign*(pk['cover_outer_z_mm']-m['bearing_width_mm']),sign*pk['cover_outer_z_mm']))
            self.annulus(m['bearing_OD_mm']/2,m['bearing_OD_mm']/2+4,b0,b1,'Bearing_boss')
            self.save()
            self.new('08_BEARING_6204_'+side,(.35,.36,.39),'Purchased6204 20x47x14; geometric envelope, NOT bearing manufacture model')
            self.annulus(m['bearing_bore_mm']/2,m['bearing_OD_mm']/2,b0,b1,'Purchased_bearing_envelope');self.save()
            self.new('09_PRINTED_GUARD_'+side,(.13,.46,.68),'PETG printed nonstructural guard, keep below material service temperature')
            z0,z1=sorted((sign*(pk['cover_outer_z_mm']+.5),sign*(pk['cover_outer_z_mm']+2.5)))
            self.annulus(m['bearing_OD_mm']/2+6,pk['outer_housing_radius_mm']-1,z0,z1,'Printed_guard');self.save(stl=True)
        # Slot copper is an envelope, not a conductor-by-conductor solid. Each
        # phase gets separate colour; actual coil connections are in CSV.
        bottom=g['slot_bottom_radius_mm'];shoulder=g['slot_shoulder_radius_mm'];split=g['slot_layer_split_radius_mm']
        wb=g['slot_bottom_width_mm'];ws=g['slot_shoulder_width_mm'];wm=wb+(ws-wb)*(split-bottom)/(shoulder-bottom)
        for phase,col in [('A',(.85,.15,.1)),('B',(.95,.70,.1)),('C',(.15,.3,.85))]:
            self.new('10_WINDING_'+phase+'_ENVELOPE',col,'Copper slot-fill envelope only; end turns represented separately; follow winding CSV')
            self.begin('Slot_copper_envelopes')
            for j in range(48):
                angle=2*math.pi*j/48
                if belt(j)[0]==phase:self.poly(profile(angle,[(split+.2,wm*.65),(shoulder-.3,ws*.65)]))
                if belt((j-5)%48)[0]==phase:self.poly(profile(angle,[(bottom+.3,wb*.65),(split-.2,wm*.65)]))
            self.finish();self.extrude(-h,h,'Slot_copper_envelopes',False);self.save()
        self.new('11_ENDTURN_ENVELOPE',(.65,.24,.10),'KEEP OUT ONLY, approximate common envelope for distributed winding; not printable part')
        for sign,label in [(1,'R'),(-1,'L')]:
            z0,z1=sorted((sign*h,sign*(h+m['endwinding_overhang_mm_assumed'])))
            self.annulus(bottom-.5,pk['endturn_envelope_outer_radius_mm'],z0,z1,'Endturn_'+label,False)
        self.save()
        # Small fully printable useful tooling, outside the hot motor.
        self.new('12_PRINTED_WINDING_FORMER',(.12,.55,.65),'PETG winding trial tool; no load or hot motor duty')
        length=g['active_length_mm']+2;span=2*((bottom+shoulder)/2)*math.sin(math.pi*5/48)
        self.begin('Former_base_profile');self.poly([(-length/2-4,-span/2-4),(length/2+4,-span/2-4),(length/2+4,span/2+4),(-length/2-4,span/2+4)])
        self.finish();self.extrude(0,3,'Former_base')
        self.begin('Former_posts_profile')
        for x in [-length/2,length/2]:
            for y in [-span/2,span/2]:self.sk.CreateCircleByRadius(x/1000,y/1000,0,.002)
        self.finish();self.extrude(3,15,'Former_posts');self.save(stl=True)
        # Tool is saved separately, excluded from motor assembly.
        return self.assemble(self.parts[:-1])
    def assemble(self,motor_parts):
        g=self.g;pk=self.pk
        read_audit=not self.audit
        self.sw.DocumentVisible(False,1)
        try:
            for path,name in motor_parts:
                if self.sw.GetOpenDocumentByName(path) is None:
                    err=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0);warn=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
                    doc=self.sw.OpenDoc6(path,1,1,'',err,warn)
                    if doc is None:raise RuntimeError('Load component:'+name+':'+str(err.value))
                else:doc=self.sw.GetOpenDocumentByName(path)
                if read_audit:
                    self.audit.append({'part':name,'bodies':len(doc.GetBodies2(0,False)),
                      'bbox_mm':[float(x)*1000 for x in doc.GetPartBox(True)],
                      'solid_volume_mm3':float(call0(doc.Extension,'CreateMassProperty').Volume)*1e9})
        finally:self.sw.DocumentVisible(True,1)
        assembly=self.sw.NewDocument(str(TEMPLATES/'gost-assy.asmdot'),0,0,0)
        if assembly is None:raise RuntimeError('Assembly template missing')
        mu=call0(self.sw,'GetMathUtility');mu._FlagAsMethod('CreateTransform')
        mat=mu.CreateTransform(com.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,[1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0]))
        components=[]
        for path,name in motor_parts:
            comp=assembly.AddComponent5(path,0,'',False,'',0,0,0)
            if comp is None:raise RuntimeError('Component insertion failed:'+name)
            comp.Transform2=mat;comp.Name2=name
            comp.Select4(False,NULL,False);call0(assembly,'FixComponent');assembly.ClearSelection2(True)
            components.append(comp)
            # Hide both metal covers and plastic guards by default so internal
            # geometry is immediately visible when the assembly opens.
            if name.startswith(('07_','09_','11_')):comp.Visible=0
        call0(assembly,'EditRebuild3');assembly.ShowNamedView2('*Isometric',7);call0(assembly,'ViewZoomtofit2')
        path=self.out/('ACIM_HUB_'+self.tag+'.SLDASM');err=assembly.SaveAs3(str(path),0,1)
        if err:raise RuntimeError('Assembly save failed:'+str(err))
        # Export all components (including covers) in a neutral assembly.
        for comp in components:comp.Visible=1
        err=assembly.SaveAs3(str(self.out/'ACIM_HUB_P1_COMPLETE.STEP'),0,2)
        if err:raise RuntimeError('Assembly STEP export failed:'+str(err))
        for comp,(_,name) in zip(components,motor_parts):
            if name.startswith(('07_','09_','11_')):comp.Visible=0
        call0(assembly,'ViewZoomtofit2');assembly.SaveAs3(str(path),0,1)
        (self.out/'cad_audit.json').write_text(json.dumps({'parameters':self.p,'geometry':g,'package':pk,'parts':self.audit,
          'assembly_component_count':len(components),'native_SOLIDWORKS_version':str(call0(self.sw,'RevisionNumber')),
          'parametric_method':'Change diameter/length via rebuild.py; JSON/Python controls all regenerated native features. Global variables inside files are metadata, not full feature driving equations.',
          'manufacturing_release':False},indent=2),encoding='utf-8')
        return path

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--diameter',type=float,default=130);a.add_argument('--length',type=float,default=30);a.add_argument('--out',required=True);a.add_argument('--assembly-only',action='store_true')
    v=a.parse_args();cad=CAD(parameters(diameter=v.diameter,length=v.length),v.out)
    print(cad.assemble([(str(f),f.stem) for f in sorted(cad.out.glob('*.SLDPRT')) if not (f.stem.startswith('12_') or '_12_' in f.stem)]) if v.assembly_only else cad.build(),flush=True)
