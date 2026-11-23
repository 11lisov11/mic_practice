"""Prepare first-peak raw ADC/timer capture; no board access, PWM unchanged."""
import json
import os
from pathlib import Path
import shutil
import prepare_current_shunt_monitor as util
from current_peak_capture.display_orientation import apply as orient_display

ROOT=util.ROOT
BASE=ROOT/'artifacts/live_bench_20261024/current_shunt_monitor_r4'
OUT=BASE.parent/'current_peak_capture_r1'
OLD=(2026102411,2026102412)
NEW=(2026102501,2026102502)
RES=ROOT/'tools/current_peak_capture'

GLOBALS=r'''
static pc_capture peak;
static volatile uint32_t peak_epoch;
static uint16_t peak_active_ccr[4],peak_update_cnt,peak_update_cr1;
static uint8_t peak_sealed;

void mic_current_update_epoch(void) {
  if(peak.frozen)return;
  peak_active_ccr[0]=(uint16_t)TIM1->CCR1;
  peak_active_ccr[1]=(uint16_t)TIM1->CCR2;
  peak_active_ccr[2]=(uint16_t)TIM1->CCR3;
  peak_active_ccr[3]=(uint16_t)TIM1->CCR4;
  peak_update_cnt=(uint16_t)TIM1->CNT;peak_update_cr1=(uint16_t)TIM1->CR1;
  ++peak_epoch;
}
'''

PACKET=r'''
uint8_t mic_current_peak_packet(uint8_t *packet,uint8_t page,uint32_t build) {
  if(!peak.frozen || LL_TIM_IsEnabledAllOutputs(TIM1) || page>=35)return 0;
  if(!peak_sealed) {
    peak.blob.header.firmware=build;
    peak.blob.header.crc=pc_crc((const uint8_t *)&peak.blob);
    peak_sealed=1;
  }
  memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=0xd8;
  packet[3]=1;packet[4]=1;packet[5]=page;packet[6]=35;
  uint8_t size=page==34?4:30;packet[7]=size;
  memcpy(packet+8,((const uint8_t *)&peak.blob)+page*30U,size);
  packet[38]=1;uv3_seal(packet);return 1;
}
'''


