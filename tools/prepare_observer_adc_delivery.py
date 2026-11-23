"""Offline diagnostic-delivery fix; never replace old sources/captures or actuate."""
import json,os,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
from prepare_cin_sd_diag import sha
from test_foc_update_latency_fix import function
BASE=ROOT/'artifacts/live_bench_20261115/exact_profile_budget_r1'
OUT=ROOT/'artifacts/live_bench_20261116/observer_adc_delivery_r1'
NEW=(2026111601,2026111602)

BULK='''/* Foreground, strictly OFF-only and after RX/command servicing. One bulk
 * frame at a time; keep two queue slots for control replies. Rotate ONLY
 * after an actual enqueue, so unavailable/not-due records cannot consume turns.
 * Independent of the50ms command cadence: cyclic observer pages cannot starve
 * raw ADC, and the diagnostic stream never runs while outputs are enabled. */
static void mic_send_bulk_page(uint32_t now_ms){
 static uint8_t next;
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||
    !mic_last_control_reply_safe_off||
    (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
 for(unsigned attempt=0;attempt<7U;++attempt){
  unsigned slot=(next+attempt)%7U;uint32_t before=mic_uart_tx.head;
  switch(slot){
   case0:mic_send_repeat_meta(now_ms);break;
   case1:mic_send_boot_page(now_ms);break;
   case2:mic_send_observer_page(now_ms);break;
   case3:mic_send_break_page(now_ms);break;
   case4:mic_send_peak_page(now_ms);break;
   case5:mic_send_noise_page(now_ms);break;
   default:mic_send_identification(now_ms);break;
  }
  if(mic_uart_tx.head!=before){next=(uint8_t)((slot+1U)%7U);return;}
 }
}

'''.replace('case0:','case 0:').replace('case1:','case 1:').replace('case2:','case 2:').replace('case3:','case 3:').replace('case4:','case 4:').replace('case5:','case 5:')


