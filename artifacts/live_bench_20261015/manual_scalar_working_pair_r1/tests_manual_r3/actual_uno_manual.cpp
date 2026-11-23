
#include "manual_scalar_control.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <initializer_list>
#include <strings.h>
uint32_t tick=1000, g_run_limit_ms=0,g_run_deadline_ms=0,g_manual_operator_ms=0;
bool g_pwm_enabled=false,g_start_req=false,g_manual_scalar_mode=false,g_manual_coast_down=false;
bool g_manual_operator_seen=false,g_manual_decreasing=false,g_manual_reference_valid=false;
float g_freq_cmd=0,g_freq_ref=0,g_manual_reference_hz=0,g_last_nonzero_freq=0;
uint16_t g_manual_accel_centi=500,g_manual_decel_centi=100;
enum {STATE_SAFE,STATE_RUN};int g_state=STATE_SAFE;
const float AIR56B2_MAX_ELECTRICAL_FREQ_HZ=50;
unsigned checks=0,estops=0,stops=0;
uint32_t millis(){return tick;}
bool icmp(const char*a,const char*b){return strcasecmp(a,b)==0;}
bool starts_ci(const char*a,const char*b){return strncasecmp(a,b,strlen(b))==0;}
bool parse_single_float_arg(const char*p,float*out){char*end;*out=strtof(p,&end);while(*end==' ')++end;return end!=p && !*end;}
void ext_brake_set(float){}
void hard_stop(bool){++stops;g_pwm_enabled=false;g_state=STATE_SAFE;}
void request_estop_stop(){++estops;g_pwm_enabled=false;g_state=STATE_SAFE;}
void check(bool ok,const char*name){++checks;if(!ok){fprintf(stderr,"FAIL %s\n",name);exit(1);}}
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
static bool manual_watchdog_tick() {
  // Independent of Linux/HMI lifetime and of the continuously running UART sender.
  if (g_pwm_enabled && g_manual_scalar_mode &&
      !msc_operator_alive(millis(), g_manual_operator_seen, g_manual_operator_ms)) {
    request_estop_stop();
    return true;
  }
  return false;
}
int main(){
 check(manual_command("SET RUNMODE MANUAL"),"manual mode while stopped");
 check(!msc_start_allowed(true,0,false),"continuous mode cannot start without operator heartbeat");
 check(manual_command("CONTROL HEARTBEAT"),"operator pulse accepted");
 check(msc_start_allowed(true,0,msc_operator_alive(tick,g_manual_operator_seen,g_manual_operator_ms)),"manual start needs no total-duration timer");
 g_pwm_enabled=true;g_state=STATE_RUN;
 for(tick=1000;tick<100000;tick+=500){manual_command("CONTROL HEARTBEAT");check(!manual_watchdog_tick(),"manual run survives former 15s/ARM time limit with operator control");}
 tick=g_manual_operator_ms+2999;check(!manual_watchdog_tick(),"fresh operator remains active");
 tick=g_manual_operator_ms+3000;check(manual_watchdog_tick() && estops==1 && !g_pwm_enabled,"HMI crash/client disappearance independently stops MCU");
 for(const char*bad : {"SET ACCEL nan","SET ACCEL inf","SET ACCEL -1","SET ACCEL 0","SET ACCEL 51","SET DECEL 5.1","SET ACCEL 2 junk"})check(!manual_command(bad),"nonfinite/range/extra argument rejected under Ofast");
 for(const char*good : {"SET ACCEL 0.1","SET ACCEL 50","SET DECEL 0.1","SET DECEL 5"})check(manual_command(good),"online ramp settings accepted");
 for(float f : {0.0f,0.1f,5.0f,20.0f,50.0f})check(manual_set_frequency(f) && g_freq_cmd==f,"whole 0..50 setpoint range");
 check(!manual_set_frequency(50.1f) && !manual_set_frequency(-1),"out-of-range target rejected");
 check(!manual_set_frequency(NAN) && !manual_set_frequency(INFINITY),"nonfinite target rejected under Ofast");
 g_pwm_enabled=true;g_state=STATE_RUN;g_freq_cmd=g_freq_ref=50;
 check(manual_set_frequency(20) && g_pwm_enabled && g_manual_decreasing,"default lower target remains running and uses deceleration");
 check(!manual_command("SET RUNMODE BOUNDED") && !manual_command("SET DOWNMODE COAST"),"run mode cannot change underneath active outputs");
 g_pwm_enabled=false;g_state=STATE_SAFE;check(manual_command("SET DOWNMODE COAST"),"optional coast mode configurable stopped");
 g_pwm_enabled=true;g_state=STATE_RUN;g_freq_cmd=g_freq_ref=50;
 check(manual_set_frequency(20) && !g_pwm_enabled && stops==1 && g_freq_cmd==20,"optional coast retains new target but never auto-starts");
 check(!msc_start_allowed(false,0,true) && msc_start_allowed(false,15000,false),"bounded profile retains backup-timer requirement");
 check(msc_operator_alive(20,true,0xFFFFFFF0U),"operator watchdog handles millisecond wrap");
 int16_t next=0;
 for(unsigned rate : {10U,50U,100U,500U,5000U}) for(int target=1;target<=500;++target){
  int current=0;unsigned steps=0;
  while(current<target){auto duration=msc_segment(current,target,rate,10,1,&next);check(next>current && next<=target && duration>0 && duration<=60000,"slow ramp reaches exact target with bounded segment");current=next;check(++steps<1000,"segmented ramp progresses");}
 }
 printf("{\"pass\":true,\"assertions\":%u,\"hardware_commands\":0}\n",checks);
}
