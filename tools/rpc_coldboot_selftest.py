"""Fault-inject actual RouterBridge/RPClite headers; mock only UART/Zephyr/time."""
import json
import subprocess
from pathlib import Path
import prepare_rpc_coldboot_fix as p
import sys
if '--boot-retry' in sys.argv:import prepare_rpc_boot_retry as p

def main():
    out=p.OUT/'verification/native';out.mkdir(parents=True,exist_ok=True)
    source=p.ROOT/'tools/rpc_coldboot_native'
    results=[]
    for patched,library in ((False,p.LIB),(True,p.OUT/'libraries')):
        exe=out/('patched.exe' if patched else 'original.exe')
        includes=[source,library/'Arduino_RouterBridge/src',library/'Arduino_RPClite/src']
        includes += [p.LIB/n for n in ('MsgPack','ArxContainer','ArxTypeTraits','DebugLog')]
        cmd=['g++','-std=c++17','-O2','-Wall','-Wextra']
        if patched:
            cmd+=['-DMIC_PATCHED']
            if '--boot-retry' in sys.argv:cmd+=['-DMIC_BOOT_RETRY']
        cmd += ['-I'+str(x) for x in includes]+[str(source/'test.cpp'),'-o',str(exe)]
        build=subprocess.run(cmd,capture_output=True,text=True)
        (out/(exe.stem+'_compile.log')).write_text(build.stdout+build.stderr)
        if build.returncode:print(build.stderr[-10000:]);build.check_returncode()
        cases=('lost','late','unknown','tagged','generic','tx','admission','mutex')
        if '--boot-retry' in sys.argv:cases+=('boot_retry',)
        for case in (cases if patched else ('baseline',)):
            r=subprocess.run([str(exe),case],capture_output=True,text=True,timeout=10)
            results.append(dict(patched=patched,case=case,passed=r.returncode==0,output=r.stdout+r.stderr))
            print(results[-1]);r.check_returncode()
    report=dict(passed=True,cases=results,hardware_commands=0,
        scope='Actual local vendor headers and MsgPack/dispatcher. UART, time, and kernel mocked. No proof of bank cold-boot root cause or hardware recovery.')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
