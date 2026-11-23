"""Prepare diagnostic capture before I2C reset; no hardware access."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
UNO=ROOT/'artifacts/live_bench_20261026/uart_rx_handoff_r1'
NUC=ROOT/'artifacts/live_bench_20261026/nucleo_as5600_r1'
OUT=ROOT/'artifacts/live_bench_20261026/i2c_first_fault_r1'
RES=ROOT/'tools/i2c_first_fault'
OLD=(2026102603,2026102602);NEW=(2026102605,2026102604)

def read(p):return p.read_text(encoding='utf-8-sig')
def write(p,s):p.write_text(s,encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def once(s,a,b):
    assert s.count(a)==1,a
    return s.replace(a,b)

def main():
    assert not (OUT/'manifest.json').exists(),'Preserve prepared package'
    for base in (UNO,NUC):
        m=json.loads(read(base/'manifest.json'));assert m['installed'] and m['built']
        for rel,digest in m['source_sha256'].items():assert sha(base/rel)==digest,rel
    for name,base in [('nucleo',NUC),('UNOQ_MOTOR',UNO),('web_hmi',UNO)]:
        def copy(src,dst):
            rel=Path(src).relative_to(base/name)
            if name=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                if not Path(dst).exists():os.link(src,dst)
                return dst
            return shutil.copy2(src,dst)
        shutil.copytree(base/name,OUT/name,copy_function=copy,dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                a=read(f);b=a.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if a!=b:write(f,b)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        shutil.copyfile(RES/'fault_wire.h',OUT/folder/'fault_wire.h')
    f=OUT/'nucleo/Inc/encoder_core.h';s=read(f)
    s=once(s,'  void (*reset)(void*);','  void (*reset)(void*);\n  void (*fault)(void*,uint8_t,uint32_t,uint32_t,uint32_t);')
    s=once(s,'  uint32_t us=(cycles-e->begin_cycles)/(hz/1000000U);',
        '  if(cause && io->fault)io->fault(io->ctx,cause,isr,ms,cycles);\n  uint32_t us=(cycles-e->begin_cycles)/(hz/1000000U);')
    write(f,s)
    f=OUT/'nucleo/Inc/nucleo_encoder.h';s=read(f)
    s=once(s,'#include <stdint.h>','#include <stdint.h>\n#include <stdbool.h>')
    s=once(s,'#endif','bool mic_encoder_fault_packet(uint8_t*,unsigned,unsigned);\n#endif');write(f,s)
    f=OUT/'nucleo/Src/nucleo_encoder.c';s=read(f)
    s=once(s,'#include "encoder_wire.h"','#include "encoder_wire.h"\n#include "fault_wire.h"')
    s=once(s,'static void reset(void*x){','static void capture_after_reset(void);\nstatic void capture_before_reset(void*,uint8_t,uint32_t,uint32_t,uint32_t);\nstatic void reset(void*x){')
    s=once(s,'__DSB();I2C1->CR2=0;clear(0);SET_BIT(I2C1->CR1,I2C_CR1_PE);',
        '__DSB();I2C1->CR2=0;clear(0);SET_BIT(I2C1->CR1,I2C_CR1_PE);\n  capture_after_reset();')
    s=once(s,'static ec_io io={0,status,begin_write,write_byte,begin_read,read_byte,clear,reset};',
        'static ec_io io={0,status,begin_write,write_byte,begin_read,read_byte,clear,reset,capture_before_reset};\n'+read(RES/'capture.inc'))
    s=once(s,'  ec_poll(&enc,&io,HAL_GetTick(),DWT->CYCCNT,SystemCoreClock);',
        '''  uint32_t cyc=DWT->CYCCNT;
  poll_gap=poll_seen?cyc-poll_previous_cycles:0U;
  if(poll_gap>poll_max_gap)poll_max_gap=poll_gap;
  poll_previous_cycles=cyc;poll_seen=true;
  uint32_t isr=I2C1->ISR,cr2=I2C1->CR2,gpio=GPIOB->IDR;
  ec_poll(&enc,&io,HAL_GetTick(),cyc,SystemCoreClock);
  previous_isr=isr;previous_cr2=cr2;previous_gpio=gpio;previous_cycles=cyc;''')
    write(f,s)
    f=OUT/'nucleo/Src/main.c';s=read(f)
    s=once(s,'#include "nucleo_encoder.h"','#include "nucleo_encoder.h"\n#include "fault_wire.h"')
    s=once(s,'static void uno_send_reply(void) {', '''static void mic_send_encoder_fault_page(uint32_t now_ms) {
  static uint32_t last_ms;static uint8_t page,slot;
  if(LL_TIM_IsEnabledAllOutputs(TIM1) || !uno_link.link_seen || (uint32_t)(now_ms-last_ms)<100U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_encoder_fault_packet(packet,slot,page)) {
    if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)!=HAL_OK)return;
    last_ms=now_ms;
  }
  if(++page==FC_PAGES){page=0;slot^=1U;}
}

static void uno_send_reply(void) {''')
    s=once(s,'    mic_send_encoder_page(HAL_GetTick());','    mic_send_encoder_page(HAL_GetTick());\n    mic_send_encoder_fault_page(HAL_GetTick());');write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=once(s,'#include "uno_encoder_adapter.h"','#include "uno_encoder_adapter.h"\n#include "fault_wire.h"\nstatic fc_receiver g_i2c_fault={};')
    s=once(s,'      if(buf[2]==EW_VERSION) {', '''      if(buf[2]==FC_WIRE) {
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry && !g_pwm_enabled && !(g_bp_status&0x22U) &&
            (uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)fc_receive(&g_i2c_fault,buf,g_bp_fw_build,off);continue;
      }
      if(buf[2]==EW_VERSION) {''')
    s=once(s,'    s += " enc_peer_good=";', '''    s += " enc_fault_good=";s += String((unsigned long)g_i2c_fault.good);
    s += " enc_fault_bad=";s += String((unsigned long)g_i2c_fault.bad);
    for(unsigned slot=0;slot<2;++slot){
      s += slot==0?" enc_fault_first_hex=":" enc_fault_pwm_hex=";
      if(!g_i2c_fault.slot[slot].valid)s += "-";
      else for(unsigned j=0;j<FC_BYTES;++j){
        uint8_t v=g_i2c_fault.slot[slot].bytes[j];const char *hex="0123456789abcdef";
        s += hex[v>>4];s += hex[v&15];
      }
    }
    s += " enc_peer_good=";''');write(f,s)
    f=OUT/'web_hmi/server.py';s=read(f)
    for a,b in [('(2026102603, 2026102602)','(2026102605, 2026102604)'),('(2026102603,2026102602)','(2026102605,2026102604)')]:s=s.replace(a,a+','+b)
    lines=[]
    for line in s.splitlines(keepends=True):
        if ('mc_fw_build' in line or 'elif peer not in' in line) and ('not in (' in line or ' in (' in line) and '(2026102603,' not in line and '(2026102603, ' not in line:
            line=line.replace(',2026102602)',',2026102602,2026102604)').replace(', 2026102602)',', 2026102602, 2026102604)')
        lines.append(line)
    s=''.join(lines)
    decoder=read(RES/'decoder.py').replace('import zlib\n','')
    s=once(s,'def with_zero_history(data):',decoder+'\n\ndef with_zero_history(data):')
    s=once(s,'data=with_zero_history(with_adc_peak(with_shunt_currents(data)))',
        'data=with_i2c_first_fault(with_zero_history(with_adc_peak(with_shunt_currents(data))))')
    s=once(s,'                "enc_peer_good":', '''                "enc_fault_first_hex": kv.get("enc_fault_first_hex","-"),
                "enc_fault_pwm_hex": kv.get("enc_fault_pwm_hex","-"),
                "enc_fault_good": int(kv.get("enc_fault_good","0")),
                "enc_fault_bad": int(kv.get("enc_fault_bad","0")),
                "enc_peer_good":''')
    ast.parse(s);write(f,s)
    f=OUT/'web_hmi/static/app.js';s=read(f)
    s=once(s,'      encVal.textContent = text;', '''      const faultRecords = Array.isArray(data.enc_fault_records) ? data.enc_fault_records : [];
      const faultRecord = faultRecords.find(x => x.kind === "first_with_pwm") || faultRecords[0];
      if (faultRecord) text += `; I²C ${faultRecord.cause}: снимок сохранён`;
      encVal.textContent = text;''');write(f,s)
    for folder in ('build/uno','build/nucleo','verification'):(OUT/folder).mkdir(parents=True,exist_ok=True)
    m=dict(schema='mic_ai.i2c_first_fault.v1',pair_compatibility_ids=list(NEW),built=False,selftest_pass=False,installed=False,
        predecessor_uno=str(UNO),predecessor_nucleo=str(NUC),capture_record_bytes=160,capture_slots=2,
        capture_before_reset=True,capture_delivery_outputs_off_only=True,capture_retained_until_mcu_reset=True,
        sensor_feedback_control=False,motor_control_changed=False,calibration_changed=False,thresholds_changed=False,
        uart_command_protocol_changed=False,bkin_changed=False,adc_trigger_changed=False,pwm_ccr123_changed=False,
        deadtime_changed=False,watchdogs_changed=False,i2c_recovery_policy_changed=False,
        nucleo_static_growth_budget_bytes=512,calibration_sha256=json.loads(read(NUC/'manifest.json'))['calibration_sha256'])
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(prepared=True,pair=NEW)))

if __name__=='__main__':main()