def main():
    assert not (OUT/'manifest.json').exists(),'Preserve prepared candidate'
    manifest=json.loads(util.read(BASE/'manifest.json'))
    assert manifest['installed'] and manifest['installation_flash_verified']
    for rel,digest in manifest['source_sha256'].items():assert util.sha(BASE/rel)==digest,rel
    for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
        def copy_source(src,dst):
            rel=Path(src).relative_to(BASE)
            # Only immutable vendor trees share disk storage. Editable
            # application/sketch/HMI files are independent physical copies.
            if (len(rel.parts)>1 and rel.parts[0]=='nucleo'
                    and rel.parts[1] in ('Drivers','MCSDK_v6.4.2-Full') and not Path(dst).exists()):
                os.link(src,dst)
                return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/tree,OUT/tree,copy_function=copy_source,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file():
                s=util.read(p)
                s=s.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                util.write(p,s)
    for name,target in [('peak_core.h','nucleo/Inc/peak_core.h'),('peak_wire.h','UNOQ_MOTOR/peak_wire.h')]:
        shutil.copyfile(RES/name,OUT/target)
    p=OUT/'nucleo/Inc/current_shunt.h';s=util.read(p)
    util.write(p,util.once(s,'#endif','void mic_current_update_epoch(void);\nuint8_t mic_current_peak_packet(uint8_t *packet,uint8_t page,uint32_t build);\n#endif'))
    p=OUT/'nucleo/Src/current_shunt.c';s=util.read(p)
    s=util.once(s,'#include "current_core.h"','#include "current_core.h"\n#include "peak_core.h"')
    s=util.once(s,'static uint32_t packets;','static uint32_t packets;\n'+GLOBALS)
    s=util.once(s,'  cm_init(&state);','  cm_init(&state);pc_init(&peak);\n  CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;\n  DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;')
    s=util.once(s,'  uint32_t u=TIM1->CCR1,v=TIM1->CCR2,w=TIM1->CCR3;',
'''  uint32_t epoch0=peak_epoch,cycles0=DWT->CYCCNT;
  uint32_t u=TIM1->CCR1,v=TIM1->CCR2,w=TIM1->CCR3;''')
    s=util.once(s,'  uint8_t both=(uint8_t)LL_ADC_IsActiveFlag_JEOS(ADC2);',
'''  uint32_t isr1=0,isr2=0,jsqr1=0,jsqr2=0;
  if(!peak.frozen){isr1=ADC1->ISR;isr2=ADC2->ISR;jsqr1=ADC1->JSQR;jsqr2=ADC2->JSQR;}
  uint8_t both=(uint8_t)LL_ADC_IsActiveFlag_JEOS(ADC2);''')
    s=util.once(s,'  cm_sample(&state,HAL_GetTick(),active,pending_pair,a,b,',
'''  uint8_t captured_pair=pending_pair,valid0=pending_valid,active0=pending_active;
  uint8_t eligible=(uint8_t)(both && !lost_sync && valid0 && active0 && active && state.zero_ready);
  cm_sample(&state,HAL_GetTick(),active,pending_pair,a,b,''')
    s=util.once(s,'  queue_pair(pair);\n}',r'''  queue_pair(pair);
  uint16_t queue_cnt=(uint16_t)TIM1->CNT,queue_dir=(uint16_t)(TIM1->CR1&TIM_CR1_DIR);
  uint32_t queue_cycles=DWT->CYCCNT-cycles0;
  /* Record AFTER publishing the next ADC context. No filtering or control write. */
  if(!peak.frozen) {
    if(queue_cycles>peak.blob.header.reserved)peak.blob.header.reserved=queue_cycles;
    pc_sample sample={0};
    sample.cycles=cycles0;sample.epoch_before=epoch0;
    sample.isr1=isr1;sample.isr2=isr2;sample.jsqr1=jsqr1;sample.jsqr2=jsqr2;
    for(unsigned i=0;i<4;++i){sample.active_ccr[i]=peak_active_ccr[i];sample.offset[i]=state.offset[i];}
    sample.update_cnt=peak_update_cnt;sample.update_cr1=peak_update_cr1;
    sample.epoch_after=peak_epoch;
    sample.preload_ccr[0]=(uint16_t)u;sample.preload_ccr[1]=(uint16_t)v;
    sample.preload_ccr[2]=(uint16_t)w;sample.preload_ccr[3]=(uint16_t)TIM1->CCR4;
    sample.cnt=(uint16_t)count;sample.arr=(uint16_t)TIM1->ARR;sample.cr1=(uint16_t)direction;
    sample.raw[0]=a;sample.raw[1]=b;sample.pair=captured_pair;sample.next_pair=pair;
    sample.cnt_exit=queue_cnt;sample.bus_v=bus;
    sample.reference_deci_hz=(uint16_t)(pACIM_VF_Component_M1->fFlux_Freq_Hz*10.0f);
    uint8_t accepted=(uint8_t)(eligible && a>=16 && b>=16 && a<=4079 && b<=4079);
    sample.flags=(uint16_t)((active?1:0)|(valid0?2:0)|(active0?4:0)|(both?8:0)|
        (lost_sync?16:0)|(early?32:0)|(accepted?64:0)|
        (sample.epoch_before!=sample.epoch_after?128:0)|
        (((isr1|isr2)&ADC_ISR_JQOVF)?256:0)|(queue_dir?512:0));
    int32_t ia=(int32_t)state.offset[cm_path1(captured_pair)]-a;
    int32_t ib=(int32_t)state.offset[cm_path2(captured_pair)]-b,ic=-ia-ib;
    uint32_t mag=(uint32_t)(ia<0?-ia:ia),m=(uint32_t)(ib<0?-ib:ib);
    if(m>mag)mag=m;
    m=(uint32_t)(ic<0?-ic:ic);
    if(m>mag)mag=m;
    pc_push(&peak,&sample,HAL_GetTick(),active,eligible,mag);
  }
}''')
    util.write(p,s+'\n'+PACKET)
    p=OUT/'nucleo/Src/stm32g4xx_mc_it.c';s=util.read(p)
    s=util.once(s,'    LL_TIM_ClearFlag_UPDATE(TIM1);','    LL_TIM_ClearFlag_UPDATE(TIM1);\n    mic_current_update_epoch();')
    util.write(p,s)
    p=OUT/'nucleo/Src/main.c';s=util.read(p)
    sender='''static void mic_send_peak_page(uint32_t now_ms) {
  static uint32_t last_ms;static uint8_t page;
  if(LL_TIM_IsEnabledAllOutputs(TIM1) || (uint32_t)(now_ms-last_ms)<100U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_current_peak_packet(packet,page,MIC_NUCLEO_FW_BUILD_ID) &&
      uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){last_ms=now_ms;page=(uint8_t)((page+1U)%35U);}
}

'''
    s=util.once(s,'static void uno_send_reply(void) {',sender+'static void uno_send_reply(void) {')
    s=util.once(s,'mic_send_break_page(now_ms);mic_send_current_page(now_ms);',
                    'mic_send_break_page(now_ms);mic_send_current_page(now_ms);mic_send_peak_page(now_ms);')
    util.write(p,s)
    p=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=util.read(p)
    s=util.once(s,'static ct_receiver g_current;','static ct_receiver g_current;\n#include "peak_wire.h"\nstatic pc_receiver g_peak;')
    s=util.once(s,'ct_reset(&g_current);','ct_reset(&g_current);pc_reset(&g_peak);')
    dispatch='''      if(buf[2]==PC_WIRE) {
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry && !g_pwm_enabled && (g_bp_status&0x22U)==0 &&
            (uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)pc_receive(&g_peak,buf,g_bp_fw_build,off,now);continue;
      }
'''
    s=util.once(s,'      if(buf[2]==CT_SUMMARY',dispatch+'      if(buf[2]==CT_SUMMARY')
    rpc='''  s += " mc_adc_peak_hex=";
  if(g_peak.complete && !g_pwm_enabled) for(unsigned i=0;i<PC_WIRE_BYTES;++i) {
    s+=break_hex[g_peak.data[i]>>4];s+=break_hex[g_peak.data[i]&15];
  } else s+="-";
  s+=" mc_adc_peak_good=";s+=String((unsigned long)g_peak.good);
  s+=" mc_adc_peak_bad=";s+=String((unsigned long)g_peak.bad);
  s+=" mc_adc_peak_complete=";s+=String(g_peak.complete?1:0);
'''
    s=util.once(s,'  s += " mc_current_packet_hex=";',rpc+'  s += " mc_current_packet_hex=";')
    s=util.once(s,'  s.reserve(4096);','  s.reserve(8192);')
    util.write(p,orient_display(s))
    p=OUT/'web_hmi/server.py';s=util.read(p)
    # Historical pairs remain available for the programming precheck.
    s=util.once(s,'        (2026102411, 2026102412),','        (2026102411, 2026102412),\n        (2026102501, 2026102502),')
    s=util.once(s,'(2026102411,2026102412)) and','(2026102411,2026102412),(2026102501,2026102502)) and')
    s=''.join(line.replace(',2026102412)',',2026102412,2026102502)').replace(', 2026102412)',', 2026102412, 2026102502)')
        if ('not in (' in line or ('mc_fw_build' in line and ' in (2026' in line)) else line
        for line in s.splitlines(keepends=True))
    a=s.index('# Imported as source into the HMI;');b=s.index('def with_motor_controller_aliases',a)
    decoder=s[a:b].replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
    s=s[:a]+decoder+util.read(RES/'peak_hmi.py')+'\n\n'+s[b:]
    s=util.once(s,'        data=with_shunt_currents(data)','        data=with_adc_peak(with_shunt_currents(data))')
    s=util.once(s,'("mc_current_packet_hex", "mc_current_detail_hex", "mc_current_quality_hex")',
                    '("mc_current_packet_hex", "mc_current_detail_hex", "mc_current_quality_hex", "mc_adc_peak_hex")')
    s=util.once(s,'("mc_current_age_ms", "mc_current_detail_age_ms", "mc_current_quality_age_ms", "mc_current_good", "mc_current_bad")',
                    '("mc_current_age_ms", "mc_current_detail_age_ms", "mc_current_quality_age_ms", "mc_current_good", "mc_current_bad", "mc_adc_peak_good", "mc_adc_peak_bad", "mc_adc_peak_complete")')
    util.write(p,s)
    p=OUT/'web_hmi/static/app.js';s=util.read(p)
    s=util.once(s,'  currVal.textContent = valid ? `${format(data.mc_current_rms_a)} А RMS',
        '  if (data.mc_adc_peak_status) document.getElementById("shuntCurrentAdc").textContent += ` ${data.mc_adc_peak_status}.`;\n'
        '  currVal.textContent = valid ? `${format(data.mc_current_rms_a)} А RMS')
    util.write(p,s)
    for folder in ('build/uno','build/nucleo'):(OUT/folder).mkdir(parents=True)
    for key in ('source_sha256','build_sha256','verification_sha256','verification_summary','runtime_report','completion_report','installation_report'):
        manifest.pop(key,None)
    for key in list(manifest):
        if key.startswith(('installation_','installation','images_written','uno_flash','nucleo_flash','sd_capture_')):manifest.pop(key,None)
    manifest.update(pair_compatibility_ids=list(NEW),predecessor=str(BASE),built=False,selftest_pass=False,installed=False,
        adc_idle_zero_verified=False,uart_idle_60s_verified=False,hmi_browser_panel_verified=False,rpc_pending=False,
        adc_trigger_changed=False,peak_capture_version=0xd8,peak_capture_bytes=1024,peak_capture_sample_bytes=80,
        peak_capture_capacity=12,peak_capture_post_samples=6,peak_capture_threshold_counts=626,
        peak_capture_threshold_nominal_a=6.006,peak_capture_auto_rearm=False,peak_capture_off_only_transmission=True,
        peak_capture_changes_current_filter=False,hardware_commands=0)
    util.write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    print(OUT)


if __name__=='__main__':main()
