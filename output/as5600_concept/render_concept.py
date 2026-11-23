"""Concept visualisation only; original 3MF mesh is preserved.
Run with Blender --background --python render_concept.py.
All illustrative dimensions are mm. No production fit is implied.
"""
import bpy, math, json, os, sys
from mathutils import Vector

OUT = os.path.dirname(os.path.abspath(__file__))
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 48
scene.cycles.use_denoising = True
scene.render.resolution_x = 1600
scene.render.resolution_y = 1400
scene.render.resolution_percentage = 100
scene.world.color = (.22,.22,.22)
scene.view_settings.view_transform = 'AgX'

def material(name,color,metal=0,rough=.35):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF'); p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Metallic'].default_value=metal; p.inputs['Roughness'].default_value=rough
    return m
base=material('Original user mount — graphite',(.075,.095,.115),0,.48)
orange=material('New bridge — orange polymer',(.95,.23,.035),0,.36)
teal=material('Removable sensor cassette — teal',(.025,.34,.37),0,.32)
steel=material('Steel',(.49,.55,.59),.8,.23)
black=material('Fan polymer',(.022,.029,.034),0,.4)
pcb=material('PCB, illustrative module',(.025,.23,.09),.05,.35)
gold=material('Brass',(.65,.39,.09),.75,.3)
magnet=material('Existing magnet',(.47,.5,.54),.9,.19)
white=material('Backdrop',(.82,.85,.87),0,.7)
jigmat=material('Temporary centering jig',(.86,.73,.29),.05,.4)

def finish(obj,name,mat,bevel=0):
    obj.name=name; obj.data.materials.append(mat)
    if bevel:
        b=obj.modifiers.new('Small edge radius','BEVEL'); b.width=bevel; b.segments=3
        n=obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return obj
def box(name,loc,size,mat,bevel=.5):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object
    o.dimensions=size; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(o,name,mat,bevel)
def cyl(name,loc,r,h,mat,vertices=96,bevel=.25):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=h,location=loc)
    return finish(bpy.context.object,name,mat,bevel)
def boolean(target,cutter):
    m=target.modifiers.new('Cut','BOOLEAN'); m.operation='DIFFERENCE'; m.solver='EXACT'; m.object=cutter
    bpy.context.view_layer.objects.active=target
    bpy.ops.object.modifier_apply(modifier=m.name); bpy.data.objects.remove(cutter,do_unlink=True)
def tube(name,loc,ro,ri,h,mat,bevel=.2):
    o=cyl(name,loc,ro,h,mat,bevel=0)
    c=cyl('cutter',loc,ri,h+4,mat,bevel=0); boolean(o,c)
    if bevel:
        b=o.modifiers.new('Edge radius','BEVEL');b.width=bevel;b.segments=3
        o.modifiers.new('Normals','WEIGHTED_NORMAL')
    return o
def beam(name,a,b,width,thick,mat):
    a=Vector(a);b=Vector(b);mid=(a+b)/2
    o=box(name,mid,((b-a).length,width,thick),mat,.7)
    o.rotation_euler[2]=math.atan2(b.y-a.y,b.x-a.x)
    return o
def bolt(name,x,y,z,r=1.5):
    cyl(name+' shank',(x,y,z-2.5),r,7,steel,32,.1)
    head=cyl(name+' cap',(x,y,z+1.1),r*1.8,2.4,steel,64,.25)
    socket=cyl('hex socket',(x,y,z+2.3),r*.95,1,black,6,0); boolean(head,socket)
    return head
def camera(loc,target,scale):
    bpy.ops.object.camera_add(location=loc); c=bpy.context.object
    c.rotation_euler=(Vector(target)-c.location).to_track_quat('-Z','Y').to_euler()
    c.data.type='ORTHO';c.data.ortho_scale=scale;scene.camera=c
    return c
def area(name,loc,power,size):
    bpy.ops.object.light_add(type='AREA',location=loc); l=bpy.context.object;l.name=name
    l.data.energy=power;l.data.shape='DISK';l.data.size=size
    l.rotation_euler=(Vector((0,0,0))-l.location).to_track_quat('-Z','Y').to_euler()

# Original axis is X. The circular centre is (Y=-5.25, Z=0),
# rather than the centre of its D-shaped bounding box.
data=json.load(open(os.path.join(OUT,'original_mesh.json')))
verts=[(-v[2],v[1]+5.25,v[0]) for v in data['v']]
mesh=bpy.data.meshes.new('Exact mesh from user 3MF');mesh.from_pydata(verts,[],data['f']);mesh.update()
ring=bpy.data.objects.new('ORIGINAL D-shaped mount: R63 / R60, axial width 15',mesh)
bpy.context.collection.objects.link(ring);ring.data.materials.append(base)

floor=box('Ground',(0,0,-70),(2000,2000,2),white,0)
area('Key',(100,-80,240),1500000,180)
area('Fill',(-160,-20,100),900000,150)
area('Rim',(30,180,170),1700000,130)
cam=camera((110,-170,190),(0,2,0),162)
if '--skip-original' not in sys.argv:
    scene.render.filepath=os.path.join(OUT,'01_original_mount.png');bpy.ops.render.render(write_still=True)

# Grey rear motor envelope is illustrative, not inferred from the file.
body=cyl('AIR56 rear motor envelope — illustrative',(0,0,-40),44,62,steel,128,.8)
rear=cyl('Rear end shield — illustrative',(0,0,-7),58.8,6,steel,128,.8)
cut=box('D-flat cutter',(0,-95,-7),(200,91,20),black,0);boolean(rear,cut)
for i in range(18):
    t=2*math.pi*i/18
    rib=box('Motor cooling rib',(45*math.cos(t),45*math.sin(t),-40),(4,7,55),steel,.4)
    rib.rotation_euler[2]=t
