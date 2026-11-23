"""Bit-exact numeric regressions and unchanged timing/protection provenance."""
import json
import prepare_current_polarity_budget as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function
from test_foc_observer_schedule_fix import stripped_header


def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
 pre='''#include <cassert>\n#include <cstdio>\n#include <cmath>\n#include <cstring>\n#include <cstdint>\n#include <cfloat>\n#include "current_adc_window_plan.h"\nusing std::isfinite;using std::isnan;\n'''
 old=stripped_header(p.read(p.BASE/'nucleo/Inc/motor_control.h'))
 new=stripped_header(p.read(p.OUT/'nucleo/Inc/motor_control.h'))
 old_v=stripped_header(p.read(p.BASE/'nucleo/Inc/observer_applied_voltage.h'))
 new_v=stripped_header(p.read(p.OUT/'nucleo/Inc/observer_applied_voltage.h'))
 code=pre+'namespace baseline{\n'+old+'\n'+old_v+'\n}\nnamespace candidate{\n'+new+'\n'+new_v+'\n}\n'+r'''
static uint32_t seed=0x142025;static uint32_t next(){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static float value(float low,float high){return low+(high-low)*(next()>>8)*(1.f/16777216.f);}
static uint32_t bits(float x){uint32_t u;memcpy(&u,&x,4);return u;}
static unsigned scalar_cases;
static void scalar(uint32_t u){float x;memcpy(&x,&u,4);float a=baseline::ma_clip(x/.05f,-1,1),b=candidate::ma_current_polarity(x);
 assert(bits(a)==bits(b));++scalar_cases;}
int main(){
 assert(bits(.05f)==0x3d4ccccdU);
 for(unsigned i=0;i<1000000;++i)scalar(next());
 for(uint32_t u=0x3d4ccccdU-4096;u<=0x3d4ccccdU+4096;++u){scalar(u);scalar(u|0x80000000U);}
 for(uint32_t u:{0U,0x80000000U,0x7f800000U,0xff800000U,0x7f800001U,0xff800001U,0x7fc00000U,0xffc00000U,1U,0x80000001U})scalar(u);
 baseline::ma_motor m={12.23f,11.004422f,.52809386f,.52809386f,.4944776f,.0002f,.000147906f,1,.25f,.8f,1.35f,400,12};
 candidate::ma_motor nm;memcpy(&nm,&m,sizeof(m));
 baseline::ma_geometry g={5312,5184,771,112,240,229};candidate::ma_geometry ng;memcpy(&ng,&g,sizeof(g));
 unsigned controls=0,voltages=0;
 for(unsigned i=0;i<100000;++i){
  baseline::ma_controller a={};a.time_s=value(0,5);a.integral[0]=value(-2,2);a.integral[1]=value(-2,2);a.speed_integral=value(-.1f,.1f);
  candidate::ma_controller b;memcpy(&b,&a,sizeof(b));
  float x[6]={value(-1,1),value(-1,1),value(.01f,.3f),value(-.2f,.2f),value(-10,40),0};
  float ia=value(-1.5f,1.5f),ib=value(-1.5f,1.5f),ref=value(0,5),bus=value(250,350);
  if(i%1000==0)ia=NAN;if(i%1000==1)ia=INFINITY;if(i%1000==2)ia=-0.f;
  baseline::ma_output oa;candidate::ma_output ob;int algo=i%2?2:3;
  int ra=baseline::ma_control(&a,&m,x,&g,algo,ia,ib,ref,bus,1.f/16000,1,&oa);
  int rb=candidate::ma_control(&b,&nm,x,&ng,algo,ia,ib,ref,bus,1.f/16000,1,&ob);
  assert(ra==rb&&memcmp(&a,&b,sizeof(a))==0&&memcmp(&oa,&ob,sizeof(oa))==0);++controls;
  uint16_t c[3]={(uint16_t)(next()%5313),(uint16_t)(next()%5313),(uint16_t)(next()%5313)};
  float va,vb,wa,wb;ra=baseline::ma_applied_voltage(&g,c,5312,(uint16_t)bus,ia,ib,&va,&vb);
  rb=candidate::ma_applied_voltage(&ng,c,5312,(uint16_t)bus,ia,ib,&wa,&wb);
  assert(ra==rb&&bits(va)==bits(wa)&&bits(vb)==bits(wb));++voltages;
 }
 // Count the eliminated current/.05 divisions in the actual64 OFF cases.
 unsigned min_saved=6,max_saved=0,total_saved=0;
 for(unsigned n=0;n<64;++n){
  float angle=(n%16U)*.3926990817f,current=(n&16U)?.75f:.2f;
  float ia=current*cosf(angle),ib=current*sinf(angle);
  float phases[3]={ia,-.5f*ia+.8660254038f*ib,-.5f*ia-.8660254038f*ib};unsigned saved=0;
  for(float v:phases)if(fabsf(v)>=.05f)saved+=2; // applied-voltage and control kernels
  if(saved<min_saved)min_saved=saved;if(saved>max_saved)max_saved=saved;total_saved+=saved;
 }
 assert(min_saved>=4);
 printf("{\"polarity_bit_exact_cases\":%u,\"control_bit_exact_cases\":%u,\"applied_voltage_bit_exact_cases\":%u,\"OFF64_min_removed_divides_per_call\":%u,\"OFF64_max_removed_divides_per_call\":%u,\"OFF64_removed_divides_once_each_case\":%u}\n",scalar_cases,controls,voltages,min_saved,max_saved,total_saved);
}
'''
 code=code.replace('#include <cassert>','#include <initializer_list>\n#include <cassert>',1)
 results=json.loads(common.compile_run(out,'exact_polarity_controller',code))
 # Check every source outside the two optimized headers is unchanged except IDs.
 unchanged=0
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (p.BASE/folder).rglob('*'):
   if not f.is_file() or '__pycache__' in f.parts:continue
   rel=f.relative_to(p.BASE)
   if rel.as_posix() in ('nucleo/Inc/motor_control.h','nucleo/Inc/observer_applied_voltage.h'):continue
   expected=p.read(f).replace('2026111405',str(p.NEW[0])).replace('2026111406',str(p.NEW[1]))
   assert expected==p.read(p.OUT/rel),str(rel);unchanged+=1
 for fn in ('ma_observe','ma_derivative','ma_modulate'):
  assert function(p.read(p.BASE/'nucleo/Inc/motor_control.h'),fn)==function(p.read(p.OUT/'nucleo/Inc/motor_control.h'),fn)
 for fn in ('ma_native_fast','fe_profile_tick','fe_profile_service'):
  assert function(p.read(p.BASE/'nucleo/Src/multi_native.c'),fn)==function(p.read(p.OUT/'nucleo/Src/multi_native.c'),fn)
 native=p.read(p.OUT/'nucleo/Src/multi_native.c')
 assert native.index('int avrc=ma_applied_voltage',native.index('static int fe_profile_tick(void){'))<native.index('fe_elapsed=DWT->CYCCNT-begin')
 report=dict(passed=True,numeric=results,unchanged_source_files=unchanged,
  thresholds_changed=False,profiling_work_removed=False,hardware_commands=0,
  measured_target_cycles_available=False,baseline_measured_cycles=4007,budget_cycles=4000,
  limitation='PC proves numeric equivalence and removed divisions; MCU DWT must verify the4000-cycle bound after authorized installation.')
 p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
