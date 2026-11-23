"""Compare installed C EKF with independent flux equations and batch update.

Read-only on firmware/captures. All generated results stay in the investigation
directory. This does not measure target CPU time or establish real motor speed.
"""
import ctypes as ct
import json
import shutil
import subprocess
import numpy as np

from investigate_remaining_observer_nis import OUT, RELEASE, write


class Motor(ct.Structure):
    _fields_=[(k,ct.c_float) for k in ('rs','rr','ls','lr','lm','j','b')]+[
        ('poles',ct.c_uint32)]+[(k,ct.c_float) for k in (
            'flux','current_limit','trip_current','current_bw','speed_bw')]


class Observer(ct.Structure):
    _fields_=[('x',ct.c_float*6),('p',(ct.c_float*6)*6),('nis',ct.c_float),
              ('predicted_i',ct.c_float*2),('innovation',ct.c_float*2),
              ('innovation_variance',ct.c_float*2),('steps',ct.c_uint32),('rejected',ct.c_uint32)]


def f(m,x,v):
    # Independently written stator/rotor FLUX formulation, transformed back
    # to the installed observer's current + rotor-flux coordinates.
    rs,rr,ls,lr,lm,j,b,poles=m
    leak=ls-lm*lm/lr; kr=lm/lr
    current=x[:2]; rotor_flux=x[2:4]; omega=x[4]
    stator_flux=leak*current+kr*rotor_flux
    rotor_current=(rotor_flux-lm*current)/lr
    rotation=np.array([-rotor_flux[1],rotor_flux[0]])*poles*omega
    d_rotor=-rr*rotor_current+rotation
    d_stator=v-rs*current
    d_current=(d_stator-kr*d_rotor)/leak
    torque=1.5*poles*(stator_flux[0]*current[1]-stator_flux[1]*current[0])
    return np.r_[d_current,d_rotor,(torque-x[5]-b*omega)/j,x[5]*0]


def rk4(m,x,v,dt):
    a=f(m,x,v);bb=f(m,x+dt*a/2,v);c=f(m,x+dt*bb/2,v);d=f(m,x+dt*c,v)
    return x+dt*(a+2*bb+2*c+d)/6


