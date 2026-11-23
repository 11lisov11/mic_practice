"""Boundary, recorded-input and old/new actual-C equivalence; no board access."""
import ast, ctypes, hashlib, json, math, random, shutil, struct, subprocess
import prepare_foc_fast_budget_fix as p
import test_foc_runtime_fix as common
from audit_production_pwm_filters import function

def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=True)
    common.p=p
    rounding=r'''
#include <cassert>
#include <cstdio>
#include <cmath>
#include <limits>
#include "motor_control.h"
int main(){
 unsigned long long checked=0;
 auto check=[&](float v){
  if(!std::isfinite(v)||v<0||v>65535){assert(ma_round_ccr(v)==UINT32_MAX);}
  else assert(ma_round_ccr(v)==(uint32_t)std::lround(v));
  ++checked;
 };
 for(unsigned i=0;i<=131070;++i){float f=i*.5f;
  check(f);check(std::nextafter(f,-INFINITY));check(std::nextafter(f,INFINITY));
 }
 uint32_t state=0x67583421U;
 for(unsigned i=0;i<2000000;++i){state^=state<<13;state^=state>>17;state^=state<<5;
  float f;memcpy(&f,&state,4);check(f);
 }
 for(float f:{-0.f,-1.f,INFINITY,-INFINITY,std::numeric_limits<float>::quiet_NaN()})check(f);
 printf("{\"rounding_cases\":%llu,\"boundary_and_invalid_inputs\":true}\n",checked);
}
'''
    rounding_report=json.loads(common.compile_run(out,'rounding',rounding.replace('#include <limits>','#include <limits>\n#include <initializer_list>')))
    wrapper=r'''
#include "foc_experiment.h"
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C"
#endif
API unsigned control_size(){return sizeof(ma_controller);}
API unsigned output_size(){return sizeof(ma_output);}
API void reset(void*c){memset(c,0,sizeof(ma_controller));}
API int control(void*c,const float*x,const ma_geometry*g,int algorithm,float ia,float ib,
 float hz,float bus,float dt,int fresh,void*out){
 static const ma_motor m=FE_ESTIMATED_MOTOR;
 return ma_control((ma_controller*)c,&m,x,g,algorithm,ia,ib,hz,bus,dt,fresh,(ma_output*)out);
}
API int modulation(void*c,const ma_geometry*g,int algorithm,float va,float vb,float bus,void*out){
 memset(out,0,sizeof(ma_output));
 return ma_modulate((ma_controller*)c,g,algorithm,va,vb,bus,(ma_output*)out);
}
'''
    libs=[]
    for name,package in (('old',p.BASE),('new',p.OUT)):
        cpp=out/(name+'_kernel.cpp');p.write(cpp,wrapper);dll=cpp.with_suffix('.dll')
        result=subprocess.run([shutil.which('g++'),'-shared','-O2','-std=c++17','-I',str(package/'nucleo/Inc'),str(cpp),'-o',str(dll)],capture_output=True,text=True)
        p.write(out/(name+'_kernel_build.log'),result.stdout+result.stderr);result.check_returncode()
        lib=ctypes.CDLL(str(dll));lib.control_size.restype=lib.output_size.restype=ctypes.c_uint
        lib.control.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]+[ctypes.c_float]*5+[ctypes.c_int,ctypes.c_void_p]
        lib.modulation.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]+[ctypes.c_float]*3+[ctypes.c_void_p]
        libs.append(lib)
    assert libs[0].control_size()==libs[1].control_size()
    assert libs[0].output_size()==libs[1].output_size()
    controls=[ctypes.create_string_buffer(l.control_size()) for l in libs]
    outputs=[ctypes.create_string_buffer(l.output_size()) for l in libs]
    def compare(method,args):
        rc=[getattr(l,method)(c,*args,o) for l,c,o in zip(libs,controls,outputs)]
        assert rc[0]==rc[1] and controls[0].raw==controls[1].raw and outputs[0].raw==outputs[1].raw,(method,args,rc)
    g=(ctypes.c_uint32*6)(5312,5184,771,112,240,229)
    x=(ctypes.c_float*6)();rng=random.Random(3002)
    # Includes saturation, aperture projections, invalid/stale/bus/current stops,
    # both algorithms, and enough accumulated time to pass the torque ramp.
    counts=0
    for k in range(180000):
        phase=k*.017
        x[:]=[.3*math.sin(phase),.3*math.cos(phase),.24*math.cos(phase*.2),.24*math.sin(phase*.2),rng.uniform(-10,350),0]
        ia=rng.uniform(-1.1,1.1);ib=rng.uniform(-1.1,1.1)
        hz=rng.choice((0,5,30,50));bus=rng.uniform(300,330);dt=1/16000;fresh=1
        if k%1009==0:ia=math.nan
        if k%1013==0:ia=2.0
        if k%1019==0:fresh=0
        if k%1021==0:bus=29
        if k%1031==0:dt=.0003
        compare('control',(x,g,2+k%2,ia,ib,hz,bus,dt,fresh));counts+=1
    modulations=0
    for k in range(75000):
        arr=rng.choice((1024,2048,5312,16384,65535));g[:]=(arr,arr-24,min(200,arr//8),16,arr//24,20)
        compare('modulation',(g,2+k%2,rng.uniform(-150,150),rng.uniform(-150,150),rng.uniform(300,330)))
        modulations+=1
    capture=p.BASE/'powered_FOC_CPU_IRQ_20261030_r1/ADC_peak_decoded.json'
    record=json.loads(p.read(capture));recorded=0
    # Actual raw delta counts are transferred through the exact released scale.
    for row in record['samples']:
        raw=row.get('counts_uvw')
        if raw is None:continue
        ia=row['nominal_currents_a'][0]
        ib=(ia+2*row['nominal_currents_a'][1])*.5773502692
        g[:]=(5312,5184,771,112,240,229)
        compare('control',(x,g,2,ia,ib,5.,323.,1/16000,1));recorded+=1
    # Compile the entire released native adapter with host register seams.
    fixture=p.read(p.BASE/'verification/native_runtime.cpp')
    pre=fixture.split('#define MIC_NATIVE_BUILD',1)[0]
    native=p.read(p.OUT/'nucleo/Src/multi_native.c')
    for name in ('ma_native_profile_tick','fe_profile_tick','fe_profile_service'):
        f=function(native,name);native=native.replace(f,f.replace('DWT->CYCCNT','host_profile_clock()'))
    native='\n'.join(l for l in native.splitlines() if not l.startswith(('#include','#pragma')))
    tail=fixture[fixture.index('static void NVIC_SetPendingIRQ(int irq){'):].replace('2026102972','2026103002')
    common.compile_run(out,'native_fast',pre+native+'\n'+tail)
    tree=ast.parse(p.read(p.ROOT/'tools/test_foc_runtime_fix.py'))
    checks=next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='checks' for t in n.targets))
    checks=checks.replace('2026102972','2026103002')
    head=tail.split('int main(){',1)[0]
    common.compile_run(out,'fast_reasons','#include <cstdio>\n#include "foc_timing_wire.h"\n'+pre+native+'\n'+head+checks)
    guards=r'''
int main(){
 for(unsigned q:{7U,128U})for(unsigned field=0;field<13;++field){
  timer.BDTR=0;selected=MA_FOC;cycle.CYCCNT=1000000;
  fe_complete=1;fe_case=64;fe_fault=0;id_profile_attempted=1;id_profile_running=0;
  fake_bus=323;sample={};sample.valid=sample.zero=1;sample_coherent=1;
  assert(ma_native_prepare());qualification=q;profile_ready=1;
  uint32_t bad=0x7fc00000U,save;memcpy(&save,(char*)&model+field*4,4);
  memcpy((char*)&model+field*4,&bad,4);
  timer.BDTR=1;sample.cycles=cycle.CYCCNT;
  assert(ma_native_fast(5)!=MC_NO_ERROR);
  memcpy((char*)&model+field*4,&save,4);
 }
}
'''
    common.compile_run(out,'per_frame_model_guards','#include <initializer_list>\n'+pre+native+'\n'+head+guards)
    unchanged=['nucleo/Src/current_shunt.c','nucleo/Inc/current_adc_window_plan.h','nucleo/Inc/current_adc_deadline.h','nucleo/Inc/local_stop.h','nucleo/Inc/foc_timing_core.h','nucleo/Inc/foc_timing_irq.h']
    for rel in unchanged:assert (p.BASE/rel).read_bytes()==(p.OUT/rel).read_bytes(),rel
    before=p.read(p.BASE/'nucleo/Src/multi_native.c')
    for guard in ('elapsed>SystemCoreClock/16000U/2U','(uint32_t)(begin-sample.cycles)<SystemCoreClock*3U/16000U','(uint32_t)(begin-est_cycles)<SystemCoreClock/500U','if(dt>.002f)'):
        assert guard in before and guard in native,guard
    report=dict(passed=True,**rounding_report,actual_C_control_bitwise_equivalent_cases=counts,
        actual_C_modulator_bitwise_equivalent_cases=modulations,recorded_cases=recorded,
        native_adapter_regressions_passed=True,per_frame_invalid_model_tests=26,
        stale_reasons_first_fault_and_autostop_unchanged=True,unchanged_protection_sources=unchanged,
        target_timing_measured=False,hardware_commands=0)
    p.write(out/'selftest.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
