"""Generic3MF geometry plates for Bambu A1; no G-code or printer commands."""
import json,struct,zipfile,xml.etree.ElementTree as ET
from calculate import ROOT
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('',NS)

def mesh(path):
    d=path.read_bytes();n=struct.unpack_from('<I',d,80)[0];vertices=[];lookup={};triangles=[]
    for j in range(n):
        ids=[]
        for k in range(3):
            p=tuple(round(x,5) for x in struct.unpack_from('<3f',d,84+50*j+12+12*k))
            if p not in lookup:lookup[p]=len(vertices);vertices.append(p)
            ids.append(lookup[p])
        triangles.append(ids)
    return vertices,triangles

def plate(name,objects,placements):
    folder=ROOT/'PRINT_KIT_COLD';model=ET.Element('{'+NS+'}model',unit='millimeter');resources=ET.SubElement(model,'{'+NS+'}resources');build=ET.SubElement(model,'{'+NS+'}build')
    for i,file in enumerate(objects,1):
        vertices,tris=mesh(folder/(file+'.STL'));obj=ET.SubElement(resources,'{'+NS+'}object',id=str(i),type='model',name=file);m=ET.SubElement(obj,'{'+NS+'}mesh');vs=ET.SubElement(m,'{'+NS+'}vertices');ts=ET.SubElement(m,'{'+NS+'}triangles')
        for p in vertices:ET.SubElement(vs,'{'+NS+'}vertex',x=str(p[0]),y=str(p[1]),z=str(p[2]))
        for t in tris:ET.SubElement(ts,'{'+NS+'}triangle',v1=str(t[0]),v2=str(t[1]),v3=str(t[2]))
    for obj,x,y in placements:ET.SubElement(build,'{'+NS+'}item',objectid=str(obj),transform=f'1 0 0 0 1 0 0 0 1 {x} {y} 0')
    target=folder/(name+'.3mf')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" Target="/3D/3dmodel.model"/></Relationships>')
        z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
    print(str(target));return target

def run():
    plate('01_FIRST_COIL_AND_FIT',['30_PRINTED_COIL_FORMER','31_PRINTED_BEARING_FIT_COUPON'],[(1,35,35),(2,105,35)])
    plate('02_GEAR_COLD_TRIAL',['13_POLYMER_RING_100T','14_POLYMER_PLANET_40T'],[(1,85,85)]+[(2,215,y) for y in [35,97,159,221]])

if __name__=='__main__':run()