def jacobian(function,x):
    result=np.empty((6,6))
    for k in range(6):
        z=x.astype(complex);z[k]+=1e-20j
        result[:,k]=np.imag(function(z))/1e-20
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=OUT/'equation_bridge.cpp'
    source.write_text('''#include "foc_experiment.h"
extern "C" __declspec(dllexport) void get_model(ma_motor*m){*m=FE_ESTIMATED_MOTOR;}
extern "C" __declspec(dllexport) int observe(ma_observer*o,const ma_motor*m,float ia,float ib,float va,float vb,float dt){return ma_observe(o,m,ia,ib,va,vb,dt);}
extern "C" __declspec(dllexport) void derivative(const ma_motor*m,const float*x,float va,float vb,float*y,float*a){ma_derivative(m,x,va,vb,y,(float(*)[6])a);}
''',encoding='utf8')
    dll=OUT/'equation_bridge.dll'
    build=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-shared','-Wall','-Wextra','-Werror',
                          '-I',str(RELEASE/'nucleo/Inc'),str(source),'-o',str(dll)],
                         capture_output=True,text=True)
    (OUT/'equation_bridge_build.log').write_text(build.stdout+build.stderr,encoding='utf8')
    build.check_returncode()
    lib=ct.CDLL(str(dll));fp=ct.POINTER(ct.c_float)
    lib.get_model.argtypes=[ct.POINTER(Motor)]
    lib.observe.argtypes=[ct.POINTER(Observer),ct.POINTER(Motor)]+[ct.c_float]*5
    lib.derivative.argtypes=[ct.POINTER(Motor),fp,ct.c_float,ct.c_float,fp,fp]
    model=Motor();lib.get_model(ct.byref(model))
    m=[getattr(model,k) for k in ('rs','rr','ls','lr','lm','j','b','poles')]
    rng=np.random.default_rng(20261117)
    maxima=dict(derivative_scaled=0.,jacobian_scaled=0.,predicted_current_A=0.,
                posterior_state_scaled=0.,posterior_covariance_scaled=0.,NIS_scaled=0.,
                covariance_transition_difference_scaled=0.)
    cases=0
    variational='Experimental RK4 variational transition' in (RELEASE/'nucleo/Inc/motor_control.h').read_text(encoding='utf8')
    transitions=[]
    for dt0 in (.0005,.001,.002):
        local_max=0.
        for _ in range(40):
            obs=Observer();obs.steps=100
            x=np.r_[rng.uniform(-.6,.6,2),rng.uniform(-.25,.25,2),rng.uniform(-45,45),rng.uniform(-.005,.005)].astype('float32')
            raw=rng.normal(size=(6,6))*np.sqrt(np.array([.0025,.0025,.0025,.0025,10,.0025]))[:,None]/np.sqrt(6)
            P=(raw@raw.T+np.eye(6)*1e-6).astype('float32')
            v=rng.uniform(-16,16,2).astype('float32');y=rng.uniform(-.6,.6,2).astype('float32')
            dt=float(np.float32(dt0));x64=x.astype(float);P64=P.astype(float)
            for i in range(6):
                obs.x[i]=x[i]
                for j in range(6):obs.p[i][j]=P[i,j]
            out=np.zeros(6,dtype='float32');a=np.zeros((6,6),dtype='float32')
            lib.derivative(ct.byref(model),x.ctypes.data_as(fp),float(v[0]),float(v[1]),out.ctypes.data_as(fp),a.ctypes.data_as(fp))
            analytic=jacobian(lambda z:f(m,z,v),x64)
            maxima['derivative_scaled']=max(maxima['derivative_scaled'],float(np.max(abs(out-f(m,x64,v))/(1+abs(f(m,x64,v))))))
            maxima['jacobian_scaled']=max(maxima['jacobian_scaled'],float(np.max(abs(a-analytic)/(1+abs(analytic)))))
            xp=rk4(m,x64,v,dt)
            second_order=np.eye(6)+dt*analytic+.5*dt*dt*(analytic@analytic)
            exactF=jacobian(lambda z:rk4(m,z,v,dt),x64)
            F=exactF if variational else second_order
            pm=F@P64@F.T+np.diag([.02,.02,.00001,.00001,4,.0001])*dt
            S=pm[:2,:2]+np.eye(2)*.0004
            e=y-xp[:2];K=np.linalg.solve(S,pm[:2,:]).T
            nis=float(e@np.linalg.solve(S,e));posterior=xp+K@e
            KH=np.zeros((6,6));KH[:,:2]=K;I=np.eye(6)-KH
            covariance=I@pm@I.T+K@(.0004*np.eye(2))@K.T
            rc=lib.observe(ct.byref(obs),ct.byref(model),float(y[0]),float(y[1]),float(v[0]),float(v[1]),dt)
            assert rc==0
            measured_x=np.array(obs.x);measured_p=np.array(obs.p)
            maxima['predicted_current_A']=max(maxima['predicted_current_A'],float(np.max(abs(np.array(obs.predicted_i)-xp[:2]))))
            maxima['posterior_state_scaled']=max(maxima['posterior_state_scaled'],float(np.max(abs(measured_x-posterior)/(1+abs(posterior)))))
            maxima['posterior_covariance_scaled']=max(maxima['posterior_covariance_scaled'],float(np.max(abs(measured_p-covariance)/(1+abs(covariance)))))
            maxima['NIS_scaled']=max(maxima['NIS_scaled'],abs(obs.nis-nis)/(1+abs(nis)))
            difference=float(np.max(abs(exactF-second_order)/(1+abs(exactF))))
            local_max=max(local_max,difference)
            maxima['covariance_transition_difference_scaled']=max(maxima['covariance_transition_difference_scaled'],difference)
            assert np.linalg.eigvalsh(measured_p.astype(float)).min()>-1e-7
            assert abs(obs.nis-nis)/(1+abs(nis))<1e-4
            assert np.max(abs(measured_x-posterior)/(1+abs(posterior)))<1e-4
            cases+=1
        transitions.append(dict(dt_s=dt0,max_scaled_difference_second_order_vs_RK4=local_max))
    assert maxima['jacobian_scaled']<2e-6 and maxima['predicted_current_A']<2e-6
    write(OUT/'equation_report.json',dict(passed=True,cases=cases,maxima=maxima,transitions_by_dt=transitions,
          hardware_commands=0,firmware_changed=False,comparison='independent double flux model, complex-step Jacobian, batch two-channel Kalman/Joseph update',
          exact_physical_trace_replayed=False,target_CPU_measured=False,
          covariance_transition_variant='RK4_variational' if variational else 'second_order',
          hardware_cause_proven=False))
    print(json.dumps(dict(passed=True,cases=cases,maxima=maxima)))


if __name__=='__main__':main()
