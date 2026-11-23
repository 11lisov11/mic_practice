"""Test complete production driver, retained-PE lifecycle and old wire contracts."""
import copy,json,shutil,subprocess
import prepare_i2c_persistent_pe as p
from ipm_break_wifi_selftest import load_module
def run(name,args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=40);p.write(p.OUT/'verification'/(name+'.log'),r.stdout+r.stderr)
 if r.returncode:print(r.stdout+r.stderr);r.check_returncode()
 return r.stdout
def main():
 c=p.OUT;v=c/'verification';mock=v/'mock';mock.mkdir(exist_ok=True)
 for f in (p.BASE/'verification/mock').iterdir():
  if f.is_file():shutil.copy2(f,mock/f.name)
 f=mock/'main.h';s=p.read(f)
 s=p.once(s,'#define SET_BIT(r,b) ((r)|=(b))',
  'static unsigned mock_pe_enables,mock_pe_disables;\nstatic inline void mock_set(uint32_t*r,uint32_t b){if(r==&test_i2c.CR1&&(b&1))++mock_pe_enables;*r|=b;}\n#define SET_BIT(r,b) mock_set(&(r),(b))')
 s=p.once(s,'void mock_clear(uint32_t*r,uint32_t b){*r&=~b;','void mock_clear(uint32_t*r,uint32_t b){if(r==&test_i2c.CR1&&(b&1))++mock_pe_disables;*r&=~b;');p.write(f,s)
 compiler=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers']
 inc=['-I',str(mock),'-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src')]
 exe=v/'persistent_platform.exe';run('platform_compile',compiler+inc+[str(p.RES/'platform_test.cpp'),'-o',str(exe)])
 platform=[json.loads(run('platform_'+mode,[str(exe),mode])) for mode in ('normal','lost_pe','missing_hook')]
 # Retain the existing bus-clear startup replay and all92 bus-clear core cases.
 exe=v/'bus_clear_driver.exe';run('bus_clear_driver_compile',compiler+inc+[str(p.ROOT/'tools/sda_idle_bus_clear/driver_test.cpp'),'-o',str(exe)])
 bus_driver=[json.loads(run('bus_clear_driver_'+str(i),[str(exe),str(i)])) for i in range(3)]
 exe=v/'bus_clear_core.exe';run('bus_clear_core_compile',compiler+inc+[str(p.ROOT/'tools/sda_idle_bus_clear/core_test.cpp'),'-o',str(exe)]);bus=json.loads(run('bus_clear_core',[str(exe)]))
 # The exact audited lifecycle core and platform delta are used in the target.
 assert p.read(c/'nucleo/Inc/encoder_core.h')==p.identity(p.read(p.AUDIT/'candidate/encoder_core.h'))
 assert p.read(c/'nucleo/Src/nucleo_encoder.c')==p.identity(p.read(p.AUDIT/'candidate/nucleo_encoder.c'))
 p.write(v/'regression.cpp',p.read(p.AUDIT/'regression.cpp'))
 p.write(v/'record_fixture.h',p.identity(p.read(p.BASE/'verification/record_fixture.h')))
 exe=v/'regression.exe';run('regression_compile',compiler+['-I',str(c/'nucleo/Inc'),'-I',str(v),str(v/'regression.cpp'),'-o',str(exe)]);regression=json.loads(run('regression',[str(exe)]))
 exe=v/'lifecycle_ab.exe';run('ab_compile',compiler+['-DMIC_PERSISTENT_PE=1','-I',str(c/'nucleo/Inc'),str(p.ROOT/'tools/pwm_i2c_lifecycle_ab.cpp'),'-o',str(exe)]);ab=json.loads(run('ab',[str(exe)]))
 assert ab['healthy_reads']==200 and ab['healthy_enables']==1 and ab['healthy_pe_disables']==0 and ab['nack_errors']==1
 # No motor/main/Uno changes beyond version identity; libraries/IRQ/ADC/bus clear
 # remain exact. The only two implementation changes are the core and adapter.
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  for f in (p.BASE/folder).rglob('*'):
   rel=f.relative_to(p.BASE/folder);key=str(rel).replace('\\','/')
   if not f.is_file() or any(x in ('Debug','Release','__pycache__','.settings') for x in rel.parts):continue
   g=c/folder/rel
   if folder=='nucleo' and key in ('Src/nucleo_encoder.c','Inc/encoder_core.h'):continue
   if folder=='web_hmi' and key=='server.py':assert p.read(g)==p.hmi(p.read(f));continue
   if f.read_bytes()!=g.read_bytes():assert p.read(g)==p.identity(p.read(f)),str(rel)
 h=load_module(c/'web_hmi/server.py');old=load_module(p.BASE/'web_hmi/server.py');checks=0
 for flags in range(256):
  expected=old.sd_live_status(dict(mc_fw_build=p.OLD[1],mc_age_ms=20,bp_temp_flags=flags))
  assert h.sd_live_status(dict(mc_fw_build=p.NEW[1],mc_age_ms=20,bp_temp_flags=flags))==expected;checks+=1
 z=h.break_wire_status(dict(bp_fw_build=p.NEW[1],bp_age_ms=20,mc_break0_hex='00'*92,mc_break0_age_ms=100,mc_break1_hex='00'*92,mc_break1_age_ms=100));assert all(x['available'] for x in z['mc_break_snapshots']);checks+=1
 for r in bus_driver[:2]:
  d=dict(mc_fw_build=p.NEW[1],enc_fault_first_hex=r['parent'],enc_fault_decode_valid=1,enc_bus_clear_hex=r['record'])
  assert h.with_bus_clear(d)['enc_bus_clear_record'];checks+=1
  for n in range(43):
   b=bytearray.fromhex(r['record']);b[n]^=1;assert h.with_bus_clear(dict(d,enc_bus_clear_hex=b.hex()))['enc_bus_clear_decode_valid']==0;checks+=1
 # Re-identify saved raw frames with recomputed CRCs, never alter the originals.
 fixture=json.loads(p.read(p.BASE/'runtime_idle_r2/report.json'))['last'];s=copy.deepcopy(fixture)
 s.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_fw_build=p.NEW[1])
 for key in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex','mc_zero_history_hex'):
  raw=bytearray.fromhex(s[key]);assert len(raw)%43==0
  for i in range(0,len(raw),43):raw[i+6:i+10]=p.NEW[1].to_bytes(4,'little');raw[i+39:i+43]=h.current_crc32c(raw[i:i+39]).to_bytes(4,'little')
  s[key]=raw.hex()
 assert h.with_zero_history(h.with_shunt_currents(copy.deepcopy(s)))['mc_zero_history_valid']==1;checks+=1
 assert h.manual_scalar_supported(dict(s,manual_scalar_capable=1));checks+=1
 assert h._vbus_calibration_identity_matches(dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1),dict(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1));checks+=1
 raw=bytearray.fromhex(s['enc_fault_first_hex']);raw[4:8]=p.NEW[1].to_bytes(4,'little');s['enc_fault_first_hex']=raw.hex();parent_crc=h.crc32c(raw)
 child=bytearray.fromhex(s['enc_release_first_hex']);child[4:8]=p.NEW[1].to_bytes(4,'little');child[8:12]=parent_crc.to_bytes(4,'little');child[96:100]=h.crc32c(child[:96]).to_bytes(4,'little');s['enc_release_first_hex']=child.hex()
 clear=bytearray.fromhex(s['enc_bus_clear_hex']);clear[6:10]=p.NEW[1].to_bytes(4,'little');clear[22:26]=parent_crc.to_bytes(4,'little');clear[39:43]=h.current_crc32c(clear[:39]).to_bytes(4,'little');s['enc_bus_clear_hex']=clear.hex()
 decoded=h.with_i2c_first_fault(s);assert decoded['enc_fault_decode_valid']==decoded['enc_release_decode_valid']==decoded['enc_bus_clear_decode_valid']==1 and decoded['enc_bus_clear_record'];checks+=1
 for n in range(100):
  b=child.copy();b[n]^=1;assert h.with_i2c_first_fault(dict(s,enc_release_first_hex=b.hex()))['enc_release_decode_valid']==0;checks+=1
 # Old captures still decode on the new HMI with their original peer identity.
 d=h.with_i2c_first_fault(copy.deepcopy(fixture));assert d['enc_fault_decode_valid']==d['enc_release_decode_valid']==d['enc_bus_clear_decode_valid']==1;checks+=1
 for rel,digest in json.loads(p.read(c/'manifest.json'))['historical_records_preserved'].items():assert p.sha(c/'preserved_records'/rel)==digest
 r=dict(passed=True,hardware_commands=0,platform=platform,bus_clear_driver=bus_driver,bus_clear_core=bus,regression=regression,ab=ab,hmi_checks=checks,
  healthy_idle_config_verified=True,error_cleanup_preserved=True,frozen_records_verified=True,protection_source_isolation=True,rpc_libraries_unchanged=True,calibration_identity_compatible=True,historical_records_preserved=True)
 p.write(v/'native_report.json',json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ('bus_clear_driver',)}))
if __name__=='__main__':main()
