"""Build a new, independently reviewable pair; never flash or issue motor commands."""
import json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261029/research_suite_r1'
OUT=ROOT/'artifacts/live_bench_20261029/multi_algorithm_r1'
NEW=(2026102921,2026102922)
def read(p):return p.read_text(encoding='utf-8-sig')
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def once(s,a,b):
    assert s.count(a)==1,(a[:100],s.count(a))
    return s.replace(a,b)
def main():
    assert not OUT.exists(),'Never overwrite a candidate or old evidence'
    for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        def copy(src,dst):
            rel=Path(src).relative_to(BASE/folder)
            if folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
    for folder in ('nucleo/Src','nucleo/Inc','UNOQ_MOTOR'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                a=read(f);b=a.replace('2026102911',str(NEW[0])).replace('2026102912',str(NEW[1]))
                if a!=b:write(f,b)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        write(OUT/folder/'research_wire.h',read(ROOT/'tools/multi_algorithm/research_wire.h'))
    write(OUT/'UNOQ_MOTOR/multi_command.h',read(ROOT/'tools/multi_algorithm/multi_command.h'))
    for src,dst in [('motor_control.h','nucleo/Inc/motor_control.h'),('native.h','nucleo/Inc/multi_native.h'),('native.c','nucleo/Src/multi_native.c')]:
        write(OUT/dst,read(ROOT/'tools/multi_algorithm'/src))
    f=OUT/'nucleo/Src/current_shunt.c';s=read(f)
    s=once(s,'#include "current_shunt.h"','#include "current_shunt.h"\n#include "multi_native.h"')
    anchor='void mic_current_update_epoch(void) {'
    fast='''static volatile ma_current_sample ma_fast_sample;
int mic_current_fast(ma_current_sample*out){
 uint32_t seq=ma_fast_sample.sequence;__DMB();
 out->sequence=seq;out->cycles=ma_fast_sample.cycles;out->epoch=ma_fast_sample.epoch;
 out->valid=ma_fast_sample.valid;out->zero=ma_fast_sample.zero;
 for(unsigned i=0;i<3;i++)out->counts[i]=ma_fast_sample.counts[i];
 __DMB();
 return !(seq&1)&&seq==ma_fast_sample.sequence;
}
static void ma_publish_current(uint32_t cycles,uint32_t epoch,uint8_t eligible,uint16_t a,uint16_t b){
 ++ma_fast_sample.sequence;__DMB();ma_fast_sample.cycles=cycles;ma_fast_sample.epoch=epoch;
 ma_fast_sample.valid=(uint8_t)(eligible&&state.zero_ready&&a>=16&&b>=16&&a<=4079&&b<=4079);
 ma_fast_sample.zero=state.zero_ready;
 for(unsigned i=0;i<3;i++)ma_fast_sample.counts[i]=state.window.last[i];
 __DMB();++ma_fast_sample.sequence;
}

'''
    s=once(s,anchor,fast+anchor)
    s=once(s,'  /* With MOE off MCSDK may mask UPDATE IRQ.',
        '  ma_publish_current(cycles0,epoch0,eligible,a,b);\n  /* With MOE off MCSDK may mask UPDATE IRQ.')
    write(f,s)
    f=OUT/'nucleo/Src/mc_tasks.c';s=read(f)
    s=once(s,'#include "mc_tasks.h"','#include "mc_tasks.h"\n#include "multi_native.h"')
    s=once(s,'  returnValue = ACIM_VF_Controller(pACIM_VF[M1]);',
      '  returnValue = ma_native_selected()==1U ? ACIM_VF_Controller(pACIM_VF[M1]) :\n      ma_native_fast(pACIM_VF[M1]->fFlux_Freq_Hz);')
    write(f,s)
    f=OUT/'nucleo/Src/main.c';s=read(f)
    s=once(s,'#include "research_wire.h"','#include "research_wire.h"\n#include "multi_native.h"')
    s=once(s,'xp_packet(packet,MIC_NUCLEO_FW_BUILD_ID);','ma_native_diag(packet,MIC_NUCLEO_FW_BUILD_ID);')
    # Scalar frame format remains unchanged. New modes use identical Hz/ramp fields.
    s=s.replace('mode == UNO_MODE_SCALAR && frame[5]', '(mode==3U||mode==6U||mode==7U) && frame[5]')
    anchor='  if (!uno_service_fields_are_zero(frame) || (mode == UNO_MODE_SCALAR && !msc_wire_valid(frame))) {'
    s=once(s,anchor,'''  if(mode==8U){
    if(!ma_native_config(frame))uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_SERVICE);
    return;
  }
  const bool motor_mode=mode==3U||mode==6U||mode==7U;
  if (!uno_service_fields_are_zero(frame) || (motor_mode && !msc_wire_valid(frame))) {''')
    s=s.replace('flags != UNO_FLAG_ENABLE || mode != UNO_MODE_SCALAR','flags != UNO_FLAG_ENABLE || !motor_mode')
    anchor='  const uint16_t vbus_v = VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);\n  uno_update_softstart_state(now_ms);'
    s=once(s,anchor,'''  const unsigned algorithm=mode==3U?1U:mode==6U?2U:3U;
  if(!ma_native_request(algorithm)){
    uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_SERVICE);return;
  }
'''+anchor)
    s=once(s,'  uno_link.last_mode = UNO_MODE_SCALAR;','  uno_link.last_mode = mode;')
    anchor='  const MCI_State_t start_state = MC_GetSTMStateMotor1();'
    s=once(s,anchor,anchor+'\n  if(start_state==IDLE && !ma_native_prepare()){\n    uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_SERVICE);return;\n  }')
    s=once(s,'    uno_link_poll();','    uno_link_poll();\n    ma_native_service();')
    write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=once(s,'#include "research_wire.h"','#include "research_wire.h"\n#include "multi_command.h"')
    s=once(s,'static xp_receiver g_research_caps={};','''static xp_receiver g_research_caps={};
static uint8_t g_ma_algorithm=1;
static bool g_ma_pending=false;
static uint8_t g_ma_op,g_ma_index;
static uint32_t g_ma_value;
''')
    # Leave Uno's existing V/f supervisor responsible for stop, ramp, and deadlines;
    # the real native algorithm is explicit in both wire mode and diagnostics.
    s=once(s,'    if (mcsdk_scalar) {\n      mode = BP_MODE_SCALAR;','    if (mcsdk_scalar) {\n      mode = ma_wire_mode(g_ma_algorithm);')
    s=once(s,'  } else if (mode == BP_MODE_SCALAR) {','  } else if (mode == BP_MODE_SCALAR || mode==6U || mode==7U) {')
    s=once(s,'  uv3_seal(pkt);\n  g_bp_cmd_mode = mode;','''  if(g_ma_pending && ma_config_allowed(enable_eff,estop_eff,clear_eff,force,g_state==STATE_SAFE)){
    ma_config_encode(pkt,g_ma_op,g_ma_index,g_ma_value);mode=8;g_ma_pending=false;
  }
  uv3_seal(pkt);
  g_bp_cmd_mode = mode;''')
    s=once(s,'static void hard_stop(bool clear_cmd, bool force_link) {','static void hard_stop(bool clear_cmd, bool force_link) {\n  if(ma_config_cancel(clear_cmd,force_link,g_pwm_enabled,g_start_req,g_state==STATE_SAFE))g_ma_pending=false; // Explicit STOP outranks configuration.')
    s=once(s,'static bool manual_command(const char *cmd) {','''static bool manual_command(const char *cmd) {
  if(starts_ci(cmd,"SET ALGORITHM ")){
    if(g_pwm_enabled||g_start_req||g_state!=STATE_SAFE||g_ma_pending)return false;
    const char*p=cmd+14;unsigned algo=icmp(p,"VF")?1:icmp(p,"FOC")?2:icmp(p,"ADAPTIVE_PWM")?3:0;
    if(!algo)return false;
    g_ma_algorithm=(uint8_t)algo;g_ma_op=3;g_ma_index=(uint8_t)algo;g_ma_value=0;g_ma_pending=true;
    return true;
  }
  if(starts_ci(cmd,"MODEL ")){
    if(g_pwm_enabled||g_start_req||g_state!=STATE_SAFE||g_ma_pending)return false;
    unsigned op=0,index=0;unsigned long raw=0;char tail;
    if(sscanf(cmd+6,"%u %u %lx %c",&op,&index,&raw,&tail)!=3||op<1||op>2||index>12)return false;
    g_ma_op=(uint8_t)op;g_ma_index=(uint8_t)index;g_ma_value=(uint32_t)raw;g_ma_pending=true;return true;
  }
''')
    s=s.replace('starts_ci(cmd, "CONTROL HEARTBEAT") || starts_ci(cmd, "SET RUNMODE") ||',
       'starts_ci(cmd,"SET ALGORITHM ") || starts_ci(cmd,"MODEL ") ||\n        starts_ci(cmd, "CONTROL HEARTBEAT") || starts_ci(cmd, "SET RUNMODE") ||')
    s=once(s,'  // Sensor is observational in scalar mode; no local bus handover exists.','''  if(g_ma_pending)return "algorithm configuration pending";
  const bool native_fresh=g_bp_mcsdk_telemetry&&(uint32_t)(now_ms-g_bp_last_rsp_ms)<300U;
  if(!xp_fresh(&g_research_caps,native_fresh,now_ms)||g_research_caps.selected!=g_ma_algorithm)
    return "native algorithm acknowledgement missing";
  if(g_ma_algorithm!=1&&(!g_research_caps.profile_ready||g_research_caps.qualification!=7))
    return "FOC requires identified model, amp scale and target timing evidence";
  // Native loop owns current control; AS5600 remains disabled.''')
    s=once(s,'    s += " research_native_bad=";s += String((unsigned long)g_research_caps.bad);','''    s += " research_native_bad=";s += String((unsigned long)g_research_caps.bad);
    s += " algorithm_selected=";s += String((unsigned)g_research_caps.selected);
    s += " algorithm_requested=";s += String((unsigned)g_ma_algorithm);
    s += " algorithm_qualification=";s += String((unsigned)g_research_caps.qualification);
    s += " algorithm_profile_crc=";s += String((unsigned long)g_research_caps.profile_crc);
    s += " algorithm_fast_cycles=";s += String((unsigned long)g_research_caps.fast_cycles);
    s += " algorithm_observer_cycles=";s += String((unsigned long)g_research_caps.observer_cycles);
    s += " algorithm_fault=";s += String((unsigned)g_research_caps.fault);
    s += " rpm_est=";s += String(g_research_caps.rpm_est,2);
    s += " rpm_est_valid=";s += String((unsigned)g_research_caps.estimate_valid);''')
    write(f,s)
    write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.multi_algorithm.v1',pair=list(NEW),base_pair=[2026102911,2026102912],
      built=False,installed=False,readback_verified=False,physical_qualification=False,
      compiled_algorithms=['VF_FIXED','FOC_FIXED','ADAPTIVE_PWM'],as5600_enabled=False,
      thresholds_changed=False,adc_guard_changed=False,archived_captures_modified=False),indent=2))
    print(OUT)
if __name__=='__main__':main()
