"""Offline builders for the paired921600-baud release. Never flash or query USB."""
import argparse,json,subprocess,shutil
import prepare_start_history_release as p
def correct_uno_manifest():
 path=p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json';m=json.loads(p.read(path))
 assert m['firmware_build_id']==p.NEW[0]
 m.update(transport='Serial1 / D0-D1, 921600 8N1, protocol v0x03; paired observer history release',
  history_rows=5120,history_row_bytes=22,history_RPC='history(part,page), OFF only, 192 binary bytes/page',
  UART_rate_hardware_qualified=False)
 p.write(path,json.dumps(m,indent=2)+'\n')
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('component',choices=('native','uno'));a=ap.parse_args()
 assert not (p.OUT/'release_manifest.json').exists(),'Sealed packages are immutable; prepare a new directory for a rebuild'
 if a.component=='native':
  import build_standstill_timing as b
  b.p=p;b.main()
 else:
  cmd=[shutil.which('pwsh') or 'powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(p.ROOT/'tools/build_unoq_mcsdk_scalar.ps1'),
   '-Sketch',str(p.OUT/'UNOQ_MOTOR'),'-OutputDirectory',str(p.OUT/'build/uno'),'-LibrariesDirectory',str(p.OUT/'libraries')]
  r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf8',errors='replace')
  p.write(p.OUT/'uno_build.log',r.stdout+r.stderr);r.check_returncode();correct_uno_manifest()
if __name__=='__main__':main()