shaft=cyl('Shaft, nominal example only',(0,0,10),4,28,steel,64,.15)
fanparts=[]
fanparts.append(cyl('EXISTING fan hub',(0,0,4),12,14,black,96,.6))
fanparts.append(tube('EXISTING fan backplate',(0,0,0),45.5,11,2.5,black,.3))
for i in range(11):
    t=2*math.pi*i/11
    a=(13*math.cos(t),13*math.sin(t),6)
    b=(43*math.cos(t+.18),43*math.sin(t+.18),6)
    fanparts.append(beam('EXISTING fan blade',a,b,2.4,11,black))
existingmag=cyl('EXISTING magnet — nominal D6 x 2 example',(0,0,25),3,2,magnet,96,.1)

bridge=[]
# Three broad saddles wrap the thin original ring. All geometry here is conceptual.
for i,deg in enumerate((90,210,330)):
    t=math.radians(deg);x=61.5*math.cos(t);y=61.5*math.sin(t)
    saddle=box('New broad wrap saddle '+str(i),(x,y,0),(14,10,18),orange,.9)
    saddle.rotation_euler[2]=t+math.pi/2
    # Saddle contains a slot around the actual ring wall.
    c=box('saddle ring slot',(x,y,0),(20,3.6,15.5),orange,0);c.rotation_euler[2]=t+math.pi/2
    boolean(saddle,c)
    bridge.append(saddle)
    standoff=cyl('New standoff '+str(i),(x,y,19.25),4.5,20.5,orange,64,.4);bridge.append(standoff)
    inner=(23.5*math.cos(t),23.5*math.sin(t),32)
    outer=(x,y,32)
    arm=beam('New bridge arm '+str(i),inner,outer,11,6,orange)
    cutter=cyl('XY clearance hole',(x,y,32),3,12,orange,64,0);boolean(arm,cutter);bridge.append(arm)
    # Oversize clearance holes + wide washers allow about +/-1.5 mm XY at assembly.
    bridge.append(tube('Wide M3 washer',(x,y,35.4),5.4,1.65,.8,steel,.1))
    bridge.append(bolt('Bridge clamp '+str(i),x,y,36))
    # Radial saddle clamp is represented by its visible head.
    side=cyl('Saddle clamping screw',(x+5.5*math.cos(t),y+5.5*math.sin(t),0),2.7,2.2,steel,48,.2)
    side.rotation_euler=Vector((math.cos(t),math.sin(t),0)).to_track_quat('Z','Y').to_euler()
    bridge.append(side)
socket=tube('Bridge central precision pilot socket',(0,0,32),25,18.15,6,orange,.4);bridge.append(socket)

cassette_objects_before=set(scene.objects)
cassette=[]
cassette.append(tube('Cassette locating spigot',(0,0,32),18,15.6,5.6,teal,.3))
flange=tube('Cassette keyed flange',(0,0,36.4),23.5,16.2,2.8,teal,.4);cassette.append(flange)
for deg in (30,150,270):
    t=math.radians(deg);x=20.8*math.cos(t);y=20.8*math.sin(t)
    c=cyl('flange bolt cut',(x,y,36.4),1.6,12,teal,32,0);boolean(flange,c)
    cassette.append(bolt('Cassette fixing',x,y,38,1.2))
key=box('Cassette angular key',(18.4,0,33),(2.5,3,5),teal,.3);cassette.append(key)
board=box('AS5600 PCB — 23 x 23 placeholder',(0,0,29.65),(23,23,1.6),pcb,.5);cassette.append(board)
chip=box('AS5600 IC faces the magnet',(0,0,28.15),(4.9,3.9,1.4),black,.18);cassette.append(chip)
for x in (-3,3):
    for y in (-1.905,-.635,.635,1.905):
        cassette.append(box('IC pin',(x,y,28.45),(.9,.4,.45),steel,.08))
for x in (-9,9):
    for y in (-9,9):
        cassette.append(cyl('PCB mounting boss',(x,y,32.3),2.3,3.8,teal,48,.2))
        cassette.append(bolt('PCB fixing',x,y,32.4,.8))
for i in range(4):
    x=(i-1.5)*2.54
    cassette.append(box('Header insulation',(x,9,32),(2.5,2.5,2.8),black,.2))
    cassette.append(box('Header pin',(x,9,35),(.65,.65,4),gold,.1))
for x,y in ((-6,4),(6,-4),(-7,-4)):
    cassette.append(box('Backside passive',(x,y,30.8),(2,1,0.6),black,.1))
cassette=[o for o in scene.objects if o not in cassette_objects_before]

# IC bottom 27.45 minus magnet top 26 = 1.45 mm, illustrative starting gap.
cam.location=(150,-220,220);cam.rotation_euler=(Vector((0,0,4))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.ortho_scale=181
scene.render.filepath=os.path.join(OUT,'02_assembled_geometry.png');bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT,'as5600_assembly_concept.blend'))

# Explode only the sensor cassette. Add removable jig beside the common pilot.
for o in cassette:o.location.z+=43
jig=tube('REMOVABLE shaft centering jig — sleeve',(36,0,57),6.5,4.08,24,jigmat,.2)
jigpilot=tube('REMOVABLE jig common pilot',(36,0,69),18,4.08,6,jigmat,.3)
box('Jig extraction tab',(36,0,74),(29,5,3),jigmat,.5)
cam.location=(180,-250,260);cam.rotation_euler=(Vector((4,0,20))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.ortho_scale=204
scene.render.filepath=os.path.join(OUT,'03_exploded_geometry.png');bpy.ops.render.render(write_still=True)

print('Concept images and Blender scene saved in',OUT)
