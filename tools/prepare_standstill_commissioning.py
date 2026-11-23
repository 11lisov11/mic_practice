"""Permanent commissioning addition to one multi-algorithm pair; no flashing."""
import json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261029/multi_algorithm_r1'
OUT=ROOT/'artifacts/live_bench_20261029/standstill_commissioning_r1'
NEW=(2026102931,2026102932)
def read(p):return p.read_text(encoding='utf-8-sig')
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def once(s,a,b):
 assert s.count(a)==1,(a[:100],s.count(a));return s.replace(a,b)
def main():
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  assert not (OUT/folder).exists(),'Never overwrite prepared firmware/evidence'
  def copy(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Src','nucleo/Inc','UNOQ_MOTOR'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    a=read(f);b=a.replace('2026102921',str(NEW[0])).replace('2026102922',str(NEW[1]))
    if a!=b:write(f,b)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  write(OUT/folder/'identify_wire.h',read(ROOT/'tools/motor_commissioning/identify_wire.h'))
 write(OUT/'nucleo/Inc/identify_core.h',read(ROOT/'tools/motor_commissioning/identify_core.h'))
 f=OUT/'nucleo/Inc/multi_native.h';s=read(f)
 s=once(s,'uint8_t valid,zero;} ma_current_sample;','uint8_t valid,zero;uint16_t ccr[3],arr,bus_v;} ma_current_sample;')
 s=once(s,'unsigned ma_native_selected(void);','unsigned ma_native_selected(void);\nint ma_native_complete(void);\nvoid ma_id_status(uint8_t*,uint32_t);\nint ma_id_page(uint8_t*,uint32_t,unsigned);')
 write(f,s)
 f=OUT/'nucleo/Src/current_shunt.c';s=read(f)
 s=once(s,' out->valid=ma_fast_sample.valid;out->zero=ma_fast_sample.zero;',
  ' out->valid=ma_fast_sample.valid;out->zero=ma_fast_sample.zero;\n out->arr=ma_fast_sample.arr;out->bus_v=ma_fast_sample.bus_v;\n for(unsigned i=0;i<3;i++)out->ccr[i]=ma_fast_sample.ccr[i];')
 s=once(s,'uint8_t eligible,uint16_t a,uint16_t b){','uint8_t eligible,uint16_t a,uint16_t b,const uint16_t*ccr,uint16_t bus){')
 s=once(s,' ma_fast_sample.zero=state.zero_ready;',' ma_fast_sample.zero=state.zero_ready;ma_fast_sample.arr=(uint16_t)TIM1->ARR;ma_fast_sample.bus_v=bus;\n for(unsigned i=0;i<3;i++)ma_fast_sample.ccr[i]=ccr[i];')
 s=once(s,'ma_publish_current(cycles0,epoch0,eligible,a,b);','ma_publish_current(cycles0,epoch0,eligible,a,b,current_ccr,bus);');write(f,s)
 f=OUT/'nucleo/Src/multi_native.c';s=read(f).replace('#pragma GCC optimize (\"O2\")','#pragma GCC optimize (\"O2\",\"no-fast-math\")')
 declarations='''
#include "identify_core.h"
#include "identify_wire.h"
#define MIC_NATIVE_BUILD 2026102932U
static mi_state id_state;
static mi_config id_config,id_staged;
static uint16_t id_stage_mask;
static uint8_t id_configured;
static int mi_native_prepare(void),mi_native_config(const uint8_t*),mi_native_service(void);
static uint16_t mi_native_fast(void);
'''
 s=once(s,'#include "motor_control.h"','#include "motor_control.h"\n'+declarations)
 s=once(s,'  if(selected==MA_VF)return 1;','  if(selected==MA_VF)return 1;\n  if(selected==4)return mi_native_prepare();')
 s=once(s,'algorithm>MA_ADAPTIVE','algorithm>4')
 s=once(s,'  if(algorithm!=MA_VF&&(!profile_ready||qualification!=7))return 0;',
  '  if(algorithm==4)return id_configured&&!id_state.ready&&!id_state.done;\n  if(algorithm!=MA_VF&&(!profile_ready||qualification!=7))return 0;')
 s=once(s,'  if(op==1){','  if(op>=4)return mi_native_config(f);\n  if(op==1){')
 s=once(s,'index<=MA_ADAPTIVE','index<=4')
 s=once(s,'  const uint32_t now=DWT->CYCCNT;','  if(mi_native_service())return;\n  const uint32_t now=DWT->CYCCNT;')
 s=once(s,'  if(selected==MA_VF)return MC_NO_ERROR;','  if(selected==MA_VF)return MC_NO_ERROR;\n  if(selected==4)return mi_native_fast();')
 s=once(s,'p[2]=0xE4;p[3]=2;','p[2]=0xE4;p[3]=3;')
 s=once(s,'  p[4]=7;p[5]=selected;','  p[4]=15;p[5]=selected;')
 s+='\n'+read(ROOT/'tools/motor_commissioning/native.inc');write(f,s)
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=s.replace('(mode==3U||mode==6U||mode==7U)','(mode==3U||mode==6U||mode==7U||mode==9U)')
 s=once(s,'const bool motor_mode=mode==3U||mode==6U||mode==7U;','const bool motor_mode=mode==3U||mode==6U||mode==7U||mode==9U;')
 s=once(s,'  const unsigned algorithm=mode==3U?1U:mode==6U?2U:3U;',
  '  if(mode==9U&&ma_native_complete()){uno_stop_motor();return;}\n  const unsigned algorithm=mode==3U?1U:mode==6U?2U:mode==7U?3U:4U;')
 sender='''static void mic_send_identification(uint32_t now_ms){
 static uint32_t status_ms,page_ms;static unsigned page;
 if((uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
 uint8_t packet[UV3_FRAME];
 if((uint32_t)(now_ms-status_ms)>=250U){
  ma_id_status(packet,MIC_NUCLEO_FW_BUILD_ID);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)status_ms=now_ms;
 }else if((uint32_t)(now_ms-page_ms)>=20U&&ma_id_page(packet,MIC_NUCLEO_FW_BUILD_ID,page)){
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){page=(page+1U)%70U;page_ms=now_ms;}
 }
}
'''
 s=once(s,'static void mic_send_current_page(uint32_t now_ms) {',sender+'\nstatic void mic_send_current_page(uint32_t now_ms) {')
 s=once(s,'mic_send_research_page(now_ms); }','mic_send_research_page(now_ms);mic_send_identification(now_ms); }');write(f,s)
 # Capability format is extended honestly; existing native measurement units do not change.
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  f=OUT/folder/'research_wire.h';s=read(f).replace('XP_FORMAT=2','XP_FORMAT=3').replace('p[4]==7','p[4]==15').replace('p[5]<=3','p[5]<=4');write(f,s)
 f=OUT/'UNOQ_MOTOR/multi_command.h';s=read(f);s=once(s,'algorithm==3?7:0','algorithm==3?7:algorithm==4?9:0');write(f,s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 s=once(s,'#include "multi_command.h"','''#include "multi_command.h"
#include "identify_wire.h"
static id_meta g_id_meta={};static id_blob g_id_blob={};
static uint8_t g_id_view_page=0;static uint32_t g_id_execute_crc=0,g_id_running_crc=0;
''')
 s=once(s,'  } else if (mode == BP_MODE_SCALAR || mode==6U || mode==7U) {','  } else if (mode == BP_MODE_SCALAR || mode==6U || mode==7U || mode==9U) {')
 s=once(s,'icmp(p,"ADAPTIVE_PWM")?3:0','icmp(p,"ADAPTIVE_PWM")?3:icmp(p,"IDENT")?4:0')
 s=s.replace('starts_ci(cmd,"SET ALGORITHM ") || starts_ci(cmd,"MODEL ") ||','starts_ci(cmd,"IDENT ") || starts_ci(cmd,"SET ALGORITHM ") || starts_ci(cmd,"MODEL ") ||')
 ident_cmd=read(ROOT/'tools/motor_commissioning/uno_commands.inc')
 s=once(s,'static bool manual_command(const char *cmd) {','static bool manual_command(const char *cmd) {\n'+ident_cmd)
 s=once(s,'  if(g_ma_algorithm!=1&&(!g_research_caps.profile_ready||g_research_caps.qualification!=7))', '''  if(g_ma_algorithm==4){
    if(!id_execution_allowed(&g_id_meta,now_ms,g_id_execute_crc,g_manual_scalar_mode,g_run_limit_ms))return "bounded identification authorization required";
  }
  if(g_ma_algorithm!=1&&g_ma_algorithm!=4&&(!g_research_caps.profile_ready||g_research_caps.qualification!=7))''')
 s=once(s,'  if (manual_watchdog_tick()) return;','''  if (manual_watchdog_tick()) return;
  if(g_ma_algorithm==4&&g_pwm_enabled&&g_id_meta.seen&&(uint32_t)(millis()-g_id_meta.seen_ms)<1500U&&
     (g_id_meta.flags&8U)&&g_id_meta.config_crc==g_id_running_crc){request_normal_stop();return;}''')
 s=once(s,'      g_manual_decreasing=false;','      g_manual_decreasing=false;\n      g_id_running_crc=g_id_execute_crc;g_id_execute_crc=0;')
 s=once(s,'if(ma_config_cancel(clear_cmd,force_link,g_pwm_enabled,g_start_req,g_state==STATE_SAFE))g_ma_pending=false;',
  'if(ma_config_cancel(clear_cmd,force_link,g_pwm_enabled,g_start_req,g_state==STATE_SAFE)){g_ma_pending=false;g_id_execute_crc=0;g_id_running_crc=0;}')
 s=once(s,'      if(buf[2]==XP_WIRE){','''      if(buf[2]==ID_STATUS_WIRE||buf[2]==ID_PAGE_WIRE){
        const uint32_t now=millis();const bool fresh=g_bp_mcsdk_telemetry&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        if(buf[2]==ID_STATUS_WIRE)(void)id_receive_status(&g_id_meta,buf,g_bp_fw_build,fresh,now);
        else (void)id_receive_page(&g_id_blob,buf,g_bp_fw_build,fresh);
        continue;
      }
      if(buf[2]==XP_WIRE){''')
 s=once(s,'    s += " rpm_est_valid=";s += String((unsigned)g_research_caps.estimate_valid);',
  '    s += " rpm_est_valid=";s += String((unsigned)g_research_caps.estimate_valid);\n'+read(ROOT/'tools/motor_commissioning/uno_status.inc'))
 write(f,s)
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.standstill_commissioning.v1',pair=list(NEW),base_pair=[2026102921,2026102922],
  built=False,installed=False,physical_qualification=False,thresholds_changed=False,adc_guard_changed=False,
  start_commands=0,archived_captures_modified=False),indent=2))
 print(OUT)
if __name__=='__main__':main()
