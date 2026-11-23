"""Use the already generated native make graph, with every source path retargeted."""
import os,json,subprocess,shutil,re
from pathlib import Path
import prepare_standstill_timing as p
from build_multi_native import BIN
def main():
 old=p.BASE/'nucleo/STM32CubeIDE/Debug';dest=p.OUT/'nucleo/STM32CubeIDE/Debug';dest.mkdir(parents=True,exist_ok=True)
 for f in old.rglob('*'):
  if f.is_file() and (f.suffix=='.mk' or f.name in ('makefile','objects.list')):
   target=dest/f.relative_to(old);target.parent.mkdir(parents=True,exist_ok=True)
   text=p.read(f)
   # Uno-only predecessor packages may retain a make graph from an older
   # native package. Retarget every repository native root, not just BASE.
   text=re.sub(r'C:/mic_practice/artifacts/live_bench_20261029/[^/\s"\\]+/nucleo',
               lambda _: (p.OUT/'nucleo').as_posix(),text)
   text=re.sub(r'C:\\mic_practice\\artifacts\\live_bench_20261029\\[^\\\s"]+\\nucleo',
               lambda _: str(p.OUT/'nucleo'),text)
   text=text.replace(p.BASE.as_posix(),p.OUT.as_posix()).replace(str(p.BASE),str(p.OUT))
   p.write(target,text)
 env=dict(os.environ);env['PATH']=str(BIN)+os.pathsep+env['PATH']
 make=BIN.parents[1]/'com.st.stm32cube.ide.mcu.externaltools.make.win32_2.2.200.202604021615/tools/bin/make.exe'
 # Toolchain/bin -> toolchain-plugin/tools -> plugins is three parents.
 make=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.make.win32_2.2.200.202604021615/tools/bin/make.exe')
 r=subprocess.run([str(make),'-j4','all'],cwd=dest,env=env,capture_output=True,text=True)
 log=r.stdout+r.stderr;p.write(p.OUT/'native_build.log',log);r.check_returncode()
 assert not re.search(r'\b(?:warning|error):',log,re.I),log[-2500:]
 elf=dest/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 for fmt,ext in [('binary','.bin'),('ihex','.hex')]:subprocess.run([str(BIN/'arm-none-eabi-objcopy.exe'),'-O',fmt,str(elf),str(elf.with_suffix(ext))],check=True)
 size=subprocess.check_output([str(BIN/'arm-none-eabi-size.exe'),str(elf)],text=True)
 p.write(p.OUT/'nucleo_build_report.json',json.dumps(dict(passed=True,build_id=p.NEW[1],size=size,errors=0,warnings=0,installed=False),indent=2))
 print(size)
if __name__=='__main__':main()
