"""Clone/seal inputs for auxiliary TIM8 logic-edge diagnostic; no hardware IO."""
import json,os,shutil
from pathlib import Path
import prepare_no_switch_diag as p
OLD=p.ROOT/'artifacts/live_bench_20261027/no_switch_diag_r3'
OUT=OLD.with_name('logic_edges_diag_r1');BUILD=2026102793
def normalize_manifest(m):
 for key in ('fix_confirmed_on_hardware_registers','runtime_boot_guard_passed','GPIO_LOW_and_locks_hardware_verified',
   'snapshot_order_fix_hardware_qualified','diagnostic_full_test_passed','diagnostic_requests','hardware_test_report',
   'old_2790_readback_passed_but_boot_guard_failed','old_2790_GPIOMODER','predecessor_diagnostic_build'):
  m.pop(key,None)
 m.update(schema='mic_ai.aux_logic_edges_diag.v1',diagnostic_requests=0,diagnostic_load_requests=0,
  fix='Separate auxiliary TIM8 outputs:2s quiet +3s real edges; original TIM1 motor outputs stay GPIO LOW',
  previous_build=2026102792,predecessor_manifest_sha256=p.sha(OLD/'manifest.json'),
  baseline_evidence={'build':2026102792,'computation5s_passed':True,'new_I2C_errors':0,
   'report':'preserved_records/diagnostic2792/compute5s_r1/report.json'})
 return m
def configure_common():
 p.OUT=OUT;p.BUILD=BUILD;p.RES=OUT/'test_resources';p.identity=lambda s:s.replace('2026102710',str(BUILD));return p
def main():
 assert not (OUT/'nucleo').exists();OUT.mkdir(exist_ok=True)
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
    a=p.read(f);b=a.replace('2026102792',str(BUILD))
    if a!=b:p.write(f,b)
 for name,tree in [('logic_edges.c','Src'),('logic_edges.h','Inc')]:shutil.copy2(p.ROOT/'tools'/name,OUT/'nucleo'/tree/name)
 f=OUT/'nucleo/STM32CubeIDE/.project';s=p.read(f)
 s=p.once(s,'\t<linkedResources>','\t<linkedResources>\n\t\t<link>\n\t\t\t<name>Application/User/logic_edges.c</name>\n\t\t\t<type>1</type>\n\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/logic_edges.c</locationURI>\n\t\t</link>');p.write(f,s)
 f=OUT/'nucleo/Src/load_diag.c';s=p.read(f)
 s=s.replace('COMPUTATION-ONLY IMAGE:','AUXILIARY LOGIC-EDGE IMAGE:')
 s=p.once(s,'#include "load_core.h"','#include "load_core.h"\n#include "logic_edges.h"')
 s=p.once(s,'  return bad;\n}', '  return bad|mic_edges_guard();\n}')
 s=p.once(s,'  ld_init(&core);','  mic_edges_init();\n  ld_init(&core);')
 s=p.once(s,'static void stop_outputs(void){LL_TIM_DisableAllOutputs(TIM1);}',
  'static void stop_outputs(void){LL_TIM_DisableAllOutputs(TIM1);}\nstatic bool tick(uint32_t now,uint32_t bad){\n if(ld_tick(&core,now,bad))return true;\n mic_edges_stop(core.state!=LD_DONE);return false;\n}')
 s=s.replace('ld_tick(&core,','tick(')
 # Keep the wrapper calling the core, rather than recursing into itself.
 s=p.once(s,' if(tick(now,bad))return true;',' if(ld_tick(&core,now,bad))return true;')
 s=p.once(s,'  ++updates;','  if(!mic_edges_update(core.elapsed,core.hz)){(void)tick(DWT->CYCCNT,256U);return;}\n  ++updates;')
 s=p.once(s,'        cleanup_done=0;','        mic_edges_begin();\n        cleanup_done=0;')
 s=p.once(s,'    stop_outputs();LL_TIM_DisableIT_UPDATE(TIM1);','    mic_edges_stop(core.state!=LD_DONE);stop_outputs();LL_TIM_DisableIT_UPDATE(TIM1);')
 s=p.once(s,'  cached_bad=bad;cached_at=now;','  bad|=mic_edges_guard();cached_bad=bad;cached_at=now;')
 p.write(f,s)
 f=OUT/'nucleo/Src/nucleo_encoder.c';s=p.read(f)+'''\n/* Read-only phase-boundary counters: no state reset. */
void mic_encoder_load_counters(uint32_t *reads,uint32_t *errors){
 *reads=enc.reads;*errors=enc.errors;
}
''';p.write(f,s)
 for tree in ('preserved_records','preserved_live','restore'):shutil.copytree(OLD/tree,OUT/tree,copy_function=os.link)
 for tree in ('build/nucleo','install_usb_r1','compute5s_r1'):
  shutil.copytree(OLD/tree,OUT/'preserved_records/diagnostic2792'/tree)
 for tree in ('build/nucleo','verification','test_resources'):(OUT/tree).mkdir(parents=True,exist_ok=True)
 for name in ('core_test.cpp','platform_test.cpp'):shutil.copy2(OLD/'test_resources'/name,OUT/'test_resources'/name)
 for name in ('load_core.h','load_diag.h','logic_edges.h'):shutil.copy2(OUT/'nucleo/Inc'/name,OUT/'test_resources'/name)
 for name in ('load_diag.c','logic_edges.c'):shutil.copy2(OUT/'nucleo/Src'/name,OUT/'test_resources'/name)
 m=dict(old)
 for key in ('sealed_sha256','tool_sha256','installation_report','post_install_preflight'):m.pop(key,None)
 m.update(diagnostic_build=BUILD,built=False,offline_verified=False,installed=False,active=False,readback_verified=False,hardware_tested=False,
  previous_build=2026102792,auxiliary_timer='TIM8: PC6/PC7/PC8 AF4, PD2 BKIN AF4 from PA6; PC9 marker',
  quiet_ms=2000,edge_ms=3000,run_limit_ms=5000,protection_thresholds_unchanged=True,
  limitations=['Three auxiliary logic PWM lines, not the original six motor outputs or their harness',
   'Carrier/duty follow real TIM1 computation; TIM8 carrier phase is independent of ADC/TIM1',
   'Inverter and gate supplies must remain OFF; this test cannot prove powered EMC immunity',
   'Digital Saleae cannot measure analog rise time/ringing', 'AS5600 is stationary; no motor START'],
  preserved_records={str(f.relative_to(OUT/'preserved_records')).replace('\\','/'):p.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()})
 p.write(OUT/'manifest.json',json.dumps(normalize_manifest(m),indent=2)+'\n');print(json.dumps(dict(prepared=True,build=BUILD,hardware_calls=0)))
if __name__=='__main__':main()
