"""Offline native/Uno build components. Never invokes a programmer or bench."""
import argparse,json,subprocess,shutil
import prepare_exact_nis_input_release as p


def main():
    ap=argparse.ArgumentParser();ap.add_argument('component',choices=('native','uno'));args=ap.parse_args()
    assert not (p.OUT/'installation_acceptance.json').exists()
    if args.component=='native':
        import build_standstill_timing as build
        build.p=p;build.main()
    else:
        command=[shutil.which('pwsh') or 'powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(p.ROOT/'tools/build_unoq_mcsdk_scalar.ps1'),
            '-Sketch',str(p.OUT/'UNOQ_MOTOR'),'-OutputDirectory',str(p.OUT/'build/uno'),'-LibrariesDirectory',str(p.OUT/'libraries')]
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
        p.write(p.OUT/'uno_build.log',result.stdout+result.stderr);result.check_returncode()
        print(json.dumps(dict(uno_built=True,firmware=p.NEW[0],hardware_commands=0)))


if __name__=='__main__':main()
