"""Allow the existing bounded, frozen-record bus clear only outside a PWM test."""
import json,os,shutil
from pathlib import Path
import prepare_pin_pwm_diag as parent
import prepare_no_switch_diag as p
OLD=parent.OUT;OUT=OLD.with_name('pin_pwm_diag_r2');BUILD=2026102795
def configure():parent.OUT=OUT;parent.BUILD=BUILD
def main():
 OUT.mkdir(exist_ok=False)
 old=json.loads(p.read(OLD/'manifest.json'))
 for rel,h in old['sealed_sha256'].items():assert p.sha(OLD/rel)==h,rel
 def copy(src,dst):
  rel=Path(src).relative_to(OLD/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(OLD/'nucleo',OUT/'nucleo',copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 f=OUT/'nucleo/Src/main.c';s=p.read(f).replace('2026102794','2026102795')
 s=p.once(s,'while(1){mic_pin_poll();mic_encoder_poll();}',
  'while(1){mic_pin_poll();mic_encoder_allow_bus_clear(!mic_pin_active());mic_encoder_poll();}')
 p.write(f,s)
 f=OUT/'nucleo/Inc/pin_pwm_diag.h';s=p.read(f).replace('#include <stdint.h>','#include <stdint.h>\n#include <stdbool.h>')
 s=p.once(s,'void mic_pin_init(void);','bool mic_pin_active(void);\nvoid mic_pin_init(void);');p.write(f,s)
 f=OUT/'nucleo/Src/pin_pwm_diag.c';s=p.read(f).replace('2026102794','2026102795')
 s=p.once(s,'void mic_pin_init(void){','bool mic_pin_active(void){return state==1;}\nvoid mic_pin_init(void){');p.write(f,s)
 for tree in ('build/nucleo','verification','restore','preserved_records'):(OUT/tree).mkdir(parents=True,exist_ok=True)
 shutil.copytree(OLD/'preserved_records',OUT/'preserved_records/earlier',copy_function=os.link)
 for tree in ('build/nucleo','install_r1','idle_first_fault_r1'):
  shutil.copytree(OLD/tree,OUT/'preserved_records/2794'/tree,copy_function=os.link)
 for f in (OLD/'restore').iterdir():shutil.copy2(f,OUT/'restore'/f.name)
 m={k:v for k,v in old.items() if k not in ('sealed_sha256','archived','installation_report')}
 m.update(build=BUILD,built=False,offline_verified=False,installed=False,hardware_tested=False,readback_verified=False,
  hardware_pin_tested=False,AS5600_idle_after_install_ok=False,
  fix='Preserve AS5600 core, enable its existing one-shot idle bus clear after first capture/PE0 observation; disable throughout the whole5s request',
  archived={f.relative_to(OUT/'preserved_records').as_posix():p.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()})
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(prepared=True,build=BUILD,driver_core_unchanged=True)))
if __name__=='__main__':main()
