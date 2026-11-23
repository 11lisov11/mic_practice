"""U585 errata-aware recovery, transparent error events and filtered mode."""
import json
import shutil
import prepare_current_shunt_monitor as u
ROOT=u.ROOT
BASE=ROOT/'artifacts/live_bench_20261025/as5600_poll_schedule_r1'
HMI=ROOT/'artifacts/live_bench_20261025/as5600_poll_schedule_hmi_r1'
OUT=ROOT/'artifacts/live_bench_20261025/as5600_recovery_r1'
RES=ROOT/'tools/as5600_recovery'
FIELDS=('berr_count','arlo_count','busy_count','graceful_cleanups','post_reset_busy','kernel_hz','timingr','cr1','event_count')
def main():
    if (OUT/'manifest.json').exists():
        prev=json.loads(u.read(OUT/'manifest.json'));assert not prev['installed'] and not prev['built']
    m=json.loads(u.read(BASE/'manifest.json'));hm=json.loads(u.read(HMI/'manifest.json'))
    assert m['installed'] and m['installation_runtime_pair_verified'] and hm['installed'] and hm['runtime_verified']
    for parent,manifest in [(BASE,m),(HMI,hm)]:
        for rel,digest in manifest['source_sha256'].items():assert u.sha(parent/rel)==digest,rel
    for tree in ('UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    shutil.copyfile(HMI/'web_hmi/server.py',OUT/'web_hmi/server.py')
    sk=OUT/'UNOQ_MOTOR'
    shutil.copyfile(RES/'reader.h',sk/'as5600_poll_reader.h');shutil.copyfile(RES/'timing.h',sk/'as5600_filter_timing.h')
    p=sk/'as5600_teacher.cpp';s=u.read(p)
    s=u.once(s,'#include "as5600_poll_section.h"','#include "as5600_poll_section.h"\n#include "as5600_filter_timing.h"\n#include <zephyr/drivers/clock_control/stm32_clock_control.h>\n#include <zephyr/drivers/clock_control.h>')
    s=u.once(s,'K_THREAD_STACK_DEFINE(sensor_stack, 2048);','K_THREAD_STACK_DEFINE(sensor_stack, 4096);')
    s=u.once(s,'uint8_t requested_mode = 4, active_mode = 255;','uint8_t requested_mode = 5, active_mode = 255;')
    begin=s.index('struct PollSchedule {');end=s.index('\nint configure(',begin)
    s=s[:begin]+u.read(RES/'adapter.inc')+'\n'+s[end:]
    s=u.once(s,'if (mode == 0 || mode == 3 || mode == 4) {','if (mode == 0 || mode == 3 || mode == 4 || mode == 5) {')
    s=u.once(s,'    rc=i2c_configure(bus, I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_STANDARD));',
        '    LL_I2C_EnableAnalogFilter(I2C2);LL_I2C_SetDigitalFilter(I2C2,0);\n    rc=i2c_configure(bus, I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_STANDARD));')
    s=u.once(s,'    if (!rc && mode==4) PollIo::claim();',
        '    if(!rc && mode==5){\n      const auto timing=encfix::standard_filtered(as5600_kernel_clock());\n'
        '      if(!timing.valid)return -ERANGE;\n      LL_I2C_SetDigitalFilter(I2C2,timing.dnf);LL_I2C_SetTiming(I2C2,timing.word);\n    }\n'
        '    if (!rc && (mode==4||mode==5)) PollIo::claim();')
    s=u.once(s,'  uint32_t sections=0,max_hold_us=0;',
        '  uint32_t sections=0,max_hold_us=0,berrs=0,arlos=0,busy=0,cleanups=0,reset_busy=0;\n'
        '  uint32_t events[4][8]={},event_count=0;\n  encdiag::PollResult last_poll;')
    s=u.once(s,'    else if (mode == 4) {','    else if (mode == 4 || mode == 5) {')
    anchor='      diag=result.transfer; isr=result.error_isr;'
    s=u.once(s,anchor,anchor+'\n      last_poll=result;\n'
        '      berrs=UINT32_MAX-berrs<result.berr_events?UINT32_MAX:berrs+result.berr_events;\n'
        '      if(diag.cause==encdiag::ARBITRATION && arlos!=UINT32_MAX)++arlos;\n'
        '      if(diag.cause==encdiag::BUS_BUSY && busy!=UINT32_MAX)++busy;\n'
        '      if(result.graceful_cleanup && cleanups!=UINT32_MAX)++cleanups;\n'
        '      if(result.controller_reset && (result.post_isr&encdiag::BUSY) && reset_busy!=UINT32_MAX)++reset_busy;')
    anchor='    if (error) {\n      last_error_ms = now;'
    s=u.once(s,anchor,'''    if(!setup&&(mode==4||mode==5)&&(error||last_poll.berr_events)&&event_count<4){
      const bool advisory=!error;uint32_t *e=events[event_count++];e[0]=now;e[1]=mode|(advisory?256U:0U);
      e[2]=diag.stage;e[3]=advisory?8U:diag.cause;e[4]=advisory?last_poll.first_berr_isr:isr;
      e[5]=advisory?last_poll.first_berr_cr2:last_poll.error_cr2;e[6]=advisory?last_poll.first_berr_lines:last_poll.error_lines;e[7]=last_poll.post_isr;
    }
    if (error) {
      last_error_ms = now;''')
    anchor='    sample.diag_sched_sections=sections;sample.diag_sched_max_hold_us=max_hold_us;'
    s=u.once(s,anchor,anchor+'\n'
        '    sample.diag_berr_count=berrs;sample.diag_arlo_count=arlos;sample.diag_busy_count=busy;\n'
        '    sample.diag_graceful_cleanups=cleanups;sample.diag_post_reset_busy=reset_busy;\n'
        '    sample.diag_kernel_hz=as5600_kernel_clock();sample.diag_timingr=I2C2->TIMINGR;sample.diag_cr1=I2C2->CR1;\n'
        '    sample.diag_event_count=event_count;for(unsigned e=0;e<event_count;++e)for(unsigned w=0;w<8;++w)sample.diag_events[e][w]=events[e][w];')
    s=u.once(s,'  if (mode > 4 || !started) return false;','  if (mode > 5 || !started) return false;');u.write(p,s)
    p=sk/'as5600_teacher.h';s=u.read(p)
    s=u.once(s,'  float rpm = 0.0f;','  float rpm = 0.0f;\n'+''.join(f'  uint32_t diag_{f}=0;\n' for f in FIELDS)+'  uint32_t diag_events[4][8]={};');u.write(p,s)
    p=sk/'UNOQ_MOTOR.ino';s=u.read(p)
    s=u.once(s,'FW_BUILD_ID = 2026102517U;','FW_BUILD_ID = 2026102518U;')
    s=u.once(s,'  else if (icmp(arg, "POLL100")) mode = 4;','  else if (icmp(arg, "POLL100")) mode = 4;\n  else if (icmp(arg, "FILTER100")) mode = 5;')
    anchor='    s += " enc_diag_mode="; s += String((unsigned long)g_as5600.diag_mode);'
    telemetry=''.join(f'    s += " enc_diag_{f}="; s += String((unsigned long)g_as5600.diag_{f});\n' for f in FIELDS)
    telemetry+='''    s += " enc_diag_events_hex=";
    if(!g_as5600.diag_event_count)s += "-";
    else for(unsigned e=0;e<g_as5600.diag_event_count&&e<4;++e)for(unsigned w=0;w<8;++w){
      String hex=String((unsigned long)g_as5600.diag_events[e][w],HEX);
      for(unsigned n=hex.length();n<8;++n)s += '0';s += hex;
    }'''
    s=u.once(s,anchor,anchor+'\n'+telemetry);u.write(p,s)
    p=OUT/'web_hmi/server.py';s=u.read(p)
    for a,b in [('(2026102517, 2026102510)','(2026102517, 2026102510), (2026102518, 2026102510)'),
                ('(2026102517,2026102510)','(2026102517,2026102510),(2026102518,2026102510)')]:
        assert a in s;s=s.replace(a,b)
    anchor='                "enc_diag_mode": int(float(kv.get("enc_diag_mode", "0"))),'
    s=u.once(s,anchor,anchor+'\n'+''.join(f'                "enc_diag_{f}": int(kv.get("enc_diag_{f}", "0")),\n' for f in FIELDS)+'                "enc_diag_events_hex": kv.get("enc_diag_events_hex", "-"),');u.write(p,s)
    (OUT/'build/uno').mkdir(parents=True,exist_ok=True)
    manifest=dict(schema='mic_ai.as5600_recovery.v1',predecessor=str(BASE),hmi_predecessor=str(HMI),pair_compatibility_ids=[2026102518,2026102510],
        built=False,selftest_pass=False,installed=False,hardware_validated=False,uno_only=True,nucleo_firmware_unchanged=True,
        calibration_changed=False,thresholds_changed=False,motor_control_changed=False,uart_protocol_changed=False,sd_capture_changed=False,sensor_feedback_control=False,
        calibration_sha256=m['calibration_sha256'],mode_map={'4':'POLL100 corrected recovery/native timing','5':'FILTER100 corrected recovery/ANF+DNF with conservative recalculated timing'},
        event_layout=['tick_ms','mode|256_if_BERR_only_completed_advisory','stage','cause','raw_ISR','raw_CR2','GPIO_SCL_bit0_SDA_bit1_before_cleanup','ISR_after_cleanup'],
        limitations=['Physical PWM NACK source not proven','Filter assumes standard-mode rise<=1000ns/fall<=300ns, not electrically measured','BERR erratum workaround does not waive NACK/ARLO/OVR/deadline or full3byte STOP requirement'],
        source_sha256={str(x.relative_to(OUT)).replace('\\','/'):u.sha(x) for tree in ('UNOQ_MOTOR','web_hmi') for x in (OUT/tree).rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.suffix!='.pyc'})
    u.write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n');print(OUT)
if __name__=='__main__':main()
