"""Compile exact V/f, PWM, SDK ramp and angle code; no device connection."""
import json
import re
import subprocess
import sys
from pathlib import Path
import audit_production_pwm_filters as audit
from uart_tx_dma_selftest import body
import prepare_vf_smooth_start as package

ROOT,C,BASE=package.ROOT,package.OUT,package.BASE
TEST=r'''
static unsigned checks;
static void check(bool ok,const char*why){++checks;if(!ok){fprintf(stderr,"FAIL %s\n",why);exit(1);}}
static float voltage(ACIM_VF_Handle_t &h,float f){h.fFlux_Freq_Hz=f;check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"voltage calculation");return h.VoltageAmpl;}
int main(){
 TIM_TypeDef timer;PWM_Handle_t pwm{&timer};ACIM_VF_Handle_t h{&pwm};
 h.fFlux_Angle_rad=.7f;h.fVoutMax_PWM_Mod_V=200;
 h.fFlux_Freq_Hz=9.999f;old_ACIM_VF_Controller(&h);float oldlow=h.VoltageAmpl;
 h.fFlux_Freq_Hz=10;old_ACIM_VF_Controller(&h);float oldhigh=h.VoltageAmpl;
 check(oldhigh-oldlow>15.9f,"old15.9V discontinuity reproduced");
 check(voltage(h,0)==0,"zero frequency means zero voltage reference");
 check(fabs(voltage(h,5)-20)<.00003f,"original5Hz20V peak anchor preserved");
 float left=voltage(h,9.999f),join=voltage(h,10),right=voltage(h,10.001f);
 check(join-left<.004f && right-join<.004f,"10Hz has no amplitude jump");
 float ls=(join-left)/.001f,rs=(right-join)/.001f;
 check(fabs(ls-rs)<.03f && ls>3.5f && ls<3.7f,"voltage slope joins linear branch continuously");
 float previous=0,max_step=0;
 for(unsigned i=0;i<=50000;++i){
  float value=voltage(h,i*.001f);
  check(value+.00003f>=previous,"dense0..50Hz voltage profile monotonic");
  max_step=std::max(max_step,value-previous);previous=value;
 }
 check(max_step<.0054f,"no hidden voltage discontinuity in dense sweep");
 unsigned controller_calls=0;float max_linear_ccr_difference=0;
 for(float bus:{250.f,325.f,380.f}){
  h.fVoutMax_PWM_Mod_V=bus/2;
  for(unsigned fi=0;fi<=500;++fi)for(unsigned angle=0;angle<360;++angle){
   h.fFlux_Freq_Hz=fi*.1f;h.fFlux_Angle_rad=angle*(2*PI/360);writes=0;
   check(ACIM_VF_Controller(&h)==MC_NO_ERROR && writes==3,"all frequency/angle combinations publish valid PWM");
   for(float d:{pwm.fDuty1,pwm.fDuty2,pwm.fDuty3})check(mic_float_isfinite(d) && d>=0 && d<=1,"duty finite and bounded");
   check(timer.CCR1<timer.ARR && timer.CCR2<timer.ARR && timer.CCR3<timer.ARR,"compare below timer period");
   if(fi>=100){
    float newvoltage=h.VoltageAmpl;uint32_t a=timer.CCR1,b=timer.CCR2,c=timer.CCR3;
    check(old_ACIM_VF_Controller(&h)==MC_NO_ERROR,"old linear branch valid");
    check(fabs(h.VoltageAmpl-newvoltage)<.00005f,"linear amplitude above10Hz unchanged");
    float delta=std::max({fabs(float(a)-timer.CCR1),fabs(float(b)-timer.CCR2),fabs(float(c)-timer.CCR3)});
    max_linear_ccr_difference=std::max(max_linear_ccr_difference,delta);check(delta<=1,"linear duty rounding within one timer count");
   }
   ++controller_calls;
  }
 }
 // Exact MCSDK ramp runs at500Hz; phase/PWM run at16kHz as in this project.
 FILE*trace=fopen("ramp0_to50.csv","w");check(trace,"open ramp trace");
 fprintf(trace,"time_ms,field_hz,phase_peak_v,phase_angle_rad,duty_u,duty_v,duty_w\n");
 float max_freq_step=0,max_ramp_voltage_step=0;unsigned ramp_cases=0;
 for(unsigned rate:{1U,5U,10U}){
  RampExtMngr_Handle_t ramp{};ramp.FrequencyHz=500;REMNG_Init(&ramp);
  Motor motor{1};Speed speed{};h=ACIM_VF_Handle_t{&pwm};h.pRMNGR=&ramp;h.pACIM_MotorParams=&motor;h.SPD_real=&speed;h.bVF_Mode=VF_OL;
  h.fCalcAngleExecTime_s=1.f/16000;h.fVoutMax_PWM_Mod_V=162.5f;
  unsigned duration=50000/rate;check(ACIM_VF_ExecRamp(&h,500,duration),"SDK accepts0..50Hz ramp");
  float last_hz=0,last_v=0;
  for(unsigned ms=0;ms<=duration+4;ms+=2){
   ACIM_VF_FluxFreqCalc(&h);float hz=h.fFlux_Freq_Hz;
   check(hz>=last_hz-.00001f && hz<=50 && hz-last_hz<.1001f,"actual ramp frequency is monotonic and bounded to0.1Hz steps");
   max_freq_step=std::max(max_freq_step,hz-last_hz);
   for(unsigned tick=0;tick<32;++tick){
    float old_angle=h.fFlux_Angle_rad;ACIM_VF_CalcAngle(&h);
    float advance=h.fFlux_Angle_rad-old_angle;if(advance<0)advance+=2*PI;
    check(advance>=0 && advance<.0197f,"actual integrated phase has no reset/jump");
    check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"actual ramp and angle drive exact PWM calculation");
   }
   float delta=h.VoltageAmpl-last_v;
   check(delta>=-.00005f && delta<.53f,"ramp voltage has no former15.9V step");
   max_ramp_voltage_step=std::max(max_ramp_voltage_step,delta);
   if(rate==5 && (ms%20==0 || ms==duration+4))fprintf(trace,"%u,%.6f,%.6f,%.6f,%.7f,%.7f,%.7f\n",ms,hz,h.VoltageAmpl,h.fFlux_Angle_rad,pwm.fDuty1,pwm.fDuty2,pwm.fDuty3);
   last_hz=hz;last_v=h.VoltageAmpl;
  }
  check(ACIM_VF_RampCompleted(&h) && h.fFlux_Freq_Hz==50,"SDK reaches50Hz and completes");++ramp_cases;
  float old_ref=h.fFlux_Freq_Hz;check(ACIM_VF_ExecRamp(&h,250,5000),"retarget ramp accepted");
  ACIM_VF_FluxFreqCalc(&h);check(old_ref-h.fFlux_Freq_Hz<.1001f,"retarget does not jump to new target");
 }
 fclose(trace);
 // Invalid values and profiles still fail before publishing compare registers.
 for(float bad:{0.f,-1.f,NAN,INFINITY}){h=ACIM_VF_Handle_t{&pwm};h.fVoutMax_PWM_Mod_V=bad;writes=0;
  check(ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0,"invalid normalizer fails closed");}
 h=ACIM_VF_Handle_t{&pwm};h.fVoltage_Offset=100;writes=0;
 check(ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0,"nonmonotonic low-speed boost configuration rejected");
 h=ACIM_VF_Handle_t{&pwm};h.fMinFreq_TH_Hz=0;check(voltage(h,0)==0,"zero join threshold never divides by zero");
 h=ACIM_VF_Handle_t{&pwm};h.fVoutMax_PWM_Mod_V=200;
 check(fabs(voltage(h,-5)-20)<.00003f,"negative-frequency amplitude remains symmetric");
 printf("{\"passed\":true,\"checks\":%u,\"controller_sweep_calls\":%u,\"ramp_cases\":%u,\"old_voltage_jump_v\":%.6f,\"new_join_left_v\":%.6f,\"new_join_v\":%.6f,\"new_join_right_v\":%.6f,\"left_slope_v_per_hz\":%.6f,\"right_slope_v_per_hz\":%.6f,\"maximum_0_001hz_voltage_step_v\":%.6f,\"maximum_actual_ramp_frequency_step_hz\":%.6f,\"maximum_actual_ramp_voltage_step_v\":%.6f,\"max_above10hz_ccr_difference\":%.1f,\"hardware_commands\":0}\n",
 checks,controller_calls,ramp_cases,oldhigh-oldlow,left,join,right,ls,rs,max_step,max_freq_step,max_ramp_voltage_step,max_linear_ccr_difference);
}
'''

