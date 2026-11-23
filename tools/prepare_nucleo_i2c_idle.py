"""Prepare bounded, parked-idle I2C driver from verified2609/2604 sources."""
import ast
import json
import os
from pathlib import Path
import shutil
import prepare_i2c_first_fault as u

ROOT=u.ROOT
UNO=ROOT/'artifacts/live_bench_20261026/rpc_boot_retry_r1'
NUC=u.OUT
OUT=ROOT/'artifacts/live_bench_20261027/nucleo_i2c_idle_r1'
OLD=(2026102609,2026102604);NEW=(2026102701,2026102702)
RES=ROOT/'tools/nucleo_i2c_idle'
read,write,sha,once=u.read,u.write,u.sha,u.once

def core(s):
    s=once(s,'  void (*fault)(void*,uint8_t,uint32_t,uint32_t,uint32_t);',
        '  void (*fault)(void*,uint8_t,uint32_t,uint32_t,uint32_t);\n  uint8_t (*lines)(void*);\n  void (*enable)(void*);\n  void (*park)(void*);\n  void (*clear_berr)(void*);')
    s=once(s,'  float rpm;','''  float rpm;
  uint32_t free_since_cycles,busy_waits,berr_clears,parks;
  uint8_t prepare;
  bool have_free_since;
''')
    s=once(s,'  e->state=0;e->sample_ms=ms;', '  e->state=0;e->prepare=0;e->have_free_since=false;e->sample_ms=ms;')
    s=once(s,'    io->clear(io->ctx);ec_inc32(&e->reads);e->stage=0;',
        '    io->clear(io->ctx);io->park(io->ctx);ec_inc32(&e->parks);ec_inc32(&e->reads);e->stage=0;')
    a=s.index('  if(!e->state){',s.index('static inline void ec_poll'))
    b=s.index('  if(cause){',a)
    s=s[:a]+'''  // Missing platform hooks cannot silently bypass physical-bus checks.
  if(!io->lines||!io->enable||!io->park||!io->clear_berr){
    e->configured=0;e->cause=EC_SETUP;e->bus_ok=false;e->angle_ok=false;ec_speed_reset(e);return;
  }
  if(!e->state && !e->prepare){
    uint32_t interval=e->cause?20U:5U;
    if((uint32_t)(ms-e->last_start_ms)<interval)return;
    e->last_start_ms=ms;e->begin_cycles=cycles;e->stage=4;
    e->prepare=1;e->have_free_since=false;
    if(isr&EC_BUSYF)ec_inc32(&e->busy_waits);
  }
  if(!e->state && e->prepare){
    // The original3ms acquisition budget includes the entire preflight.
    // Every call is one bounded step; never spin or drive SCL/SDA manually.
    if((uint32_t)(cycles-e->begin_cycles)>=e->budget_cycles ||
        (uint32_t)(ms-e->last_start_ms)>=3U){
      ec_finish(e,io,ms,cycles,hz,EC_BUSY,isr);return;
    }
    const bool high=io->lines(io->ctx)==3U;
    if(!high || (e->prepare==2 && (isr&EC_BUSYF))){e->have_free_since=false;return;}
    if(!e->have_free_since){e->have_free_since=true;e->free_since_cycles=cycles;return;}
    // At least2us and two observations with both lines HIGH. The sampled
    // level check does not claim to measure sub-poll electrical glitches.
    if((uint32_t)(cycles-e->free_since_cycles)<(hz/1000000U)*2U)return;
    e->have_free_since=false;
    if(e->prepare==1){io->enable(io->ctx);e->prepare=2;return;}
    io->clear(io->ctx);memset(e->bytes,0,3);e->n=0;
    io->begin_write(io->ctx);e->prepare=0;e->state=1;return;
  }
  uint8_t cause=(isr&EC_ARLOF)?EC_ARLO:(isr&EC_NACKF)?EC_NACK:
      (isr&EC_OVRF)?EC_OVR:EC_NONE;
'''+s[b:]
    s=once(s,'  if(e->state==1 && (isr&EC_TXIS)){','''  // Fatal errors/deadline were captured above before any flag clearing.
  // ES0431 section2.11.2: sole master BERR is cleared; transfer continues.
  if(isr&EC_BERR){io->clear_berr(io->ctx);ec_inc32(&e->berr_clears);isr&=~EC_BERR;}
  if(e->state==1 && (isr&EC_TXIS)){''')
    return s

