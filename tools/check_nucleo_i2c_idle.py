"""Replay real first-fault entry through original and actual candidate C core."""
import json
import subprocess
from pathlib import Path
import prepare_nucleo_i2c_idle as p

def main():
    c=p.OUT;v=c/'verification';results=[]
    capture=p.UNO/'powered_first_fault_5hz_r1/trial/first_i2c_capture.json'
    r=json.loads(p.read(capture));raw=bytes.fromhex(r['pwm_hex']);assert len(raw)==160
    import struct
    words=struct.unpack('<40I',raw)
    p.write(v/'record_fixture.h','#pragma once\nstatic const uint32_t record[40]={'+','.join(hex(n)+'U' for n in words)+'};\n')
    for label,folder in [('original',p.NUC/'nucleo/Inc'),('candidate',c/'nucleo/Inc')]:
        exe=v/(label+'_driver_test.exe')
        cmd=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-include','cstdlib','-include','initializer_list',
            '-I',str(folder),'-I',str(v),str(p.RES/'driver_test.cpp'),'-o',str(exe)]
        if label=='candidate':cmd+=['-DPATCHED']
        b=subprocess.run(cmd,capture_output=True,text=True);p.write(v/(label+'_compile.log'),b.stdout+b.stderr)
        if b.returncode:print(b.stderr[-6000:]);b.check_returncode()
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        p.write(v/(label+'_run.log'),run.stdout+run.stderr)
        if run.returncode:print(run.stdout+run.stderr);run.check_returncode()
        result=json.loads(run.stdout);assert result['passed'];results.append(dict(kind=label,result=result))
    report=dict(passed=True,hardware_commands=0,record_sha256=p.sha(capture),results=results,
        limitation='Only the recorded first entry is replayed exactly. Later flag/line sequences are fault-injection models, not a recorded analog waveform or proof of immunity under real PWM.')
    exe=v/'platform_test.exe'
    # The complete production .c file uses standard C {0} aggregate init.
    cmd=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-I',str(p.RES/'mock'),
         '-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src'),str(p.RES/'platform_test.cpp'),'-o',str(exe)]
    build=subprocess.run(cmd,capture_output=True,text=True);p.write(v/'platform_compile.log',build.stdout+build.stderr)
    if build.returncode:print(build.stderr[-6000:]);build.check_returncode()
    run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
    p.write(v/'platform_run.log',run.stdout+run.stderr)
    if run.returncode:print(run.stdout+run.stderr);run.check_returncode()
    report['platform_test']=json.loads(run.stdout)
    p.write(v/'driver_replay.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
