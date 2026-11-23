"""Remove global IRQ blackout from current telemetry; no hardware access."""
import json,os,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261029/foc_fast_budget_fix_r1'
OUT=ROOT/'artifacts/live_bench_20261029/foc_update_latency_fix_r1'
NEW=(2026103003,2026103004)

def main():
 assert not OUT.exists()
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='libraries' or (folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full')):os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026103001','2026103003').replace('2026103002','2026103004').replace('3001-fast-budget','3003-update-latency')
    if n!=s:write(f,n)
 header='''#ifndef MIC_CURRENT_SNAPSHOT_H
#define MIC_CURRENT_SNAPSHOT_H
#include "current_core.h"
/* Single ADC-IRQ writer, foreground reader. No interrupt masks or unbounded
 * waits. An interrupted copy is NEVER sent; a busy reader skips this packet. */
#ifndef CM_SNAPSHOT_COPY
#define CM_SNAPSHOT_COPY(dst,src) (*(dst)=*(src))
#endif
#ifndef CM_SNAPSHOT_BARRIER
#define CM_SNAPSHOT_BARRIER() __DMB()
#endif
static inline uint8_t cm_snapshot_read(cm_core*out,const cm_core*source,
                                      const volatile uint32_t*sequence){
 for(unsigned attempt=0;attempt<3;++attempt){
  uint32_t before=*sequence;CM_SNAPSHOT_BARRIER();
  if(before&1U)continue;
  CM_SNAPSHOT_COPY(out,source);CM_SNAPSHOT_BARRIER();
  if(before==*sequence)return 1;
 }
 return 0;
}
#endif
'''
 write(OUT/'nucleo/Inc/current_snapshot.h',header)
 f=OUT/'nucleo/Src/current_shunt.c';s=read(f)
 s=once(s,'static cm_core state;','static cm_core state;\nstatic volatile uint32_t state_sequence;\n#include "current_snapshot.h"')
 s=once(s,'cm_init(&state);nd_init','state_sequence=0;cm_init(&state);nd_init')
 old='''  if(captured_pair<3)cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,
            bus<=20U && both && !lost_sync && early && !active);'''
 new='''  if(captured_pair<3){
    ++state_sequence;__DMB();
    cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,
            bus<=20U && both && !lost_sync && early && !active);
    __DMB();++state_sequence;
  }'''
 s=once(s,old,new)
 s=once(s,'void mic_current_packet(uint8_t *packet,uint8_t detail,uint32_t build) {','uint8_t mic_current_packet(uint8_t *packet,uint8_t detail,uint32_t build) {')
 s=once(s,'uint32_t key=__get_PRIMASK();__disable_irq();copy=state;__set_PRIMASK(key);','if(!cm_snapshot_read(&copy,&state,&state_sequence))return 0;')
 s=once(s,'packet[3]=flags;packet[38]=1;uv3_seal(packet);','packet[3]=flags;packet[38]=1;uv3_seal(packet);return 1;')
 write(f,s)
 f=OUT/'nucleo/Inc/current_shunt.h';write(f,once(read(f),'void mic_current_packet(','uint8_t mic_current_packet('))
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'''  if(slot!=4U || !mic_zero_packet(packet,MIC_NUCLEO_FW_BUILD_ID))
    mic_current_packet(packet,(uint8_t)(slot==0U?1U:slot==2U?2U:0U),MIC_NUCLEO_FW_BUILD_ID);''',
 '''  if(slot!=4U || !mic_zero_packet(packet,MIC_NUCLEO_FW_BUILD_ID)) {
    if(!mic_current_packet(packet,(uint8_t)(slot==0U?1U:slot==2U?2U:0U),MIC_NUCLEO_FW_BUILD_ID))return;
  }''')
 write(f,s)
 write(OUT/'manifest.json',json.dumps(dict(pair=list(NEW),base_pair=[2026103001,2026103002],built=False,installed=False,
  current_model_changed=False,thresholds_changed=False,ADC_windows_changed=False,age_limits_changed=False,
  IRQ_priorities_changed=False,observer_math_changed=False,IRQ_masking_added=False,
  removed_global_IRQ_blackout_bytes=296,exact_historical_blackout_site_not_captured=True,
  hardware_5s_completion_not_yet_proven=True,start_commands=0,clear_commands=0,flash_commands=0),indent=2)+'\n')
 print('Prepared3003/3004 offline; no hardware commands')
if __name__=='__main__':main()