def main():
 assert not OUT.exists(),'Never overwrite prepared releases or evidence'
 for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=os.path.relpath(src,BASE/folder).split(os.sep)
   if folder=='libraries' or folder=='nucleo' and rel[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026111503',str(NEW[0])).replace('2026111504',str(NEW[1]))
    if n!=s:write(f,n)
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'static void uno_send_reply(void) {',BULK+'static void uno_send_reply(void) {')
 old='''    if(!LL_TIM_IsEnabledAllOutputs(TIM1)){
      mic_send_repeat_meta(now_ms);
      mic_send_boot_page(now_ms);mic_send_observer_page(now_ms);
      mic_send_break_page(now_ms);mic_send_peak_page(now_ms);
      mic_send_noise_page(now_ms);mic_send_identification(now_ms);
    }'''
 s=once(s,old,'    /* Bulk delivery runs after RX/command processing in uno_link_poll. */')
 poll=function(s,'uno_link_poll');updated=poll[:-1]+'  mic_send_bulk_page(HAL_GetTick());\n}'
 s=once(s,poll,updated);write(f,s)
 # A first loss of previously-valid observer data requests a diagnostic ADC
 # trigger. No NIS/R/Q/state/controller/timing/protection change is made.
 f=OUT/'nucleo/Inc/peak_core.h';s=read(f)
 s=once(s,'PC_PEAK=1, PC_SHORT=2, PC_NO_PEAK=4','PC_PEAK=1, PC_SHORT=2, PC_NO_PEAK=4, PC_OBSERVER=8')
 s=once(s,'uint8_t running,triggered;','uint8_t running,triggered,observer_requested;')
 s=once(s,'static inline void pc_push(','''static inline void pc_request_observer(pc_capture*c){
  if(!c->frozen&&!c->triggered)c->observer_requested=1;
}
static inline void pc_push(''')
 s=once(s,'if(c->after>=PC_POST){pc_freeze(c,now,PC_PEAK);return;}',
 'if(c->after>=PC_POST){pc_freeze(c,now,c->blob.header.flags&PC_OBSERVER?PC_OBSERVER:PC_PEAK);return;}')
 s=once(s,'} else if(active && eligible && magnitude>=PC_THRESHOLD) {',
 '} else if(active && ((eligible && magnitude>=PC_THRESHOLD)||c->observer_requested)) {')
 s=once(s,'c->triggered=1;c->blob.header.trigger_slot=slot;',
 '''c->blob.header.flags=(eligible&&magnitude>=PC_THRESHOLD)?PC_PEAK:PC_OBSERVER;
    c->triggered=1;c->blob.header.trigger_slot=slot;''')
 s=once(s,'c->triggered?(PC_PEAK|PC_SHORT):PC_NO_PEAK',
 'c->triggered?((c->blob.header.flags&PC_OBSERVER?PC_OBSERVER:PC_PEAK)|PC_SHORT):PC_NO_PEAK')
 write(f,s)
 f=OUT/'nucleo/Inc/current_shunt.h';s=read(f)
 s=once(s,'void mic_current_init(void);','void mic_current_init(void);\nvoid mic_current_request_observer_capture(void);');write(f,s)
 f=OUT/'nucleo/Src/current_shunt.c';s=read(f)
 s=once(s,'static uint8_t peak_sealed;', '''static uint8_t peak_sealed;
/* Foreground only requests; ADC IRQ remains sole writer of raw capture. */
static volatile uint8_t peak_observer_request;
void mic_current_request_observer_capture(void){peak_observer_request=1;}
''')
 s=once(s,'    pc_push(&peak,&sample,HAL_GetTick(),active,raw_eligible,mag);',
 '''    if(peak_observer_request){peak_observer_request=0;pc_request_observer(&peak);}
    pc_push(&peak,&sample,HAL_GetTick(),active,raw_eligible,mag);''');write(f,s)
 f=OUT/'nucleo/Src/multi_native.c';s=read(f)
 s=once(s,'#include "multi_native.h"','#include "multi_native.h"\n#include "current_shunt.h"')
 s=once(s,' od_push(&observer_trace,&r);', ''' od_push(&observer_trace,&r);
 /* First validity loss is immutable; request raw ADC around that event.
  * No diagnostic outcome changes observer/control validity or fault gates. */
 if(observer_trace.blob.header.first_loss_present&&
    observer_trace.blob.header.first_loss_step==r.steps&&(r.reasons&OD_NIS))
   mic_current_request_observer_capture();''');write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 s=once(s,'    peak_seen = bool(h[15] & 1)',
 '    peak_seen = bool(h[15] & 1)\n    observer_trigger = bool(h[15] & 8)\n    triggered = peak_seen or observer_trigger')
 s=once(s,"if h[15] & ~7 or (peak_seen and not 0 <= h[8] < 12) or (not peak_seen and h[8] != 65535):",
 "if h[15] & ~15 or (peak_seen and observer_trigger) or (triggered and not 0 <= h[8] < 12) or (not triggered and h[8] != 65535):")
 s=once(s,"is_trigger=peak_seen and slot==h[8]","is_trigger=triggered and slot==h[8]")
 s=once(s,"if peak_seen and (trigger_row is None", "if triggered and (trigger_row is None")
 s=once(s,"peak_seen=peak_seen,post_short=bool(h[15]&2),no_peak=bool(h[15]&4),",
 "peak_seen=peak_seen,observer_validity_trigger=observer_trigger,post_short=bool(h[15]&2),no_peak=bool(h[15]&4),")
 s=once(s,"mc_adc_peak_status=('Захват пика АЦП сохранён' if trace['peak_seen'] else 'Сохранены последние отсчёты: порог пика не достигнут'))",
 "mc_adc_peak_status=('Захват АЦП при отказе достоверности наблюдателя сохранён' if trace['observer_validity_trigger'] else 'Захват пика АЦП сохранён' if trace['peak_seen'] else 'Сохранены последние отсчёты: порог пика не достигнут'))")
 write(f,s)
 preserved=json.loads(read(BASE/'preserved_capture_hashes.json'))
 for f in BASE.rglob('*'):
  if f.is_file() and f.suffix in ('.json','.jsonl','.bin','.log','.txt','.png','.md'):
   preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2)+'\n')
 old=json.loads(read(BASE/'manifest.json'))
 keep=('trip_A','ADC_guard_ticks','estimate_limit_ms','fast_budget_cycles','frequency_max_hz',
       'runlimit_ms','peer_reply_timeout_ms','send_cadence_us','reply_guard_us','CPU_probe_budget_cycles')
 m={k:old[k] for k in keep}
 m.update(pair=list(NEW),base_pair=old['pair'],built=False,installed=False,hardware_commands=0,
     START=0,CLEAR=0,ARM=0,RESET=0,thresholds_changed=False,observer_tuning_changed=False,
     controller_equations_changed=False,OFF_CPU_qualified=False,FOC_start_ready=False,
     target_timing_measured=False,hardware_validated=False,
     observer_physical_root_cause_proven=False,observer_validity_problem_solved=False,
     diagnostic_ADC_first_NIS_loss_trigger=True,OFF_bulk_round_robin=True)
 write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print('Prepared offline diagnostic delivery',NEW)


if __name__=='__main__':main()
