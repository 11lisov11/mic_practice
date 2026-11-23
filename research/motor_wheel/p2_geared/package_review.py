"""Bundle the reviewed CAD, estimates, sources and local generator dependencies."""
import hashlib,json,zipfile
from model import ROOT

def run():
    files=[]
    for tag in ['P2_HUB','P2_HUB_SMALL']:
        files += [p for p in (ROOT/tag).rglob('*') if p.is_file() and p.suffix.lower() not in ['.log']]
    files += [p for p in (ROOT/'REVIEW').rglob('*') if p.is_file() and 'render' not in p.parts]
    files += [p for p in ROOT.iterdir() if p.is_file() and p.suffix.lower() in ['.py','.txt','.json']]
    case=ROOT/'C108_L40_G025_R29_CU3'
    for folder in ['femm','femm_refine','femm_launch_hot']:
        files += [p for p in (case/folder).iterdir() if p.suffix.lower() in ['.json','.fem','.ans']]
    parent=ROOT.parent
    files += [parent/'donor_measurements.json']
    files += [parent/'parametric_hub'/n for n in ['solidworks.py','geometry.py','parameters.json','verify_cad.py']]
    files += [parent/'design_v1/femm_motor.py']
    files=sorted(set(files));manifest={str(p.relative_to(parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    path=ROOT/'ACIM_P2_REVIEW.zip'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,str(p.relative_to(parent)))
        z.writestr('SHA256_manifest.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(path) as z:
        bad=z.testzip()
        if bad:raise RuntimeError('Corrupt zip member:'+bad)
    print(json.dumps({'zip':str(path),'MB':round(path.stat().st_size/1e6,2),'files':len(files),'crc':'all passed'}))

if __name__=='__main__':run()
