"""Prepare two independent Break records offline. No board access."""
import json,os,shutil,re
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
from prepare_cin_sd_diag import sha
BASE=ROOT/'artifacts/live_bench_20261030/boot_reset_capture_r1'
OUT=ROOT/'artifacts/live_bench_20261114/repeat_break_capture_r1'
NEW=(2026111401,2026111402)
SOURCE=ROOT/'tools/repeat_break_capture'

def function(s,name):
 m=re.search(r'\b'+name+r'\([^;{}]*\)\s*\{',s);assert m,name
 pos=s.index('{',m.start());level=1
 while level:pos+=1;level+=(s[pos]=='{')-(s[pos]=='}')
 return s[m.start():pos+1]

def main():
 assert not OUT.exists(),'Never overwrite prepared firmware or evidence'
 for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='libraries' or folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026103013',str(NEW[0])).replace('2026103014',str(NEW[1])).replace('3013-boot-capture','111401-repeat-break')
    if n!=s:write(f,n)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):write(OUT/folder/'repeat_state.h',read(SOURCE/'repeat_state.h'))
 # Preserve the existing wave schema and receiver checks on a separate wire ID.
 wire=read(OUT/'UNOQ_MOTOR/bkin_wave_wire.h')
 wire=wire.replace('BKW','RPW').replace('bkw','rpw').replace('0xD2','0xEC').replace('0xd2','0xEC').replace('MIC_BKIN_WAVE_WIRE_H','MIC_REPEAT_WAVE_WIRE_H')
 assert 'RPW_VERSION=0xEC' in wire.replace(' ','') or 'RPW_VERSION = 0xEC' in wire,wire[:400]
 write(OUT/'UNOQ_MOTOR/repeat_wave_wire.h',wire)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  f=OUT/folder/'break_wire.h';s=read(f)
  s=s.replace('stage[2]','stage[3]').replace('data[2][','data[3][').replace('received_ms[2]','received_ms[3]').replace('complete[2]','complete[3]')
  s=s.replace('kind>1','kind>2');write(f,s)
 f=OUT/'nucleo/Inc/first_break_snapshot.h';s=read(f)
 s=once(s,'void mic_bkin_capture_trigger_from_break(uint32_t tick_ms);','void mic_bkin_capture_trigger_from_break(uint32_t tick_ms);\nvoid mic_repeat_break_irq(uint32_t tick_ms,uint32_t sr);')
 s=once(s,'  mic_break_capture_record(&mic_first_break, tick_ms, sr);','  mic_break_capture_record(&mic_first_break, tick_ms, sr);\n  mic_repeat_break_irq(tick_ms,sr);')
 write(f,s)
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'#include "sd_live_status.h"','#include "sd_live_status.h"\n#include "repeat_state.h"')
 s=once(s,'static bool uno_rearm_break_irq(void) {','static void mic_repeat_capture_arm(uint32_t tick_ms);\nstatic bool uno_rearm_break_irq(void) {')
 s=once(s,'uint32_t mic_bkin_record_crc;','uint32_t mic_bkin_record_crc;\nvolatile rp_state mic_repeat_state;\nuint8_t mic_repeat_wave[320];\nuint32_t mic_repeat_wave_crc;\nvolatile uint32_t mic_repeat_wave_ready;\nstatic bool mic_repeat_active;')
 s=once(s,'volatile mic_break_snapshot_t mic_first_break;','volatile mic_break_snapshot_t mic_first_break;\nvolatile mic_break_snapshot_t mic_after_clear_break;')
 # First and repeat share only the DMA ring, never their frozen evidence.
 s=once(s,'if (mic_bkin_capture_state!=MIC_BKIN_CAPTURED || mic_bkin_record_ready) return;',
   'if (mic_bkin_capture_state!=MIC_BKIN_CAPTURED || (mic_repeat_active?mic_repeat_wave_ready:mic_bkin_record_ready)) return;')
 a=s.index('static void mic_bkin_prepare_record(void)');b=s.index('static void mic_bkin_wave_packet',a)
 chunk=s[a:b]
 chunk=once(chunk,'  const uint32_t h[16]=','  uint8_t *destination=mic_repeat_active?mic_repeat_wave:mic_bkin_record;\n  const uint32_t h[16]=')
 chunk=chunk.replace('memset(mic_bkin_record,0,sizeof(mic_bkin_record));','memset(destination,0,MIC_BKIN_RECORD_BYTES);').replace('mic_bkin_put32(mic_bkin_record+','mic_bkin_put32(destination+')
 chunk=once(chunk,'  mic_bkin_record_crc=uv3_crc32c(mic_bkin_record,MIC_BKIN_RECORD_BYTES);\n  __DMB(); mic_bkin_record_ready=1;',
 '''  const uint32_t crc=uv3_crc32c(destination,MIC_BKIN_RECORD_BYTES);
  if(mic_repeat_active){
    mic_repeat_wave_crc=crc;__DMB();mic_repeat_wave_ready=1;
    mic_repeat_state.state=(mic_after_clear_break.magic==MIC_BREAK_MAGIC &&
      mic_repeat_state.event_tick==mic_bkin_event_tick_ms)?RP_CAPTURED:RP_ERROR;
  }else{mic_bkin_record_crc=crc;__DMB();mic_bkin_record_ready=1;}''')
 s=s[:a]+chunk+s[b:]
 w=function(s,'mic_bkin_wave_packet')
 rw=w.replace('mic_bkin_wave_packet','mic_repeat_wave_packet').replace('MIC_BKIN_WIRE_VERSION','0xECU').replace('mic_bkin_record_crc','mic_repeat_wave_crc').replace('mic_bkin_record','mic_repeat_wave')
 integration=read(SOURCE/'native.inc')
 s=once(s,'static uint16_t uno_speed_ramp_ms(int16_t target) {','static void '+rw+'\n\n'+integration+'\nstatic uint16_t uno_speed_ramp_ms(int16_t target) {')
 s=once(s,'  LL_TIM_EnableIT_BRK(TIM1);','  mic_repeat_capture_arm(HAL_GetTick());\n  LL_TIM_EnableIT_BRK(TIM1);')
 # Keep the diagnostic send rate and OFF eligibility unchanged.
 old=function(s,'mic_send_break_page');new=read(SOURCE/'send_pages.inc').strip()
 s=once(s,old,new)
 s=once(s,'      mic_send_boot_page(now_ms);','      mic_send_repeat_meta(now_ms);\n      mic_send_boot_page(now_ms);')
 write(f,s)
 # UNO has separate reassembly state; repeat packets cannot replace first data.
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 s=once(s,'static bkw_receiver g_bkin_wave;','static bkw_receiver g_bkin_wave;\n#include "repeat_state.h"\n#include "repeat_wave_wire.h"\nstatic rpw_receiver g_repeat_wave;\nstatic uint8_t g_repeat_meta[UV3_FRAME];\nstatic uint32_t g_repeat_meta_ms;\nstatic bool g_repeat_meta_valid;')
 anchor='      memset(&g_native_boot,0,sizeof(g_native_boot));'
 assert s.count(anchor)==2
 s=s.replace(anchor,anchor+'\n      rpw_reset(&g_repeat_wave);g_repeat_meta_valid=false;')
 s=once(s,'      if (buf[2] == BKW_VERSION) {',read(SOURCE/'uno_receive.inc')+'\n      if (buf[2] == BKW_VERSION) {')
 s=once(s,'  for (unsigned kind=0;kind<2;++kind) {',read(SOURCE/'uno_text.inc')+'\n  for (unsigned kind=0;kind<3;++kind) {')
 s=once(s,'s += kind == 0 ? " mc_break0_hex=" : " mc_break1_hex=";','s += kind == 0 ? " mc_break0_hex=" : kind==1 ? " mc_break1_hex=" : " mc_break2_hex=";')
 s=once(s,'s += kind == 0 ? " mc_break0_age_ms=" : " mc_break1_age_ms=";','s += kind == 0 ? " mc_break0_age_ms=" : kind==1 ? " mc_break1_age_ms=" : " mc_break2_age_ms=";')
 # A boot record is additional evidence for discarding previous repeat pages.
 s=once(s,'        (void)mb_receive(&g_native_boot,buf,g_bp_fw_build,fresh,now);continue;',
 '''        const bool prior=g_native_boot.received;
        const uint32_t prior_crc=prior?mb_u32(g_native_boot.packet+30):0;
        if(mb_receive(&g_native_boot,buf,g_bp_fw_build,fresh,now)&&prior&&
           prior_crc!=mb_u32(g_native_boot.packet+30)){rpw_reset(&g_repeat_wave);g_repeat_meta_valid=false;}
        continue;''')
 write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 s=once(s,'    for kind in (0, 1):','    for kind in (0, 1, 2):')
 s=once(s,'"kind": "first_since_boot" if kind == 0 else "first_start_window",','"kind": ("first_since_boot","first_start_window","first_after_CLEAR")[kind],')
 s=once(s,'def bkin_wave_status(data):',read(SOURCE/'web_status.py')+'\n\ndef bkin_wave_status(data):')
 s=once(s,'                **break_wire_status(kv),','''                **break_wire_status(kv),
                **repeat_capture_status(kv),
                **{key:kv.get(key,"-") for key in ("repeat_meta_hex","mc_repeat_wave_hex")},
                **{key:int(kv.get(key,"0")) for key in ("repeat_meta_age_ms","mc_repeat_wave_age_ms","mc_repeat_wave_good","mc_repeat_wave_bad")},''')
 # Add one read-only route while retaining the old /api/bkin-trace semantics.
 s=once(s,'        if parsed.path == "/api/status":',
 '''        if parsed.path == "/api/repeat-break":
            ok,data,err=self.server.app.rpc.get()
            self._send_json({"ok":bool(ok),"data":data.get("repeat_break") if data else None,"error":err or ""},200 if ok else 503)
            return
        if parsed.path == "/api/status":''')
 write(f,s)
 f=OUT/'web_hmi/static/app.js';s=read(f)
 anchor='  d.driveDiagRaw.textContent = String(data.mc_fault_detail || "Нет кода ошибки от контроллера.")'
 s=once(s,anchor,anchor+'\n    + (data.repeat_break?.summary_ru ? ` · ${data.repeat_break.summary_ru}` : "")')
 write(f,s)
 preserved={}
 for folder in (ROOT/'artifacts/live_bench_20261114',BASE/'powered_FOC_boot_capture_20261030_r1'):
  for f in folder.rglob('*'):
   if f.is_file() and OUT not in f.parents and f.suffix in ('.json','.jsonl','.bin','.log','.txt','.png'):
    preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2))
 write(OUT/'manifest.json',json.dumps(dict(pair=NEW,base_pair=[2026103013,2026103014],built=False,installed=False,
   first_wave_immutable=True,repeat_slot_immutable=True,explicit_CLEAR_required=True,auto_CLEAR=False,auto_START=False,
   thresholds_changed=False,current_trip_A=1.35,ADC_guard_ticks=2048,estimate_age_limit_ms=2,fast_budget_cycles=5312,
   sample_rate_hz=5000000,hardware_commands=0),indent=2))
 print('Prepared repeat capture offline',NEW)
if __name__=='__main__':main()
