"""Prepare estimated-mean zero quality plus complete block history; no device access."""
import json
import os
import shutil
import prepare_current_shunt_monitor as u
from current_zero_noise.statistics_update import apply_core

ROOT=u.ROOT
BASE=ROOT/'artifacts/live_bench_20261024/current_peak_capture_r1'
UNO_BASE=BASE.parent/'uno_display_order_r2'
OUT=BASE.parent/'current_zero_noise_r1'
OLD=(2026102503,2026102502)
NEW=(2026102505,2026102506)
RES=ROOT/'tools/current_zero_noise'

REPORT_DECL='''static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths);
#define CM_ZERO_REPORT(s,mean,var,paths) mic_zero_record((s)->zero_attempts,(s)->zero_stable,(s)->zero_last_bad,mean,(s)->zero_low,(s)->zero_high,var,paths)
'''
HISTORY='''typedef struct { uint8_t bytes[15]; } zh_block;
typedef char zh_block_must_be_15[(sizeof(zh_block)==15)?1:-1];
static zh_block zero_history[8];
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths) {
 if(attempt<1 || attempt>8)return;
 uint8_t *b=zero_history[attempt-1U].bytes;
 for(unsigned i=0;i<4;++i){
   b[2*i]=(uint8_t)mean[i];b[2*i+1]=(uint8_t)(mean[i]>>8);
   unsigned span=high[i]-low[i];b[8+i]=(uint8_t)(span>255U?255U:span);
   if(span>255U)paths|=16U<<i;
 }
 b[12]=(uint8_t)((stable&3U)|(rejected<<2));b[13]=(uint8_t)variance_q7;b[14]=(uint8_t)paths;
}
'''
PACKET='''
uint8_t mic_zero_packet(uint8_t *packet,uint32_t build) {
 if(LL_TIM_IsEnabledAllOutputs(TIM1) || (!state.zero_ready && !state.zero_bad))return 0;
 unsigned count=state.zero_attempts;
 if(count<3 || count>8)return 0;
 unsigned page=(packets/4U)%count;
 memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=0xd9;
 packet[3]=1;packet[4]=(uint8_t)page;packet[5]=(uint8_t)count;put32(packet+6,build);
 memcpy(packet+10,&zero_history[page],15);
 packet[30]=3;packet[31]=2;packet[32]=3;packet[33]=8;packet[34]=2;
 packet[35]=128;packet[37]=15;packet[38]=1;uv3_seal(packet);return 1;
}
'''


