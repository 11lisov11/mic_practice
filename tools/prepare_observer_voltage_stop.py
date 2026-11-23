"""Offline-only reply-lifecycle/applied-voltage corrections and first-fault evidence."""
import json,os,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
from prepare_cin_sd_diag import sha
from test_foc_update_latency_fix import function
BASE=ROOT/'artifacts/live_bench_20261114/observer_input_epoch_r1'
OUT=ROOT/'artifacts/live_bench_20261114/observer_voltage_stop_r1'
NEW=(2026111405,2026111406)
SOURCE=ROOT/'tools/observer_voltage_stop'


def main():
 assert not (OUT/'manifest.json').exists(),'Never overwrite a prepared release/evidence'
 if OUT.exists():assert {x.name for x in OUT.iterdir()}<={'nucleo','UNOQ_MOTOR','libraries','web_hmi'}
 for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
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
    s=read(f);n=s.replace('2026111403',str(NEW[0])).replace('2026111404',str(NEW[1]))
    if s!=n:write(f,n)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 s=once(s,'''      g_nucleo_superseded.retire(g_nucleo_waiting_seq, g_nucleo_last_send_us);
      g_nucleo_waiting_rsp = false;
''','''      // Still the current request until an actual replacement is transmitted.
      // The50ms cadence may return below; an8ms-old reply remains correlated.
''')
 s=once(s,'if (force && g_nucleo_waiting_rsp) {','if (g_nucleo_waiting_rsp) {')
 # First local stop evidence is independent of native MCSDK's fault snapshot.
 s=once(s,'static uint8_t g_fault = 0;', '''static uint8_t g_fault = 0;
#include "stop_evidence.h"
static StopEvidence g_stop_evidence;
static uint32_t g_stop_origin;''')
 s=once(s,'  const bool outputs_were_active = g_pwm_enabled || g_pwm_outputs_active || g_state != STATE_SAFE;',
 '''  const bool outputs_were_active = g_pwm_enabled || g_pwm_outputs_active || g_state != STATE_SAFE;
  if(outputs_were_active && g_timed_run.active){
    g_stop_evidence.capture(g_stop_origin,millis(),g_timed_run.id,g_fault,g_estop_latched,
      g_bp_status,g_bp_fault_code,g_bp_last_rsp_ms,g_nucleo_last_tx_ms,g_nucleo_waiting_rsp,
      g_nucleo_waiting_seq,g_nucleo_rx_superseded);
  }
  g_stop_origin=0;''')
 s=once(s,'  if (bp_fault_or_timeout(now_ms)) {','  if (bp_fault_or_timeout(now_ms)) {\n    g_stop_origin=StopEvidence::PEER_GUARD;')
 s=once(s,'    g_timed_run.finish(now_ms,TimedRun::LIMIT);','    g_stop_origin=StopEvidence::LIMIT;\n    g_timed_run.finish(now_ms,TimedRun::LIMIT);')
 s=once(s,'static void request_normal_stop() {','static void request_normal_stop() {\n  if(!g_stop_origin)g_stop_origin=StopEvidence::NORMAL_REQUEST;')
 s=once(s,'  s += " bp_fault=";',read(SOURCE/'uno_status.inc')+'\n  s += " bp_fault=";')
 write(f,s);write(OUT/'UNOQ_MOTOR/stop_evidence.h',read(SOURCE/'stop_evidence.h'))

 f=OUT/'nucleo/Inc/motor_control.h';s=read(f)
 s=once(s,'float x[6],p[6][6],nis;','float x[6],p[6][6],nis; float predicted_i[2],innovation[2],innovation_variance[2];')
 s=once(s,'  o->nis=0;','  o->nis=0;\n  o->predicted_i[0]=o->x[0];o->predicted_i[1]=o->x[1];')
 s=once(s,'    if(!isfinite(s)||s<=0)return MA_OBSERVER;',
 '    o->innovation[ch]=e;o->innovation_variance[ch]=s;\n    if(!isfinite(s)||s<=0)return MA_OBSERVER;')
 write(f,s);write(OUT/'nucleo/Inc/observer_applied_voltage.h',read(SOURCE/'observer_applied_voltage.h'))
 f=OUT/'nucleo/Src/multi_native.c';s=read(f)
 s=once(s,'#include "foc_experiment.h"','#include "foc_experiment.h"\n#include "observer_applied_voltage.h"')
 s=once(s,'  ma_output out;\n  /* fe_profile_allowed', '''  ma_output out;
  float applied_a=0,applied_b=0;
  const float actual_ia=ma_amps(sample.counts[0]);
  const float actual_ib=(actual_ia+2.f*ma_amps(sample.counts[1]))*.5773502692f;
  int voltage_fault=ma_applied_voltage(&g,sample.ccr,sample.arr,sample.bus_v,
    actual_ia,actual_ib,&applied_a,&applied_b);
  /* fe_profile_allowed''')
 fast=function(s,'ma_native_fast')
 fixed=once(fast,'  const uint32_t elapsed=DWT->CYCCNT-begin;',
  '  if(!fault && voltage_fault)fault=voltage_fault;\n  const uint32_t elapsed=DWT->CYCCNT-begin;')
 s=once(s,fast,fixed)
 s=once(s,'  sum_va+=out.va;sum_vb+=out.vb;', '''  /* ADC context contains ACTIVE compares, not the CCR preload just written.
   * Retain the same dead-time model; do not invent measured terminal voltage. */
  sum_va+=applied_a;sum_vb+=applied_b;''')
 # Include this extra kernel in the existing OFF timing budget; no budget edit.
 s=once(s,'static volatile int fe_rc;', 'static volatile float fe_applied_a,fe_applied_b;\nstatic volatile int fe_rc;')
 s=once(s,' fe_rc=ma_control(&fe_test_controller', ''' const uint16_t cc[3]={(uint16_t)(fe_test_geometry.arr/2U),(uint16_t)(fe_test_geometry.arr/2U),(uint16_t)(fe_test_geometry.arr/2U)};
 float av,bv;int avrc=ma_applied_voltage(&fe_test_geometry,cc,(uint16_t)fe_test_geometry.arr,
   (uint16_t)fe_test_bus,fe_test_ia,fe_test_ib,&av,&bv);
 fe_applied_a=av;fe_applied_b=bv;
 fe_rc=avrc?avrc:ma_control(&fe_test_controller''')
 # New trace records prediction/residual/S and the actual endpoint CCR context.
 s=once(s,' r.va=va;r.vb=vb;r.dt=dt;', ''' r.va=va;r.vb=vb;r.dt=dt;
 for(unsigned i=0;i<2;++i){r.predicted_i[i]=observer.predicted_i[i];r.innovation[i]=observer.innovation[i];r.innovation_variance[i]=observer.innovation_variance[i];}
 for(unsigned i=0;i<3;++i)r.active_ccr[i]=s->ccr[i];
 r.bus_arr=(uint32_t)s->bus_v|((uint32_t)s->arr<<16);''')
 s=s.replace('p[2]=OD_WIRE;p[3]=1;', 'p[2]=OD_WIRE;p[3]=2;')
 s=once(s,'unsigned len=page==OD_PAGES-1U?16U:', 'unsigned len=page==OD_PAGES-1U?2U:')
 write(f,s)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  s=read(BASE/folder/'observer_trace_wire.h')
  s=s.replace('OD_WIRE_BYTES=1696','OD_WIRE_BYTES=1832').replace('OD_PAGES=57','OD_PAGES=62')
  s=s.replace('?16U:', '?2U:').replace('p[3]!=1','p[3]!=2').replace('data+4)!=1U','data+4)!=2U')
  write(OUT/folder/'observer_trace_wire.h',s)
 f=OUT/'nucleo/Inc/observer_trace_core.h';s=read(f)
 s=s.replace('OD_CAPACITY=16,OD_STRIDE=334,OD_BYTES=1696','OD_CAPACITY=12,OD_STRIDE=455,OD_BYTES=1832')
 s=once(s,' uint32_t observer_fault,published;', ''' uint32_t observer_fault,published;
 float predicted_i[2],innovation[2],innovation_variance[2];
 uint32_t active_ccr[3],bus_arr;''')
 s=s.replace('od_sample_96','od_sample_136').replace('sizeof(od_sample)==96','sizeof(od_sample)==136')
 s=s.replace('od_blob_1696','od_blob_1832').replace('h->schema=1;','h->schema=2;')
 write(f,s)
 f=OUT/'nucleo/Src/main.c';s=read(f);s=once(s,'page=(page+1U)%57U','page=(page+1U)%62U');write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 a=s.index('def decode_observer_trace_hex(');b=s.index('\ndef with_observer_trace(',a)
 s=s[:a]+read(SOURCE/'decoder.py')+'\n'+s[b:]
 s=once(s,'                "run_reason": int(kv.get("run_reason", "0")),',
  '                "run_reason": int(kv.get("run_reason", "0")),\n'+read(SOURCE/'web_fields.inc'))
 s=once(s,'def motor_fault_detail(data: dict) -> str:',
  read(SOURCE/'web_stop_detail.py')+'\n\ndef _native_motor_fault_detail(data: dict) -> str:')
 write(f,s)
 preserved=json.loads(read(BASE/'preserved_capture_hashes.json'))
 for root in (BASE,):
  for f in root.rglob('*'):
   if f.is_file() and f.suffix in ('.json','.jsonl','.bin','.log','.txt','.png'):preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2))
 write(OUT/'manifest.json',json.dumps(dict(pair=NEW,base_pair=[2026111403,2026111404],built=False,installed=False,
   hardware_commands=0,START=0,CLEAR=0,ARM=0,thresholds_changed=False,trip_A=1.35,ADC_guard_ticks=2048,
   estimate_limit_ms=2,fast_budget_cycles=5312,frequency_max_hz=5,runlimit_ms=5000,
   peer_reply_timeout_ms=500,send_cadence_us=50000,reply_guard_us=8000,
   observer_tuning_changed=False,first_fault_trace_schema=2,trace_bytes=1832,
   physical_NIS_root_cause_proven=False,stop_path_reproduction_required=True,
   target_timing_requalification_required=True),indent=2))
 print('Prepared offline candidate',NEW)


if __name__=='__main__':main()
