#include <cstdint>
#include <initializer_list>
#include <cstdio>
#include <cstring>
#include <cctype>
#include <cassert>
static bool starts_ci(const char*s,const char*p){while(*p)if(std::toupper(*s++)!=std::toupper(*p++))return false;return true;}
static bool g_pwm_enabled=false,g_start_req=false;enum {STATE_SAFE=0,STATE_RUN=1};static int g_state=STATE_SAFE;
static struct {bool complete;} g_idle_noise{true};static unsigned g_noise_view_page;
static bool page(const char*cmd){  if(starts_ci(cmd,"NOISE PAGE ")){
    unsigned page;char extra;
    if(g_pwm_enabled||g_start_req||g_state!=STATE_SAFE||!g_idle_noise.complete||
      sscanf(cmd+11,"%u %c",&page,&extra)!=1||page>=17)return false;
    g_noise_view_page=(uint8_t)page;return true;
  }
return false;}
static bool route0(const char*cmd){return starts_ci(cmd,"NOISE PAGE ") || starts_ci(cmd,"IDENT ") || starts_ci(cmd,"SET ALGORITHM ") || starts_ci(cmd,"MODEL ") ||
        starts_ci(cmd, "CONTROL HEARTBEAT") || starts_ci(cmd, "SET RUNMODE") ||
        starts_ci(cmd, "SET ACCEL") || starts_ci(cmd, "SET DECEL") || starts_ci(cmd, "SET DOWNMODE");}
static bool route1(const char*cmd){return starts_ci(cmd,"NOISE PAGE ") || starts_ci(cmd,"IDENT ") || starts_ci(cmd,"SET ALGORITHM ") || starts_ci(cmd,"MODEL ") ||
        starts_ci(cmd, "CONTROL HEARTBEAT") || starts_ci(cmd, "SET RUNMODE") ||
        starts_ci(cmd, "SET ACCEL") || starts_ci(cmd, "SET DECEL") || starts_ci(cmd, "SET DOWNMODE");}
int main(){
 for(auto route:{route0,route1}){
  assert(route("NOISE PAGE 0")&&route("NOISE PAGE 16"));
  assert(route("IDENT PAGE 0"));assert(!route("NOISE START"));
 }
 assert(page("NOISE PAGE 16")&&g_noise_view_page==16);
 assert(!page("NOISE PAGE 17"));assert(!page("NOISE PAGE 0 trailing"));
 g_pwm_enabled=true;assert(!page("NOISE PAGE 0"));g_pwm_enabled=false;
 g_start_req=true;assert(!page("NOISE PAGE 0"));g_start_req=false;
 g_idle_noise.complete=false;assert(!page("NOISE PAGE 0"));g_idle_noise.complete=true;
 g_state=STATE_RUN;assert(!page("NOISE PAGE 0"));
 puts("{\"passed\":true,\"actual_dispatch_predicates\":2,\"off_only_page_branch\":true,\"hardware_commands\":0}");}
