"""Run the actual two Uno dispatch predicates and the exact read-only page branch."""
import json,re,shutil,subprocess,tempfile
from pathlib import Path
import prepare_adc_noise_rpc_fix as p

def main():
 s=p.read(p.OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
 expressions=re.findall(r'if \((starts_ci\(cmd,"NOISE PAGE ".*?)\) \{\s*handled = manual_command\(cmd\);',s,re.S)
 assert len(expressions)==2
 begin=s.index('  if(starts_ci(cmd,"NOISE PAGE ")){',s.index('static bool manual_command(const char *cmd) {'))
 end=s.index('  if(starts_ci(cmd,"IDENT ")){',begin)
 branch=s[begin:end]
 source='''#include <cstdio>\n#include <cstring>\n#include <cctype>\n#include <cassert>
static bool starts_ci(const char*s,const char*p){while(*p)if(std::toupper(*s++)!=std::toupper(*p++))return false;return true;}
static bool g_pwm_enabled=false,g_start_req=false;enum {STATE_SAFE=0,STATE_RUN=1};static int g_state=STATE_SAFE;
static struct {bool complete;} g_idle_noise{true};static unsigned g_noise_view_page;
static bool page(const char*cmd){'''+branch+'return false;}\n'
 for i,expr in enumerate(expressions):source+=f'static bool route{i}(const char*cmd){{return {expr};}}\n'
 source+='''int main(){
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
 puts("{\\"passed\\":true,\\"actual_dispatch_predicates\\":2,\\"off_only_page_branch\\":true,\\"hardware_commands\\":0}");}
'''
 source='#include <cstdint>\n#include <initializer_list>\n'+source
 out=p.OUT/'route_selftest';out.mkdir(exist_ok=True);unit=out/'routes.cpp';p.write(unit,source)
 with tempfile.TemporaryDirectory() as temp:
  exe=Path(temp)/'test.exe'
  r=subprocess.run([shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror',str(unit),'-o',str(exe)],capture_output=True,text=True)
  p.write(out/'build.log',r.stdout+r.stderr);r.check_returncode()
  r=subprocess.run([str(exe)],capture_output=True,text=True);p.write(out/'run.log',r.stdout+r.stderr);r.check_returncode()
 report=json.loads(r.stdout);p.write(out/'report.json',json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
