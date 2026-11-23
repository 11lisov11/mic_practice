"""Fix the fixture's foreground/TIM state-vs-MOE snapshot race, not its limits."""
import json,os,shutil
from pathlib import Path
import prepare_combined_io_diag as previous
import prepare_no_switch_diag as p
from audit_production_pwm_filters import function
OLD=previous.OUT;OUT=OLD.with_name('combined_io_diag_r2');BUILD=2026102802
GUARD='''static uint32_t guard(void){
 const uint32_t stamp=cached_at,now=DWT->CYCCNT;
 /* The TIM IRQ publishes phase and MOE together. Snapshot both before an
  * IRQ can turn PRE/LOW into ON/HIGH between two foreground reads.
  * Only three loads are protected; hardware BKIN remains asynchronous. */
 const uint32_t mask=__get_PRIMASK();__disable_irq();
 const uint32_t sampled_state=state,sampled_phase=phase,sampled_bdtr=TIM1->BDTR;
 __set_PRIMASK(mask);
 uint32_t bad=0;
 if(SystemCoreClock!=170000000U)bad|=1;
 if(!pins_ok()||(sampled_bdtr&~TIM_BDTR_MOE)!=protection||TIM1->CCER!=PIN_CC||TIM1->ARR!=5312U)bad|=2;
 if(!(GPIOA->IDR&GPIO_PIN_6)||(TIM1->SR&(TIM_SR_BIF|TIM_SR_B2IF)))bad|=4;
 if(mic_local_stop_blocked())bad|=8;
 if(sampled_state==1 && (uint32_t)(now-stamp)>SystemCoreClock/200U)bad|=16;
 if(sampled_state==1 && sampled_phase>=2 && !(sampled_bdtr&TIM_BDTR_MOE))bad|=32;
 if((sampled_phase<2||sampled_state!=1)&&(sampled_bdtr&TIM_BDTR_MOE))bad|=32;
 return bad|mic_io_guard();
}'''
FINISH='''static void finish(uint32_t why){
 /* A pending TIM IRQ must never see RUN with an intentionally disabled MOE. */
 const uint32_t mask=__get_PRIMASK();__disable_irq();
 LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableIT_UPDATE(TIM1);
 bool record=false;
 if(state==1){stop=DWT->CYCCNT;elapsed=stop-start;reason|=why;state=why?3U:2U;record=true;}
 __set_PRIMASK(mask);
 if(record)counters(6);
}'''
def configure():
 previous.OUT=OUT;previous.BUILD=BUILD
 import prepare_pin_pwm_diag as base
 base.OUT=OUT;base.BUILD=BUILD
def main():
 OUT.mkdir(exist_ok=False);m=json.loads(p.read(OLD/'manifest.json'))
 for rel,h in m['sealed_sha256'].items():assert p.sha(OLD/rel)==h,rel
 def copy(src,dst):
  rel=Path(src).relative_to(OLD/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(OLD/'nucleo',OUT/'nucleo',copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for name in ('Src/main.c','Src/pin_pwm_diag.c','Src/combined_io_diag.c'):
  f=OUT/'nucleo'/name;p.write(f,p.read(f).replace('2026102801','2026102802'))
 f=OUT/'nucleo/Src/pin_pwm_diag.c';s=p.read(f)
 s=p.once(s,function(s,'guard'),GUARD);s=p.once(s,function(s,'finish'),FINISH);p.write(f,s)
 for tree in ('build/nucleo','verification','restore','preserved_records'):(OUT/tree).mkdir(parents=True,exist_ok=True)
 shutil.copytree(OLD/'preserved_records',OUT/'preserved_records/earlier',copy_function=os.link)
 for tree in ('build/nucleo','install_r1','install_r2','preflight_r1','run_r1'):
  shutil.copytree(OLD/tree,OUT/'preserved_records/2801'/tree,copy_function=os.link)
 for f in (OLD/'restore').iterdir():shutil.copy2(f,OUT/'restore'/f.name)
 m={k:v for k,v in m.items() if k not in ('sealed_sha256','archived','installation_report')}
 m.update(build=BUILD,built=False,offline_verified=False,installed=False,hardware_tested=False,readback_verified=False,
  fix='Atomic coherent phase/state/MOE snapshot and atomic terminal state publication; limits/Break/ADC/UART guards unchanged',
  archived={f.relative_to(OUT/'preserved_records').as_posix():p.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()})
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(prepared=True,build=BUILD,hardware_calls=0)))
if __name__=='__main__':main()
