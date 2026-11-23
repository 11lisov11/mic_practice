"""Prepare 3015/3016 observer diagnostics offline; unchanged actuator equations."""
import json,os,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261030/boot_reset_capture_r1'
OUT=ROOT/'artifacts/live_bench_20261030/observer_trace_r1'
NEW=(2026103015,2026103016)
SOURCE=ROOT/'tools/observer_trace'


def main():
    assert not (OUT/'manifest.json').exists()
    if OUT.exists():assert {p.name for p in OUT.iterdir()}<={'nucleo','UNOQ_MOTOR','libraries','web_hmi'}
    for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        def cp(src,dst):
            rel=os.path.relpath(src,BASE/folder).split(os.sep)
            if folder=='libraries' or folder=='nucleo' and rel[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                if os.path.exists(dst):assert os.path.samefile(src,dst)
                else:os.link(src,dst)
                return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                s=read(f);n=s.replace('2026103013',str(NEW[0])).replace('2026103014',str(NEW[1])).replace('3013-boot-capture','3015-observer-trace')
                if s!=n:write(f,n)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        write(OUT/folder/'observer_trace_wire.h',read(SOURCE/'observer_trace_wire.h'))
    write(OUT/'nucleo/Inc/observer_trace_core.h',read(SOURCE/'observer_trace_core.h'))
    f=OUT/'nucleo/Inc/motor_control.h';s=read(f)
    s=once(s,'uint32_t ccr[3],trigger; uint8_t pair,valid,fault;',
        'uint32_t ccr[3],trigger; uint8_t pair,valid,fault;\n  float id_measured,iq_measured; /* Observational taps of already computed values. */')
    s=once(s,'  out->id_ref=idref;out->iq_ref=iqref;out->omega_est=x[4];out->flux=flux;',
        '  out->id_ref=idref;out->iq_ref=iqref;out->omega_est=x[4];out->flux=flux;\n  out->id_measured=id;out->iq_measured=iq;')
    write(f,s)
    f=OUT/'nucleo/Inc/multi_native.h';s=read(f)
    s=once(s,'void ma_timing_diag(uint8_t*,uint32_t,unsigned);',
        'void ma_timing_diag(uint8_t*,uint32_t,unsigned);\nint ma_observer_trace_packet(uint8_t*,uint32_t,unsigned);')
    write(f,s)
    f=OUT/'nucleo/Src/multi_native.c';s=read(f)
    s=once(s,'#include "foc_experiment.h"','#include "foc_experiment.h"\n#include "observer_trace_core.h"\n#include "observer_trace_wire.h"')
    s=once(s,'void ma_timing_diag(uint8_t*p,uint32_t build,unsigned page){',
        read(SOURCE/'native.inc')+'\nvoid ma_timing_diag(uint8_t*p,uint32_t build,unsigned page){')
    s=once(s,'  ma_estimate_reset(DWT->CYCCNT);\n  sum_va=sum_vb=0;',
        '  ma_estimate_reset(DWT->CYCCNT);\n  od_begin(&observer_trace,MIC_NATIVE_BUILD);\n  bin_id=bin_iq=bin_idref=bin_iqref=bin_reference=0;bin_control_sequence=bin_control_adc_cycles=0;\n  sum_va=sum_vb=0;')
    s=once(s,'    running=0;return;','    od_freeze(&observer_trace,run_fault);\n    running=0;return;')
    s=once(s,'  uint32_t seq=telemetry_seq,stamp=bin_cycles;float va=bin_va,vb=bin_vb;',
        '  uint32_t seq=telemetry_seq,stamp=bin_cycles;float va=bin_va,vb=bin_vb;\n  float trace_id=bin_id,trace_iq=bin_iq,trace_idref=bin_idref,trace_iqref=bin_iqref,trace_ref=bin_reference;\n  uint32_t trace_seq=bin_control_sequence,trace_adc=bin_control_adc_cycles;')
    s=once(s,'  ma_observer_stage=EP_IDLE;\n}',
        '  ma_observer_stage=EP_IDLE;\n  ma_observer_record(&sample,stamp,trace_seq,trace_adc,trace_id,trace_iq,trace_idref,trace_iqref,trace_ref,va,vb,dt,fault,published);\n}')
    s=once(s,'    __DMB();++telemetry_seq;sum_va=sum_vb=0;voltage_n=0;',
        '    bin_id=out.id_measured;bin_iq=out.iq_measured;bin_idref=out.id_ref;bin_iqref=out.iq_ref;bin_reference=reference_hz;\n    bin_control_sequence=sample.sequence;bin_control_adc_cycles=sample.cycles;\n    __DMB();++telemetry_seq;sum_va=sum_vb=0;voltage_n=0;')
    write(f,s)
    f=OUT/'nucleo/Src/main.c';s=read(f)
    anchor='static void mic_send_research_page(uint32_t now_ms) {'
    s=once(s,anchor,'''static void mic_send_observer_page(uint32_t now_ms){
  static uint32_t last_ms;static unsigned page;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||!mic_last_control_reply_safe_off||
      (uint32_t)(now_ms-last_ms)<20U||(uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(ma_observer_trace_packet(packet,MIC_NUCLEO_FW_BUILD_ID,page)&&uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){
    page=(page+1U)%57U;last_ms=now_ms;
  }
}

'''+anchor)
    s=once(s,'      mic_send_boot_page(now_ms);','      mic_send_boot_page(now_ms);mic_send_observer_page(now_ms);')
    write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=once(s,'#include "boot_wire.h"','#include "boot_wire.h"\n#include "observer_trace_wire.h"\nstatic od_receiver g_observer_trace={};')
    s=once(s,'      if(buf[2]==PC_WIRE) {','''      if(buf[2]==OD_WIRE){
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&(g_bp_status&0x22U)==0U&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)odw_receive(&g_observer_trace,buf,g_bp_fw_build,2026103016U,off);continue;
      }
      if(buf[2]==PC_WIRE) {''')
    anchor='      memset(&g_native_boot,0,sizeof(g_native_boot));'
    assert s.count(anchor)==2;s=s.replace(anchor,anchor+'odw_reset(&g_observer_trace);')
    s=once(s,'  s += " mc_adc_peak_hex=";', '''  s += " mc_observer_trace_hex=";
  if(g_observer_trace.complete&&!g_pwm_enabled){
    for(unsigned i=0;i<OD_WIRE_BYTES;++i){s+=break_hex[g_observer_trace.data[i]>>4];s+=break_hex[g_observer_trace.data[i]&15];}
  }else s+="-";
  s+=" mc_observer_trace_complete=";s+=String(g_observer_trace.complete?1:0);
  s+=" mc_observer_trace_good=";s+=String((unsigned long)g_observer_trace.good);
  s+=" mc_observer_trace_bad=";s+=String((unsigned long)g_observer_trace.bad);
  s += " mc_adc_peak_hex=";''')
    write(f,s)
    f=OUT/'web_hmi/server.py';s=read(f)
    s=once(s,'def decode_adc_peak_hex(',read(SOURCE/'web_status.py')+'\n\ndef decode_adc_peak_hex(')
    s=once(s,'data=with_i2c_first_fault(with_zero_history(with_adc_peak(with_shunt_currents(data))))',
        'data=with_observer_trace(with_i2c_first_fault(with_zero_history(with_adc_peak(with_shunt_currents(data)))))')
    s=once(s,'"mc_adc_peak_hex", "mc_zero_history_hex")}',
        '"mc_adc_peak_hex", "mc_zero_history_hex", "mc_observer_trace_hex")}')
    s=once(s,'                "foc_runtime_valid": int(kv.get("foc_runtime_valid","0")),',
        '                **{k:int(kv.get(k,"0")) for k in ("mc_observer_trace_complete","mc_observer_trace_good","mc_observer_trace_bad")},\n                "foc_runtime_valid": int(kv.get("foc_runtime_valid","0")),')
    write(f,s)
    f=OUT/'web_hmi/static/app.js';s=read(f)
    s=once(s,'+ (data.native_boot?.available ? ` · Загрузка Nucleo: ${data.native_boot.summary_ru}` : " · Причина сброса Nucleo: запись пока не получена");',
        '+ (data.native_boot?.available ? ` · Загрузка Nucleo: ${data.native_boot.summary_ru}` : " · Причина сброса Nucleo: запись пока не получена")\n    + (data.observer_trace?.available ? ` · Наблюдатель: ${data.observer_trace.summary_ru}` : "");')
    write(f,s)
    write(OUT/'manifest.json',json.dumps(dict(pair=list(NEW),base_pair=[2026103013,2026103014],
        built=False,installed=False,hardware_commands=0,START=0,CLEAR=0,ARM=0,RESET=0,
        trip_A=1.35,ADC_guard_ticks=2048,estimate_limit_ms=2,fast_budget_cycles=5312,
        frequency_max_hz=5,runlimit_ms=5000,thresholds_changed=False,observer_tuning_changed=False,
        rotor_speed_independently_measured=False,OFF_only_bulk_trace=True,trace_bytes=1696),indent=2)+'\n')
    print('Prepared3015/3016 offline; no hardware access')


if __name__=='__main__':main()
