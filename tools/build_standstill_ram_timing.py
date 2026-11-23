"""Build a CPU-only SRAM timing fixture, not a flashable motor image."""
import argparse,json,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--include',type=Path,required=True);p.add_argument('--outdir',type=Path,required=True);a=p.parse_args()
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 cmd=[str(BIN/'arm-none-eabi-gcc.exe'),'-O2','-fno-fast-math','-g3','-mcpu=cortex-m4','-mthumb',
  '-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-ffunction-sections','-fdata-sections','--specs=nano.specs','--specs=nosys.specs',
  '-nostartfiles','-I',str(a.include.resolve()),str(ROOT/'tools/motor_commissioning/timing_ram.c'),
  '-T',str(ROOT/'tools/motor_commissioning/timing_ram.ld'),'-Wl,--gc-sections','-Wl,-Map='+str(out/'timing.map'),
  '-lm','-lc','-lgcc','-o',str(out/'timing.elf')]
 r=subprocess.run(cmd,capture_output=True,text=True);(out/'build.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode()
 nm=subprocess.check_output([str(BIN/'arm-none-eabi-nm.exe'),'-S',str(out/'timing.elf')],text=True)
 symbols={}
 for line in nm.splitlines():
  fields=line.split()
  if len(fields)==4 and fields[3] in ('bench_run','timing_result'):symbols[fields[3]]=dict(address=int(fields[0],16),bytes=int(fields[1],16))
 assert len(symbols)==2
 subprocess.run([str(BIN/'arm-none-eabi-objcopy.exe'),'-O','binary',str(out/'timing.elf'),str(out/'timing.bin')],check=True)
 report=dict(compiled=True,flash_image=False,hardware_commands=0,source_samples='synthetic',symbols=symbols,
  static_register_access=['DWT_CYCCNT_read_only'])
 (out/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
