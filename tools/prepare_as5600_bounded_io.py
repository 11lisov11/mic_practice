"""One Uno-only candidate: bounded peripheral reader and local timed STOP."""
import json
import shutil
import prepare_current_shunt_monitor as u

ROOT=u.ROOT
BASE=ROOT/'artifacts/live_bench_20261025/as5600_software_regression_r1'
OUT=ROOT/'artifacts/live_bench_20261025/as5600_bounded_io_r1'
RES=ROOT/'tools/as5600_bounded_io'
FIELDS=('isr','last_isr','controller_resets','timeout_count','nack_count')
RUN_FIELDS=('id','start_ms','stop_ms','limit_ms','reason')

def main():
    if (OUT/'manifest.json').exists():
        previous=json.loads(u.read(OUT/'manifest.json'))
        assert not previous['installed'] and not previous['built'], 'Preserve sealed candidate'
    m=json.loads(u.read(BASE/'manifest.json'))
    assert m['installed'] and m['installation_readback_verified']
    for rel,digest in m['source_sha256'].items():assert u.sha(BASE/rel)==digest,rel
    for tree in ('UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    sk=OUT/'UNOQ_MOTOR'
    for src,dst in [('poll_reader.h','as5600_poll_reader.h'),('timed_run.h','timed_run.h')]:
        shutil.copyfile(RES/src,sk/dst)
    p=sk/'as5600_teacher.h';s=u.read(p)
    s=u.once(s,'  float rpm = 0.0f;','  float rpm = 0.0f;\n'+''.join(f'  uint32_t diag_{f}=0;\n' for f in FIELDS).rstrip())
    u.write(p,s)
    p=sk/'as5600_teacher.cpp';s=u.read(p)
    s=u.once(s,'#include "as5600_i2c_reader.h"','#include "as5600_i2c_reader.h"\n#include "as5600_poll_reader.h"')
    s=u.once(s,'uint8_t requested_mode = 0, active_mode = 255;','uint8_t requested_mode = 4, active_mode = 255;')
    adapter=u.read(RES/'poll_adapter.inc')
    s=u.once(s,'int configure(const device *bus, GpioIo &io, uint8_t mode,',adapter+'\nint configure(const device *bus, GpioIo &io, uint8_t mode,')
    s=u.once(s,'  if (mode == 0 || mode == 3) {','  if (mode == 0 || mode == 3 || mode == 4) {')
    s=u.once(s,'    return i2c_configure(bus, I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_STANDARD));',
        '    rc=i2c_configure(bus, I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_STANDARD));\n'
        '    if (!rc && mode==4) PollIo::claim();\n    return rc;')
    s=u.once(s,'  encdiag::Reader<GpioIo> reader(io);','  encdiag::Reader<GpioIo> reader(io);\n  PollIo poll_io;\n  encdiag::PollReader<PollIo> poll(poll_io);\n  uint32_t resets=0,timeouts=0,nacks=0,last_isr=0;')
    s=u.once(s,'    int error = setup;','    uint32_t isr=0;\n    int error = setup;')
    s=u.once(s,'    else if (mode == 0 || mode == 3) {',
        '    else if (mode == 4) {\n'
        '      const auto result=poll.read(bytes); diag=result.transfer; isr=result.error_isr;\n'
        '      error=diag.cause==encdiag::NONE ? 0 : -EIO;\n'
        '      if(result.controller_reset && resets!=UINT32_MAX)++resets;\n'
        '      if(diag.cause==encdiag::DEADLINE && timeouts!=UINT32_MAX)++timeouts;\n'
        '      if(diag.cause==encdiag::NACK && nacks!=UINT32_MAX)++nacks;\n'
        '      if(error)last_isr=isr;\n'
        '    }\n    else if (mode == 0 || mode == 3) {')
    s=u.once(s,'    sample.diag_mode = mode;',
        '    sample.diag_isr=isr; sample.diag_last_isr=last_isr;\n'
        '    sample.diag_controller_resets=resets;sample.diag_timeout_count=timeouts;sample.diag_nack_count=nacks;\n'
        '    sample.diag_mode = mode;')
    s=u.once(s,'  if (mode > 3 || !started) return false;','  if (mode > 4 || !started) return false;')
    u.write(p,s)
    p=sk/'UNOQ_MOTOR.ino';s=u.read(p)
    s=u.once(s,'FW_BUILD_ID = 2026102515U;','FW_BUILD_ID = 2026102516U;')
    s=u.once(s,'#include "uno_q_control.h"','#include "uno_q_control.h"\n#include "timed_run.h"')
    s=u.once(s,'static uint32_t g_run_limit_ms = 0;','static uint32_t g_run_limit_ms = 0;\nstatic TimedRun g_timed_run;')
    s=u.once(s,'  else if (icmp(arg, "LEGACY")) mode = 3;','  else if (icmp(arg, "LEGACY")) mode = 3;\n  else if (icmp(arg, "POLL100")) mode = 4;')
    anchor='    s += " enc_diag_mode="; s += String((unsigned long)g_as5600.diag_mode);'
    telemetry=''.join(f'    s += " enc_diag_{f}="; s += String((unsigned long)g_as5600.diag_{f});\n' for f in FIELDS)
    telemetry+=''.join(f'    s += " run_{f}="; s += String((unsigned long)g_timed_run.{f});\n' for f in RUN_FIELDS)
    telemetry+='    s += " run_elapsed_ms="; s += String((unsigned long)g_timed_run.elapsed(millis()));'
    s=u.once(s,anchor,anchor+'\n'+telemetry)
    anchor='  const bool outputs_were_active = g_pwm_enabled || g_pwm_outputs_active || g_state != STATE_SAFE;'
    s=u.once(s,anchor,anchor+'\n  g_timed_run.finish(millis(),TimedRun::STOP);')
    old='''  if (g_pwm_enabled && g_run_deadline_ms != 0U && (int32_t)(now_ms - g_run_deadline_ms) >= 0) {
    g_estop_latched = true;
    g_fault = 4;
    brake_set(false);
    hard_stop(true);
    ext_brake_set(0.0f);
    pwm_write(0, 0, 0);
    return;
  }'''
    new='''  if (g_pwm_enabled && g_run_deadline_ms != 0U && (int32_t)(now_ms - g_run_deadline_ms) >= 0) {
    // A finite run completing is normal STOP; genuine ESTOP/SD/UART paths above remain.
    g_timed_run.finish(now_ms,TimedRun::LIMIT);
    request_normal_stop();
    return;
  }'''
    s=u.once(s,old,new)
    anchor='''      g_run_deadline_ms = (g_run_limit_ms > 0U) ?
          unoq_bounded_run_deadline(millis(), g_run_limit_ms, 0U, START_REQUIRE_RUN_LIMIT) : 0U;'''
    s=u.once(s,anchor,'''      const uint32_t run_begin_ms=millis();
      g_run_deadline_ms = (g_run_limit_ms > 0U) ?
          unoq_bounded_run_deadline(run_begin_ms, g_run_limit_ms, 0U, START_REQUIRE_RUN_LIMIT) : 0U;
      g_timed_run.start(run_begin_ms,g_run_limit_ms);''')
    anchor='''    g_run_deadline_ms = unoq_bounded_run_deadline(millis(), g_run_limit_ms,
        g_run_deadline_ms, START_REQUIRE_RUN_LIMIT);'''
    s=u.once(s,anchor,anchor+'\n    g_timed_run.limit_ms=uint32_t(g_run_deadline_ms-g_timed_run.start_ms);')
    u.write(p,s)
    p=OUT/'web_hmi/server.py';s=u.read(p)
    for old,new in [('(2026102515, 2026102510)','(2026102515, 2026102510), (2026102516, 2026102510)'),
                    ('(2026102515,2026102510)','(2026102515,2026102510),(2026102516,2026102510)')]:
        assert old in s;s=s.replace(old,new)
    anchor='                "enc_diag_mode": int(float(kv.get("enc_diag_mode", "0"))),'
    s=u.once(s,anchor,anchor+'\n'+''.join(f'                "enc_diag_{f}": int(kv.get("enc_diag_{f}", "0")),\n' for f in FIELDS)+''.join(
        f'                "run_{f}": int(kv.get("run_{f}", "0")),\n' for f in (*RUN_FIELDS,'elapsed_ms')).rstrip())
    s=u.once(s,'def manual_scalar_supported(data):',u.read(RES/'completion_policy.py')+'\n\ndef manual_scalar_supported(data):')
    anchor='''                if run_ok and running:
                    self.hv_arm.mark_started()'''
    s=u.once(s,anchor,'''                if (run_ok and not self._manual_start_requested and
                        bounded_run_complete(candidate, initial_status, effective_limit)):
                    self.hv_arm.disarm()
                    self.logs.add("WIFI_BOUNDED_COMPLETE MCU deadline; HTTP response may be late")
                    return True, "Timed run already completed by MCU; outputs off", candidate
                if run_ok and running:
                    self.hv_arm.mark_started()''')
    s=u.once(s,'resp = self._call("cmd", [cmd], timeout=0.8, retries=2)',
        'resp = self._call("cmd", [cmd], timeout=0.8, retries=0 if _cmd_head(cmd) in ("START", "CLEAR") else 2)')
    s=u.once(s,'ok = self._serial_text.cmd(cmd, timeout=0.8, retries=2)',
        'ok = self._serial_text.cmd(cmd, timeout=0.8, retries=0 if _cmd_head(cmd) in ("START", "CLEAR") else 2)')
    u.write(p,s)
    (OUT/'build/uno').mkdir(parents=True,exist_ok=True)
    manifest=dict(schema='mic_ai.as5600_bounded_io.v1',predecessor=str(BASE),pair_compatibility_ids=[2026102516,2026102510],
        uno_only=True,nucleo_firmware_unchanged=True,built=False,selftest_pass=False,installed=False,hardware_validated=False,
        calibration_changed=False,thresholds_changed=False,sd_capture_changed=False,uart_protocol_changed=False,
        sensor_feedback_control=False,root_cause_proven=False,calibration_sha256=m['calibration_sha256'],
        motor_control_change='finite MCU run deadline uses normal STOP; all fault/ESTOP paths retained',
        sensor_change='POLL100 sole-owner hardware peripheral polling;3ms transaction deadline;frozen ISR before controller reset;no same-sample retry',
        stop_time_basis='Uno MCU dispatch, not HTTP receipt or measured IGBT edges; UART stop delay still needs measurement',
        source_sha256={str(p.relative_to(OUT)).replace('\\','/'):u.sha(p) for tree in ('UNOQ_MOTOR','web_hmi') for p in (OUT/tree).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'})
    u.write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
