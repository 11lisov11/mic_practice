"""Bounded headless build of the offline candidate. No programmer is invoked."""
import json,subprocess,time
from pathlib import Path
from prepare_multi_algorithm import ROOT,OUT
IDE=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE')
BIN=IDE/'plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin'
def main():
    out=OUT/'nucleo/STM32CubeIDE/Debug';out.mkdir(parents=True,exist_ok=True)
    log=OUT/'nucleo_build_r2.log';workspace=ROOT/'_cubeide_ws_multi_algorithm_r2'
    cmd=[str(IDE/'stm32cubeidec.exe'),'-nosplash','-application','org.eclipse.cdt.managedbuilder.core.headlessbuild',
         '-data',str(workspace),'-import',str(OUT/'nucleo/STM32CubeIDE'),'-cleanBuild','ACIM-NUCLEOG431RB-IPM15B-VF_OL/Debug']
    terminated=False
    with log.open('w') as f:
        proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
        end=time.monotonic()+180;last=0;quiet=time.monotonic()
        while proc.poll() is None and time.monotonic()<end:
            size=log.stat().st_size
            if size!=last:last=size;quiet=time.monotonic()
            text=log.read_text(errors='replace')
            if 'Saving workspace.' in text and time.monotonic()-quiet>12:break
            time.sleep(.5)
        if proc.poll() is None:
            # Only this freshly created, owned headless process tree. IDE already
            # saved its result; no board reset or programming process exists here.
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            terminated=True
        proc.wait(timeout=15)
    text=log.read_text(errors='replace');passed='Build Finished. 0 errors, 0 warnings.' in text
    if passed:
        elf=out/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
        for typ,ext in [('binary','bin'),('ihex','hex')]:
            subprocess.run([str(BIN/'arm-none-eabi-objcopy.exe'),'-O',typ,str(elf),str(elf.with_suffix('.'+ext))],check=True)
        size=subprocess.run([str(BIN/'arm-none-eabi-size.exe'),str(elf)],capture_output=True,text=True,check=True).stdout.strip()
    else:size=''
    report=dict(passed=passed,log=str(log),firmware=2026102922,kernels=['VF_FIXED','FOC_FIXED','ADAPTIVE_PWM'],
                owned_builder_terminated_after_save=terminated,size=size,physical_qualification=False)
    (OUT/'nucleo_build_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2));raise SystemExit(0 if passed else 1)
if __name__=='__main__':main()
