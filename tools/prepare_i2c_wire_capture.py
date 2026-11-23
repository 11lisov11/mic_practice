"""Prepare a passive pre-error bus recorder. No board or network access."""
import ast,json,os,shutil
from pathlib import Path
import prepare_i2c_persistent_pe as previous
ROOT=previous.ROOT;BASE=previous.OUT
OUT=ROOT/'artifacts/live_bench_20261028/i2c_wire_capture_r1'
RES=ROOT/'tools/i2c_wire_capture'
OLD=(2026102709,2026102710);NEW=(2026102811,2026102812)
read,write,sha,once=previous.read,previous.write,previous.sha,previous.once

def identity(s):
    return s.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))

def hmi(s):
    # Extend actual peer lists and exact compatibility pairs separately. Earlier
    # generators accidentally inflated a historical two-element pair; repair it
    # to the real original pair rather than carrying the malformed tuple forward.
    s=s.replace('(2026102703, 2026102704, 2026102706, 2026102708,2026102710)','(2026102703, 2026102704)')
    s=s.replace('(2026102703,2026102704,2026102706,2026102708,2026102710)','(2026102703,2026102704)')
    for old in ('(2026102709,2026102710)','(2026102709, 2026102710)'):
        s=s.replace(old,old+', (2026102811,2026102812)')
    tree=ast.parse(s);lines=s.splitlines(keepends=True);offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    edits=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.Tuple) or not all(isinstance(x,ast.Constant) and type(x.value) is int for x in node.elts):continue
        values=tuple(x.value for x in node.elts)
        if values in (OLD,NEW,(2026102703,2026102704)) or OLD[1] not in values or NEW[1] in values:continue
        a=offsets[node.lineno-1]+node.col_offset;b=offsets[node.end_lineno-1]+node.end_col_offset
        edits.append((a,b,s[a:b][:-1].rstrip().rstrip(',')+','+str(NEW[1])+')'))
    for a,b,text in sorted(edits,reverse=True):s=s[:a]+text+s[b:]
    # HMI decoder is also usable offline by a single import from the package.
    extra=read(RES/'hmi_decoder.py')
    s=once(s,'def with_i2c_first_fault(data):',extra+'\n\ndef with_i2c_first_fault(data):')
    s=once(s,'return with_bus_clear(with_i2c_release(out))','return with_i2c_wire(with_bus_clear(with_i2c_release(out)))')
    keys=('enc_wire_state','enc_wire_valid','enc_wire_good','enc_wire_bad','enc_peer_epoch','enc_previous_epoch','enc_previous_records_retained')
    fields=''.join('                "'+k+'": int(kv.get("'+k+'","0")),\n' for k in keys)
    fields+='                "enc_wire_hex": kv.get("enc_wire_hex","-"),\n'
    fields+='                "enc_wire_crc": kv.get("enc_wire_crc","-"),\n'
    fields+='                "enc_previous_record_crcs": kv.get("enc_previous_record_crcs","-"),\n'
    s=once(s,'                "enc_bus_clear_hex": kv.get("enc_bus_clear_hex","-"),',fields+'                "enc_bus_clear_hex": kv.get("enc_bus_clear_hex","-"),')
    ast.parse(s);return s

