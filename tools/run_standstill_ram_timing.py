"""Temporary no-output SRAM timing probe; explicit discharged USB state required."""
import argparse,json,subprocess,struct,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OPENOCD=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.openocd.win32_2.4.500.202604080855/tools/bin/openocd.exe')
SCRIPTS=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.debug.openocd_2.3.400.202606220929/resources/openocd/st_scripts')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--outdir',type=Path,required=True)
 p.add_argument('--confirm-j1-off-below20-both-usb',action='store_true');p.add_argument('--plan-only',action='store_true');a=p.parse_args()
 fixture=a.fixture.resolve();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
 manifest=json.loads((fixture/'manifest.json').read_text(encoding='utf-8'));assert manifest['compiled'] and not manifest['flash_image']
 symbols=manifest['symbols'];template=(ROOT/'tools/motor_commissioning/run_timing_ram.tcl').read_text(encoding='utf-8')
 for key,value in dict(BACKUP=out/'sram_before.bin',RESTORED=out/'sram_restored.bin',ELF=fixture/'timing.elf',
  RESULT=out/'timing_result.bin',ENTRY=hex(symbols['bench_run']['address']),
  RESULT_ADDRESS=hex(symbols['timing_result']['address']),RESULT_BYTES=symbols['timing_result']['bytes']).items():
  template=template.replace('@'+key+'@',str(value).replace('\\','/'))
 assert '@' not in template
 cfg=out/'run.tcl';cfg.write_text(template,encoding='utf-8')
 command=[str(OPENOCD),'-s',str(SCRIPTS),'-f','interface/stlink-dap.cfg','-c','adapter serial 003A002C3335510933383531',
  '-f','target/stm32g4x.cfg','-f',str(cfg)]
 report=dict(passed=False,flash_commands=0,start_commands=0,clear_commands=0,synthetic_samples=True,plan_only=a.plan_only)
 if a.plan_only:
  (out/'plan.json').write_text(json.dumps(dict(command=command,hardware_commands=0),indent=2),encoding='utf-8');print('CPU-only timing plan prepared; no hardware commands');return 0
 raise RuntimeError('Prototype execution disabled after a target fault; SRAM was restored and native reset. Use permanent OFF-only flash timing self-check instead.')
 if not a.confirm_j1_off_below20_both_usb:p.error('Explicit confirmed discharged USB bench required')
 from install_bkin_boot_armed_pair import board_ports
 board_ports()
 from current_only_lab import get_status
 s=get_status('http://192.168.1.138:8080')
 assert (s['fw_build'],s['mc_fw_build'])==(2026102931,2026102932) and s['state']=='SAFE' and s['pwm']==0 and not(s['bp_status']&0x22)
 assert 0<=s['vdc']<=20 and 0<=s['mc_age_ms']<300 and s['hmi_hv_armed']==0
 (out/'before_status.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
 try:
  r=subprocess.run(command,capture_output=True,text=True,timeout=35)
  (out/'openocd.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode()
  before=(out/'sram_before.bin').read_bytes();after=(out/'sram_restored.bin').read_bytes()
  assert before==after and len(before)==32768,'SRAM restoration mismatch'
  raw=(out/'timing_result.bin').read_bytes();magic,done,count,clock=struct.unpack_from('<4I',raw)
  assert magic==0x54494d45 and done==1 and count==8 and clock==170000000
  rows=[]
  for n in range(count):
   values=struct.unpack_from('<9I',raw,16+36*n)
   row=dict(zip(('kind','late','frequency','initialization','first','max_step','min_step','steps','fault'),values))
   rows.append(row)
  assert all(v['steps']==256 and v['fault']==0 for v in rows),rows
  report.update(passed=True,sram_restored_byte_identical=True,original_sram_sha256=hashlib.sha256(before).hexdigest(),rows=rows,
   maximum_initialization_cycles=max(v['initialization'] for v in rows),maximum_kernel_cycles=max(v['max_step'] for v in rows),
   deadline_cycles=5312,fixture_is_flash_executed=False)
 except Exception as exc:report['error']=str(exc)
 (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
