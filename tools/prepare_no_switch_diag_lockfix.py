"""Fix only diagnostic GPIO initialization order; preserve the flashed2790."""
import json,os,shutil,hashlib
from pathlib import Path
import prepare_no_switch_diag as common
ROOT=common.ROOT;OLD=common.OUT;OUT=OLD.with_name('no_switch_diag_r2');BUILD=2026102791
def main():
 assert not OUT.exists();OUT.mkdir()
 old=json.loads(common.read(OLD/'manifest.json'))
 for rel,d in old['sealed_sha256'].items():assert common.sha(OLD/rel)==d,rel
 def copier(src,dst):
  rel=Path(src).relative_to(OLD/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(OLD/'nucleo',OUT/'nucleo',copy_function=copier,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for tree in ('Inc','Src'):
  for f in (OUT/'nucleo'/tree).iterdir():
   if f.is_file():
    a=common.read(f);b=a.replace('2026102790','2026102791')
    if a!=b:common.write(f,b)
 f=OUT/'nucleo/Src/load_diag.c';s=common.read(f)
 a=s.index('  /* Independent physical-pin inhibit;');b=s.index('  protection=safety_bits();',a)
 setup=s[a:b];s=s[:a]+s[b:]
 anchor='void mic_load_init(void){'
 setup='void mic_load_prepare_pins(void){\n  stop_outputs();\n'+setup+'}\n'
 s=common.once(s,anchor,setup+anchor);common.write(f,s)
 f=OUT/'nucleo/Inc/load_diag.h';s=common.read(f).replace('void mic_load_init(void);','void mic_load_prepare_pins(void);\nvoid mic_load_init(void);');common.write(f,s)
 f=OUT/'nucleo/Src/main.c';s=common.read(f)
 s=common.once(s,'  MX_MotorControl_Init();','  /* Set phase GPIO LOW before MCSDK permanently locks its configuration. */\n  mic_load_prepare_pins();\n  MX_MotorControl_Init();')
 common.write(f,s)
 for tree in ('preserved_records','preserved_live','restore'):
  shutil.copytree(OLD/tree,OUT/tree,copy_function=os.link)
 # Keep2790 images, initial readback and the observed hardware lock state.
 for tree in ('build/nucleo','install_usb_r1','install_usb_r1_preflash_live'):
  dst=OUT/'preserved_records/diagnostic2790'/tree
  shutil.copytree(OLD/tree,dst,copy_function=shutil.copy2)
 for tree in ('build/nucleo','verification','test_resources'):(OUT/tree).mkdir(parents=True,exist_ok=True)
 for name in ('core_test.cpp','platform_test.cpp'):shutil.copy2(common.RES/name,OUT/'test_resources'/name)
 for name in ('load_core.h','load_diag.h'):shutil.copy2(OUT/'nucleo/Inc'/name,OUT/'test_resources'/name)
 shutil.copy2(OUT/'nucleo/Src/load_diag.c',OUT/'test_resources/load_diag.c')
 f=OUT/'test_resources/platform_test.cpp';s=common.read(f)
 s=s.replace('struct GPIO {uint32_t MODER=0,ODR=0,IDR=0;};','struct GPIO {uint32_t MODER=0,ODR=0,IDR=0,LCKR=0;};')
 s=common.once(s,'if(q->Pin&(1U<<i))g->MODER=', 'if((q->Pin&(1U<<i))&&!(g->LCKR&(1U<<i)))g->MODER=')
 s=common.once(s,' mic_load_init();dwt.CYCCNT=100;',
  ' mic_load_prepare_pins();pa.LCKR=0x107c2;pb.LCKR=0x10003;\n mic_load_init();dwt.CYCCNT=100;')
 # A hardware-lock model reproduces2790 rejection; the early configuration
 # then passes without clearing a single lock bit or changing the guards.
 s=common.once(s,' reset();test(core.state==LD_IDLE);',
  ' reset();pa.MODER=(pa.MODER&~mode_mask(pa_mask()))|(2U*output_mode(pa_mask()));\n'
  ' pb.MODER=(pb.MODER&~mode_mask(pb_mask()))|(2U*output_mode(pb_mask()));\n'
  ' mic_load_prepare_pins();mic_load_init();request();\n'
  ' test(!pins_low());test(core.state==LD_DENIED&&(core.reason&LD_CONFIG));\n'
  ' test(pa.LCKR==0x107c2&&pb.LCKR==0x10003);\n'
  ' reset();test(core.state==LD_IDLE);')
 common.write(f,s)
 # The orchestration is unchanged; its existing mocked-host proof is retained.
 shutil.copy2(OLD/'verification/host_selftest.json',OUT/'verification/host_selftest.json')
 result=dict(old)
 for k in ('sealed_sha256','tool_sha256','offline_report'):result.pop(k,None)
 result.update(diagnostic_build=BUILD,built=False,offline_verified=False,installed=False,hardware_tested=False,
  predecessor_diagnostic_build=2026102790,fix='Phase GPIO LOW setup before MX_MotorControl_Init/mc_lock_pins; protection snapshot remains after boot',
  protection_thresholds_unchanged=True,GPIO_lock_not_removed=True,
  preserved_records={str(f.relative_to(OUT/'preserved_records')).replace('\\','/'):common.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()})
 common.write(OUT/'manifest.json',json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(prepared=True,build=BUILD,preserved_files=len(result['preserved_records']),hardware_commands=0)))
def configure_common():
 common.OUT=OUT;common.BUILD=BUILD;common.RES=OUT/'test_resources'
 common.identity=lambda s:s.replace('2026102710','2026102791')
 return common
if __name__=='__main__':main()