def main():
    out=C/'selftest';checks=[]
    def check(v,name):
        checks.append(dict(name=name,passed=bool(v)))
        if not v:raise AssertionError(name)
    def run(cmd,label,cwd=out):
        p=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace')
        (out/(label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        if p.returncode:raise RuntimeError(label+': '+(p.stderr or p.stdout)[-2500:])
        return p.stdout
    base=C/'nucleo';lib=base/'MCSDK_v6.4.2-Full/MotorControl/MCSDK'
    vf=package.read(C/package.VF);old=package.read(BASE/package.VF)
    pwm=package.read(base/audit.PWM);math=package.read(base/'Src/mc_math.c')
    header=package.read(lib/'MCLib/Any/Inc/ramp_ext_mngr.h')
    struct=header[header.index('typedef struct'):header.index('} RampExtMngr_Handle_t;')+len('} RampExtMngr_Handle_t;')]
    ramp=package.read(lib/'MCLib/Any/Src/ramp_ext_mngr.c').replace('#include "ramp_ext_mngr.h"','')
    preamble=audit.PREAMBLE.replace('using std::isfinite;','#include <cstring>\n#include <cstdlib>\nusing std::isfinite;\n#define SPEED_UNIT 10\n'+struct+'\n')
    preamble=preamble.replace('void ACIM_VF_CalcAngle(ACIM_VF_Handle_t *){}','')
    preamble=preamble.replace('struct ACIM_VF_Handle_t {PWM_Handle_t *pPWM;','''enum {VF_OL,VF_CL};struct Motor{uint8_t bPP;};struct Speed{int16_t hAvrMecSpeedUnit;};
struct ACIM_VF_Handle_t {PWM_Handle_t*pPWM;RampExtMngr_Handle_t*pRMNGR=nullptr;Motor*pACIM_MotorParams=nullptr;Speed*SPD_real=nullptr;void*fPI=nullptr;
 int bVF_Mode=VF_OL;int16_t hElAngle=0;float fFlux_Freq_rads=0,fCalcAngleExecTime_s=0,
 fRotorFreqRef_rads=0,fRotorFreqRef_RPM=0,fSlipFrequency_rads=0;
''')
    preamble+='\nfloat PI_Float_Calc(void*,float){return 0;}\n'
    unit=lib/'MCLibACIM/Any/Src/unit_conversions.c'
    # The unused CL PI is stubbed; ramp, flux, angle conversion and PWM are exact.
    conversion=audit.function(package.read(unit),'Convert_Rad_to16bit')
    table=re.search(r'#define SIN_FLOAT_0_90_TABLE.*?\}',math,re.S)[0]
    code=preamble+ramp+'\n'+conversion+'\n'+audit.function(vf,'mic_float_isfinite')+'\n'+table+'\nconst float fSin_Table[256]=SIN_FLOAT_0_90_TABLE;\n'
    code+=audit.function(math,'MCM_floatTrig_Functions')+'\n'+audit.function(pwm,'PWM_SetPhasePWMOutputs')+'\n'
    for name in ('ACIM_VF_ExecRamp','ACIM_VF_RampCompleted','ACIM_VF_FluxFreqCalc','ACIM_VF_CalcAngle','ACIM_VF_Controller'):
        code+=body(vf,name)+'\n' if name not in ('ACIM_VF_ExecRamp','ACIM_VF_FluxFreqCalc') else audit.function(vf,name)+'\n'
    code+=audit.function(old,'ACIM_VF_Controller').replace('ACIM_VF_Controller','old_ACIM_VF_Controller')+'\n'
    (out/'actual_vf_ramp.cpp').write_text(code+TEST,encoding='utf-8')
    flags=['g++','-std=c++17','-Ofast','-Wall','-Wextra','-Werror']
    exe=out/'vf_ramp.exe';run(flags+[str(out/'actual_vf_ramp.cpp'),'-o',str(exe)],'vf_compile')
    result=json.loads(run([str(exe)],'vf_run'));check(result['passed'],'actual controller/ramp/phase arithmetic')
    # Old formula must fail the same smoothness checks.
    mutant=code.replace(body(vf,'ACIM_VF_Controller'),body(old,'ACIM_VF_Controller'))
    (out/'old_curve.cpp').write_text(mutant+TEST,encoding='utf-8');mex=out/'old_curve.exe'
    run(flags+[str(out/'old_curve.cpp'),'-o',str(mex)],'old_curve_compile')
    p=subprocess.run([str(mex)],cwd=out,capture_output=True,text=True)
    (out/'old_curve_run.log').write_text(p.stdout+p.stderr,encoding='utf-8')
    check(p.returncode!=0 and 'FAIL ' in p.stderr,'old curve fails same continuity test')
    # Everything except the curve, its parameter comment and exact pair lists is unchanged.
    m=json.loads(package.read(BASE/'manifest.json'));changed=[]
    for rel in m['source_sha256']:
        if (BASE/rel).read_bytes()==(C/rel).read_bytes():continue
        expected=package.read(BASE/rel)
        if not rel.startswith('web_hmi/'):
            expected=expected.replace(str(package.OLD[0]),str(package.NEW[0])).replace(str(package.OLD[1]),str(package.NEW[1]))
        if expected!=package.read(C/rel):changed.append(rel)
    check(set(changed)=={package.VF,'nucleo/Inc/acim_vf_parameters.h','web_hmi/server.py'},'scope of firmware changes bounded')
    # Transport, Break, ADC, timer settings and command guards remain byte-for-byte.
    uart_dir=out/'uart';uart_dir.mkdir(exist_ok=True)
    executable=uart_dir/'replay.exe'
    run(flags+['-I',str(BASE/'selftest'),'-I',str(C/'nucleo/Inc'),str(ROOT/'tools/uart_clean_confirm_test.cpp'),'-o',str(executable)],'uart_compile')
    uart=json.loads(run([str(executable)],'uart_run',cwd=uart_dir));check(uart['pass'],'7447 actual UART regression checks retained')
    import importlib.util
    spec=importlib.util.spec_from_file_location('vf_smooth_hmi',C/'web_hmi/server.py')
    hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
    new=dict(fw_build=package.NEW[0],mc_fw_build=package.NEW[1],manual_scalar_capable=1)
    check(hmi.manual_scalar_supported(new),'new exact pair accepted')
    check(not hmi.manual_scalar_supported(dict(new,mc_fw_build=package.OLD[1])),'mixed pair rejected')
    cal=dict(fw_build=package.OLD[0],mc_fw_build=package.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    check(hmi._vbus_calibration_identity_matches(cal,dict(cal,fw_build=package.NEW[0],mc_fw_build=package.NEW[1])),'Vbus calibration identity preserved')
    check(hmi.sd_live_status(dict(mc_fw_build=package.NEW[1],mc_age_ms=20,bp_temp_flags=189))['available'],'SD telemetry accepts new pair')
    run(['node','--check',str(C/'web_hmi/static/app.js')],'browser_syntax')
    r=dict(passed=True,checks=checks,vf=result,uart=uart,negative_controls=1,hardware_commands=0,
        actual_medium_rate_hz=500,actual_pwm_rate_hz=16000,
        limitations=['No physical PWM/rotor measurement; peripheral writes and unused CL PI are stubs.',
            'SDK frequency resolution is0.1Hz; continuity refers to envelope, not an infinitely fine frequency command.',
            'Starting torque below5Hz must be qualified later with real motor.'])
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r[k] for k in ('passed','vf','uart','negative_controls','hardware_commands')}))

if __name__=='__main__':main()
