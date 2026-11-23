"""Check the real bounded centered modulator against the unchanged ADC planner."""
import subprocess,shutil
import prepare_standstill_stack as p
CODE=r'''
#include "identify_core.h"
#include <cassert>
#include <random>
int main(){
 ma_geometry g={5312,5184,771,112,240,229};std::mt19937 rng(26);
 std::uniform_real_distribution<float> voltage(-60,60),bus(250,350);
 unsigned accepted=0;
 for(unsigned n=0;n<50000;n++){
  float va=voltage(rng),vb=voltage(rng),dc=bus(rng);ma_output out={};
  int rc=mi_modulate(&g,va,vb,dc,&out);
  if(rc==MA_OK){
   accepted++;assert(mic_current_window_safe(out.pair,out.ccr[0],out.ccr[1],out.ccr[2],out.trigger,g.settle,g.acquire));
   for(unsigned k=0;k<3;k++)assert(out.ccr[k]>=g.min_pulse&&out.ccr[k]<=g.arr-g.min_pulse);
   assert(hypotf(va-out.va,vb-out.vb)<.14f);
  }else assert(rc==MA_WINDOW);
 }
 assert(accepted>45000);
 ma_output out={};assert(mi_modulate(&g,NAN,0,320,&out)==MA_BUS);
 assert(mi_modulate(&g,0,INFINITY,320,&out)==MA_BUS);
 assert(mi_modulate(&g,1.e30f,1.e30f,320,&out)!=MA_OK);
 assert(mi_modulate(&g,1,0,20,&out)==MA_BUS);
}
'''
def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);unit=out/'modulator.cpp';p.write(unit,CODE);exe=unit.with_suffix('.exe')
 r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
  '-I',str(p.OUT/'nucleo/Inc'),str(unit),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'modulator_compile.log',r.stdout+r.stderr);r.check_returncode();subprocess.run([str(exe)],check=True)
 print('50000 vectors: existing all-three-leg guard and pulse limits verified; no hardware commands')
if __name__=='__main__':main()
