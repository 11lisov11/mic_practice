"""Offline builders only; never enumerate, reset or flash boards."""
import argparse,json,subprocess,shutil
import prepare_uart_921600_rx as p
def main():
 ap=argparse.ArgumentParser();ap.add_argument('component',choices=('native','uno'));a=ap.parse_args()
 assert not (p.OUT/'release_manifest.json').exists()
 if a.component=='native':
  import build_standstill_timing as b
  b.p=p;b.main()
 else:
  cmd=[shutil.which('pwsh') or 'powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(p.ROOT/'tools/build_unoq_mcsdk_scalar.ps1'),
   '-Sketch',str(p.OUT/'UNOQ_MOTOR'),'-OutputDirectory',str(p.OUT/'build/uno'),'-LibrariesDirectory',str(p.OUT/'libraries')]
  r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf8',errors='replace')
  p.write(p.OUT/'uno_build.log',r.stdout+r.stderr);r.check_returncode()
  path=p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json';m=json.loads(p.read(path))
  m.update(transport='Serial1 D0/D1 921600 8N1; FIFO8 dedicated ISR',UART_hardware_qualified=False)
  p.write(path,json.dumps(m,indent=2)+'\n')
if __name__=='__main__':main()
