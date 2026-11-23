"""Run actual firmware core against independent event-driven register model."""
import json,struct,subprocess
import prepare_nucleo_i2c_stop as p
def main():
    v=p.OUT/'verification'
    capture=p.BASE/'powered_first_fault_5hz_r1/trial/first_i2c_capture.json'
    raw=bytes.fromhex(json.loads(p.read(capture))['pwm_hex']);words=struct.unpack('<40I',raw)
    assert words[5]==0x8011 and words[1]==2026102702
    p.write(v/'record_fixture.h','#pragma once\nstatic const uint32_t record[40]={'+','.join(hex(x)+'U' for x in words)+'};\n')
    cmd=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(p.OUT/'nucleo/Inc'),'-I',str(v),str(p.RES/'selftest.cpp'),'-o',str(v/'stop_selftest.exe')]
    for name,args in [('core_compile',cmd),('core_test',[str(v/'stop_selftest.exe')])]:
        r=subprocess.run(args,capture_output=True,text=True,timeout=30);p.write(v/(name+'.log'),r.stdout+r.stderr)
        if r.returncode: print(r.stdout+r.stderr);r.check_returncode()
    result=json.loads(r.stdout);assert result['passed']
    cmd=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(p.BASE/'nucleo/Inc'),'-I',str(v),str(p.RES/'original_replay.cpp'),'-o',str(v/'original_replay.exe')]
    for name,args in [('original_compile',cmd),('original_replay',[str(v/'original_replay.exe')])]:
        r=subprocess.run(args,capture_output=True,text=True,timeout=30);p.write(v/(name+'.log'),r.stdout+r.stderr)
        if r.returncode:print(r.stdout+r.stderr);r.check_returncode()
    result['original']=json.loads(r.stdout)
    exe=v/'platform_test.exe'
    cmd=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-I',str(v/'mock'),'-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'nucleo/Src'),str(p.RES/'platform_test.cpp'),'-o',str(exe)]
    for name,args in [('platform_compile',cmd),('platform_test',[str(exe)])]:
        r=subprocess.run(args,capture_output=True,text=True,timeout=30);p.write(v/(name+'.log'),r.stdout+r.stderr)
        if r.returncode:print(r.stdout+r.stderr);r.check_returncode()
    result['platform']=json.loads(r.stdout)
    result.update(record_sha256=p.sha(capture),hardware_commands=0)
    p.write(v/'core_report.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