def driver(s):
    a=s.index('static void reset(void*x){');b=s.index('static void begin_write',a)
    s=s[:a]+'''static uint8_t lines(void*x){(void)x;return (uint8_t)((GPIOB->IDR>>8)&3U);}
static void enable(void*x){(void)x;SET_BIT(I2C1->CR1,I2C_CR1_PE);(void)I2C1->CR1;__DSB();}
static void park(void*x){
  (void)x;CLEAR_BIT(I2C1->CR1,I2C_CR1_PE);(void)I2C1->CR1;__DSB();I2C1->CR2=0;
  // PE stays LOW until nonblocking preflight observes HIGH twice, >=2us
  // apart. This exceeds the RM0440 minimum of three APB clock cycles.
}
static void clear_berr(void*x){(void)x;I2C1->ICR=I2C_ICR_BERRCF;}
static void reset(void*x){park(x);clear(x);capture_after_reset();}
'''+s[b:]
    s=once(s,'static ec_io io={0,status,begin_write,write_byte,begin_read,read_byte,clear,reset,capture_before_reset};',
        'static ec_io io={0,status,begin_write,write_byte,begin_read,read_byte,clear,reset,capture_before_reset,lines,enable,park,clear_berr};')
    s=once(s,'      (GPIOB->AFR[1]&255U)==0x44U && (I2C1->CR1&I2C_CR1_PE)!=0 &&',
        '''      (GPIOB->AFR[1]&255U)==0x44U &&
      ((I2C1->CR1&I2C_CR1_PE)!=0)==(enc.state!=0 || enc.prepare==2) &&
      (I2C1->CR1&(I2C_CR1_ANFOFF|I2C_CR1_DNF))==(2U<<I2C_CR1_DNF_Pos) &&''')
    s=once(s,'    clear(0);SET_BIT(I2C1->CR1,I2C_CR1_PE);','    clear(0); // Remain parked until the first bounded acquisition.')
    return s

def main():
    assert not (OUT/'manifest.json').exists(),'Preserve candidate'
    for base in (UNO,NUC):
        m=json.loads(read(base/'manifest.json'));assert m['installed'] and m['built']
        for rel,digest in m['source_sha256'].items():assert sha(base/rel)==digest,rel
    for name,base in [('nucleo',NUC),('UNOQ_MOTOR',UNO),('web_hmi',UNO),('libraries',UNO)]:
        def copier(src,dst):
            rel=Path(src).relative_to(base/name)
            if name=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(base/name,OUT/name,copy_function=copier,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                a=read(f);b=a.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if a!=b:write(f,b)
    f=OUT/'nucleo/Inc/encoder_core.h';write(f,core(read(f)))
    f=OUT/'nucleo/Src/nucleo_encoder.c';write(f,driver(read(f)))
    # Format2 truthfully reports the current PE bit, including parked PE0.
    # A valid cached acquisition depends on config/freshness/CRC, not on
    # whether the next transfer is currently active. Old/mixed peers reject.
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        f=OUT/folder/'encoder_wire.h';s=read(f)
        s=once(s,'EW_FORMAT=1','EW_FORMAT=2')
        s=once(s,'(f[3]&8U) && f[37]==1U && ew_u16(f+10)<EW_TTL_MS','(f[3]&8U) && ew_u16(f+10)<EW_TTL_MS')
        write(f,s)
    f=OUT/'UNOQ_MOTOR/uno_encoder_adapter.h';s=read(f)
    s=once(s,'s.diag_cfg_match=((p[3]&8U)&&p[37]==1)?1:0;','s.diag_cfg_match=(p[3]&8U)?1:0; // Format2: valid parked engine may have PE0.')
    write(f,s)
    f=OUT/'web_hmi/server.py';s=read(f)
    for a,b in [('(2026102609, 2026102604)','(2026102701, 2026102702)'),('(2026102609,2026102604)','(2026102701,2026102702)')]:s=s.replace(a,a+','+b)
    lines=[]
    for line in s.splitlines(keepends=True):
        if ('mc_fw_build' in line or 'elif peer not in' in line) and ('not in (' in line or ' in (' in line) and '(2026102609,' not in line and '(2026102609, ' not in line:
            line=line.replace(',2026102604)',',2026102604,2026102702)').replace(', 2026102604)',', 2026102604, 2026102702)')
        lines.append(line)
    s=''.join(lines)
    s=once(s,'peer!=2026102604','peer not in (2026102604,2026102702)')
    ast.parse(s);write(f,s)
    for folder in ('build/uno','build/nucleo','verification'):(OUT/folder).mkdir(parents=True)
    m=dict(schema='mic_ai.nucleo_i2c_idle.v1',pair_compatibility_ids=list(NEW),built=False,selftest_pass=False,installed=False,
        predecessor_uno=str(UNO),predecessor_nucleo=str(NUC),i2c_recovery_policy_changed=True,
        encoder_wire_format=2,encoder_idle_pe_disabled=True,preflight_nonblocking=True,
        acquisition_budget_ms=3,sample_interval_ms=5,error_backoff_ms=20,
        berr_master_clear_continue=True,capture_before_reset=True,capture_record_bytes=160,capture_slots=2,
        capture_delivery_outputs_off_only=True,hardware_validated=False,sensor_under_pwm_qualified=False,
        sensor_feedback_control=False,motor_control_changed=False,thresholds_changed=False,calibration_changed=False,
        uart_command_protocol_changed=False,bkin_changed=False,adc_trigger_changed=False,pwm_ccr123_changed=False,
        deadtime_changed=False,watchdogs_changed=False,rpc_libraries_unchanged=True,
        observed_primary_physical_cause_proven=False,calibration_sha256=json.loads(read(UNO/'manifest.json'))['calibration_sha256'])
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(prepared=True,pair=NEW)))
if __name__=='__main__':main()
