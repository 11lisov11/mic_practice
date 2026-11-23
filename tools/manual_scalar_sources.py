"""Auditable source transforms from the installed UART r2 working pair."""
import re

PAIR=(2026101501,2026101502)

def replace(s,a,b,n=1):
    assert s.count(a)==n,(a[:100],s.count(a),n)
    return s.replace(a,b)

def sketch(s):
    s=replace(s,'#include "uart_v3_transport.h"','#include "uart_v3_transport.h"\n#include "manual_scalar_control.h"')
    s=replace(s,'FW_BUILD_ID = 2026101415U','FW_BUILD_ID = 2026101501U')
    s=replace(s,'static uint32_t g_run_limit_ms = 0;', '''static uint32_t g_run_limit_ms = 0;
static bool g_manual_scalar_mode = false;
static bool g_manual_coast_down = false;
static uint16_t g_manual_accel_centi = 500;
static uint16_t g_manual_decel_centi = 100;
static bool g_manual_operator_seen = false;
static uint32_t g_manual_operator_ms = 0;
static bool g_manual_decreasing = false;
static float g_manual_reference_hz = 0.0f;
static bool g_manual_reference_valid = false;
static bool g_manual_bus_hold = false;
static bool manual_command(const char *cmd);
static bool manual_set_frequency(float f);''')
    s=replace(s,'if (START_REQUIRE_RUN_LIMIT && g_run_limit_ms == 0U) {',
        '''if (!msc_start_allowed(g_manual_scalar_mode, g_run_limit_ms,
      msc_operator_alive(now_ms, g_manual_operator_seen, g_manual_operator_ms))) {''')
    s=replace(s,'if (icmp(cmd, "START")) {', '''if (starts_ci(cmd, "CONTROL HEARTBEAT") || starts_ci(cmd, "SET RUNMODE") ||
        starts_ci(cmd, "SET ACCEL") || starts_ci(cmd, "SET DECEL") || starts_ci(cmd, "SET DOWNMODE")) {
      handled = manual_command(cmd);
    } else if (icmp(cmd, "START")) {''',2)
    s=replace(s,'''f = clampf(f, 0.0f, AIR56B2_MAX_ELECTRICAL_FREQ_HZ);
        g_freq_cmd = f;
        if (f > 0.1f) g_last_nonzero_freq = f;''','handled = manual_set_frequency(f);')
    s=replace(s,'''f = clampf(f, 0.0f, AIR56B2_MAX_ELECTRICAL_FREQ_HZ);
      g_freq_cmd = f;
      if (f > 0.1f) g_last_nonzero_freq = f;''','handled = manual_set_frequency(f);')
    s=replace(s,'if (g_pwm_enabled && START_REQUIRE_RUN_LIMIT) request_normal_stop();',
        'if (g_pwm_enabled && START_REQUIRE_RUN_LIMIT && !g_manual_scalar_mode) request_normal_stop();')
    s=replace(s,'static void control_step() {', '''static bool manual_watchdog_tick() {
  // Independent of Linux/HMI lifetime and of the continuously running UART sender.
  if (g_pwm_enabled && g_manual_scalar_mode &&
      !msc_operator_alive(millis(), g_manual_operator_seen, g_manual_operator_ms)) {
    request_estop_stop();
    return true;
  }
  return false;
}
static void control_step() {
  if (manual_watchdog_tick()) return;''')
    s=replace(s,'g_freq_ref = ramp_toward(g_freq_ref, g_freq_cmd, FREQ_RAMP_STEP);',
        '''g_freq_ref = ramp_toward(g_freq_ref, g_freq_cmd,
        g_manual_scalar_mode ? ((g_freq_cmd >= g_freq_ref ? g_manual_accel_centi : g_manual_decel_centi)*0.01f*CONTROL_DT) : FREQ_RAMP_STEP);''',2)
    s=replace(s,'  pkt[14] = ext_flags;', '''  if (mcsdk_scalar && enable_eff && !clear_eff && g_manual_scalar_mode) {
    const uint16_t rate = g_manual_decreasing ? g_manual_decel_centi : g_manual_accel_centi;
    pkt[10] = (uint8_t)rate;
    pkt[11] = (uint8_t)(rate >> 8);
    pkt[12] = g_manual_coast_down ? MSC_TAG_COAST : MSC_TAG_RAMP;
    pkt[13] = MSC_TAG_END;
  }
  pkt[14] = ext_flags;''')
    s=replace(s,'  mp_tx_array(91);','  mp_tx_array(99);')
    s=replace(s,'  mp_tx_int(g_mc_diagnostics.last_tx_status);\n  mp_tx_send();', '''  mp_tx_int(g_mc_diagnostics.last_tx_status);
  mp_tx_int(1); // manual scalar capability
  mp_tx_int(g_manual_scalar_mode ? 1 : 0);
  mp_tx_float(g_manual_accel_centi*0.01f);
  mp_tx_float(g_manual_decel_centi*0.01f);
  mp_tx_int(g_manual_coast_down ? 1 : 0);
  mp_tx_float(g_manual_reference_hz);
  mp_tx_int(g_manual_reference_valid && bp_age < 300U ? 1 : 0);
  mp_tx_int(g_manual_bus_hold ? 1 : 0);
  mp_tx_send();''')
    s=replace(s,'      brake_set(true);\n      g_stop_requested = false;',
        '      g_manual_decreasing=false;\n      brake_set(true);\n      g_stop_requested = false;')
    helper=r'''
static bool manual_set_frequency(float f) {
  if (!msc_finite(f) || f < 0.0f || f > AIR56B2_MAX_ELECTRICAL_FREQ_HZ) return false;
  // A coast retarget is a STOP, never an automatic restart into a spinning rotor.
  if (g_pwm_enabled && g_manual_scalar_mode && g_manual_coast_down && f < g_freq_cmd) {
    ext_brake_set(0.0f);
    hard_stop(false);
  }
  g_freq_cmd=f;
  g_manual_decreasing=g_pwm_enabled && f < (g_manual_reference_valid ? g_manual_reference_hz : g_freq_ref);
  if (f > 0.1f) g_last_nonzero_freq=f;
  return true;
}
static bool manual_command(const char *cmd) {
  if (icmp(cmd,"CONTROL HEARTBEAT")) {
    g_manual_operator_ms=millis();g_manual_operator_seen=true;return true;
  }
  if (starts_ci(cmd,"SET RUNMODE")) {
    if (g_pwm_enabled || g_start_req || g_state != STATE_SAFE) return false;
    const char *p=cmd+11;while (*p==' ') ++p;
    if (icmp(p,"MANUAL")) g_manual_scalar_mode=true;
    else if (icmp(p,"BOUNDED")) g_manual_scalar_mode=false;
    else return false;
    g_run_limit_ms=0;g_run_deadline_ms=0;return true;
  }
  if (starts_ci(cmd,"SET DOWNMODE")) {
    if (g_pwm_enabled || g_start_req) return false;
    const char *p=cmd+12;while (*p==' ') ++p;
    if (icmp(p,"COAST")) g_manual_coast_down=true;
    else if (icmp(p,"RAMP")) g_manual_coast_down=false;
    else return false;
    return true;
  }
  const bool accel=starts_ci(cmd,"SET ACCEL");
  if (accel || starts_ci(cmd,"SET DECEL")) {
    float value=0;
    if (!parse_single_float_arg(cmd+9,&value) || !msc_finite(value) || value<0.1f || value>(accel ? 50.0f : 5.0f)) return false;
    const uint16_t rate=(uint16_t)(value*100.0f+0.5f);
    if (!msc_rate_valid(rate)) return false;
    if (accel) g_manual_accel_centi=rate;else g_manual_decel_centi=rate;
    return true;
  }
  return false;
}
'''
    s=replace(s,'static void request_normal_stop() {',helper+'\nstatic void request_normal_stop() {')
    s=replace(s,'  g_mc_diagnostics = decode_nucleo_fault_diagnostics(rx, g_bp_mcsdk_telemetry, g_bp_fw_build);', '''  g_manual_reference_valid=g_bp_mcsdk_telemetry && g_bp_fw_build==2026101502U && (rx[11]&0xFEU)==0xA0U;
  if (g_manual_reference_valid) {
    const uint16_t reference=(uint16_t)(rx[12] | ((uint16_t)rx[13]<<8));
    if (reference>5000U) return false;
    g_manual_reference_hz=reference*0.01f;
    g_manual_bus_hold=(rx[11]&1U)!=0;
  } else g_manual_bus_hold=false;
  g_mc_diagnostics = decode_nucleo_fault_diagnostics(rx, g_bp_mcsdk_telemetry, g_bp_fw_build);''')
    return s

