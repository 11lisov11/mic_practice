"""Offline-only source package for a complete start-to-first-NIS replay journal."""
import hashlib,json,os,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261118/exact_nis_input_release_r1'
OUT=ROOT/'artifacts/live_bench_20261118/observer_start_history_r1'
NEW=(2026111803,2026111804)
def read(p):return Path(p).read_text(encoding='utf-8-sig')
def write(p,s):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(s,a,b):
 assert s.count(a)==1,(a[:100],s.count(a));return s.replace(a,b,1)
def main():
 assert not OUT.exists(),'Never replace a package or old evidence'
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def copy(src,dst):
   parts=Path(src).relative_to(BASE/folder).parts
   if folder=='libraries' or folder=='nucleo' and parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log','backups'))
 protected={}
 for folder in (BASE,ROOT/'artifacts/live_bench_20261118/nis_exact_source_analysis_r1'):
  for path in folder.rglob('*'):
   if path.is_file() and '__pycache__' not in path.parts:
    protected[path.relative_to(ROOT).as_posix()]=sha(path)
 write(OUT/'preserved_inputs_sha256.json',json.dumps(protected,indent=2)+'\n')
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for path in (OUT/folder).rglob('*'):
   if path.is_file():
    a=read(path);b=a.replace('2026111801',str(NEW[0])).replace('2026111802',str(NEW[1]))
    if a!=b:write(path,b)
 shutil.copy2(ROOT/'tools/observer_start_history.h',OUT/'nucleo/Inc/observer_start_history.h')
 shutil.copy2(ROOT/'tools/observer_start_history_wire.h',OUT/'UNOQ_MOTOR/observer_start_history_wire.h')
 path=OUT/'nucleo/Src/multi_native.c';s=read(path)
 s=once(s,'#include "observer_trace_core.h"','#include "observer_trace_core.h"\n#include "observer_start_history.h"')
 s=once(s,'static od_capture observer_trace;','static od_capture observer_trace;\nstatic nh_capture observer_history;\nint ma_history_packet(uint8_t*p,int off){return nh_packet(&observer_history,p,off);}\nvoid ma_history_sent(void){nh_sent(&observer_history);}')
 s=once(s,'  od_begin(&observer_trace,MIC_NATIVE_BUILD);','  od_begin(&observer_trace,MIC_NATIVE_BUILD);\n  nh_begin(&observer_history,&observer,&model,MIC_NATIVE_BUILD,DWT->CYCCNT,od_fpscr());')
 s=once(s,'    od_freeze(&observer_trace,run_fault);','    od_freeze(&observer_trace,run_fault);\n    nh_freeze(&observer_history,&observer,NH_STOP);')
 s=once(s,'  int fault=mic_observer_step(&observer,&model,input,&noise);',
  '  const uint32_t history_fpscr=od_fpscr();\n  int fault=mic_observer_step(&observer,&model,input,&noise);\n  int history_event=nh_step(&observer_history,&observer,input,window.pair_counts,history_fpscr,fault,window.center,stamp);')
 s=once(s,'  if(!replay_was_latched&&observer_trace.replay_latched)',
  '  if(history_event||(!replay_was_latched&&observer_trace.replay_latched))')
 # Deliberately capture-only: do not silently install the prior stricter
 # publication-policy candidate as part of an instrumentation change.
 write(path,s)
 path=OUT/'nucleo/Inc/multi_native.h';s=read(path)
 write(path,once(s,'void ma_native_service(void);','void ma_native_service(void);\nint ma_history_packet(uint8_t*,int);\nvoid ma_history_sent(void);'))
 path=OUT/'nucleo/Src/main.c';s=read(path)
 s=once(s,'huart1.Init.BaudRate = 115200;','huart1.Init.BaudRate = 921600; /* Paired history release: 43kB/s journal + control headroom. */')
 before='static void uno_link_poll(void) {'
 addition='''/* One nonblocking history enqueue in foreground, after command RX.
 * At least two existing TX slots remain reserved for control replies.
 * No retry loop, no new IRQ or DMA channel, no control timeout changes. */
static void mic_send_start_history(void){
 if(mic_uart_tx.hard_error||(uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U)return;
 uint8_t p[UV3_FRAME];int off=!LL_TIM_IsEnabledAllOutputs(TIM1)&&!uno_link.command_enabled&&mic_last_control_reply_safe_off;
 /* Frozen metadata only OFF, <=50fps; run rows have priority and no delay. */
 static uint32_t last_meta;
 if(ma_history_packet(p,off)){
  if(p[4]==2&&(uint32_t)(HAL_GetTick()-last_meta)<20U)return;
  if(uno_tx_submit(p,UNO_TX_TAG_DIAG)==HAL_OK){ma_history_sent();if(p[4]==2)last_meta=HAL_GetTick();}
 }
}

'''
 s=once(s,before,addition+before)
 # Invoked only after normal RX servicing; a journal never displaces a command.
 s=once(s,'  if (uno_link.command_enabled && !uno_link.softstart_ready) {',
  '  mic_send_start_history();\n  if (uno_link.command_enabled && !uno_link.softstart_ready) {')
 write(path,s)
 path=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(path)
 s=once(s,'#include "observer_trace_wire.h"','#include "observer_trace_wire.h"\n#include "observer_start_history_wire.h"\nstatic nh_receiver g_start_history={};')
 s=once(s,'static const uint32_t NUCLEO_UART_BAUD = 115200;',
  'static const uint32_t NUCLEO_UART_BAUD = 921600;')
 s=once(s,'      if(buf[2]==OD_WIRE){',
  '      if(buf[2]==NH_WIRE){\n        (void)nhr_receive(&g_start_history,buf,g_bp_fw_build,2026111804U);continue;\n      }\n      if(buf[2]==OD_WIRE){')
 # Reuse the existing read-only GET route. A bounded OFF-only page is selected
 # by a separate read-only RPC callback, never a cmd/START extension.
 rpc='''static String rpc_history(uint32_t part,uint32_t page) {
#if USE_ROUTER_BRIDGE
  ScopedControlLock<ControlMutex> owner(g_control_owner);
#endif
  if(g_pwm_enabled||g_pwm_outputs_active||(g_bp_status&BP_STATUS_PWM_ACTIVE))return "ERR RUN";
  if(!g_start_history.complete)return "ERR NOT_COMPLETE";
  const uint8_t*data=nullptr;unsigned size=0;
  if(part==0){data=g_start_history.meta;size=NH_META_BYTES;}
  else if(part==1){data=(const uint8_t*)g_start_history.rows;size=g_start_history.count*NH_ROW;}
  else if(part==2){data=(const uint8_t*)g_start_history.checkpoints;size=(g_start_history.count/16U)*4U;}
  else return "ERR PART";
  const unsigned chunk=192U,offset=page*chunk;
  if(page>1024U||(size?offset>=size:page!=0U))return "ERR PAGE";
  unsigned len=size-offset;if(len>chunk)len=chunk;
  String out;out.reserve(480);out="NH ";out+=String((unsigned long)g_start_history.epoch);
  out+=" ";out+=String(nhr_exact(&g_start_history)?1:0);out+=" ";out+=String((unsigned long)size);out+=" ";
  if(!len)out+="-";
  const char hex[]="0123456789abcdef";
  for(unsigned i=0;i<len;++i){out+=hex[data[offset+i]>>4];out+=hex[data[offset+i]&15];}return out;
}
static bool g_history_route_ready=false;

'''
 s=once(s,'static String rpc_get() {',rpc+'static String rpc_get() {')
 s=once(s,'  s.reserve(16384);','  s.reserve(16384);\n  s+="DATA nh_complete=";s+=String(g_start_history.complete?1:0);\n  s+=" nh_exact=";s+=String(nhr_exact(&g_start_history)?1:0);\n  s+=" nh_count=";s+=String((unsigned long)g_start_history.count);\n  s+=" nh_bad=";s+=String((unsigned long)g_start_history.bad);s+=" ";')
 # Do not create an additional giant DATA prefix or append a history hex dump.
 s=once(s,'  s += "DATA freq=";','  s += "freq=";')
 s=once(s,'  if (!g_bridge_get_ready) {',
  '  if (!g_history_route_ready)g_history_route_ready=Bridge.provide("history", rpc_history);\n  if (!g_bridge_get_ready) {')
 s=once(s,'    const uint8_t get_result=Bridge.refreshProvided("get");',
  '    const uint8_t get_result=Bridge.refreshProvided("get");\n    if(g_history_route_ready)(void)Bridge.refreshProvided("history");')
 # An owned bridge reconnect requires registering the history route too.
 s=s.replace('    g_bridge_get_ready = false;','    g_bridge_get_ready = false;g_history_route_ready=false;')
 # A global initializer occurs before rpc_history, so its declaration must be
 # beside the receiver rather than adjacent to the later callback.
 s=s.replace('static bool g_history_route_ready=false;\n\n','')
 s=once(s,'static nh_receiver g_start_history={};','static nh_receiver g_start_history={};\nstatic bool g_history_route_ready=false;')
 write(path,s)
 # Existing guards and fast code remain identical apart from firmware IDs.
 old=read(BASE/'nucleo/Src/multi_native.c');new=read(OUT/'nucleo/Src/multi_native.c')
 assert old[old.index('uint16_t ma_native_fast('):].replace('2026111802','2026111804')==new[new.index('uint16_t ma_native_fast('):]
 for f in ('motor_control.h','observer_pair_noise.h','foc_experiment.h','current_adc_window_plan.h','current_adc_deadline.h','local_stop.h','first_break_snapshot.h'):
  assert sha(BASE/'nucleo/Inc'/f)==sha(OUT/'nucleo/Inc'/f),f
 write(OUT/'preparation.json',json.dumps(dict(pair=NEW,installed=False,built=False,hardware_commands=0,
  purpose='All observer inputs from initial reset to first NIS>=25, including warmup; exact ARM state/P reconstruction with checkpoints and final snapshot',
  rows=5120,row_bytes=22,checkpoint_stride=16,uart_baud=921600,
  old_capture_formats_preserved=True,control_and_observer_math_unchanged=True,
  publication_policy_candidate_NOT_included=True,fast_limit_cycles=4000,estimate_age_ms=2,
  target_timing_measured=False,hardware_link_rate_qualified=False),indent=2)+'\n')
 print(json.dumps(dict(prepared=True,pair=NEW,protected_files=len(protected),hardware_commands=0)))
if __name__=='__main__':main()
