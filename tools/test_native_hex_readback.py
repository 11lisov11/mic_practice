"""Known programmed-HEX padding and corrupted-image rejection; offline only."""
import json,tempfile
from pathlib import Path
from probe_native_programming_state import programmed_hex_image

def main():
 root=Path(__file__).resolve().parents[1];p=root/'artifacts/live_bench_20261029'
 old=p/'estimated_foc_trial_r5/nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 binary=old.with_suffix('.bin').read_bytes()
 image,holes=programmed_hex_image(old.with_suffix('.hex'),binary)
 actual=(p/'foc_start_epoch_fix_r1/hardware_install_r2/passive_native_guard/installed_native.bin').read_bytes()
 assert image==actual and holes==list(range(95212,95216))
 bad=bytearray(actual);bad[0]^=1;assert bytes(bad)!=image
 bad=bytearray(actual);bad[holes[0]]=0;assert bytes(bad)!=image
 rejected=0
 with tempfile.TemporaryDirectory(prefix='mic_hex_guard_') as d:
  dest=Path(d)/'bad.hex';s=old.with_suffix('.hex').read_text()
  for corrupt in (s.replace(':020000040800F2',':020000040800F3',1),s.replace(':00000001FF','')):
   dest.write_text(corrupt,encoding='ascii')
   try:programmed_hex_image(dest,binary)
   except AssertionError:rejected+=1
   else:raise AssertionError('bad HEX accepted')
 assert rejected==2
 report=dict(passed=True,hardware_commands=0,known_padding_offsets=holes,
  all_programmed_bytes_match=True,code_corruption_rejected=True,
  non_erased_padding_rejected=True,invalid_and_truncated_hex_rejected=rejected)
 out=p/'foc_start_epoch_fix_r1/verification/native_hex_readback.json'
 out.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
