"""Fix instantaneous-current publication and add a strictly OFF-only ADC comparison."""
import json
import os
from pathlib import Path
import shutil
from prepare_standstill_commissioning import ROOT, read, write, once

BASE=ROOT/'artifacts/live_bench_20261029/standstill_irq_timing_r1'
OUT=ROOT/'artifacts/live_bench_20261029/standstill_current_noise_r1'
NEW=(2026102939,2026102940)


def main():
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  if (OUT/folder).exists():
   assert not (OUT/'release').exists() and not (OUT/'manifest.json').exists()
   continue
  def copy(src,dest):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    os.link(src,dest);return dest
   return shutil.copy2(src,dest)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Src','nucleo/Inc','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    old=read(f);new=old.replace('2026102937','2026102939').replace('2026102938','2026102940')
    if old!=new:write(f,new)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  write(OUT/folder/'noise_wire.h',read(ROOT/'tools/adc_idle_noise/noise_wire.h'))
 write(OUT/'nucleo/Inc/noise_core.h',read(ROOT/'tools/adc_idle_noise/noise_core.h'))
 def source(f):
  return read(BASE/f.relative_to(OUT)).replace('2026102937','2026102939').replace('2026102938','2026102940')
 f=OUT/'nucleo/Inc/current_core.h';s=source(f)
 anchor='static inline uint8_t cm_path2(uint8_t pair) {return pair==0?2:3;}'
 s=once(s,anchor,anchor+'''
/* Instantaneous feedback is independent of RMS window rollover/publication. */
static inline int cm_reconstruct(const cm_core*s,uint8_t pair,uint16_t a,uint16_t b,int16_t out[3]){
  if(pair>2)return 0;
  unsigned first=pair==2?1:0,second=pair==0?1:2,third=3-first-second;
  out[first]=(int16_t)((int32_t)s->offset[cm_path1(pair)]-a);
  out[second]=(int16_t)((int32_t)s->offset[cm_path2(pair)]-b);
  out[third]=(int16_t)(-out[first]-out[second]);return 1;
}''')
 write(f,s)
 f=OUT/'nucleo/Src/current_shunt.c';s=source(f)
 s=once(s,'#include "uart_v3_transport.h"','#include "uart_v3_transport.h"\n#include "noise_core.h"')
 s=once(s,'static cm_core state;','static cm_core state;\nstatic nd_state idle_noise;')
 s=once(s,'eligible,uint16_t a,uint16_t b,const uint16_t*ccr','eligible,uint8_t pair,uint16_t a,uint16_t b,const uint16_t*ccr')
 s=once(s,' for(unsigned i=0;i<3;i++)ma_fast_sample.counts[i]=state.window.last[i];',
 '''  int16_t counts[3]={0,0,0};
  if(!cm_reconstruct(&state,pair,a,b,counts))ma_fast_sample.valid=0;
  for(unsigned i=0;i<3;i++)ma_fast_sample.counts[i]=counts[i];''')
 s=once(s,'pair==2?7U:1U','pair>=2?7U:1U')
 s=once(s,'pair==0?7U:6U','(pair==0||pair==3)?7U:6U')
 s=once(s,'  cm_init(&state);pc_init(&peak);','  cm_init(&state);nd_init(&idle_noise);pc_init(&peak);')
 # Unchanged active geometry/flags. Diagnostic pair3 can never be a valid current.
 s=once(s,'  uint8_t pair=active?cm_choose_pair(u,v,w):(pending_pair==0?2:0);',
 '''  uint8_t pair=active?cm_choose_pair(u,v,w):(pending_pair==0?2:0);
  int noise_next=nd_step(&idle_noise,captured_pair,a,b,!active,bus<=20U,state.zero_ready,
    both&&!lost_sync&&!jsqr1&&!jsqr2,cycles0);
  if(!active && noise_next>=0)pair=(uint8_t)noise_next;''')
 s=once(s,'  cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,',
 '  if(captured_pair<3)cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,')
 s=once(s,'  ma_publish_current(cycles0,epoch0,eligible,a,b,current_ccr,bus);',
 '  ma_publish_current(cycles0,epoch0,eligible,captured_pair,a,b,current_ccr,bus);')
 s+='''
/* Main/OFF-only export of a separate diagnostic buffer. It never touches the
 * frozen motor-current trace, the SD snapshot, the ID result or zero history. */
uint8_t mic_current_noise_packet(uint8_t*packet,uint8_t page,uint32_t build){
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||page>=ND_PAGES||!idle_noise.done)return 0;
 if(!idle_noise.ready){
  uint32_t registers[8]={ADC1->SMPR1,ADC1->SMPR2,ADC2->SMPR1,ADC2->SMPR2,
   ADC12_COMMON->CCR,ADC1->CFGR,ADC2->CFGR,TIM1->CCR4};
  (void)nd_seal(&idle_noise,build,SystemCoreClock,DBGMCU->IDCODE,registers);
 }
 memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=0xE7;
 packet[3]=1;packet[4]=page;packet[5]=ND_PAGES;put32(packet+6,build);put32(packet+10,idle_noise.crc);
 unsigned offset=page*24U,n=ND_BYTES-offset;if(n>24)n=24;
 memcpy(packet+14,idle_noise.bytes+offset,n);uv3_seal(packet);return 1;
}
'''
 write(f,s)
 f=OUT/'nucleo/Inc/current_shunt.h';s=source(f)
 s=once(s,'#endif','uint8_t mic_current_noise_packet(uint8_t*,uint8_t,uint32_t);\n#endif');write(f,s)
 f=OUT/'nucleo/Src/main.c';s=source(f)
 anchor='static void mic_send_current_page(uint32_t now_ms) {'
 s=once(s,anchor,'''static void mic_send_noise_page(uint32_t now_ms){
 static uint32_t last_ms;static uint8_t page;
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||(uint32_t)(now_ms-last_ms)<20U||
  (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
 uint8_t packet[UV3_FRAME];
 if(mic_current_noise_packet(packet,page,MIC_NUCLEO_FW_BUILD_ID)&&
  uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){last_ms=now_ms;page=(uint8_t)((page+1U)%91U);}
}

'''+anchor)
 s=once(s,'mic_send_peak_page(now_ms);','mic_send_peak_page(now_ms);mic_send_noise_page(now_ms);')
 write(f,s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=source(f)
 s=once(s,'#include "identify_wire.h"','#include "identify_wire.h"\n#include "noise_wire.h"')
 s=once(s,'static uint8_t g_id_view_page=0;',
  'static nd_blob g_idle_noise={};static uint8_t g_noise_view_page=0;\nstatic uint8_t g_id_view_page=0;')
 s=once(s,'      if(buf[2]==ID_STATUS_WIRE||buf[2]==ID_PAGE_WIRE){',
 '''      if(buf[2]==ND_WIRE){
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&!(g_bp_status&0x22U)&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)nd_receive(&g_idle_noise,buf,g_bp_fw_build,off);continue;
      }
      if(buf[2]==ID_STATUS_WIRE||buf[2]==ID_PAGE_WIRE){''')
 s=once(s,'static bool manual_command(const char *cmd) {','''static bool manual_command(const char *cmd) {
  if(starts_ci(cmd,"NOISE PAGE ")){
    unsigned page;char extra;
    if(g_pwm_enabled||g_start_req||g_state!=STATE_SAFE||!g_idle_noise.complete||
      sscanf(cmd+11,"%u %c",&page,&extra)!=1||page>=17)return false;
    g_noise_view_page=(uint8_t)page;return true;
  }''')
 anchor='    s += " id_view_page=";s += String((unsigned)g_id_view_page);'
 s=once(s,anchor,'''    s += " noise_complete=";s += String(g_idle_noise.complete?1:0);
    s += " noise_crc=";s += String((unsigned long)g_idle_noise.crc);
    s += " noise_good=";s += String((unsigned long)g_idle_noise.good);
    s += " noise_bad=";s += String((unsigned long)g_idle_noise.bad);
    s += " noise_view_page=";s += String((unsigned)g_noise_view_page);
    s += " noise_page_hex=";
    if(g_idle_noise.complete){
      const char digits[]="0123456789abcdef";
      for(unsigned j=0;j<128;j++){uint8_t value=g_idle_noise.bytes[128U*g_noise_view_page+j];s+=digits[value>>4];s+=digits[value&15];}
    }else s+="-";
'''+anchor)
 write(f,s)
 f=OUT/'web_hmi/server.py';s=source(f)
 s=s.replace('(2026102935,2026102936), (2026102939,2026102940)',
  '(2026102935,2026102936), (2026102937,2026102938), (2026102939,2026102940)')
 anchor='                "id_view_page": int(kv.get("id_view_page","0")),'
 s=once(s,anchor,'''                "noise_complete": int(kv.get("noise_complete","0")),
                "noise_crc": int(kv.get("noise_crc","0")),
                "noise_good": int(kv.get("noise_good","0")),
                "noise_bad": int(kv.get("noise_bad","0")),
                "noise_view_page": int(kv.get("noise_view_page","0")),
                "noise_page_hex": kv.get("noise_page_hex","-"),
'''+anchor);write(f,s)
 f=OUT/'web_hmi/static/index.html';write(f,source(f).replace('2937-irq-timing','2939-current-noise'))
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.standstill_current_noise.v1',pair=list(NEW),
  base_pair=[2026102937,2026102938],built=False,installed=False,thresholds_changed=False,
  active_adc_timing_changed=False,active_adc_geometry_changed=False,
  current_noise_cause_identified=False,diagnostic_off_only=True,start_commands=0),indent=2))
 print('2939/2940 prepared; OFF-only unfiltered ADC comparison; no hardware commands')


if __name__=='__main__':main()
