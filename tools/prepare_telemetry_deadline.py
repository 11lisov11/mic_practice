"""Offline1603/1604: normal telemetry before OFF bulk, unchanged control/guards."""
import json,os,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
from prepare_cin_sd_diag import sha
BASE=ROOT/'artifacts/live_bench_20261116/observer_adc_delivery_r1'
OUT=ROOT/'artifacts/live_bench_20261116/telemetry_deadline_r1'
NEW=(2026111603,2026111604)


def main():
    assert not OUT.exists(),'Never replace earlier sources or captures'
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
                s=read(f);n=s.replace('2026111601',str(NEW[0])).replace('2026111602',str(NEW[1]))
                if n!=s:write(f,n)
    f=OUT/'nucleo/Src/main.c';s=read(f)
    old='''static void mic_send_bulk_page(uint32_t now_ms){
 static uint8_t next;
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||
    !mic_last_control_reply_safe_off||
    (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
 for(unsigned attempt=0;attempt<7U;++attempt){'''
    new='''static void mic_send_bulk_page(uint32_t now_ms){
 static uint8_t next;static uint32_t last_bulk_ms;
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||
    !mic_last_control_reply_safe_off||mic_uart_tx.hard_error)return;
 /* Ordinary telemetry has deadlines too. Retry from foreground as soon as
  * TX has room, not only immediately after the50ms control reply (which may
  * find the queue occupied). Keep the original200ms slot schedule/sequence,
  *100ms research schedule and all receiver freshness/CRC/zero guards. */
 mic_send_current_page(now_ms);
 mic_send_research_page(now_ms);
 /* OFF bulk remains secondary, one frame per invocation and <=100fps.
  * Two slots stay reserved for control. Timers wrap with unsigned arithmetic. */
 if((uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||
    (uint32_t)(now_ms-last_bulk_ms)<10U)return;
 for(unsigned attempt=0;attempt<7U;++attempt){'''
    s=once(s,old,new)
    s=once(s,'if(mic_uart_tx.head!=before){next=(uint8_t)((slot+1U)%7U);return;}',
        'if(mic_uart_tx.head!=before){next=(uint8_t)((slot+1U)%7U);last_bulk_ms=now_ms;return;}')
    write(f,s)
    preserved=json.loads(read(BASE/'preserved_capture_hashes.json'))
    for f in BASE.rglob('*'):
        if f.is_file() and f.suffix in ('.json','.jsonl','.bin','.log','.txt','.png','.md'):
            preserved[f.relative_to(ROOT).as_posix()]=sha(f)
    write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2)+'\n')
    base=json.loads(read(BASE/'manifest.json'))
    keep=('trip_A','ADC_guard_ticks','estimate_limit_ms','fast_budget_cycles','frequency_max_hz',
          'runlimit_ms','peer_reply_timeout_ms','send_cadence_us','reply_guard_us','CPU_probe_budget_cycles',
          'diagnostic_ADC_first_NIS_loss_trigger','OFF_bulk_round_robin')
    m={k:base[k] for k in keep}
    m.update(pair=list(NEW),base_pair=base['pair'],built=False,installed=False,hardware_commands=0,
        START=0,CLEAR=0,ARM=0,RESET=0,thresholds_changed=False,observer_tuning_changed=False,
        controller_equations_changed=False,OFF_CPU_qualified=False,FOC_start_ready=False,
        target_timing_measured=False,hardware_validated=False,ordinary_freshness_guards_changed=False,
        ordinary_OFF_foreground_priority=True,OFF_bulk_max_fps=100,
        observer_validity_problem_solved=False,target_timing_requalification_required=True)
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print('Prepared offline telemetry deadline candidate',NEW)


if __name__=='__main__':main()
