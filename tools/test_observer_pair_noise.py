"""Independent coordinate/batch-Kalman tests and conditional saved-step audit."""
import ctypes as ct,json,shutil,subprocess
import numpy as np
import prepare_observer_pair_noise as p
from check_observer_equations_offline import Motor,Observer,f,rk4,jacobian


def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True)
 code=out/'pair_kernel.cpp';dll=out/'pair_kernel.dll'
 code.write_text(r'''
#include <cassert>
#include <cstddef>
#include "foc_experiment.h"
#include "multi_native.h"
#include "observer_current_window.h"
extern "C" __declspec(dllexport) int noise(unsigned n,float*r){ma_noise v;if(!ma_pair_noise(n,&v))return 0;memcpy(r,&v,sizeof(v));return 1;}
extern "C" __declspec(dllexport) int step(ma_observer*o,const ma_motor*m,const float*v,unsigned n){ma_noise r;if(!ma_pair_noise(n,&r))return MA_INVALID;return ma_observe_noise(o,m,v[0],v[1],v[2],v[3],v[4],&r);}
extern "C" __declspec(dllexport) unsigned guards(){
 unsigned count=0;ma_noise n;for(unsigned bad:{0U,15U,17U,0xffffU,0x10000U}){assert(!ma_pair_noise(bad,&n));++count;}
 ma_motor m=FE_ESTIMATED_MOTOR;ma_observer o={};ma_controller c={};ma_reset(&o,&c);
 assert(ma_observe(&o,&m,.1f,.1f,1,2,.0021f)==MA_INVALID);++count;
 ma_noise bad={.0004f,.001f,.0004f};assert(ma_observe_noise(&o,&m,.1f,.1f,1,2,.001f,&bad)==MA_INVALID);++count;
 ma_geometry g={5312,5184,771,112,240,229};ma_output output;float x[6]={.3f,0,.2f,0,20,0};
 assert(ma_control(&c,&m,x,&g,MA_FOC,1.351f,0,5,321,1.f/16000,1,&output)==MA_CURRENT);++count;
 assert(ma_control(&c,&m,x,&g,MA_FOC,.3f,0,5,321,1.f/16000,0,&output)==MA_STALE);++count;
 assert(FE_FAST_BUDGET==4000&&FE_OBSERVER_BUDGET==85000);++count;
 assert(sizeof(ma_current_sample)==32&&offsetof(ma_current_sample,ccr)==20&&offsetof(ma_current_sample,pair)==30);++count;
 ow_state window;ow_reset(&window,1000);ow_bin bin;unsigned expected=0;
 assert(ow_push_pair(&window,11624,31875,.1f,.2f,1,2,&bin,3)==-1&&window.n==0);++count;
 for(unsigned i=0;i<16;++i){unsigned pair=i%3;expected+=1U<<(pair*5);int rc=ow_push_pair(&window,1000+(i+1)*10624,31875,.1f,.2f,1,2,&bin,pair);assert(rc==(i==15));++count;}
 assert(bin.pair_counts==expected&&window.pair_counts==0&&ma_pair_noise(bin.pair_counts,&n));++count;
 assert(ow_push_pair(&window,window.last,31875,.1f,.2f,1,2,&bin,0)==-1);++count;
 // Correlated-R correction must NOT weaken the old fixed-R shutdown metric.
 // Here the corrected diagnostic NIS is below50, but the preserved legacy
 // metric exceeds50 for the20th consecutive step and MUST stop.
 ma_observer guarded={};for(unsigned i=0;i<6;++i)guarded.p[i][i]=1e-7f;
 guarded.steps=500;guarded.rejected=19;assert(ma_pair_noise(16U<<5,&n));
 int rc=ma_observe_noise(&guarded,&m,0,.15f,0,0,.001f,&n);
 assert(guarded.nis<50&&guarded.rejected==20&&rc==MA_OBSERVER);++count;
 // Also retain the corrected metric: a low legacy statistic must not hide
 // a20-step event which is larger in the correctly transformed coordinates.
 guarded={};for(unsigned i=0;i<6;++i)guarded.p[i][i]=1e-7f;
 guarded.steps=500;guarded.rejected=19;assert(ma_pair_noise(16U<<10,&n));
 rc=ma_observe_noise(&guarded,&m,0,.13f,0,0,.001f,&n);
 assert(guarded.nis>50&&guarded.rejected==20&&rc==MA_OBSERVER);++count;
 return count;
}
''',encoding='utf8')
 run=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-shared','-Wall','-Wextra','-Werror','-include','initializer_list',
   '-I',str(p.OUT/'nucleo/Inc'),str(code),'-o',str(dll)],capture_output=True,text=True)
 (out/'pair_kernel_build.log').write_text(run.stdout+run.stderr,encoding='utf8');run.check_returncode()
 lib=ct.CDLL(str(dll));lib.noise.argtypes=[ct.c_uint,ct.POINTER(ct.c_float)];lib.step.argtypes=[ct.POINTER(Observer),ct.POINTER(Motor),ct.POINTER(ct.c_float),ct.c_uint]
 guards=lib.guards()
 cap=p.BASE/'FOC_5Hz_r1';saved=json.loads(p.read(cap/'observer_trace_decoded.json'))['first_nis_replay']
 md=saved['motor'];model=Motor(**md);m=[md[k] for k in ('rs','rr','ls','lr','lm','j','b','poles')]
 x=np.array(saved['prior_state']);P=np.array(saved['prior_covariance']);v=np.array([saved['inputs'][k] for k in ('ia_A','ib_A','va_V','vb_V','dt_s')],dtype='float32')
 xp=rk4(m,x,v[2:4],v[4]);A=jacobian(lambda z:f(m,z,v[2:4]),x);dt=float(v[4]);F=np.eye(6)+dt*A+.5*dt*dt*A@A
 pm=F@P@F.T+np.diag([.02,.02,.00001,.00001,4,.0001])*dt
 Ts=[np.array([[1,0],[1/np.sqrt(3),2/np.sqrt(3)]]),np.array([[1,0],[-1/np.sqrt(3),-2/np.sqrt(3)]]),np.array([[-1,-1],[1/np.sqrt(3),-1/np.sqrt(3)]])]
 results=[];maxerr=0.
 for n0 in range(17):
  for n1 in range(17-n0):
   ns=[n0,n1,16-n0-n1];packed=sum(n<<(5*i) for i,n in enumerate(ns));buf=(ct.c_float*3)();assert lib.noise(packed,buf)
   R=.0004*sum(n*(T@T.T) for n,T in zip(ns,Ts))/16
   np.testing.assert_allclose(buf,[R[0,0],R[0,1],R[1,1]],rtol=3e-7,atol=1e-11)
   o=Observer();o.steps=saved['prior_steps'];o.rejected=saved['prior_rejected']
   for i in range(6):
    o.x[i]=x[i]
    for j in range(6):o.p[i][j]=P[i,j]
   values=(ct.c_float*5)(*v);assert lib.step(ct.byref(o),ct.byref(model),values,packed)==0
   S=pm[:2,:2]+R;e=v[:2]-xp[:2];want=float(e@np.linalg.solve(S,e));K=np.linalg.solve(S,pm[:2,:]).T
   post=xp+K@e;I=np.eye(6);I[:,:2]-=K;cov=I@pm@I.T+K@R@K.T
   err=abs(o.nis-want)/(1+want);maxerr=max(maxerr,err);assert err<2e-5
   np.testing.assert_allclose(o.x,post,rtol=2e-5,atol=1e-6)
   np.testing.assert_allclose(o.p,cov,rtol=2e-4,atol=1e-7)
   assert np.linalg.eigvalsh(np.array(o.p)).min()>0
   results.append(dict(pair_counts=ns,NIS=float(o.nis),passes_25=o.nis<25))
 for pair,T in enumerate(Ts):
  # Explicit reconstruction of independent phase errors, not reuse of firmware
  # covariance formula: sample400k two-channel errors and map through Clarke.
  rng=np.random.default_rng(171600+pair);z=rng.normal(0,.02,(400000,2))@T.T
  R=.0004*T@T.T;nis=np.einsum('ni,ij,nj->n',z,np.linalg.inv(R),z)
  assert abs(nis.mean()-2)<.015
  np.testing.assert_allclose(np.cov(z.T),R,rtol=.015,atol=3e-6)
 # Physical trip/age/window/Break modules are not replaced by statistical gates.
 for rel in ('nucleo/Inc/foc_experiment.h','nucleo/Inc/current_adc_window_plan.h','nucleo/Inc/current_adc_deadline.h','nucleo/Inc/local_stop.h','nucleo/Inc/first_break_snapshot.h'):
  assert p.read(p.OUT/rel)==p.read(p.BASE/rel),rel
 orig=p.read(p.BASE/'nucleo/Src/current_shunt.c');new=p.read(p.OUT/'nucleo/Src/current_shunt.c')
 new=new.replace(' out->pair=ma_fast_sample.pair;out->reserved=0;\n','').replace(' ma_fast_sample.pair=pair;ma_fast_sample.reserved=0;\n','')
 assert new==orig,'ADC protection/math changed beyond passing the real pair'
 report=dict(passed=True,hardware_commands=0,guards=guards,pair_mixtures_checked=len(results),
  independent_noise_samples=1200000,max_relative_NIS_error_vs_batch_double=maxerr,
  saved_step_results=results,record_pair_history_missing=True,physical_replay_corrected=False,
  Q_and_phase_noise_floor_unchanged=True,NIS_threshold_unchanged=True,physical_noise_scale_qualified=False,
  interpretation='Counterfactual correction at frozen saved prior x/P; actual16-pair composition was not saved, so physical success is not claimed')
 (out/'pair_kernel_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:v for k,v in report.items() if k!='saved_step_results'}))
 print('Constant U/W NIS:',next(x['NIS'] for x in results if x['pair_counts']==[0,16,0]))


if __name__=='__main__':main()
