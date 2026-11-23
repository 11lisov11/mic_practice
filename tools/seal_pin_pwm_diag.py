import json,subprocess,shutil,re
import prepare_pin_pwm_diag as prep
import prepare_no_switch_diag as p
from seal_no_switch_diag import GNU
def main():
 c=prep.OUT;v=c/'verification';b=c/'nucleo/STM32CubeIDE/Debug';stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 test=json.loads(p.read(v/'native_tests.json'));assert test['passed']
 m=json.loads(p.read(c/'manifest.json'));bm=json.loads(p.read(b/(stem+'.build-manifest.json')))
 assert bm['firmware_build_id']==prep.BUILD and bm['build_errors']==bm['build_warnings']==0
 for x in bm['artifacts']:assert p.sha(b/x['file'])==x['sha256'].lower()
 for ext in ('.hex','.bin','.elf','.map','.build-manifest.json'):shutil.copy2(b/(stem+ext),c/'build/nucleo'/(stem+ext))
 lines=subprocess.check_output([str(GNU/'arm-none-eabi-nm.exe'),'-S','-n',str(b/(stem+'.elf'))],text=True).splitlines()
 symbols={}
 for line in lines:
  a=line.split()
  if len(a)==4 and a[3] in ('mic_pin_request','mic_pin_report','fault_record','release_probe','bus_clear'):
   addr,size=int(a[0],16),int(a[1],16);assert 0x20000000<=addr<addr+size<=0x20008000;symbols[a[3]]=dict(address=addr,bytes=size)
 assert symbols['mic_pin_report']['bytes']==256 and symbols['mic_pin_request']['bytes']==4 and symbols['fault_record']['bytes']==320
 p.write(v/'symbols.json',json.dumps(symbols,indent=2)+'\n')
 for rel,h in m['archived'].items():assert p.sha(c/'preserved_records'/rel)==h
 m.update(built=True,offline_verified=True,target_errors=0,target_warnings=0,native_checks=test['checks'])
 m['sealed_sha256']={f.relative_to(c).as_posix():p.sha(f) for tree in ('nucleo','build','restore','verification','preserved_records') for f in (c/tree).rglob('*') if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
 p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(ready=True,build=prep.BUILD,hardware_tested=False,archived=len(m['archived']))))
if __name__=='__main__':main()
