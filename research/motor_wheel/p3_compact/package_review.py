"""Package only P3 deliverables and the generator dependencies it uses."""
import hashlib,json,zipfile
from calculate import ROOT,P2

def run():
    parent=ROOT.parent;files=[]
    for folder in ['P3_L30_M145','PRINT_KIT_COLD','REVIEW']:
        files += [p for p in (ROOT/folder).rglob('*') if p.is_file() and 'render' not in p.parts and not p.name.startswith('~$')]
    files += [p for p in ROOT.iterdir() if p.is_file() and p.suffix in ['.py','.txt','.json']]
    files += [P2/n for n in ['build_cad.py','model.py','optimise.py','planetary.py','field.py','review.py','inputs.json','SOURCES.txt']]
    files += [p for p in (P2/'C108_L30_G025_R29_CU3/femm').iterdir() if p.suffix in ['.json','.fem','.ans']]
    files += [parent/'parametric_hub'/n for n in ['solidworks.py','geometry.py','parameters.json','verify_cad.py']]
    files += [parent/'design_v1/femm_motor.py',parent/'donor_measurements.json',parent/'CURRENT_RU.txt']
    files=sorted(set(files));manifest={str(p.relative_to(parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files};out=ROOT/'ACIM_P3_REVIEW.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,str(p.relative_to(parent)))
        z.writestr('SHA256_manifest.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(out) as z:
        if z.testzip() is not None:raise RuntimeError('Archive CRC failed')
    print(json.dumps({'zip':str(out),'size_MB':round(out.stat().st_size/1e6,2),'files':len(files),'CRC':'all passed'}))

if __name__=='__main__':run()
