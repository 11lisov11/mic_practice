"""Exercise exact installed V/f and PWM arithmetic on the host; no board access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import audit_production_pwm_filters as audit

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'artifacts/live_bench_20261021/uart_clean_confirm_r1'
TEST=r'''
static unsigned checks=0;
static void check(bool v,const char*why){++checks;if(!v){fprintf(stderr,"FAIL %s\n",why);exit(1);}}
int main(){
 TIM_TypeDef t;PWM_Handle_t p{&t};ACIM_VF_Handle_t h{&p};
 unsigned calls=0;float minimum=1,maximum=0;unsigned clipped50=0;
 for(float bus:{250.f,325.f,380.f}){
  h.fVoutMax_PWM_Mod_V=bus/2;
  for(unsigned fi=0;fi<=500;++fi){
   h.fFlux_Freq_Hz=fi*.1f;
   for(unsigned angle=0;angle<720;++angle){
    h.fFlux_Angle_rad=angle*(2*PI/720);writes=0;
    check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"exact controller returns success in0..50Hz sweep");
    check(writes==3,"exact PWM converter publishes exactly three compares");
    for(float d:{p.fDuty1,p.fDuty2,p.fDuty3}){
     check(mic_float_isfinite(d) && d>=0 && d<=1,"all three calculated duties finite and bounded");
     minimum=std::min(minimum,d);maximum=std::max(maximum,d);
    }
    check(t.CCR1<t.ARR && t.CCR2<t.ARR && t.CCR3<t.ARR,"timer compares remain below period");
    ++calls;
   }
  }
  if(h.VoltageAmpl==h.fVoutMax_PWM_Mod_V)++clipped50;
 }
 h=ACIM_VF_Handle_t{&p};h.fFlux_Angle_rad=.7f;
 float before=0,after=0;
 for(float hz:{9.99f,10.f}){
  h.fFlux_Freq_Hz=hz;check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"threshold sample valid");
  if(hz<10)before=h.VoltageAmpl;else after=h.VoltageAmpl;
 }
 check(before==20 && after>35.9f && after<36,"actual installed code reproduces10Hz voltage discontinuity");
 FILE*table=fopen("vf_points.csv","w");check(table,"open output table");
 fprintf(table,"field_hz,phase_peak_v,line_line_rms_equivalent_v,bus_normalizer_v\n");
 for(float hz:{0.f,5.f,9.99f,10.f,15.f,20.f,23.f,25.f,30.f,40.f,50.f}){
  h.fFlux_Freq_Hz=hz;h.fVoutMax_PWM_Mod_V=162.5f;
  check(ACIM_VF_Controller(&h)==MC_NO_ERROR,"table calculation valid");
  fprintf(table,"%.3f,%.6f,%.6f,%.3f\n",hz,h.VoltageAmpl,h.VoltageAmpl*sqrt(1.5),h.fVoutMax_PWM_Mod_V);
 }
 fclose(table);
 for(float bad:{0.f,-1.f,NAN,INFINITY}){
  h=ACIM_VF_Handle_t{&p};h.fVoutMax_PWM_Mod_V=bad;writes=0;
  check(ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0,"invalid bus normalizer cannot publish PWM compares");
 }
 for(float bad:{-.1f,1.1f,NAN,INFINITY}){
  writes=0;check(PWM_SetPhasePWMOutputs(&p,bad,.5f,.5f)==MC_SW_ERROR && writes==0,"invalid duty cannot publish compares");
 }
 printf("{\"passed\":true,\"controller_calls_in_sweep\":%u,\"assertions\":%u,\"minimum_calculated_duty\":%.8f,\"maximum_calculated_duty\":%.8f,\"voltage_peak_below10hz_v\":%.6f,\"voltage_peak_at10hz_v\":%.6f,\"bus_cases_voltage_limited_at50hz\":%u,\"hardware_commands\":0}\n",
        calls,checks,minimum,maximum,before,after,clipped50);
}
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--outdir',type=Path,required=True)
    a=ap.parse_args();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    base=PACKAGE/'nucleo'
    paths=[audit.PWM,audit.VF,Path('Src/mc_math.c'),Path('Inc/acim_vf_parameters.h'),Path('Inc/acim_motor_parameters.h')]
    hashes={str(p):hashlib.sha256((base/p).read_bytes()).hexdigest() for p in paths}
    source={p:(base/p).read_text(encoding='utf-8-sig') for p in paths}
    # Verify the actual installed parameter set rather than treating stub defaults as evidence.
    assert re.search(r'VOLTAGE_OFFSET\s+\(\(float\)\(20\)\)',source[paths[3]])
    assert re.search(r'MIN_FREQUENCY_TH\s+\(\(float\)\(10\)\)',source[paths[3]])
    assert re.search(r'FLUX_K\s+\(\(float\)\(0\.5717009\)\)',source[paths[4]])
    preamble=audit.PREAMBLE.replace('using std::isfinite;','#include <cstring>\n#include <cstdlib>\nusing std::isfinite;')
    table=re.search(r'#define SIN_FLOAT_0_90_TABLE.*?\}',source[paths[2]],re.S)[0]
    program=preamble+audit.function(source[audit.VF],'mic_float_isfinite')+'\n'+table+'\nconst float fSin_Table[256]=SIN_FLOAT_0_90_TABLE;\n'
    for rel,name in [(paths[2],'MCM_floatTrig_Functions'),(audit.PWM,'PWM_SetPhasePWMOutputs'),(audit.VF,'ACIM_VF_Controller')]:
        program+=audit.function(source[rel],name)+'\n'
    unit=out/'actual_vf.cpp';unit.write_text(program+TEST,encoding='utf-8');exe=out/'actual_vf.exe'
    command=['g++','-std=c++17','-Ofast','-Wall','-Wextra','-Werror',str(unit),'-o',str(exe)]
    p=subprocess.run(command,cwd=out,capture_output=True,text=True);(out/'build.log').write_text(p.stdout+p.stderr,encoding='utf-8');p.check_returncode()
    p=subprocess.run([str(exe)],cwd=out,capture_output=True,text=True,timeout=40);(out/'run.log').write_text(p.stdout+p.stderr,encoding='utf-8');p.check_returncode()
    r=json.loads(p.stdout);r.update(source_pair=[2026102103,2026102104],source_sha256=hashes,
        sources_unchanged=all(hashlib.sha256((base/p).read_bytes()).hexdigest()==hashes[str(p)] for p in paths),
        scope='Exact compiled installed V/f controller, sine lookup and duty-to-CCR conversion; peripheral writes are host stubs.',
        limitations=['Not a hardware PWM waveform or motor simulation',
            'Zero-Hz stopping is enforced by the supervisory command owner, not by this voltage formula',
            'At325V bus, sinusoidal PWM voltage clips before50Hz; this is voltage limitation, not a frequency cutoff',
            'Passing arithmetic checks does not identify physical UART/SD noise'])
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps(r))

if __name__=='__main__':main()
