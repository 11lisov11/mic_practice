"""Native SOLIDWORKS P2 hub insert + planetary6:1, donor dimensions assumed.

No firmware/drive hardware access. Reference rim is explicitly distinguished
from the new motor/transmission insert in the bill of materials and mass.
"""
import argparse,json,math,sys
from pathlib import Path
import pythoncom,win32com.client as com
from model import ROOT,load,stator_slot,rotor_slot,cage_bar,profile,belt
from planetary import config,gear_outline
sys.path.insert(0,str(ROOT.parent/'parametric_hub'))
from solidworks import CAD,call0,NULL,TEMPLATES
from geometry import parameters as old_parameters

class Hub(CAD):
    def __init__(self,module=1.6,data=None,output=None,gear=None):
        g=json.loads(json.dumps(data)) if data is not None else load();p=old_parameters();p['stator_diameter_mm']=g['stator_OD_mm'];p['stack_length_mm']=g['stack_mm'];p['radial_airgap_mm']=g['gap_mm']
        folder='P2_HUB' if module==1.6 else ('P2_HUB_SMALL' if module==1.25 else f'P2_HUB_M{module:g}')
        location=Path(output) if output is not None else ROOT/folder
        super().__init__(p,location/'CAD');self.data=g;self.gear=gear or config(module);self.tag=location.name;self.placements=[]
    def new(self,name,color,material):
        d=super().new(name,color,material)
        cp=d.Extension.CustomPropertyManager('');cp.Add3('STATUS',30,self.tag+'_NOMINAL_INSERT_DONOR_NOT_MEASURED',1)
        cp.Add3('PARAMETRIC_MASTER',30,'Python/JSON generator; diameter change requires regeneration and validation',1)
        return d
    def holes(self,centres,r,depth=200):
        self.begin('Through_holes')
        for x,y in centres:self.sk.CreateCircleByRadius(x/1000,y/1000,0,r/1000)
        self.finish();self.cut(depth,'Through_holes')
    def cut_at(self,z0,z1,name):
        feat=self.doc.FeatureManager.FeatureCut3(True,False,True,0,0,(z1-z0)/1000,0,
          False,False,False,False,0,0,False,False,False,False,False,True,True,False,False,False,3 if z0 else 0,abs(z0)/1000,z0<0)
        if feat is None:raise RuntimeError('Cut failed:'+name)
        feat.Name=name
    def radial_rect(self,ri,ro,w,a):
        return [(r*math.cos(a)-t*math.sin(a),r*math.sin(a)+t*math.cos(a)) for r,t in [(ri,-w/2),(ro,-w/2),(ro,w/2),(ri,w/2)]]
    def keep(self,stl=False,where=None,include=True):
        path=self.save(stl)
        if include:
            for x,y,z,a in (where or [(0,0,0,0)]):self.placements.append((str(path),self.name,x,y,z,a))
        return path
    def build_hub(self):
        g=self.data;p=self.gear;h=g['stack_mm']/2;si=g['stator_bore_mm']/2;so=g['stator_OD_mm']/2;ro=si-g['gap_mm'];G0=h+15;G1=G0+p['ring_face_mm']
        mod=p['module_mm'];dc=30*mod;ringro=p['ring_outer_r_mm'];tier=ringro-4;casei=p['case_inner_r_mm'];heatro=casei+1;finro=min(heatro-4,72)
        rearro=dc+8;frontro=dc+12;boltR=dc+2;rimri=p['donor_rim_inner_r_mm_ASSUMED'];rimro=p['donor_rim_outer_r_mm_ASSUMED']
        bearingZ=G0+p.get('needle_start_after_G0_mm',G1-G0+.5 if mod<1.59 else 12.5)
        bearingEnd=bearingZ+p.get('needle_width_mm',16);needleRo=p.get('needle_outer_r_mm',12.5);needleNeckRo=needleRo+1
        planetBearingRo=p.get('planet_bearing_outer_r_mm',11);planetBearingW=p.get('planet_bearing_width_mm',7)
        planetBearingOffset=p.get('planet_bearing_rear_offset_mm',2);planetBearingStep=p.get('planet_bearing_axial_step_mm',9)
        planetBearingName=p.get('planet_bearing_name','608');needleName=p.get('needle_name','NK17_16')
        steel=(.5,.54,.58);cu=(.92,.49,.2);al=(.72,.77,.82);blue=(.12,.48,.72);gearcol=(.84,.77,.54)
        self.new('01_STATOR_24S',steel,'0.35mm electrical steel laminations; actual grade to specify')
        self.annulus(si,so,-h,h,'Stator_stack');self.begin('Stator_slots')
        for j in range(24):self.poly(stator_slot(g,j,1))
        self.finish();self.cut(g['stack_mm']+2,'Stator_slots');self.keep()
        self.new('02_ROTOR_29B',steel,'0.35mm electrical steel laminations; nominal open slots')
        self.annulus(g['rotor_bore_r_mm'],ro,-h,h,'Rotor_stack');self.begin('Rotor_slots')
        for j in range(g['rotor_bars']):self.poly(rotor_slot(g,j,1))
        self.finish();self.cut(g['stack_mm']+2,'Rotor_slots');self.keep()
        self.new('03_COPPER_CAGE',cu,'Copper bars and two end rings, assembled and brazed by contractor')
        self.begin('Cage_bars')
        for j in range(g['rotor_bars']):self.poly(cage_bar(g,j))
        self.finish();c=g['cage_end_clearance_mm'];self.extrude(-h-c-.1,h+c+.1,'Bars',False)
        ri=g['endring_mean_r_mm']-g['endring_radial_mm']/2;rr=g['endring_mean_r_mm']+g['endring_radial_mm']/2
        self.annulus(ri,rr,h+c,h+c+g['endring_axial_mm'],'End_ring_front')
        self.annulus(ri,rr,-h-c-g['endring_axial_mm'],-h-c,'End_ring_rear');self.keep()
        self.new('04_ROTOR_AL_HUB',al,'Aluminium hollow rotor hub, bearing seats26 nominal, press fit lamination seat32 nominal')
        self.annulus(8.7,16,-h,h+8,'Hollow_hub')
        self.annulus(13,22.2,-h-1.5,-h,'Rear_stack_flange')
        self.annulus(8.7,21,h+8,h+12,'Sun_mount_flange')
        for za,zb,label in [(-h,-h+5,'Rear_rotor_bearing_seat'),(h-5,h,'Front_rotor_bearing_seat')]:
            self.begin(label);self.circle(13);self.finish();self.cut_at(za,zb,label)
        self.begin('Circlip_groove');self.circle(17);self.circle(15.4);self.finish();self.cut_at(h+1.5,h+2.5,'Circlip_groove')
        self.holes([(17*math.cos(a),17*math.sin(a)) for a in [0,math.pi/2,math.pi,3*math.pi/2]],1.25)
        self.keep()
        self.new('05_ROTOR_STACK_WASHER',steel,'Steel end washer, retained by DIN47132 clip')
        self.annulus(16,22.2,h,h+1.5,'Stack_washer');self.keep()
        self.new('06_ROTOR_CIRCLIP_ENVELOPE',steel,'Purchased DIN47132 clip; envelope, not production shape')
        self.annulus(15.4,18.5,h+1.5,h+2.5,'Circlip_envelope');self.keep()
        self.new('07_ROTOR_BEARING_6803',(.38,.4,.43),'Purchased6803 17x26x5 bearing envelope')
        self.annulus(8.5,13,-h,-h+5,'Bearing6803');self.keep(where=[(0,0,0,0),(0,0,2*h-5,0)])
        self.new('08_STATOR_AL_JACKET',al,'Aluminium heat jacket, stator OD108 nominal, clamping flanges; manufacturing fits pending')
        self.annulus(so,so+2,-h-12,h,'Jacket')
        self.annulus(so,61,-h-12,-h-9,'Rear_flange');self.annulus(so,61,h-2,h,'Front_flange')
        self.holes([(58*math.cos(a),58*math.sin(a)) for a in [j*math.pi/3 for j in range(6)]],1.65);self.keep()
        self.new('09_STATOR_FRONT_CLAMP',al,'Aluminium lamination clamping ring, leaves winding overhang envelope clear')
        self.annulus(49,61,h,h+2,'Stator_clamp');self.holes([(58*math.cos(j*math.pi/3),58*math.sin(j*math.pi/3)) for j in range(6)],1.65);self.keep()
        self.new('10_FIXED_HEAT_SPREADER',al,'Aluminium fixed backplate and48 radial fins; fixed to hardened main axle via keyed metal collar')
        self.annulus(8.5,heatro,-h-15,-h-12,'Heat_spreader')
        self.begin('Tie_rod_ears')
        tie=[math.pi/4+j*math.pi/2 for j in range(4)]
        for a in tie:self.poly(self.radial_rect(heatro-6,ringro,12,a))
        self.finish();self.extrude(-h-15,-h-12,'Tie_rod_ears')
        self.begin('48_cooling_fins')
        for j in range(48):self.poly(self.radial_rect(26,finro,1,j*2*math.pi/48))
        self.finish();self.extrude(-h-23.5,-h-15,'Cooling_fins')
        self.holes([(tier*math.cos(a),tier*math.sin(a)) for a in tie]+[(58*math.cos(j*math.pi/3),58*math.sin(j*math.pi/3)) for j in range(6)],2.25)
        if p.get('keyed_reaction_collar'):
            self.annulus(8.5,14,-h-15,-h-2.5,'Keyed_reaction_collar')
            self.begin('Collar_keyway_profile');self.poly([(5.5,-2.5),(10.5,-2.5),(10.5,2.5),(5.5,2.5)]);self.finish();self.cut_at(-h-15,-h-2.5,'Collar_keyway')
        self.keep()
        self.new('11_MAIN_AXLE_HARDENED',steel,f'Steel hollow axle17, cable bore6; {needleName} track hardened/ground; dropout flats/threads donor-specific')
        self.annulus(3,8.5,-75,80,'Axle_envelope')
        if p.get('keyed_reaction_collar'):
            self.begin('Axle_keyway_profile');self.poly([(5.5,-2.5),(10.5,-2.5),(10.5,2.5),(5.5,2.5)]);self.finish();self.cut_at(-h-15,-h-2.5,'Axle_keyway')
        self.keep()
        self.new('12_METAL_SUN_20T',steel,f'Contractor-made steel sun m{mod:g} z20, integral flange; countersunk screws')
        self.begin('Sun_profile');self.poly(gear_outline(20,mod));self.circle(8.7);self.finish();self.extrude(G0,G0+p['sun_face_mm'],'Sun_teeth')
        self.annulus(8.7,21,h+12,G0,'Sun_flange')
        self.holes([(17*math.cos(j*math.pi/2),17*math.sin(j*math.pi/2)) for j in range(4)],1.65);self.keep()
        self.new('13_POLYMER_RING_100T',gearcol,'POM purchased or qualified printed PA; PETG cold fit prototype only; root production rounding pending')
        self.begin('Internal_gear_profile');self.circle(ringro);self.poly(gear_outline(100,mod,True));self.finish();self.extrude(G0,G1,'Internal_ring_teeth')
        self.annulus(rearro+2,ringro,G0-2,G0,'Ring_back_flange')
        self.holes([(tier*math.cos(a),tier*math.sin(a)) for a in tie],2.25);self.keep(stl=True)
        self.new('14_POLYMER_PLANET_40T',gearcol,f'POM or qualified printed polymer; PETG fit trial only; bearing bore{2*planetBearingRo:g} to calibrate after conditioning')
        self.begin('Planet_profile');self.poly(gear_outline(40,mod));self.circle(planetBearingRo);self.finish();self.extrude(G0+1,G1-1,'Planet_teeth')
        positions=[(dc*math.cos(a),dc*math.sin(a),0,math.pi/40) for a in [j*math.pi/2 for j in range(4)]]
        self.keep(stl=True,where=positions)
        self.new('15_PLANET_BEARING_'+planetBearingName,(.37,.39,.42),f'Purchased {planetBearingName}, 8x{2*planetBearingRo:g}x{planetBearingW:g}; two per planet')
        self.annulus(4,planetBearingRo,G0+planetBearingOffset,G0+planetBearingOffset+planetBearingW,'Planet_bearing')
        self.keep(where=[(x,y,z,0) for x,y,_,_ in positions for z in [0,planetBearingStep]])
        self.new('16_PLANET_PIN_METAL',steel,'Hardened8mm planet pin, M4 end fixing omitted from envelope')
        self.annulus(0,4,G0-3,G1+3,'Planet_pin');self.keep(where=[(x,y,0,0) for x,y,_,_ in positions])
        self.new('17_PLANET_SPACERS',al,'Purchased/cut metal spacers, avoid axial clamping through polymer gear')
        for z0,z1,n in [(G0-.5,G0+planetBearingOffset,'Rear'),(G0+planetBearingOffset+planetBearingW,G0+planetBearingOffset+planetBearingStep,'Middle'),(G0+planetBearingOffset+planetBearingStep+planetBearingW,G1+.5,'Front')]:self.annulus(4.1,6,z0,z1,n,False)
        self.keep(where=[(x,y,0,0) for x,y,_,_ in positions])
        self.new('18_CARRIER_REAR_AL',al,f'Aluminium rear carrier,8mm pins on{2*dc:g}mm PCD')
        self.annulus(22,rearro,G0-3,G0-.5,'Carrier_rear');self.holes([(x,y) for x,y,_,_ in positions],4);self.keep()
        self.new('19_CARRIER_FRONT_AL',al,f'Aluminium front carrier;6xPCD{2*boltR:g}mm output interface ASSUMED, offset15deg')
        self.annulus(17,frontro,G1+.5,G1+3.5,'Carrier_front')
        self.holes([(x,y) for x,y,_,_ in positions]+[(boltR*math.cos(math.pi/12+j*math.pi/3),boltR*math.sin(math.pi/12+j*math.pi/3)) for j in range(6)],2.25)
        # Separate8mm pin bores; small output bolt bores above remain2.25mm.
        self.holes([(x,y) for x,y,_,_ in positions],4);self.keep()
        self.new('20_OUTPUT_NEEDLE_HOUSING',steel,f'Steel {needleName} housing;{2*needleRo:g}mm bore, hardened shaft17mm required')
        if bearingZ<G1+.5:self.annulus(needleRo,needleNeckRo,bearingZ,G1+.5,'Needle_neck')
        self.annulus(needleRo,17,G1+.5,bearingEnd,'Needle_outer_hub');self.keep()
        self.new('21_OUTPUT_NEEDLE_'+needleName,(.36,.38,.41),f'Purchased {needleName} envelope; hardened17mm axle race required')
        self.annulus(8.5,needleRo,bearingZ,bearingEnd,'Needle_bearing');self.keep()
        self.new('22_REAR_WHEEL_BEARING_6003',(.36,.38,.41),'Purchased6003 17x35x10 envelope, rear wheel support')
        self.annulus(8.5,17.5,-h-27,-h-17,'Rear_bearing');self.keep()
        self.new('23_TIE_ROD_TUBE_AL',al,'Aluminium8x4.5 tube, four; M4 studs, keep clamping load off polymer')
        self.annulus(2.25,4,-h-12,G0-2,'Tie_tube');self.keep(where=[(tier*math.cos(a),tier*math.sin(a),0,0) for a in tie])
        self.new('24_TIE_STUD_M4',steel,'PurchasedM4 studs/nuts; nominal cylindrical envelope')
        self.annulus(0,2,-h-18,G1+3,'Tie_stud');self.keep(where=[(tier*math.cos(a),tier*math.sin(a),0,0) for a in tie])
        self.new('25_PRINTED_FIXED_CASE',blue,'PETG cold case or qualified PA warm case; metal tie rods carry alignment/preload; temperature limit applies')
        self.annulus(casei,casei+2,-h-12,G0-2,'Printed_fixed_case');self.keep(stl=True)
        self.new('26_PRINTED_COOLING_PLENUM',blue,'Cold PETG external air plenum; frame mounting and fan curves to qualify,2mm clearance to rotating cover')
        self.annulus(23,80,-h-37,-h-35,'Plenum_backplate')
        self.annulus(78,80,-h-37,-h-29,'Plenum_outer_wall')
        self.annulus(23,25,-h-37,-h-29,'Plenum_inner_wall')
        self.holes([(-48,0),(48,0)],23)
        self.keep(stl=True)
        self.new('27_PRESSURE_FAN_ENVELOPE',(.18,.2,.22),'PURCHASED fan package placeholder50x50x20; each >=1.5L/s at60Pa, not a selected fan specification')
        self.begin('Fan_frame');self.poly([(-25,-25),(25,-25),(25,25),(-25,25)]);self.circle(23);self.finish();self.extrude(-h-57,-h-37,'Fan_envelope')
        self.keep(where=[(-48,0,0,0),(48,0,0,0)])
        if p.get('keyed_reaction_collar'):
            self.new('28_REACTION_KEY_5X5',steel,'Steel rectangular key5x5x12; nominal parallel sides, end and fit details pending')
            self.begin('Reaction_key_profile');self.poly([(5.5,-2.5),(10.5,-2.5),(10.5,2.5),(5.5,2.5)]);self.finish();self.extrude(-h-14.75,-h-2.75,'Reaction_key');self.keep()
        # These three metal components are generic donor references. Their
        # dimensions/masses must not be represented as measured Ninebot data.
        self.new('90_DONOR_REAR_COVER_REFERENCE',al,'ASSUMED donor cover/reference replacement; not a verified Ninebot interface')
        self.annulus(17.5,rimro,-h-27,-h-24.5,'Rear_cover_reference')
        self.annulus(17.5,23,-h-27,-h-17,'Bearing_boss_reference')
        vents=[(rad*math.cos((j*30+off)*math.pi/180),rad*math.sin((j*30+off)*math.pi/180)) for rad,off in [(40,0),(65,15)] for j in range(12)]
        self.holes(vents,6.5);self.keep()
        self.new('91_DONOR_RIM_REFERENCE',(.30,.34,.38),f'ASSUMED rim envelope OD{2*rimro:g}/ID{2*rimri:g}; NOT measured Ninebot')
        self.annulus(rimri,rimro,-h-24.5,G1+3.5,'Rim_reference');self.keep()
        self.new('92_DONOR_FRONT_COVER_REFERENCE',al,f'ASSUMED front cover with6xPCD{2*boltR:g}mm adapter; actual interface unknown')
        self.annulus(17.5,rimro,G1+3.5,G1+6,'Front_cover_reference')
        self.holes([(boltR*math.cos(math.pi/12+j*math.pi/3),boltR*math.sin(math.pi/12+j*math.pi/3)) for j in range(6)],2.25);self.keep()
        # End turns are a separate keep-out object, never counted as solid
        # copper mass. Flattening to12mm is a trial target, not measured fit.
        self.new('80_ENDTURN_KEEP_OUT',(.70,.30,.13),'KEEP OUT:12mm formed distributed end turns; wound coupon needed')
        for a,b,n in [(-h-12,-h,'Rear_endturn'),(h,h+12,'Front_endturn')]:self.annulus(31,48.5,a,b,n,False)
        self.keep()
        b=g['slot_bottom_r_mm'];s=g['slot_shoulder_r_mm'];split=g['slot_split_r_mm'];wb=g['slot_bottom_w_mm'];ws=g['slot_shoulder_w_mm'];wm=ws+(wb-ws)*(split-s)/(b-s)
        for ph,col in [('A',(.86,.18,.12)),('B',(.94,.68,.12)),('C',(.15,.35,.88))]:
            self.new('82_WINDING_'+ph+'_ENVELOPE',col,'Slot copper envelope; actual conductor and end-turn mass comes from winding length calculation')
            self.begin('Coil_sides')
            for j in range(24):
                a=2*math.pi*j/24
                if belt(j)[0]==ph:self.poly(profile(a,[(s+.25,ws*.65),(split-.2,wm*.65)]))
                if belt((j-5)%24)[0]==ph:self.poly(profile(a,[(split+.2,wm*.65),(b-.3,wb*.65)]))
            self.finish();self.extrude(-h,h,'Coil_sides',False);self.keep()
        self.new('81_TIRE_REFERENCE',(.12,.13,.14),'REFERENCE ONLY:254mm rolling diameter,70mm assumed tyre width')
        self.annulus(rimro,127,-35,35,'Tire_reference');self.keep()
        # Small cold printable parts are functional fabrication aids.
        self.new('30_PRINTED_COIL_FORMER',blue,'PETG cold forming tool, test12mm end envelope with real insulated wire')
        self.begin('Former_base');self.poly([(-25,-29),(25,-29),(25,29),(-25,29)]);self.finish();self.extrude(0,3,'Former_base')
        self.begin('Former_posts')
        for x in [-g['stack_mm']/2,g['stack_mm']/2]:
            for y in [-23.7,23.7]:self.sk.CreateCircleByRadius(x/1000,y/1000,0,.0025)
        self.finish();self.extrude(3,15,'Former_posts');self.keep(stl=True,include=False)
        self.new('31_PRINTED_BEARING_FIT_COUPON',blue,f'Cold fit coupon{2*planetBearingRo:g}/26mm bearing bores; calibrate shrinkage before gears')
        self.begin('Fit_coupon');self.poly([(-35,-18),(35,-18),(35,18),(-35,18)]);self.finish();self.extrude(0,8,'Coupon')
        self.begin('Bores')
        for x,r in [(-17,planetBearingRo),(17,13)]:self.sk.CreateCircleByRadius(x/1000,0,0,r/1000)
        self.finish();self.cut(30,'Coupon_bores');self.keep(stl=True,include=False)
        return self.assemble_hub()
    def assemble_hub(self):
        self.sw.DocumentVisible(False,1)
        try:
            for path in dict.fromkeys(x[0] for x in self.placements):
                if self.sw.GetOpenDocumentByName(path) is None:
                    e=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0);wr=com.VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
                    if self.sw.OpenDoc6(path,1,1,'',e,wr) is None:raise RuntimeError('Open component:'+path)
        finally:self.sw.DocumentVisible(True,1)
        doc=self.sw.NewDocument(str(TEMPLATES/'gost-assy.asmdot'),0,0,0);mu=call0(self.sw,'GetMathUtility');mu._FlagAsMethod('CreateTransform');components=[]
        for path,name,x,y,z,a in self.placements:
            comp=doc.AddComponent5(path,0,'',False,'',0,0,0)
            if comp is None:raise RuntimeError('Insert:'+name)
            mat=mu.CreateTransform(com.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,[math.cos(a),math.sin(a),0,-math.sin(a),math.cos(a),0,0,0,1,x/1000,y/1000,z/1000,1,0,0,0]))
            comp.Transform2=mat;comp.Select4(False,NULL,False);call0(doc,'FixComponent');doc.ClearSelection2(True);components.append((comp,name))
        call0(doc,'EditRebuild3');doc.ShowNamedView2('*Isometric',7);call0(doc,'ViewZoomtofit2')
        out=self.out/(self.tag+'.SLDASM');doc.SaveAs3(str(out),0,1);doc.SaveAs3(str(self.out/(self.tag+'_COMPLETE.STEP')),0,3)
        for comp,name in components:
            if name.startswith(('80_','81_','90_','91_','92_','25_','26_','27_')):comp.Visible=0
        call0(doc,'GraphicsRedraw2');call0(doc,'ViewZoomtofit2');doc.SaveAs3(str(out),0,1)
        doc.SaveAs3(str(self.out/'P2_INTERNAL.PNG'),0,3)
        (self.out/'cad_audit.json').write_text(json.dumps({'geometry':self.data,'gear':self.gear,'parts':self.audit,'placements':[{'name':n,'x_mm':x,'y_mm':y,'z_mm':z,'angle_rad':a} for _,n,x,y,z,a in self.placements],
          'assembly_components':len(components),'status':'NOMINAL_INSERT; donor interfaces and12mm end-turn target not verified'},indent=2),encoding='utf-8')
        print(str(out),flush=True);return out

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--gear-module',type=float,default=1.6);a=ap.parse_args();Hub(a.gear_module).build_hub()
