"""Offline1605/1606: CLEAR must not depend on a healthy TX FIFO being empty."""
import json,os,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
from prepare_cin_sd_diag import sha
BASE=ROOT/'artifacts/live_bench_20261116/telemetry_deadline_r1'
OUT=ROOT/'artifacts/live_bench_20261116/clear_recovery_r1'
NEW=(2026111605,2026111606)
SOURCE=ROOT/'tools/clear_recovery'


def main():
    assert not (OUT/'manifest.json').exists(),'Never replace a completed candidate or captures'
    for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
    for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        if (OUT/folder).exists():
            # Resume only this interrupted, not-yet-manifested preparation.
            assert not (OUT/'release').exists() and not (OUT/'verification').exists()
            continue
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
                s=read(f);n=s.replace('2026111603',str(NEW[0])).replace('2026111604',str(NEW[1]))
                if n!=s:write(f,n)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        write(OUT/folder/'clear_recovery_wire.h',read(SOURCE/'clear_recovery_wire.h'))
    f=OUT/'nucleo/Src/main.c';s=read(f)
    s=once(s,'#include "uart_reject_record.h"','#include "uart_reject_record.h"\n#include "clear_recovery_wire.h"')
    old='''  return !mic_uart_tx.hard_error && !mic_uart_tx.active && mic_uart_tx.head==mic_uart_tx.tail;'''
    new='''  /* Healthy in-flight telemetry owns its DMA buffer and may finish normally.
     CLEAR changes no TX buffer/register/counter. Reserve its reply slot, and
     retain hard-error, late-transfer and original wall-clock deadline guards. */
  uno_tx_lock();
  const uint32_t now_ms=HAL_GetTick();
  const bool ready=!mic_uart_tx.hard_error &&
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)<UNO_TX_SLOTS &&
      (!mic_uart_tx.active || (!mic_uart_tx.late_reported &&
       (uint32_t)(now_ms-mic_uart_tx.started_ms)<=UNO_REPLY_TIMEOUT_MS));
  uno_tx_unlock();return ready;'''
    s=once(s,old,new)
    s=once(s,'static void mic_repeat_capture_arm(uint32_t tick_ms);',read(SOURCE/'native.inc')+'\nstatic void mic_repeat_capture_arm(uint32_t tick_ms);')
    s=once(s,'  if (uno_clear_frame_is_safe(frame)) {\n','  if (uno_clear_frame_is_safe(frame)) {\n    mic_clear_diag_begin();\n')
    s=once(s,'uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_TX);return;\n    }\n    uno_link.coast_hold',
        'mic_clear_diag_finish(CC_TX_BLOCKED);\n      uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_TX);return;\n    }\n    uno_link.coast_hold')
    s=once(s,'    if (!uno_rearm_break_irq()) {\n','    if (!uno_rearm_break_irq()) {\n      mic_clear_diag_finish(CC_BREAK_BLOCKED);\n')
    s=once(s,'    (void)MC_AcknowledgeFaultMotor1();','''    /* Do not erase evidence or claim recovery when MCSDK rejects ACK.
       An accepted ACK may leave FAULT_OVER until its scheduler next runs;
       existing START/host guards still require the completed transition. */
    if (uno_mcsdk_fault_present() && !MC_AcknowledgeFaultMotor1()) {
      mic_clear_diag_finish(CC_MCSDK_REJECTED);
      uno_latch_fault_reason(UNO_FAULT_INTERNAL, UNO_DIAG_MCSDK);return;
    }''')
    s=once(s,'    if (mic_local_stop_latched != 0U && !mic_local_stop_clear()) {\n',
        '    if (mic_local_stop_latched != 0U && !mic_local_stop_clear()) {\n      mic_clear_diag_finish(CC_LOCAL_STOP_BLOCKED);\n')
    s=once(s,'    uno_clear_diagnostics();\n    return;','    uno_clear_diagnostics();\n    mic_clear_diag_finish(CC_ACCEPTED);\n    return;')
    # A single extra OFF-only class, under the existing100fps cap and normal-packet priority.
    s=once(s,'attempt<7U','attempt<8U');s=once(s,'(next+attempt)%7U','(next+attempt)%8U')
    s=once(s,'(slot+1U)%7U','(slot+1U)%8U')
    s=once(s,'   default:mic_send_identification(now_ms);break;',
        '   case 6:mic_send_identification(now_ms);break;\n   case 7:mic_send_clear_page(now_ms);break;')
    write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=once(s,'#include "boot_wire.h"','#include "boot_wire.h"\n#include "clear_recovery_wire.h"\nstatic uint8_t g_clear_recovery[UV3_FRAME];static bool g_clear_recovery_seen=false;')
    s=once(s,'    s += " rpc_response_timeouts=";', '''    s += " mc_clear_recovery_hex=";
    if(g_clear_recovery_seen){static const char cc_digits[]="0123456789abcdef";
      for(unsigned i=0;i<UV3_FRAME;++i){s+=cc_digits[g_clear_recovery[i]>>4];s+=cc_digits[g_clear_recovery[i]&15U];}}
    else s+="-";
    s += " rpc_response_timeouts=";''')
    s=once(s,'      if(buf[2]==MB_WIRE){','''      if(buf[2]==CC_WIRE){
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&!(g_bp_status&0x22U)&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        if(off&&cc_valid(buf,g_bp_fw_build)){memcpy(g_clear_recovery,buf,UV3_FRAME);g_clear_recovery_seen=true;}
        continue;
      }
      if(buf[2]==MB_WIRE){''')
    s=s.replace('memset(&g_native_boot,0,sizeof(g_native_boot));odw_reset(&g_observer_trace);',
        'memset(&g_native_boot,0,sizeof(g_native_boot));g_clear_recovery_seen=false;odw_reset(&g_observer_trace);')
    s=once(s,'prior_crc!=mb_u32(g_native_boot.packet+30)){rpw_reset',
        'prior_crc!=mb_u32(g_native_boot.packet+30)){g_clear_recovery_seen=false;rpw_reset')
    write(f,s)
    f=OUT/'web_hmi/server.py';s=read(f)
    s=once(s,'def boot_wire_status(kv):',read(SOURCE/'hmi.inc')+'def boot_wire_status(kv):')
    s=once(s,'                **boot_wire_status(kv),','                **boot_wire_status(kv),\n                **clear_recovery_status(kv),');write(f,s)
    s=once(s,'f"MCSDK_current={masks[0]} MCSDK_occurred={masks[1]} "',
        'f"MCSDK_at_first_current={masks[0]} MCSDK_at_first_occurred={masks[1]} "')
    s=once(s,'                "mc_fault_current_mask":',
        '                "mc_fault_mask_scope": "first_retained_diagnostic",\n                "mc_fault_live_mask_available": False,\n                "mc_fault_current_mask":');write(f,s)
    preserved=json.loads(read(BASE/'FOC_NIS_trial_preservation_r1/before_sha256.json'))
    for folder in ('powered_FOC_NIS_5Hz_r1','powered_FOC_NIS_5Hz_r1_RPC_preflight'):
        for f in (BASE/folder).rglob('*'):
            if f.is_file():preserved[f.relative_to(ROOT).as_posix()]=sha(f)
    for rel,h in preserved.items():assert sha(ROOT/rel)==h,rel
    write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2)+'\n')
    manifest=json.loads(read(BASE/'manifest.json'))
    for k in ('artifacts','verification_reports','RAM_sections','RAM_allocated','RAM_unallocated'):manifest.pop(k,None)
    manifest.update(pair=list(NEW),base_pair=[2026111603,2026111604],built=False,installed=False,
        hardware_commands=0,START=0,CLEAR=0,ARM=0,RESET=0,thresholds_changed=False,
        target_timing_measured=False,OFF_CPU_qualified=False,FOC_start_ready=False,
        target_timing_measured_OFF=False,
        host_tests_passed=False,model_tests_passed=False,qualified=False,
        target_timing_requalification_required=True,hardware_validated=False,
        clear_first_attempt_record=True,clear_healthy_TX_inflight_allowed=True,
        previous_event_exact_reject_stage_proven=False)
    write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    print('Prepared OFF-only candidate',NEW,'preserved',len(preserved))


if __name__=='__main__':main()
