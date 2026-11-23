"""Offline investigation: preserve the installed pair and test persistent PE.

This creates a source patch, NOT an installed image or proof of EMI immunity.
"""
import difflib,hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261027/sda_idle_recovery_r1'
OUT=ROOT/'artifacts/live_bench_20261027/pwm_i2c_lifecycle_audit_r1'
def read(p):return p.read_text(encoding='utf-8')
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8')
def once(s,a,b):assert s.count(a)==1,a;return s.replace(a,b)
def run(name,args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=40);write(OUT/(name+'.log'),r.stdout+r.stderr)
 if r.returncode:print(r.stdout+r.stderr);r.check_returncode()
 return r.stdout
def main():
 assert not (OUT/'report.json').exists(),'Keep previous report'
 OUT.mkdir(exist_ok=True)
 (OUT/'candidate').mkdir(exist_ok=True)
 for name in ('encoder_core.h','encoder_health_wire.h','fault_wire.h','uart_v3_transport.h','cleanup_flags.h'):shutil.copy2(BASE/'nucleo/Inc'/name,OUT/'candidate'/name)
 old=read(BASE/'nucleo/Inc/encoder_core.h');s=old
 s=once(s,'  void (*terminal)(void*,uint8_t);','  void (*terminal)(void*,uint8_t);\n  void (*completed)(void*);')
 s=once(s,'  bool have_free_since;','  bool have_free_since;\n  bool pe_on;')
 s=once(s,'  ec_elapsed(e,cycles,hz);ec_idle(e);','  e->pe_on=false;\n  ec_elapsed(e,cycles,hz);ec_idle(e);')
 s=once(s,'io->clear(io->ctx);io->park(io->ctx);ec_inc32(&e->parks);ec_inc32(&e->reads);','io->clear(io->ctx);io->completed(io->ctx);ec_inc32(&e->reads);')
 s=once(s,'!io->stop_ready||!io->request_stop||!io->flush_tx||!io->terminal)', '!io->stop_ready||!io->request_stop||!io->flush_tx||!io->terminal||!io->completed)')
 s=once(s,'    e->prepare=1;e->have_free_since=false;','    e->prepare=e->pe_on?2:1;e->have_free_since=false;')
 s=once(s,'if(e->prepare==1){io->enable(io->ctx);e->prepare=2;return;}','if(e->prepare==1){io->enable(io->ctx);e->pe_on=true;e->prepare=2;return;}')
 write(OUT/'candidate/encoder_core.h',s)
 driver=read(BASE/'nucleo/Src/nucleo_encoder.c')
 new=once(driver,'static void begin_write(void*x){','static void completed(void*x){(void)x;I2C1->CR2=0;}\nstatic void begin_write(void*x){')
 new=once(new,'flush_tx,capture_terminal};','flush_tx,capture_terminal,completed};')
 new=once(new,'(enc.state!=0 || enc.prepare==2)','enc.pe_on')
 patch=''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='nucleo/Inc/encoder_core.h',tofile='nucleo/Inc/encoder_core.h'))
 patch+=''.join(difflib.unified_diff(driver.splitlines(True),new.splitlines(True),fromfile='nucleo/Src/nucleo_encoder.c',tofile='nucleo/Src/nucleo_encoder.c'))
 write(OUT/'persistent_pe.patch',patch);write(OUT/'candidate/nucleo_encoder.c',new)
 # Retain the existing400 error/recovery cases; change only the healthy
 # transaction expectation and its new completion callback.
 test=read(ROOT/'tools/nucleo_i2c_stop/selftest.cpp')
 test=once(test,'static ec_io io(Model&b){','static void completed(void*p){auto&b=*(Model*)p;REQUIRE(b.pe&&!(b.isr&EC_BUSYF));}\nstatic ec_io io(Model&b){')
 test=once(test,'request,flush,terminal};','request,flush,terminal,completed};')
 test=once(test,'b.e.raw==2048&&!b.e.state&&!b.pe','b.e.raw==2048&&!b.e.state&&b.pe')
 write(OUT/'regression.cpp',test)
 shutil.copy2(BASE/'verification/record_fixture.h',OUT/'candidate/record_fixture.h')
 compiler=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror']
 exe=OUT/'regression.exe';run('regression_compile',compiler+['-I',str(OUT/'candidate'),str(OUT/'regression.cpp'),'-o',str(exe)])
 regression=json.loads(run('regression',[str(exe)]));assert regression['passed']
 # The A/B model makes a false-BUSY event ONLY on a new enable edge. This
 # demonstrates exposure to that mechanism, not that it happened on hardware.
 ab=ROOT/'tools/pwm_i2c_lifecycle_ab.cpp';results={}
 for mode,inc in [('installed',BASE/'nucleo/Inc'),('persistent_pe',OUT/'candidate')]:
  exe=OUT/(mode+'.exe');run(mode+'_compile',compiler+['-DMIC_PERSISTENT_PE='+str(int(mode=='persistent_pe')),'-I',str(inc),str(ab),'-o',str(exe)])
  results[mode]=json.loads(run(mode,[str(exe)]))
 assert results['installed']['false_busy_errors']==1 and results['persistent_pe']['false_busy_errors']==0
 assert results['installed']['nack_errors']==results['persistent_pe']['nack_errors']==1
 # Installed sources/images and saved records stay byte-for-byte unchanged.
 m=json.loads(read(BASE/'manifest.json'))
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for rel,h in m[table].items():assert hashlib.sha256((BASE/rel).read_bytes()).hexdigest()==h,rel
 report=dict(passed=True,hardware_commands=0,source_patch_only=True,installed_firmware_unchanged=True,regression=regression,ab=results,
  confirmed_unnecessary_pe_reset_after_healthy_read=True,pe_reset_frequency_at_200_reads_per_second=200,
  initial_pwm_nack_fixed_or_reproduced=False,physical_cause_proven=False,
  limits=['A/B false BUSY is injected by the model only on PE enable; no recorded analog waveform proves that origin',
          'The recorded first NACK remains an error in both implementations',
          'This is an offline source patch; target build, full integration and hardware validation are outstanding'])
 write(OUT/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
