"""Prepare fully audited nonblocking NACK/STOP recovery, no hardware access."""
import ast
import json
import os
from pathlib import Path
import shutil
import prepare_nucleo_i2c_idle as old

ROOT=old.ROOT;BASE=old.OUT
OUT=ROOT/'artifacts/live_bench_20261027/nucleo_i2c_stop_recovery_r1'
RES=ROOT/'tools/nucleo_i2c_stop'
OLD=(2026102701,2026102702);NEW=(2026102703,2026102704)
read,write,sha,once=old.read,old.write,old.sha,old.once

def core(s):
    s=once(s,'  if(!e->configured)return;','  if(!e->configured && !e->recovering)return;')
    s=once(s,'#include <string.h>','#include <string.h>\n#include "cleanup_flags.h"')
    s=once(s,'  void (*clear_berr)(void*);','''  void (*clear_berr)(void*);
  void (*clear_nack)(void*);
  bool (*stop_ready)(void*);
  void (*request_stop)(void*);
  void (*flush_tx)(void*);
  void (*terminal)(void*,uint8_t);
''')
    s=once(s,'  uint8_t prepare;','''  uint32_t abort_cycles;
  uint32_t primary_nack,primary_busy,primary_arlo,primary_ovr,primary_short,primary_setup;
  uint32_t clean_stops,forced_resets,stop_requests,cleanup_expired;
  uint8_t recovering,cleanup_flags;
  uint8_t prepare;''')
    a=s.index('static inline void ec_finish(');b=s.index('static inline void ec_poll(',a)
    s=s[:a]+read(RES/'recovery.inc')+'\n'+s[b:]
    s=once(s,'  if(!io->lines||!io->enable||!io->park||!io->clear_berr){',
        '  if(!io->lines||!io->enable||!io->park||!io->clear_berr||!io->clear_nack||\n      !io->stop_ready||!io->request_stop||!io->flush_tx||!io->terminal){')
    s=once(s,'  if(!e->state && !e->prepare){',
        '  if(e->recovering){ec_recover(e,io,ms,cycles,hz,isr);return;}\n  if(!e->state && !e->prepare){')
    s=once(s,'<(hz/1000000U)*2U','<(hz/1000000U)*EC_FREE_US')
    s=once(s,'  if(e->state==1 && (isr&EC_TXIS)){',
        '  if((isr&EC_RXNE) && e->state!=3){ec_finish(e,io,ms,cycles,hz,EC_SHORT,isr);return;}\n  if(e->state==1 && (isr&EC_TXIS)){')
    s=s.replace('// At least2us and two observations with both lines HIGH. The sampled',
                '// At least5us and two observations with both lines HIGH. The sampled')
    return s

def driver(s):
    s=once(s,'static void capture_after_reset(void);','static void capture_terminal(void*,uint8_t);')
    s=once(s,'static void reset(void*x){park(x);clear(x);capture_after_reset();}', '''static void flush_tx(void*x){(void)x;I2C1->ISR=I2C_ISR_TXE;}
static void clear_nack(void*x){(void)x;I2C1->ICR=I2C_ICR_NACKCF;}
static bool stop_ready(void*x){(void)x;return (I2C1->CR2&(I2C_CR2_START|I2C_CR2_STOP))==0;}
static void request_stop(void*x){(void)x;SET_BIT(I2C1->CR2,I2C_CR2_STOP);}
static void reset(void*x){park(x);clear(x);flush_tx(x);}''')
    s=once(s,'capture_before_reset,lines,enable,park,clear_berr};',
        'capture_before_reset,lines,enable,park,clear_berr,clear_nack,stop_ready,request_stop,flush_tx,capture_terminal};')
    s=once(s,'static void capture_after_reset(void){','static void capture_terminal(void*ctx,uint8_t flags){\n  (void)ctx;')
    s=once(s,'    uint32_t *r=fault_record[slot];r[35]=isr;',
        '    uint32_t *r=fault_record[slot];r[4]|=(uint32_t)flags<<26;r[35]=isr;')
    # Config failure is a bounded fault, preserving the pre-recovery registers.
    s=once(s,'    enc.configured=0;enc.cause=EC_SETUP;enc.bus_ok=false;enc.angle_ok=false;ec_speed_reset(&enc);',
        '    ec_finish(&enc,&io,HAL_GetTick(),DWT->CYCCNT,SystemCoreClock,EC_SETUP,I2C1->ISR);\n    enc.configured=0;')
    s+= '\n'+read(RES/'health_producer.inc')
    return s

