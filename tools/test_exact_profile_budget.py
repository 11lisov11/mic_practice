"""Truth-table/numeric equivalence and exact timed-work/protection provenance."""
import importlib.util,json,sys
import prepare_exact_profile_budget as p
import test_foc_runtime_fix as common
from test_foc_observer_schedule_fix import stripped_header
from test_foc_update_latency_fix import function


def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
 pre=r'''
#include <cassert>
#include <cstdio>
#include <cmath>
#include <cstring>
#include <cstdint>
#include <cfloat>
#include <cfenv>
#include <cerrno>
#include <initializer_list>
#include "current_adc_window_plan.h"
using std::isfinite;using std::isnan;
static uint64_t core_calls;
static uint32_t word(float x){uint32_t v;memcpy(&v,&x,4);return v;}
static float value(uint32_t v){float x;memcpy(&x,&v,4);return x;}
static float host_hypot_core(float a,float b){
 assert((word(a)&0x7fffffffU)<=0x58800000U&&(word(b)&0x7fffffffU)<=0x58800000U);
 ++core_calls;float r=std::hypot(a,b);assert(std::isfinite(r));return r;
}
#define MIC_CONTROL_HYPOT_CORE(a,b) ::host_hypot_core(a,b)
'''
 old=stripped_header(p.read(p.BASE/'nucleo/Inc/motor_control.h'))
 new=stripped_header(p.read(p.OUT/'nucleo/Inc/motor_control.h'))
 of=stripped_header(p.read(p.BASE/'nucleo/Inc/foc_experiment.h'))
 nf=stripped_header(p.read(p.OUT/'nucleo/Inc/foc_experiment.h'))
 code=pre+'namespace baseline{\n'+old+'\n'+of+'\n}\nnamespace candidate{\n'+new+'\n'+nf+'\n}\n'+r'''
static uint32_t rng=0x1503f04;static uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static float random_value(float lo,float hi){return lo+(hi-lo)*(next()>>8)*(1.f/16777216.f);}
static void norm(uint32_t x,uint32_t y){
 float a=value(x),b=value(y);core_calls=0;errno=0;float old=std::hypot(a,b);int old_errno=errno;
 errno=0;float now=candidate::ma_control_norm(a,b);int new_errno=errno;
 assert(word(old)==word(now)&&old_errno==new_errno);
 bool bounded=(x&0x7fffffffU)<=0x58800000U&&(y&0x7fffffffU)<=0x58800000U;
 assert(core_calls==(bounded?1U:0U));
}
int main(){
 static_assert(sizeof(baseline::ma_motor)==52&&sizeof(candidate::ma_motor)==52,"same full model ABI");
 baseline::ma_motor expected=FE_ESTIMATED_MOTOR;
 assert(baseline::ma_motor_valid(&expected));
 unsigned predicates=0;
 auto compare=[&](const baseline::ma_motor&m){candidate::ma_motor n;memcpy(&n,&m,52);
  bool a=baseline::fe_model_exact(&m),b=candidate::fe_model_exact(&n);
  assert(a==b&&b==(memcmp(&m,&expected,52)==0));++predicates;};
 compare(expected);
 for(unsigned bit=0;bit<416;++bit){auto m=expected;((uint8_t*)&m)[bit/8]^=(uint8_t)(1U<<(bit%8));compare(m);}
 for(unsigned n=0;n<250000;++n){
  auto m=expected;
  if(n&1)for(unsigned i=0;i<52;++i)((uint8_t*)&m)[i]=(uint8_t)next();
  else for(unsigned i=0;i<1+n%20;++i)((uint8_t*)&m)[next()%52]^=(uint8_t)next();
  compare(m);
 }
 for(int round:{FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO}){
  assert(std::fesetround(round)==0);assert(baseline::ma_motor_valid(&expected));compare(expected);
 }
 assert(std::fesetround(FE_TONEAREST)==0);
 unsigned norms=0;
 for(unsigned i=0;i<2000000;++i){norm(next(),next());++norms;}
 const uint32_t special[]={0U,0x80000000U,1U,0x80000001U,0x007fffffU,0x00800000U,
  0x3f800000U,0xbf800000U,0x58800000U,0x58800001U,0x7f7fffffU,0xff7fffffU,
  0x7f800000U,0xff800000U,0x7fc12345U,0x7f800001U,0xffc12345U};
 for(uint32_t a:special)for(uint32_t b:special){norm(a,b);++norms;}
 for(uint32_t a=0x58800000U-1024;a<=0x58800000U+1024;++a){norm(a,0x3f800000U);norm(a|0x80000000U,0x3f800000U);norm(0x3f800000U,a);norm(0x3f800000U,a|0x80000000U);norms+=4;}
 candidate::ma_motor cm;memcpy(&cm,&expected,52);
 baseline::ma_geometry g={5312,5184,771,112,240,229};candidate::ma_geometry cg;memcpy(&cg,&g,sizeof(g));
 unsigned controls=0,trips=0;
 for(unsigned i=0;i<200000;++i){
  baseline::ma_controller a={};a.time_s=random_value(0,5);a.integral[0]=random_value(-2,2);a.integral[1]=random_value(-2,2);a.speed_integral=random_value(-.1f,.1f);
  candidate::ma_controller b;memcpy(&b,&a,sizeof(b));
  float x[6]={random_value(-1,1),random_value(-1,1),random_value(.001f,.3f),random_value(-.2f,.2f),random_value(-10,40),0};
  float ia=random_value(-1.5f,1.5f),ib=random_value(-1.5f,1.5f),ref=random_value(0,5),bus=random_value(250,350);
  if(i%1000==0)ia=NAN;if(i%1000==1)ia=INFINITY;if(i%1000==2)ia=-0.f;
  baseline::ma_output oa;candidate::ma_output ob;int algo=i%2?2:3;
  int ra=baseline::ma_control(&a,&expected,x,&g,algo,ia,ib,ref,bus,1.f/16000,1,&oa);
  int rb=candidate::ma_control(&b,&cm,x,&cg,algo,ia,ib,ref,bus,1.f/16000,1,&ob);
  assert(ra==rb&&!memcmp(&a,&b,sizeof(a))&&!memcmp(&oa,&ob,sizeof(oa)));++controls;
 }
 for(float a:{std::nextafter(1.35f,0.f),1.35f,std::nextafter(1.35f,INFINITY)}){
  baseline::ma_controller ac={};candidate::ma_controller bc={};baseline::ma_output ao;candidate::ma_output bo;
  float x[6]={0,0,.25f,0,0,0};
  int r1=baseline::ma_control(&ac,&expected,x,&g,2,a,0,5,320,1.f/16000,1,&ao);
  int r2=candidate::ma_control(&bc,&cm,x,&cg,2,a,0,5,320,1.f/16000,1,&bo);
  assert(r1==r2&&((r1==baseline::MA_CURRENT)==(a>1.35f)));++trips;
 }
 printf("{\"exact_model_predicate_cases\":%u,\"all416_single_bit_mutations\":true,\"normal_rounding_modes\":4,\"hypot_dispatch_bit_exact_cases\":%u,\"controller_bit_exact_cases\":%u,\"raw135A_boundary_cases\":%u}\n",predicates,norms,controls,trips);
}
'''
 numeric=json.loads(common.compile_run(out,'exact_guard_and_norm',code))
 unchanged=[]
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (p.BASE/folder).rglob('*'):
   if not f.is_file() or '__pycache__' in f.parts:continue
   rel=f.relative_to(p.BASE)
   if rel.as_posix() in ('nucleo/Inc/foc_experiment.h','nucleo/Inc/motor_control.h'):continue
   expected=p.read(f).replace('2026111501',str(p.NEW[0])).replace('2026111502',str(p.NEW[1]))
   assert expected==p.read(p.OUT/rel),str(rel);unchanged.append(rel.as_posix())
 for name in ('ma_native_fast','fe_profile_tick','fe_profile_service','ma_estimate_publish','ma_fail_at'):
  a=function(p.read(p.BASE/'nucleo/Src/multi_native.c'),name)
  b=function(p.read(p.OUT/'nucleo/Src/multi_native.c'),name)
  assert a==b,name
 a=p.read(p.BASE/'nucleo/Inc/motor_control.h');b=p.read(p.OUT/'nucleo/Inc/motor_control.h')
 for name in ('ma_observe','ma_derivative','ma_modulate','ma_control'):
  assert function(a,name)==function(b,name),name
 old_control=function(a,'ma_control_checked');new_control=function(b,'ma_control_checked')
 assert new_control.replace('ma_control_norm(x[2],x[3])','hypotf(x[2],x[3])').replace('ma_control_norm(dq[0],dq[1])','hypotf(dq[0],dq[1])')==old_control
 assert 'else if(hypotf(ia,ib)>m->trip_current)fault=MA_CURRENT;' in new_control
 report=dict(passed=True,hardware_commands=0,numeric=numeric,unchanged_source_files=len(unchanged),
     threshold_protections_identical=True,FE_predicate_equivalent_full52_bytes=True,
     timed_probe_and_full_fast_function_unchanged=True,raw_current_trip_expression_unchanged=True,
     no_fast_math_or_global_math_override=True,target_cycles_measured=False,
     baseline_target_cycles=4229,budget_cycles=4000,
     limitation='PC checks predicate/output equivalence and protected source scope. ARM disassembly must verify native bounded calls enter the same installed hypot core. Fresh MCU DWT qualification is still required; no claim of target4000 pass from host timing.')
 p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
