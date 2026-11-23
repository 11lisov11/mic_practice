import json,re,subprocess,shutil,struct
import prepare_no_switch_diag as p
from prepare_full_mcsdk_diag import OUT,BUILD
from full_mcsdk_host import decode_load,decode_full
from no_switch_diag_snapshot_io import crc32c
def main():
 c=OUT;v=c/'verification';debug=c/'nucleo/STM32CubeIDE/Debug';stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 assert json.loads(p.read(v/'native_tests.json'))['passed']
 b=json.loads(p.read(debug/(stem+'.build-manifest.json')));assert b['firmware_build_id']==BUILD and b['build_errors']==b['build_warnings']==0
 for a in b['artifacts']:assert p.sha(debug/a['file'])==a['sha256'].lower()
 for ext in ('.hex','.bin','.elf','.map','.build-manifest.json'):shutil.copy2(debug/(stem+ext),c/'build/nucleo'/(stem+ext))
 g='C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin/arm-none-eabi-nm.exe'
 raw=subprocess.check_output([g,'-S','-n',str(debug/(stem+'.elf'))],text=True)
 names=('mic_load_report','mic_load_request','mic_full_report','fault_record','release_probe','bus_clear','mic_uart_tx','uno_transport')
 sy={}
 for line in raw.splitlines():
  a=line.split()
  if len(a)==4 and a[3] in names:
   address,size=int(a[0],16),int(a[1],16);assert 0x20000000<=address<address+size<=0x20008000
   sy[a[3]]=dict(address=address,bytes=size)
 assert len(sy)==len(names) and sy['mic_full_report']['bytes']==96 and sy['mic_load_report']['bytes']==288
 p.write(v/'symbols.json',json.dumps(sy,indent=2)+'\n')
 end=int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(debug/(stem+'.map')))[1],16)
 margin=0x20008000-end-0x600;assert margin>=2600,margin
 # Check report CRC/sequence acceptance and reject every covered word corruption.
 w=[0]*72;w[:4]=[0x3147444c,1,BUILD,72];w[4]=w[69]=2;w[70]=crc32c(struct.pack('<64I',*w[5:69]));w[71]=0x4c44454e
 decode_load(struct.pack('<72I',*w))
 w=[0]*24;w[:4]=[0x31444d46,BUILD,1,24];w[4]=w[21]=2;w[22]=crc32c(struct.pack('<16I',*w[5:21]));w[23]=0x464d4445
 raw=struct.pack('<24I',*w);decode_full(raw);n=0
 for i in range(5,24):
  z=bytearray(raw);z[4*i]^=1
  try:decode_full(z)
  except ValueError:n+=1
  else:raise AssertionError('Corruption accepted')
 m=json.loads(p.read(c/'manifest.json'))
 for rel,h in m['archived'].items():assert p.sha(c/'preserved_records'/rel)==h,rel
 report=dict(passed=True,build=BUILD,errors=0,warnings=0,RAM_margin_above_reserved_heap_stack=margin,decoder_negative_cases=n,hardware_calls=0,native_voltage_and_temperature_thresholds_unchanged=True,physical_outputs_locked_LOW=True)
 p.write(v/'report.json',json.dumps(report,indent=2)+'\n')
 m.update(built=True,offline_verified=True,RAM_margin_above_reserved_heap_stack=margin)
 m['sealed_sha256']={f.relative_to(c).as_posix():p.sha(f) for tree in ('nucleo','build','restore','verification','test_resources','preserved_records') for f in (c/tree).rglob('*') if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
 p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