def main():
    assert not (OUT/'manifest.json').exists(),'Preserve candidate'
    m=json.loads(read(BASE/'manifest.json'));assert m['installed'] and m['built']
    for rel,digest in m['source_sha256'].items():assert sha(BASE/rel)==digest,rel
    for name in ('nucleo','UNOQ_MOTOR','web_hmi','libraries'):
        def copier(src,dst):
            rel=Path(src).relative_to(BASE/name)
            if name=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/name,OUT/name,copy_function=copier,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                a=read(f);b=a.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if a!=b:write(f,b)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        shutil.copyfile(RES/'cleanup_flags.h',OUT/folder/'cleanup_flags.h')
        shutil.copyfile(RES/'encoder_health_wire.h',OUT/folder/'encoder_health_wire.h')
    f=OUT/'nucleo/Inc/encoder_core.h';write(f,core(read(f)))
    f=OUT/'nucleo/Src/nucleo_encoder.c';write(f,driver(read(f)))
    f=OUT/'nucleo/Inc/nucleo_encoder.h';s=read(f);s=once(s,'#endif',
        'void mic_encoder_health_snapshot(uint32_t*);\n#endif');write(f,s)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        f=OUT/folder/'fault_wire.h';s=read(f)
        s=once(s,'FC_FORMAT=1','FC_FORMAT=2')
        s=once(s,'(meta>>24)<=3','((meta>>24)&3U)<=3')
        write(f,s)
    f=OUT/'nucleo/Src/main.c';s=read(f)
    s=once(s,'#include "fault_wire.h"','#include "fault_wire.h"\n#include "encoder_health_wire.h"')
    s=once(s,'static void uno_send_reply(void) {',read(RES/'health_sender.inc')+'\nstatic void uno_send_reply(void) {')
    s=once(s,'    mic_send_encoder_fault_page(HAL_GetTick());','    mic_send_encoder_fault_page(HAL_GetTick());\n    mic_send_encoder_health_page(HAL_GetTick());');write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=once(s,'static fc_receiver g_i2c_fault={};',
        'static fc_receiver g_i2c_fault={};\n#include "encoder_health_wire.h"\nstatic eh_receiver g_encoder_health={};')
    s=once(s,'      if(buf[2]==FC_WIRE) {',read(RES/'health_rx.inc')+'\n      if(buf[2]==FC_WIRE) {')
    s=once(s,'    s += " enc_diag_category_counts_available=0";',read(RES/'health_text.inc'))
    for name,index in [('berr_count',7),('arlo_count',3),('busy_count',2),('graceful_cleanups',8),('nack_count',0)]:
        a='String((unsigned long)g_as5600.diag_'+name+')'
        s=once(s,a,'String((unsigned long)(health_valid?g_encoder_health.values['+str(index)+']:0))')
    s=once(s,'  const uint32_t poll_ms = millis();','  const uint32_t poll_ms = millis();\n  if(g_pwm_enabled || (g_bp_status&0x22U) || !g_bp_mcsdk_telemetry || g_bp_fw_build!=EH_PEER || (uint32_t)(poll_ms-g_bp_last_rsp_ms)>=300U){g_encoder_health.valid=false;g_encoder_health.mask=0;}')
    write(f,s)
    f=OUT/'web_hmi/server.py';s=read(f)
    for a,b in [('(2026102701, 2026102702)','(2026102703, 2026102704)'),('(2026102701,2026102702)','(2026102703,2026102704)')]:s=s.replace(a,a+','+b)
    lines=[]
    for line in s.splitlines(keepends=True):
        if ('mc_fw_build' in line or 'elif peer not in' in line) and ('not in (' in line or ' in (' in line) and '(2026102701,' not in line and '(2026102701, ' not in line:
            line=line.replace(',2026102702)',',2026102702,2026102704)').replace(', 2026102702)',', 2026102702, 2026102704)')
        lines.append(line)
    s=''.join(lines)
    s=once(s,'peer not in (2026102604,2026102702)','peer not in (2026102604,2026102702,2026102704)')
    s=once(s,'n=w[4]>>24','n=((w[4]>>24)&3) if peer==2026102704 else w[4]>>24')
    s=once(s,"    return result\n\ndef with_i2c_first_fault",read(RES/'decode_cleanup.inc')+"    return result\n\ndef with_i2c_first_fault")
    s=once(s,'                "enc_fault_first_hex":',read(RES/'health_hmi.inc')+'                "enc_fault_first_hex":')
    ast.parse(s);write(f,s)
    for folder in ('build/uno','build/nucleo','verification'):(OUT/folder).mkdir(parents=True)
    m=dict(schema='mic_ai.nucleo_i2c_stop_recovery.v1',pair_compatibility_ids=list(NEW),built=False,selftest_pass=False,installed=False,
        predecessor=str(BASE),sensor_feedback_control=False,motor_control_changed=False,thresholds_changed=False,
        calibration_changed=False,uart_command_protocol_changed=False,bkin_changed=False,adc_trigger_changed=False,
        pwm_ccr123_changed=False,deadtime_changed=False,watchdogs_changed=False,rpc_libraries_unchanged=True,
        data_acquisition_budget_ms=3,cleanup_budget_us=500,nack_auto_stop_grace_us=100,error_backoff_ms=20,
        cleanup_nonblocking=True,no_same_sample_retry=True,no_gpio_bus_pulses=True,capture_bytes=160,capture_format=2,
        health_delivery_outputs_off_only=True,sensor_under_pwm_qualified=False,hardware_validated=False,
        primary_nack_physical_cause_proven=False,calibration_sha256=m['calibration_sha256'])
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(prepared=True,pair=NEW)))
if __name__=='__main__':main()