def main():
    assert not OUT.exists(),'Keep the previous package; do not overwrite it'
    manifest=json.loads(read(BASE/'manifest.json'))
    assert manifest['installed'] and manifest['built']
    for table in ('source_sha256','build_sha256','verification_sha256'):
        for rel,digest in manifest[table].items():assert sha(BASE/rel)==digest,rel
    for folder in ('nucleo','UNOQ_MOTOR','web_hmi','libraries'):
        def copy(src,dst):
            rel=Path(src).relative_to(BASE/folder)
            if folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                a=read(f);b=identity(a)
                if a!=b:write(f,b)
    for dst in ('nucleo/Inc','UNOQ_MOTOR'):
        write(OUT/dst/'wire_capture.h',read(RES/'wire_capture.h'))
    write(OUT/'UNOQ_MOTOR/peer_epoch.h',read(RES/'peer_epoch.h'))
    for name,dst in [('nucleo_i2c_wire.h','nucleo/Inc'),('nucleo_i2c_wire.c','nucleo/Src')]:
        write(OUT/dst/name,read(RES/name))
    f=OUT/'nucleo/STM32CubeIDE/.project';s=read(f)
    link='\t\t<link>\n\t\t\t<name>Application/User/nucleo_i2c_wire.c</name>\n\t\t\t<type>1</type>\n\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/nucleo_i2c_wire.c</locationURI>\n\t\t</link>\n'
    write(f,once(s,'\t</linkedResources>',link+'\t</linkedResources>'))
    f=OUT/'nucleo/Src/nucleo_encoder.c';s=read(f)
    s=once(s,'#include "nucleo_encoder.h"','#include "nucleo_encoder.h"\n#include "nucleo_i2c_wire.h"')
    s=once(s,'  if(wanted==3U)memcpy(fault_record[1],r,FC_BYTES);','  if(wanted==3U)memcpy(fault_record[1],r,FC_BYTES);\n  if(wanted&2U)mic_i2c_wire_freeze(fault_record[1],cycles);')
    s=once(s,'bool mic_encoder_fault_packet(uint8_t*p,unsigned slot,unsigned page){','bool mic_encoder_pwm_fault_ready(void){return (fault_ready&2U)!=0;}\nbool mic_encoder_fault_packet(uint8_t*p,unsigned slot,unsigned page){')
    write(f,s)
    f=OUT/'nucleo/Inc/nucleo_encoder.h';write(f,once(read(f),'void mic_encoder_init(void);','bool mic_encoder_pwm_fault_ready(void);\nvoid mic_encoder_init(void);'))
    f=OUT/'nucleo/Src/main.c';s=read(f)
    s=once(s,'#include "nucleo_encoder.h"','#include "nucleo_encoder.h"\n#include "nucleo_i2c_wire.h"\n#include "wire_capture.h"')
    s=once(s,'volatile uint16_t mic_bkin_ring[MIC_BKIN_SAMPLE_COUNT];','volatile uint8_t mic_bkin_ring[MIC_BKIN_SAMPLE_COUNT];')
    s=once(s,'  /* GPIO is read as a word; DMA stores its low 16 bits, including PA6. */\n  hdma_mic_bkin.Init.MemDataAlignment=DMA_MDATAALIGN_HALFWORD;',
       '  /* Unchanged WORD GPIO read; retain low byte containing PA4 and PA6.\n     All8192 samples, sample rate and SD pulse processing are unchanged. */\n  hdma_mic_bkin.Init.MemDataAlignment=DMA_MDATAALIGN_BYTE;')
    scheduler='''static void mic_send_i2c_wire_page(uint32_t now_ms){
  static uint32_t last_ms;static uint8_t page;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||MC_GetSTMStateMotor1()==RUN||
     !mic_last_control_reply_safe_off||!uno_link.link_seen||
     (uint32_t)(now_ms-uno_link.last_valid_ms)>UNO_LINK_TIMEOUT_MS||
     (uint32_t)(now_ms-last_ms)<50U||
     (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_i2c_wire_packet(packet,page)&&uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){
    last_ms=now_ms;if(packet[3]==0)page=(uint8_t)((page+1U)%WC_PAGES);
  }
}

'''
    s=once(s,'static void mic_send_encoder_page(uint32_t now_ms) {',scheduler+'static void mic_send_encoder_page(uint32_t now_ms) {')
    s=once(s,'  mic_encoder_init();','  mic_encoder_init();\n  mic_i2c_wire_init();')
    old='''    mic_encoder_allow_bus_clear(!uno_link.command_enabled && mic_break_start_window==0U &&
      !LL_TIM_IsEnabledAllOutputs(TIM1) &&
      (MC_GetSTMStateMotor1()==IDLE || MC_GetSTMStateMotor1()==FAULT_NOW || MC_GetSTMStateMotor1()==FAULT_OVER) &&
      VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)<20U);'''
    new=old.replace('mic_encoder_allow_bus_clear(','const bool off_low_bus=').replace('<20U);','<20U;')
    s=once(s,old,new+'\n    mic_encoder_allow_bus_clear(off_low_bus);')
    s=once(s,'    mic_encoder_poll();','    mic_encoder_poll();\n    mic_i2c_wire_service(off_low_bus);\n    mic_send_i2c_wire_page(HAL_GetTick());')
    write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=once(s,'static fc_receiver g_i2c_fault={};','#include "peer_epoch.h"\nstatic pe_records g_encoder_records={};\nstatic pe_history g_encoder_history={};\n#define g_i2c_fault g_encoder_records.fault\n#define g_wire_capture g_encoder_records.wire')
    s=once(s,'static uint8_t g_bus_clear[UV3_FRAME];static bool g_bus_clear_seen;','#define g_bus_clear g_encoder_records.clear\n#define g_bus_clear_seen g_encoder_records.clear_seen')
    s=once(s,'static pr_receiver g_release_capture={};','#define g_release_capture g_encoder_records.release')
    s=once(s,'  s.reserve(12288);','  s.reserve(16384);')
    extra='''    s += " enc_peer_epoch=";s += String((unsigned long)g_encoder_history.epoch);
    s += " enc_previous_epoch=";s += String((unsigned long)g_encoder_history.previous_epoch);
    s += " enc_previous_records_retained=";s += String(g_encoder_history.previous_valid?1:0);
    s += " enc_previous_record_crcs=";
    if(!g_encoder_history.previous_valid)s+='-';
    else {
      const pe_records*old=&g_encoder_history.previous;
      const uint32_t crcs[]={old->fault.slot[0].valid?old->fault.slot[0].crc:0U,
        old->fault.slot[1].valid?old->fault.slot[1].crc:0U,
        old->release.slot[0].valid?old->release.slot[0].published_crc:0U,
        old->release.slot[1].valid?old->release.slot[1].published_crc:0U,
        old->wire.valid?old->wire.crc:0U,old->clear_seen?uv3_crc32c(old->clear,UV3_FRAME):0U};
      for(unsigned i=0;i<6;i++){if(i)s+=',';s+=String((unsigned long)crcs[i],HEX);}
    }
    s += " enc_wire_state=";s += String((unsigned)g_wire_capture.state);
    s += " enc_wire_valid=";s += String(g_wire_capture.valid?1:0);
    s += " enc_wire_good=";s += String((unsigned long)g_wire_capture.good);
    s += " enc_wire_bad=";s += String((unsigned long)g_wire_capture.bad);
    s += " enc_wire_crc=";s += String((unsigned long)g_wire_capture.crc,HEX);
    s += " enc_wire_hex=";
    if(!g_wire_capture.valid)s+='-';
    else for(unsigned i=0;i<WC_BYTES;i++){const char*hex="0123456789abcdef";uint8_t v=g_wire_capture.bytes[i];s+=hex[v>>4];s+=hex[v&15];}
'''
    s=once(s,'    s += " enc_fault_good=";',extra+'    s += " enc_fault_good=";')
    extra='''      if(buf[2]==WC_WIRE){
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&!(g_bp_status&0x22U)&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)wc_receive(&g_wire_capture,buf,g_bp_fw_build,off);continue;
      }
'''
    s=once(s,'      if(buf[2]==EH_WIRE){',extra+'      if(buf[2]==EH_WIRE){')
    s=once(s,'(int32_t)(ct_u32(buf+10)-old_tick)<0)zh_reset(&g_zero_history);',
      '(int32_t)(ct_u32(buf+10)-old_tick)<0){\n          pe_reset(&g_encoder_history,&g_encoder_records);\n          memset(&g_encoder_health,0,sizeof(g_encoder_health));\n          zh_reset(&g_zero_history);\n        }')
    write(f,s);write(OUT/'web_hmi/server.py',hmi(read(BASE/'web_hmi/server.py')))
    for folder in ('verification','build/uno','build/nucleo','preserved_records'):(OUT/folder).mkdir(parents=True)
    # Immutable reference hashes preserve all older archives without duplicating
    # gigabytes of previous build products or capture files.
    roots=[BASE/'preserved_records',ROOT/'artifacts/live_bench_20261028/no_motor_powered_AS5600_5hz_r1',ROOT/'artifacts/live_bench_20261028/dir_fixed_powered_5hz_r1']
    history={str(f.relative_to(ROOT)).replace('\\','/'):sha(f) for folder in roots for f in folder.rglob('*') if f.is_file()}
    write(OUT/'preserved_records/reference_sha256.json',json.dumps(history,indent=2)+'\n')
    m=dict(schema='mic_ai.i2c_wire_capture.v1',predecessor=str(BASE),pair_compatibility_ids=list(NEW),
      built=False,installed=False,selftest_pass=False,hardware_validated=False,initial_pwm_i2c_fixed_or_proven=False,
      passive_sampler=True,sample_timer='TIM4',dma='DMA2_Channel4',timer_hz=170000000,timer_period=20,
      nominal_sample_hz=8500000,samples=4096,nominal_history_us=4096/8.5,wire_record_bytes=1072,
      first_pwm_error_frozen=True,stream_only_outputs_off=True,sd_ring_samples=8192,sd_sample_hz=5000000,
      sd_gpio_access='WORD (unchanged)',sd_storage='BYTE (PA4/PA6 retained)',thresholds_changed=False,
      motor_control_changed=False,i2c_recovery_changed=False,i2c_timing_filters_changed=False,
      calibration_changed=False,rpc_libraries_changed=False,calibration_sha256=manifest['calibration_sha256'],
      archived_reference_files=len(history),previous_epoch_cache_retained=True)
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(prepared=True,pair=NEW,archived_references=len(history),hardware_commands=0)))
if __name__=='__main__':main()
