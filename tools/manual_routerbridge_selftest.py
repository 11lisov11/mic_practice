"""Compile the actual Uno text-status producer and pass its output through the real HMI decoder."""
import argparse
import json
import subprocess
from pathlib import Path
from ipm_break_wifi_selftest import load_module
from prepare_pwm_filter_pair import sha

def string_function(source, name):
    start=source.index('static String '+name+'(')
    opening=source.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

def main(package):
    out=package/'routerbridge_selftest';out.mkdir(exist_ok=False)
    source=(package/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()
    assert 's += manual_status_fields(bp_age);' in string_function(source,'rpc_get')
    producer=string_function(source,'manual_status_fields')
    program=r'''
#include <string>
#include <cstdio>
#include <cstdint>
#include <cmath>
using std::isnan;using std::isinf;
struct String {
 std::string text;
 String()=default;String(const char*s):text(s){}String(char c):text(1,c){}
 String(unsigned long x):text(std::to_string(x)){}String(unsigned x):text(std::to_string(x)){}String(int x):text(std::to_string(x)){}
 void reserve(unsigned x){text.reserve(x);}
 String&operator+=(const String&s){text+=s.text;return *this;}
 String&operator+=(const char*s){text+=s;return *this;}
 String&operator+=(char c){text+=c;return *this;}
};
bool g_manual_scalar_mode=true,g_manual_coast_down=false,g_manual_reference_valid=true,g_manual_bus_hold=true;
uint16_t g_manual_accel_centi=200,g_manual_decel_centi=50;
float g_manual_reference_hz=23.4f;
'''+string_function(source,'format_fixed')+'\n'+producer+r'''
int main(){
 for(unsigned age : {20U,300U}) std::puts(manual_status_fields(age).text.c_str());
 g_manual_reference_valid=false;std::puts(manual_status_fields(20).text.c_str());
}
'''
    cpp=out/'actual_text_producer.cpp';cpp.write_text(program);exe=cpp.with_suffix('.exe')
    build=subprocess.run(['g++','-std=c++17','-Ofast','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)],capture_output=True,text=True)
    (out/'compile.log').write_text(build.stdout+build.stderr);build.check_returncode()
    run=subprocess.run([str(exe)],capture_output=True,text=True);run.check_returncode()
    (out/'producer_output.txt').write_text(run.stdout)
    mod=load_module(package/'web_hmi/server.py');pair=json.loads((package/'manifest.json').read_text())['pair']
    bridge=mod.RpcBridge.__new__(mod.RpcBridge);bridge._serial_text=None
    prefix=f'DATA state=VF_RUN mode=VF pwm=1 freq=12.0 speed=720.0 freqcmd=50.0 fw_build={pair[0]} bp_fw_build={pair[1]} bp_age_ms=20 rpc_schema=3 mc_caps=1'
    count=0
    def check(ok,name):
        nonlocal count
        assert ok,name;count+=1
    records=run.stdout.splitlines()
    for i,record in enumerate(records):
        bridge._call=lambda *args,**kwargs:[1,0,None,prefix+record]
        ok,data,error=bridge.get()
        check(ok and error is None,'actual RouterBridge text is decoded')
        check(mod.manual_scalar_supported(data),'text route exposes manual capability')
        check(data['freq_cmd']==50 and data['accel_hz_per_s']==2 and data['decel_hz_per_s']==.5,'settings survive actual wire text')
        check(data['mc_decel_bus_hold']==1 and data['manual_run_mode']==1,'hold and session flags survive')
        check(data['freq']==(23.4 if i==0 else 12.0),'only fresh valid controller reference substitutes local estimate')
    data=mod.RpcBridge._parse_status_string(prefix+records[0])
    check(data['local_ramp_reference_hz']==12 and data['speed']==1404,'reference RPM is derived consistently')
    check(not mod.manual_scalar_supported(mod.RpcBridge._parse_status_string(prefix)),'legacy missing capability fails closed')
    for changed in (prefix.replace(str(pair[0]),'2026101415'),prefix.replace(str(pair[1]),'2026101414'),prefix.replace('bp_age_ms=20','bp_age_ms=500')):
        data=mod.RpcBridge._parse_status_string(changed+records[0])
        check(data['freq']==12,'mixed identity or stale controller cannot substitute reference')
    report=dict(pass_=True,cases=count,hardware_commands=0,uno_sha256=sha(package/'UNOQ_MOTOR/UNOQ_MOTOR.ino'),hmi_sha256=sha(package/'web_hmi/server.py'),scope='Actual Uno String formatter and manual producer compiled on host; actual HMI RpcBridge.get() receives generated text; MCU HAL/RouterBridge transport mocked')
    report['pass']=report.pop('pass_');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);a=p.parse_args();main(a.candidate.resolve())
