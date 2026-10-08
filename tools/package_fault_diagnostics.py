"""Package diagnostic update images without replacing the older full release."""
import hashlib
import argparse
import json
from pathlib import Path
import shutil
import zipfile
import re


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,default=root/'artifacts/fault_diagnostics_20261007')
    parser.add_argument('--build',type=int,choices=(2026100704,2026100705,2026100706,2026100707,2026100708),default=2026100704)
    parser.add_argument('--nucleo-build',type=int,help='Nucleo ID when the two firmware build IDs differ')
    parser.add_argument('--uno-folder',default='uno_q_final')
    parser.add_argument('--nucleo-folder',default='nucleo_final')
    parser.add_argument('--name',help='single output folder name; no paths')
    args=parser.parse_args()
    artifacts=args.artifacts.resolve()
    evidence=artifacts/'RESULTS.json'
    recorded=json.loads(evidence.read_text(encoding='utf-8'))
    builds={'uno_q':args.build,'nucleo':args.nucleo_build or args.build}
    if recorded.get('installed_builds')!=builds:
        raise RuntimeError('results do not match requested package firmware identities')
    if args.name and not re.fullmatch(r'[a-z0-9_-]+',args.name):
        parser.error('name must be a single lowercase folder name')
    destination=artifacts/(args.name or f'diagnostic_update_{args.build}')
    destination.mkdir(exist_ok=False)
    for kind,folder in (('uno_q',args.uno_folder),('nucleo',args.nucleo_folder)):
        src=artifacts/folder
        manifest=next(src.glob('*.build-manifest.json'))
        expected=args.build if kind=='uno_q' else (args.nucleo_build or args.build)
        if json.loads(manifest.read_text(encoding='utf-8-sig'))['firmware_build_id']!=expected:
            raise RuntimeError('package build does not match artifact: '+str(manifest))
        shutil.copytree(src,destination/kind)
    for name in ('server.py','requirements.txt','flash_unoq_sketch_090.cfg',
                 'static/index.html','static/app.js','static/style.css'):
        target=destination/'linux/web_hmi'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/'web_hmi'/name,target)
    result={'schema':'mic_ai.diagnostic_update.v1','firmware_build_id':args.build,
            'builds':builds,
            'scope':('asynchronous CLEAR diagnostic capture and START flight-recorder update; UART_NE not fixed'
                     if args.build==2026100708 else
                     'diagnostic and UART RX update; V/f unchanged' if args.build==2026100704
                     else 'single-owner bounded V/f ramp, correct current-trip ownership, bus-loss STOP'
                         + ('; zero-frequency STOP and non-extendable run deadline' if args.build>=2026100706 else '')
                         + ('; sustained-break IRQ starvation fix with clean-CLEAR rearm' if args.build==2026100707 else '')
                         + '; no powered motor acceptance'),
            'hardware_readback_performed_by_packager':False,
            'readback_evidence':'RESULTS.json from the connected-stand verification',
            'hv_release_approved':False,'motor_start_validated':False,
            'older_ready_to_flash_package_replaced':False,
            'calibration_reuse':'audited same measurement contract; original points not rewritten',
            'open_checks':['root cause of original HV trip not proven',
                           'diagnose powered UART/I2C failures before another motor trial',
                           'qualified Nucleo phase-current telemetry',
                           'updated loaded-mode and protection timing qualification'],
            'files':[]}
    shutil.copy2(evidence,destination/'RESULTS.json')
    (destination/'README.txt').write_text(
        f'Update {args.build}, not a complete HV release.\n'
        'Verify readback after programming. See RESULTS.json for the recorded connected-stand test.\n'
        'Use nucleo/*.hex through ST-Link and uno_q/*.elf-zsk.bin through the Arduino UNO Q loader.\n'
        'Keep the mains input physically disconnected and DC-link discharged during programming.\n'
        'Linux HMI files preserve the original control credential and Vbus calibration.\n'
        'The main firmware/ready_to_flash package is older; do not use it to overwrite this update.\n'
        'From the repository: tools/capture_fault_diagnostics.py reads Wi-Fi status/logs without commands.\n'
        'tools/wifi_motor_first_start.py permits one guarded V/f trial only after operator readiness.\n'
        'No USB, ST-Link or analyzer wires may remain attached to the energized unisolated stand.\n'
        'Rotation after the RX fix and qualified Nucleo phase-current telemetry are still unverified.\n',encoding='utf-8')
    files=[]
    for file in sorted(destination.rglob('*')):
        if file.is_file():
            files.append({'file':file.relative_to(destination).as_posix(),
                          'bytes':file.stat().st_size,
                          'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
    result['files']=files
    (destination/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    archive=destination.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for file in sorted(destination.rglob('*')):
            if file.is_file(): z.write(file,file.relative_to(destination).as_posix())
    print(json.dumps({'package':str(destination),'archive':str(archive),'files':len(files)},indent=2))


if __name__=='__main__':
    main()
