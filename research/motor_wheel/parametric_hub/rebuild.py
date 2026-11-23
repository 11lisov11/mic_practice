"""One input path for diameter/stack changes: native CAD + FEMM + reports.

--cad-only regenerates geometry fast, with no claim of a new electrical fit.
--reuse-field requires an exactly matching saved FEMM geometry record.
"""
import argparse,json,subprocess,sys,time
from pathlib import Path
from geometry import ROOT,parameters,geometry,package

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--diameter',type=float);ap.add_argument('--length',type=float)
    ap.add_argument('--interactive',action='store_true');ap.add_argument('--cad-only',action='store_true');ap.add_argument('--reuse-field',action='store_true')
    ap.add_argument('--no-cad',action='store_true');v=ap.parse_args();p=parameters()
    if v.interactive:
        print('ACIM HUB P1 — change stator diameter and stack length, millimetres.')
        v.diameter=float(input(f'Stator diameter [110..170, default {p["stator_diameter_mm"]:g}]: ') or p['stator_diameter_mm'])
        v.length=float(input(f'Stack length [20..50, default {p["stack_length_mm"]:g}]: ') or p['stack_length_mm'])
        v.cad_only=(input('Mode: [1] CAD only, [2] CAD + full FEMM calculation (default 1): ') or '1')=='1'
    p=parameters(diameter=v.diameter,length=v.length);g=geometry(p);tag=f'D{p["stator_diameter_mm"]:g}_L{g["active_length_mm"]:g}'
    out=ROOT/tag;out.mkdir(parents=True,exist_ok=True);start=time.time()
    (out/'parameters_used.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
    from drawings import drawings
    if not v.no_cad:
        from solidworks import CAD,call0
        cad=CAD(p,out/'CAD')
        # Never overwrite a user's unsaved edit to a generated CAD document.
        docs=[d for d in (call0(cad.sw,'GetDocuments') or []) if str(call0(d,'GetPathName')).startswith(str(out))]
        for d in docs:
            if call0(d,'GetSaveFlag'):raise RuntimeError('Save and close edited project CAD before regeneration: '+call0(d,'GetTitle'))
        for d in sorted(docs,key=lambda d:0 if str(call0(d,'GetPathName')).lower().endswith('.sldasm') else 1):cad.sw.CloseDoc(call0(d,'GetTitle'))
        assy=cad.build()
        from verify_cad import verify
        verify(assy)
    if v.cad_only:
        drawings({'parameters':p,'geometry':g,'package':package(p,g),'selected':None},out/'drawings')
        (out/'CAD_ONLY_STATUS.txt').write_text('CAD regenerated. Electrical, thermal and winding results must match parameters_used.json; run full calculation after geometry changes.',encoding='utf-8')
    else:
        field=out/'femm'/'linear.json'
        if v.reuse_field and field.exists():
            old=json.loads(field.read_text(encoding='utf-8'))['geometry']
            keys=[k for k in g if k not in ['status','lamination_stack_note']]
            if any(old.get(k)!=g[k] for k in keys):raise RuntimeError('FEMM cache geometry differs. Re-run without --reuse-field.')
        else:
            from femm_run import run
            run(p,out/'femm')
        from engine import calculate
        data=calculate(p,field,out);drawings(data,out/'drawings')
    (out/'last_build.json').write_text(json.dumps({'parameters':p,'elapsed_s':time.time()-start,'CAD_only':v.cad_only,'no_CAD':v.no_cad},indent=2),encoding='utf-8')
    print('Saved:',out)
    if v.interactive:input('Done. Enter to close.')

if __name__=='__main__':main()