def nucleo(s):
    s=replace(s,'#include "uart_v3_transport.h"','#include "uart_v3_transport.h"\n#include "manual_scalar_control.h"')
    s=replace(s,'MIC_NUCLEO_FW_BUILD_ID 2026101414UL','MIC_NUCLEO_FW_BUILD_ID 2026101502UL')
    s=replace(s,'  int16_t last_speed_unit;', '''  int16_t last_speed_unit;
  int16_t ramp_target_speed_unit;
  uint16_t ramp_rate_centi;
  bool coast_hold;''')
    s=replace(s,'  bool coast_hold;', '  bool coast_hold;\n  bool manual_ramp_down;\n  bool decel_bus_hold;')
    s=replace(s,'  if (flags == 0U && mode == UNO_MODE_OFF) {\n    uno_stop_motor();',
        '  if (flags == 0U && mode == UNO_MODE_OFF) {\n    uno_link.coast_hold=false;\n    uno_stop_motor();')
    s=replace(s,'  if (uno_clear_frame_is_safe(frame)) {\n    uno_stop_motor();',
        '  if (uno_clear_frame_is_safe(frame)) {\n    uno_link.coast_hold=false;\n    uno_stop_motor();')
    s=replace(s,'  if (!uno_service_fields_are_zero(frame)) {',
        '  if (!uno_service_fields_are_zero(frame) || (mode == UNO_MODE_SCALAR && !msc_wire_valid(frame))) {')
    a='''  const bool update_ramp = !uno_link.command_enabled || target_speed_unit != uno_link.last_speed_unit;
  const uint16_t ramp_ms = update_ramp ? uno_speed_ramp_ms(target_speed_unit) : 0U;'''
    b='''  bool update_ramp = !uno_link.command_enabled || target_speed_unit != uno_link.last_speed_unit;
  uint16_t ramp_ms = update_ramp ? uno_speed_ramp_ms(target_speed_unit) : 0U;
  int16_t programmed_speed_unit=target_speed_unit;
  uint16_t rate=0U;
  if (msc_wire_present(frame)) {
    rate=(uint16_t)(frame[10] | ((uint16_t)frame[11]<<8));
    if (frame[12]==MSC_TAG_COAST && uno_link.command_enabled && target_speed_unit<uno_link.last_speed_unit) {
      uno_link.coast_hold=true;uno_stop_motor();return;
    }
    if (uno_link.coast_hold) { uno_stop_motor();return; }
    const int16_t current=MC_GetSTMStateMotor1()==IDLE ? 0 : MC_GetMecSpeedReferenceMotor1();
    uno_link.manual_ramp_down=frame[12]==MSC_TAG_RAMP;
    if (uno_link.decel_bus_hold && target_speed_unit<current) {
      uno_link.last_speed_unit=target_speed_unit;return;
    }
    if (target_speed_unit>=current) uno_link.decel_bus_hold=false;
    update_ramp=update_ramp || rate!=uno_link.ramp_rate_centi ||
        (uno_link.ramp_target_speed_unit!=target_speed_unit && current==uno_link.ramp_target_speed_unit);
    if (update_ramp) ramp_ms=msc_segment(current,target_speed_unit,rate,SPEED_UNIT,POLE_PAIR_NUM,&programmed_speed_unit);
  }'''
    s=replace(s,a,b)
    s=replace(s,'MC_ProgramSpeedRampMotor1(target_speed_unit, ramp_ms);',
        '''MC_ProgramSpeedRampMotor1(programmed_speed_unit, ramp_ms);
      uno_link.ramp_target_speed_unit=programmed_speed_unit;
      uno_link.ramp_rate_centi=rate;''')
    s=replace(s,'  uv3_reply_diagnostics(reply, &uno_transport);', '''  // Live reference uses a new explicit tag only with no retained first fault.
  // Any fault keeps the original complete diagnostic snapshot layout.
  if (uno_link.first_reason==UNO_DIAG_NONE && !fault) {
    const int32_t value=(int32_t)MC_GetMecSpeedReferenceMotor1()*POLE_PAIR_NUM*100/SPEED_UNIT;
    const uint16_t reference=(uint16_t)(value<0 ? 0 : value);
    reply[11]=0xA0U | (uno_link.decel_bus_hold ? 1U : 0U);
    reply[12]=(uint8_t)reference;reply[13]=(uint8_t)(reference>>8);
  }
  uv3_reply_diagnostics(reply, &uno_transport);''')
    # Define before polling, after fault-latching functions have been defined.
    anchor='static void uno_link_poll(void) {'
    s=replace(s,anchor,'''static void uno_manual_bus_control(void) {
  if (!uno_link.command_enabled || !uno_link.manual_ramp_down || !uno_link.ramp_rate_centi) return;
  const int16_t current=MC_GetMecSpeedReferenceMotor1();
  if (uno_link.last_speed_unit>=current) return;
  const uint16_t bus=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  if (bus>=360U) { uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_BUS);return; }
  if (bus>=350U && !uno_link.decel_bus_hold) {
    MC_ProgramSpeedRampMotor1(current,0U);
    uno_link.ramp_target_speed_unit=current;
    uno_link.decel_bus_hold=true;
  } else if (bus<=340U) uno_link.decel_bus_hold=false;
}
'''+anchor+'\n  uno_manual_bus_control();')
    return s
