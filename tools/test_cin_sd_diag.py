"""Actual acquisition/wire code on a register stub + strict HMI decoding and archive checks."""
import ast,importlib.util,json,shutil,subprocess,sys,struct
from pathlib import Path
import prepare_cin_sd_diag as p
def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True)
 (out/'stm32g4xx_ll_adc.h').write_text('#include "stub_adc.h"\n',encoding='utf-8')
 exe=out/'cin_target_test.exe'
 command=['g++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-I'+str(out),'-I'+str(p.SOURCE),
          '-I'+str(p.OUT/'nucleo/Inc'),str(p.SOURCE/'test_target.cpp'),'-o',str(exe)]
 result=subprocess.run(command,capture_output=True,text=True);p.write(out/'host_build.log',result.stdout+result.stderr);result.check_returncode()
 result=subprocess.run([str(exe)],capture_output=True,text=True);p.write(out/'host_run.log',result.stdout+result.stderr);result.check_returncode()
 scope={};exec(p.read(p.SOURCE/'web_status.py'),scope);decode=scope['cin_sd_status']
 def crc(data):
  c=0xffffffff
  for b in data:
   c^=b
   for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
  return c^0xffffffff
 def packet(raw=635,flags=1,reason=0,delta=0):
  b=bytearray(43);b[:4]=bytes([0x55,0xaa,0xeb,1]);b[4]=flags
  for off,val in ((6,p.NEW[1]),(10,1),(14,100),(18,100+delta)):struct.pack_into('<I',b,off,val)
  struct.pack_into('<HH',b,22,raw,3290);b[38]=reason;struct.pack_into('<I',b,39,crc(b[:39]));return b
 def value(b,fresh='1',peer=p.NEW[1]):return decode(dict(cin_packet_hex=b.hex(),cin_fresh=fresh,bp_fw_build=str(peer)))['cin_sd']
 good=packet();v=value(good);assert v['valid'] and abs(v['voltage_mv_approx']-510.171)<.002
 assert v['threshold_band']=='threshold_or_uncertain' and not v['physical_cause_identified']
 assert value(packet(raw=0))['threshold_band']=='below_threshold_band'
 assert value(packet(raw=1000))['threshold_band']=='above_threshold_band'
 assert not value(good,fresh='0')['valid'] and value(good,fresh='0')['voltage_mv_approx'] is None
 assert not value(good,peer=2026103014)['available']
 assert not value(packet(delta=2))['available']
 assert not value(packet(flags=0,reason=1,delta=1000))['valid']
 for i in range(43):
  for bit in range(8):
   b=bytearray(good);b[i]^=1<<bit;assert not value(b)['available']
 server=p.read(p.OUT/'web_hmi/server.py');tree=ast.parse(server)
 for cls in tree.body:
  if isinstance(cls,ast.ClassDef):
   for fun in cls.body:
    if isinstance(fun,ast.FunctionDef) and fun.name=='start_sequence':
     assert isinstance(fun.body[1],ast.Return) and ast.literal_eval(fun.body[1].value)==(False,'CIN_DIAGNOSTIC_ONLY: no motor start',None)
 native=p.read(p.OUT/'nucleo/Src/main.c')
 a=native.index('/* OFF-only PB11/ADC2_IN14');b=native.index('static void mic_send_boot_page',a)
 assert native[a:b].strip()==p.read(p.SOURCE/'native.inc').strip()
 assert native.index('if(flags==UNO_FLAG_ENABLE){uno_stop_motor();return;}')<native.index('if(!ma_native_request(algorithm))')
 assert 'if(!LL_TIM_IsEnabledAllOutputs(TIM1)){' in native
 def body(source,name):
  import re
  match=re.search(r'\b'+name+r'\([^;{}]*\)\s*\{',source)
  assert match,name
  start=match.start();pos=source.index('{',match.start());level=1
  while level:
   pos+=1;level+=(source[pos]=='{')-(source[pos]=='}')
  return source[start:pos+1]
 oldmain=p.read(p.BASE/'nucleo/Src/main.c')
 for name in ('MX_ADC1_Init','MX_ADC2_Init','MX_TIM1_Init','uno_rearm_break_irq','uno_stop_motor','mic_bkin_capture_start','MX_USART1_UART_Init','uno_clear_frame_is_safe'):
  assert body(native,name).replace('\n  cin_diag_init();','')==body(oldmain,name),name
 shunt=p.read(p.BASE/'nucleo/Src/current_shunt.c').replace('2026103014',str(p.NEW[1]))
 assert p.read(p.OUT/'nucleo/Src/current_shunt.c')==shunt+'\n/* Read-only diagnostic eligibility; zero thresholds are unchanged. */\nuint8_t mic_current_zero_is_ready(void){return state.zero_ready;}\n'
 # Every unchanged motor/protection/ADC ISR source must remain byte-identical
 # modulo the declared firmware identities. A getter is the only shunt change.
 allowed={'Src/main.c','Src/current_shunt.c','Inc/current_shunt.h','Inc/cin_wire.h'}
 changes=[]
 for folder in ('Inc','Src'):
  for old in (p.BASE/'nucleo'/folder).rglob('*'):
   if old.is_file():
    rel=old.relative_to(p.BASE/'nucleo').as_posix();dest=p.OUT/'nucleo'/rel
    expected=p.read(old).replace('2026103013',str(p.NEW[0])).replace('2026103014',str(p.NEW[1]))
    if p.read(dest)!=expected:
     changes.append(rel);assert rel in allowed,rel
 for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert p.sha(p.BASE/rel)==h,rel
 captures=json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))
 for rel,h in captures.items():assert p.sha(p.ROOT/rel)==h,rel
 report=dict(passed=True,hardware_commands=0,START=0,CLEAR=0,flash_commands=0,
  actual_target_register_stub_tests_pass=True,wire_bit_corruptions_rejected_C=344,
  wire_bit_corruptions_rejected_Python=344,boot_zero_idle_guards=True,late_EOC_rejected=True,
  native_enable_blocked=True,HMI_start_blocked=True,other_native_source_changes=changes,
  archived_sources_unchanged=True,preserved_captures_verified=len(captures),
  limitation='Register stub and compilation do not validate the physical CIN wire or analog accuracy.')
 p.write(out/'report.json',json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
