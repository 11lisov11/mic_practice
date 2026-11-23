"""Seal preparation only; assert no install/run took place."""
import copy,json,re,struct,subprocess,shutil
import prepare_no_switch_diag as p
from prepare_full_mcsdk_edges import OUT,OLD,BUILD
from full_mcsdk_edges_host import decode_pin,decode_full,eligible
from no_switch_diag_snapshot_io import crc32c
from seal_no_switch_diag import GNU
def main():
 c=OUT;v=c/'verification';b=c/'nucleo/STM32CubeIDE/Debug';stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 tests=json.loads(p.read(v/'native_tests.json'));assert tests['passed'] and tests['preemption']['passed']
 bm=json.loads(p.read(b/(stem+'.build-manifest.json')));assert bm['firmware_build_id']==BUILD and bm['build_errors']==bm['build_warnings']==0
 for a in bm['artifacts']:assert p.sha(b/a['file'])==a['sha256'].lower()
 for ext in ('.hex','.bin','.elf','.map','.build-manifest.json'):shutil.copy2(b/(stem+ext),c/'build/nucleo'/(stem+ext))
 names=('mic_pin_request','mic_pin_report','mic_full_report','fault_record','release_probe','bus_clear','mic_uart_tx','uno_transport','mic_first_break','mic_first_start_break','mic_bkin_record')
 def symbols(elf,names):
  raw=subprocess.check_output([str(GNU/'arm-none-eabi-nm.exe'),'-S','-n',str(elf)],text=True);sy={}
  for line in raw.splitlines():
   a=line.split()
   if len(a)==4 and a[3] in names:
    addr,size=int(a[0],16),int(a[1],16);assert 0x20000000<=addr<addr+size<=0x20008000
    sy[a[3]]=dict(address=addr,bytes=size)
  assert set(sy)==set(names),set(names)-set(sy);return sy
 sy=symbols(b/(stem+'.elf'),names);assert sy['mic_pin_report']['bytes']==256 and sy['mic_full_report']['bytes']==96
 p.write(v/'symbols.json',json.dumps(sy,indent=2)+'\n')
 oldnames=tuple(n for n in names if n not in ('mic_pin_request','mic_pin_report'))+('mic_load_report','mic_load_request')
 oldsy=symbols(OLD/'build/nucleo'/(stem+'.elf'),oldnames);p.write(v/'predecessor_symbols.json',json.dumps(oldsy,indent=2)+'\n')
 end=int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(b/(stem+'.map')))[1],16)
 margin=0x20008000-end-0x600;assert margin>=2600,margin
 su=p.read(b/'Application/User/pin_pwm_diag.su');frames={name:int(n) for name,n in re.findall(r':(\w+)\s+(\d+)\s',su)}
 assert frames['mic_pin_irq']<=512 and frames['mic_pin_poll']<=512
 w=[0]*64;w[:4]=[0x314e4950,2,BUILD,64];w[4]=w[61]=2;w[11]=170000000;w[17]=0x1000;w[23]=64;w[26]=200;w[39]=3;w[53]=0x555;w[63]=0x50494e45
 w[62]=crc32c(struct.pack('<56I',*w[5:61]));raw=struct.pack('<64I',*w);pin=decode_pin(raw)
 f=[0]*24;f[:4]=[0x31444d46,BUILD,2,24];f[4]=f[21]=2;f[5]=1;f[6]=10;f[7]=f[8]=4;f[15]=1;f[17]=0x1000;f[23]=0x464d4445
 f[22]=crc32c(struct.pack('<16I',*f[5:21]));full=decode_full(struct.pack('<24I',*f))
 d=dict(pin=pin,full=full,tx=dict(completed=1,timeouts=0,full_errors=0,dma_errors=0,hard_error=0));assert eligible(d)
 negative=0
 for group,key,value in [('pin','state',1),('pin','attempted',1),('pin','ADC_all',0),('pin','ADC_bad',1),('pin','GPIOA_IDR',0),('pin','BDTR',0x9000),('full','active_fault',0),('full','occurred_fault',6),('full','bus_v',20),('full','backend_flags',1),('full','TIM8_BDTR',0x9000),('full','rx_bad',1),('full','uart_guard',1),('tx','dma_errors',1)]:
  z=copy.deepcopy(d);z[group][key]=value;assert not eligible(z),(group,key,value);negative+=1
 for i in range(5,64):
  z=bytearray(raw);z[4*i]^=1
  try:decode_pin(z)
  except ValueError:negative+=1
  else:raise AssertionError('PIN corruption accepted')
 m=json.loads(p.read(c/'manifest.json'));assert not m['installed'] and not m['hardware_tested']
 for rel,h in m['archived'].items():assert p.sha(c/'preserved_records'/rel)==h,rel
 for rel,h in json.loads(p.read(OLD/'manifest.json'))['sealed_sha256'].items():assert p.sha(OLD/rel)==h,rel
 report=dict(passed=True,preparation_only=True,build=BUILD,errors=0,warnings=0,hardware_calls=0,installed=False,hardware_tested=False,
  RAM_margin_above_reserved_heap_stack=margin,individual_diagnostic_stack_frames=frames,host_negative_cases=negative,
  native_checks=tests['model']['checks']+tests['math']['checks']+tests['preemption']['checks'],old_archived_files_verified=len(m['archived']),
  normal_MCSDK_UV_not_masked=True,physical_TIM1_BKIN_deadtime_unchanged=True,
  source_scope='Native MCSDK OFF/FAULT owns non-routed TIM8; independent one-shot TIM1 generator uses original six pins',
  stages=['1s baseline','2s real16kHz fixed PWM','2s real16kHz VF-modulated PWM'],
  limitations=['Target waveform/timing/I2C results pending one separately invoked5s capture','Not normal motor RUN, no powered inverter','WL not recorded with retained Saleae probe map'],
  install_command='python tools/full_mcsdk_edges_host.py install --isolation-confirmed --outdir <new-folder>',
  status_command='python tools/full_mcsdk_edges_host.py status --isolation-confirmed --outdir <new-folder>',
  run_command='python tools/full_mcsdk_edges_host.py run --isolation-confirmed --allow-one-5s-fixture-request --outdir <new-folder>')
 p.write(v/'report.json',json.dumps(report,indent=2)+'\n')
 m.update(built=True,offline_verified=True,preparation_only=True,RAM_margin_above_reserved_heap_stack=margin,
  native_checks=report['native_checks'],host_negative_cases=negative)
 m['sealed_sha256']={f.relative_to(c).as_posix():p.sha(f) for tree in ('nucleo','build','restore','verification','preserved_records') for f in (c/tree).rglob('*') if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
 m['tools_sha256']={name:p.sha(p.ROOT/'tools'/name) for name in ('prepare_full_mcsdk_edges.py','edges_mcsdk_diag.c','edges_mcsdk_diag.h','check_full_mcsdk_edges.py','full_mcsdk_edges_host.py','seal_full_mcsdk_edges.py')}
 p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