def main():
    assert not OUT.exists()
    for base in (BASE,UNO_BASE):
        m=json.loads(u.read(base/'manifest.json'));assert m['installed']
        for rel,digest in m['source_sha256'].items():assert u.sha(base/rel)==digest,rel
    for name,base in (('nucleo',BASE),('UNOQ_MOTOR',UNO_BASE),('web_hmi',UNO_BASE)):
        def copy(src,dst):
            rel=os.path.relpath(src,str(BASE/'nucleo')).replace('\\','/')
            if name=='nucleo' and rel.split('/')[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(base/name,OUT/name,copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for name in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for f in (OUT/name).rglob('*'):
            if f.is_file():
                s=u.read(f).replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                u.write(f,s)
    f=OUT/'nucleo/Inc/current_core.h';s=u.read(f)
    s=u.once(s,'#include <string.h>','#include <string.h>\n#ifndef CM_ZERO_REPORT\n#define CM_ZERO_REPORT(s,mean,var,paths) ((void)(var),(void)(paths))\n#endif')
    # Append so legacy memory offsets stay unchanged; exactly16 extra RAM bytes.
    s=u.once(s,'  uint8_t zero_attempts,zero_stable,zero_last_bad;',
        '  uint8_t zero_attempts,zero_stable,zero_last_bad;\n  uint32_t zero_energy[4];')
    s=u.once(s,'  s->sum[path]+=raw;++s->count[path];',
        '''  s->sum[path]+=raw;++s->count[path];
  int32_t residual=(int32_t)raw-2048;
  s->zero_energy[path]+=(uint32_t)(residual*residual);
  if(raw<16 || raw>4079)s->zero_energy[path]|=0x80000000UL;''')
    s=u.once(s,'  memset(s->sum,0,sizeof(s->sum));memset(s->count,0,sizeof(s->count));',
        '  memset(s->zero_energy,0,sizeof(s->zero_energy));\n  memset(s->sum,0,sizeof(s->sum));memset(s->count,0,sizeof(s->count));')
    s=u.once(s,'  uint16_t mean[4];','  uint16_t mean[4];unsigned variance_q7=0,bad_paths=0;')
    s=u.once(s,'    if(mean[i]<1600 || mean[i]>2500)s->zero_last_bad|=2;\n    if(s->high[i]-s->low[i]>CM_ZERO_SPAN)s->zero_last_bad|=1;',
        '''    if(mean[i]<1600 || mean[i]>2500){s->zero_last_bad|=2;bad_paths|=1U<<i;}
    /* Raw extrema remain diagnostics. Validate the estimated uncertainty
     * of the256-sample mean:3*sigma_mean<=2counts, plus3-block drift<=2.
     * This estimate assumes stationary noise; block consistency is separate.
     * Never apply this averaging or rejection to running current samples. */
    int32_t residual_sum=(int32_t)s->sum[i]-(int32_t)(2048U*CM_ZERO_N);
    uint64_t energy=(uint64_t)(s->zero_energy[i]&0x7fffffffUL)*CM_ZERO_N-
                    (uint64_t)((int64_t)residual_sum*residual_sum);
    const uint32_t denominator=CM_ZERO_N*CM_ZERO_N*(CM_ZERO_N-1U);
    if(energy*9U>(uint64_t)denominator*4U){s->zero_last_bad|=1;bad_paths|=1U<<i;}
    if(s->zero_energy[i]&0x80000000UL){s->zero_last_bad|=8;bad_paths|=1U<<i;}
    unsigned q=(unsigned)((energy+denominator/256U)/(denominator/128U));
    if(q>255U)q=255U;
    if(q>variance_q7)variance_q7=q;''')
    s=u.once(s,'      if(hi-lo>CM_ZERO_DRIFT)s->zero_last_bad|=4;',
        '      if(hi-lo>CM_ZERO_DRIFT){s->zero_last_bad|=4;bad_paths|=1U<<i;}')
    s=u.once(s,'  if(s->zero_stable>=CM_ZERO_BLOCKS) {',
        '  CM_ZERO_REPORT(s,mean,variance_q7,bad_paths);\n  if(s->zero_stable>=CM_ZERO_BLOCKS) {')
    u.write(f,apply_core(s))
    f=OUT/'nucleo/Src/current_shunt.c';s=u.read(f)
    s=u.once(s,'#include "current_core.h"',REPORT_DECL+'#include "current_core.h"')
    s=u.once(s,'static cm_core state;','static cm_core state;\n'+HISTORY)
    s=u.once(s,'  cm_init(&state);pc_init(&peak);','  cm_init(&state);pc_init(&peak);memset(zero_history,0,sizeof(zero_history));')
    old='''  cm_sample(&state,HAL_GetTick(),active,pending_pair,a,b,
            both && !lost_sync && pending_valid && pending_active && active,
            bus<=20U && both && !lost_sync && early);
'''
    assert s.count(old)==1;s=s.replace(old,'')
    anchor='  uint32_t queue_cycles=DWT->CYCCNT-cycles0;'
    s=u.once(s,anchor,anchor+'''
  /* Publish the next ADC context BEFORE zero statistics/window calculation. */
  cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,
            both && !lost_sync && valid0 && active0 && active,
            bus<=20U && both && !lost_sync && early);''')
    s=u.once(s,'  if(!peak.frozen) {\n    if(queue_cycles>',
        '  if(!peak.frozen && (active || peak.running)) {\n    if(queue_cycles>')
    s=u.once(s,'packet[34]=CM_ZERO_SPAN;packet[35]=CM_ZERO_DRIFT;',
        'packet[34]=0;packet[35]=CM_ZERO_DRIFT;packet[36]=3;packet[37]=2;')
    u.write(f,s+'\n'+PACKET)
    f=OUT/'nucleo/Inc/current_shunt.h';u.write(f,u.once(u.read(f),'#endif','uint8_t mic_zero_packet(uint8_t *packet,uint32_t build);\n#endif'))
    f=OUT/'nucleo/Src/main.c';s=u.read(f)
    s=u.once(s,'  mic_current_packet(packet,(uint8_t)(slot==0U?1U:slot==2U?2U:0U),MIC_NUCLEO_FW_BUILD_ID);',
        '  if(slot!=4U || !mic_zero_packet(packet,MIC_NUCLEO_FW_BUILD_ID))\n    mic_current_packet(packet,(uint8_t)(slot==0U?1U:slot==2U?2U:0U),MIC_NUCLEO_FW_BUILD_ID);')
    u.write(f,s)
    shutil.copyfile(RES/'zero_wire.h',OUT/'UNOQ_MOTOR/zero_wire.h')
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=u.read(f)
    s=u.once(s,'static pc_receiver g_peak;','static pc_receiver g_peak;\n#include "zero_wire.h"\nstatic zh_receiver g_zero_history;')
    s=u.once(s,'pc_reset(&g_peak);','pc_reset(&g_peak);zh_reset(&g_zero_history);')
    s=u.once(s,'      if(buf[2]==CT_SUMMARY',
        '''      if(buf[2]==ZH_WIRE) {
        const uint32_t observed_ms=millis();
        const bool off=!g_pwm_enabled && (g_bp_status&0x22U)==0 &&
            g_bp_mcsdk_telemetry && (uint32_t)(observed_ms-g_bp_last_rsp_ms)<300U;
        (void)zh_receive(&g_zero_history,buf,g_bp_fw_build,off);continue;
      }
      if(buf[2]==CT_SUMMARY''')
    s=u.once(s,'        (void)ct_receive(&g_current,buf,g_bp_fw_build,fresh,observed_ms);continue;',
        '''        const bool old_quality=g_current.has_quality;
        const uint32_t old_tick=old_quality?ct_u32(g_current.quality+10):0;
        if(ct_receive(&g_current,buf,g_bp_fw_build,fresh,observed_ms) && buf[2]==CT_QUALITY && old_quality &&
           (int32_t)(ct_u32(buf+10)-old_tick)<0)zh_reset(&g_zero_history);
        continue;''')
    s=u.once(s,'  s += " mc_current_packet_hex=";',
        '''  s += " mc_zero_history_hex=";
  if(g_zero_history.complete) {
    for(unsigned page=0;page<g_zero_history.count;++page)for(unsigned i=0;i<UV3_FRAME;++i) {
      uint8_t value=g_zero_history.frames[page][i];s+=break_hex[value>>4];s+=break_hex[value&15];
    }
  } else s+="-";
  s+=" mc_zero_history_good=";s+=String((unsigned long)g_zero_history.good);
  s+=" mc_zero_history_bad=";s+=String((unsigned long)g_zero_history.bad);
  s += " mc_current_packet_hex=";''')
    s=u.once(s,'  s.reserve(8192);','  s.reserve(12288);');u.write(f,s)
    f=OUT/'web_hmi/server.py';s=u.read(f)
    # Preserve old identities for the programming gate, extend to new pair.
    s=u.once(s,'        (2026102503, 2026102502),','        (2026102503, 2026102502),\n        (2026102505, 2026102506),')
    s=u.once(s,'(2026102503,2026102502)) and','(2026102503,2026102502),(2026102505,2026102506)) and')
    s=''.join(line.replace(',2026102502)',',2026102502,2026102506)').replace(', 2026102502)',', 2026102502, 2026102506)')
        if (('not in (' in line and 'not in ((' not in line) or ('mc_fw_build' in line and ' in (2026' in line)) else line
        for line in s.splitlines(keepends=True))
    a=s.index('# Imported as source into the HMI;');b=s.index('def with_motor_controller_aliases',a)
    decoder=s[a:b].replace('(2026102501, 2026102502), (2026102503, 2026102502)', '(2026102505, 2026102506),')
    decoder=decoder.replace('(2026102501,2026102502),(2026102503,2026102502)','(2026102505,2026102506),')
    decoder=decoder.replace('2026102502','2026102506')
    decoder=decoder.replace('bytes((3, 8, 40, 2))','bytes((3, 8, 0, 2))')
    decoder=decoder.replace("raise ValueError('Invalid zero quality contract')", "raise ValueError('Invalid zero quality contract')\n            if quality[36:38] != bytes((3,2)): raise ValueError('Invalid mean uncertainty contract')")
    s=s[:a]+decoder+u.read(RES/'zero_hmi.py')+'\n\n'+s[b:]
    s=u.once(s,'data=with_adc_peak(with_shunt_currents(data))','data=with_zero_history(with_adc_peak(with_shunt_currents(data)))')
    s=u.once(s,'"mc_current_quality_hex", "mc_adc_peak_hex")','"mc_current_quality_hex", "mc_adc_peak_hex", "mc_zero_history_hex")')
    s=u.once(s,'"mc_adc_peak_complete")','"mc_adc_peak_complete", "mc_zero_history_good", "mc_zero_history_bad")')
    u.write(f,s)
    f=OUT/'web_hmi/static/app.js';s=u.read(f)
    s=u.once(s,'Предел разброса 40.','Сырой размах — справочно; оценка 3σ среднего ≤2 отсчётов, дрейф ≤2.')
    s=u.once(s,'разброс блока больше 40','оценка 3σ среднего больше 2 отсчётов')
    s=u.once(s,'    if (why.length)', '    if (reject & 8) why.push("сырой АЦП достиг границы диапазона");\n    if (why.length)')
    s=u.once(s,'  if (data.mc_adc_peak_status)',
        '  if (data.mc_zero_history_status) document.getElementById("shuntCurrentAdc").textContent += ` ${data.mc_zero_history_status}.`;\n  if (data.mc_adc_peak_status)')
    u.write(f,s)
    for name in ('build/uno','build/nucleo'):(OUT/name).mkdir(parents=True)
    m=json.loads(u.read(BASE/'manifest.json'))
    for key in list(m):
        if key.startswith(('installation','images_written','sd_capture','display_','source_sha256','build_sha256','verification_','completion_')):m.pop(key,None)
    m.update(pair_compatibility_ids=list(NEW),predecessor_uno=str(UNO_BASE),predecessor_nucleo=str(BASE),
        built=False,selftest_pass=False,installed=False,hardware_commands=0,rpc_pending=False,
        adc_idle_zero_verified=False,uart_idle_60s_verified=False,hmi_browser_panel_verified=False,
        zero_acceptance_unchanged=False,zero_quality_method='3sigma estimated256-sample mean<=2counts and3consecutive block means within2counts',
        zero_span_limit_counts=None,zero_per_block_limits_unchanged=False,
        zero_raw_span_advisory_only=True,zero_raw_clip_rejected=True,zero_history_blocks=8,
        current_active_samples_filter_changed=False,adc_queue_published_before_statistics=True,
        zero_history_wire_version=0xd9,zero_history_record_bytes=15,zero_history_uart_off_only=True,zero_history_rpc_cached_when_active=True,
        display_mapping='raw_x=12-x, raw_y=7-y',physical_display_verified=False)
    u.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(OUT)


if __name__=='__main__':main()
