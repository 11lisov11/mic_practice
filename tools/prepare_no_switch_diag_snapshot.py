"""Fix ISR timestamp/current-clock sampling order without changing age limits."""
import json,os,shutil
from pathlib import Path
import prepare_no_switch_diag as p
OLD=p.ROOT/'artifacts/live_bench_20261027/no_switch_diag_r2'
OUT=OLD.with_name('no_switch_diag_r3');BUILD=2026102792
def main():
 assert not OUT.exists();OUT.mkdir()
 old=json.loads(p.read(OLD/'manifest.json'))
 for rel,h in old['sealed_sha256'].items():assert p.sha(OLD/rel)==h,rel
 def copier(src,dst):
  rel=Path(src).relative_to(OLD/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(OLD/'nucleo',OUT/'nucleo',copy_function=copier,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for tree in ('Inc','Src'):
  for f in (OUT/'nucleo'/tree).iterdir():
   if f.is_file():
    a=p.read(f);b=a.replace('2026102791','2026102792')
    if a!=b:p.write(f,b)
 f=OUT/'nucleo/Src/load_diag.c';s=p.read(f)
 s=p.once(s,'static uint32_t ccr_min[3]','static volatile uint32_t guard_adc_stamp,guard_cache_stamp,guard_clock;\nstatic uint32_t ccr_min[3]')
 s=p.once(s,'static uint32_t guard(uint32_t now){\n  uint32_t bad=cached_bad;',
  'static uint32_t guard(void){\n  /* Read ISR-produced timestamps before reading the current clock.\n   * If an ADC IRQ preempts us, its newer timestamp cannot underflow age. */\n  uint32_t bad=cached_bad;\n  const uint32_t seen=adc_seen,adc_stamp=adc_at,cache_stamp=cached_at;\n  const uint32_t now=DWT->CYCCNT;\n  guard_adc_stamp=adc_stamp;guard_cache_stamp=cache_stamp;guard_clock=now;')
 s=p.once(s,'if(!adc_seen || (uint32_t)(now-adc_at)>SystemCoreClock/200U ||\n     (uint32_t)(now-cached_at)>SystemCoreClock/200U)',
  'if(!seen || (uint32_t)(now-adc_stamp)>SystemCoreClock/200U ||\n     (uint32_t)(now-cache_stamp)>SystemCoreClock/200U)')
 s=s.replace('guard(now)','guard()').replace('guard(DWT->CYCCNT)','guard()')
 s=p.once(s,'r[64]=replay_ramp.FrequencyHz;r[65]=(uint32_t)replay.fCalcAngleExecFreqHz;',
  'r[64]=replay_ramp.FrequencyHz;r[65]=(uint32_t)replay.fCalcAngleExecFreqHz;\n  r[66]=guard_adc_stamp;r[67]=guard_cache_stamp;r[68]=guard_clock;')
 p.write(f,s)
 for tree in ('preserved_records','preserved_live','restore'):shutil.copytree(OLD/tree,OUT/tree,copy_function=os.link)
 for tree in ('build/nucleo','install_usb_r1','post_install_preflight_r1','compute5s_r1'):
  shutil.copytree(OLD/tree,OUT/'preserved_records/diagnostic2791'/tree)
 for tree in ('build/nucleo','verification','test_resources'):(OUT/tree).mkdir(parents=True,exist_ok=True)
 for name in ('core_test.cpp','platform_test.cpp'):shutil.copy2(OLD/'test_resources'/name,OUT/'test_resources'/name)
 for name in ('load_core.h','load_diag.h'):shutil.copy2(OUT/'nucleo/Inc'/name,OUT/'test_resources'/name)
 shutil.copy2(OUT/'nucleo/Src/load_diag.c',OUT/'test_resources/load_diag.c')
 f=OUT/'test_resources/platform_test.cpp';s=p.read(f)
 s=p.once(s,'int main(){','''int main(){
 // Model all relevant ISR preemption positions: an IRQ publishes a newer
 // ADC timestamp after the foreground has obtained its old "now" value.
 // The old subtraction falsely exceeds5ms; the actual corrected guard does not.
 reset();
 for(uint32_t start: {1000U,0xfffffff0U})for(unsigned delta=1;delta<=10000;delta++){
  uint32_t old_now=start;adc_at=start+delta;cached_at=start;
  dwt.CYCCNT=start+delta+1;
  test((uint32_t)(old_now-adc_at)>SystemCoreClock/200U);
  test((guard()&LD_ADC_STALE)==0);
 }
 reset();dwt.CYCCNT=1000000;adc_at=149999;cached_at=1000000;
 test(guard()&LD_ADC_STALE); // Genuine5ms+ ADC age still rejected.
 reset();dwt.CYCCNT=1000000;adc_at=1000000;cached_at=149999;
 test(guard()&LD_ADC_STALE); // Genuine5ms+ foreground age still rejected.
''')
 p.write(f,s)
 shutil.copy2(OLD/'verification/host_selftest.json',OUT/'verification/host_selftest.json')
 m=dict(old)
 for key in ('sealed_sha256','tool_sha256','installation_report','post_install_preflight'):m.pop(key,None)
 m.update(diagnostic_build=BUILD,built=False,offline_verified=False,installed=False,active=False,readback_verified=False,hardware_tested=False,
  previous_build=2026102791,fix='Snapshot ISR timestamps before current DWT time; preserve5ms age threshold and all original guards',
  preserved_records={str(f.relative_to(OUT/'preserved_records')).replace('\\','/'):p.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()})
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(prepared=True,build=BUILD,hardware_commands=0)))
def configure_common():
 p.OUT=OUT;p.BUILD=BUILD;p.RES=OUT/'test_resources';p.identity=lambda s:s.replace('2026102710','2026102792');return p
if __name__=='__main__':main()
