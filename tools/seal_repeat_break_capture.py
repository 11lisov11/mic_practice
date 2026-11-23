"""Seal offline repeat-Break images; no hardware access or old-file mutation."""
import json,subprocess
from elftools.elf.elffile import ELFFile
import prepare_repeat_break_capture as p
from probe_native_programming_state import programmed_hex_image
from build_multi_native import BIN

def main():
 m=json.loads(p.read(p.OUT/'manifest.json'));assert not m['installed'] and not m['built']
 tests=json.loads(p.read(p.OUT/'verification/report.json'));assert tests['passed']
 native_report=json.loads(p.read(p.OUT/'nucleo_build_report.json'));assert native_report['passed'] and native_report['build_id']==p.NEW[1]
 u=json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'));assert u['firmware_build_id']==p.NEW[0]
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 for a in u['artifacts']:assert p.sha(p.OUT/'build/uno'/a['file'])==a['sha256'].lower()
 native=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 expected,holes=programmed_hex_image(native.with_suffix('.hex'),native.with_suffix('.bin').read_bytes())
 release=p.OUT/'release';release.mkdir(exist_ok=False)
 for f,name in [(native.with_suffix('.hex'),'nucleo_2026111402_repeat_break.hex'),
                (p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin','uno_2026111401_repeat_break.elf-zsk.bin')]:
  (release/name).write_bytes(f.read_bytes())
 (release/'nucleo_2026111402_expected_readback.bin').write_bytes(expected)
 ram={}
 with native.with_suffix('.elf').open('rb') as stream:
  elf=ELFFile(stream)
  for sec in elf.iter_sections():
   if sec['sh_flags']&2 and 0x20000000<=sec['sh_addr']<0x20008000:ram[sec.name]=int(sec['sh_size'])
 allocated=sum(ram.values());assert allocated<32768
 for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert p.sha(p.BASE/rel)==h,rel
 preserved=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
 # Retain the already sealed older capture identities, not just today's run.
 old=p.ROOT/'artifacts/live_bench_20261031/cin_sd_diag_r1/preserved_capture_hashes.json'
 for rel,h in json.loads(p.read(old)).items():preserved[rel]=h
 for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
 p.write(p.OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2))
 assembly=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d','--disassemble=mic_repeat_break_irq',str(native.with_suffix('.elf'))],text=True)
 assert '<mic_repeat_break_irq>:' in assembly
 assert all(name not in assembly for name in ('HAL_DMA_Abort','HAL_DMA_Start','uno_tx_submit','printf','malloc'))
 p.write(p.OUT/'verification/repeat_irq_ARM.txt',assembly)
 sources={}
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (p.OUT/folder).rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts:sources[f.relative_to(p.OUT).as_posix()]=p.sha(f)
 p.write(p.OUT/'source_hashes.json',json.dumps(sources,indent=2))
 artifacts={f.relative_to(p.OUT).as_posix():p.sha(f) for f in release.iterdir()}
 for ext in ('.hex','.bin','.elf'):artifacts[native.with_suffix(ext).relative_to(p.OUT).as_posix()]=p.sha(native.with_suffix(ext))
 artifacts['build/uno/UNOQ_MOTOR.ino.elf-zsk.bin']=p.sha(p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')
 m.update(built=True,installed=False,host_tests_passed=True,hardware_validated=False,source_files=len(sources),
   preserved_files_verified=len(preserved),artifacts=artifacts,native_flash_bytes=len(expected),hex_padding_offsets=holes,
   verification_sha256=p.sha(p.OUT/'verification/report.json'),RAM_sections=ram,RAM_allocated=allocated,RAM_unallocated=32768-allocated,
   IRQ_has_no_DMA_rearm_or_UART_calls=True,repeat_irq_timing_measured_on_hardware=False)
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2));print(json.dumps(m))
if __name__=='__main__':main()
