"""One occupied-bus episode waits for existing recovery permission; no fault masking."""
import json,os,shutil
from pathlib import Path
import prepare_no_switch_diag as p
from audit_production_pwm_filters import function
OLD=p.ROOT/'artifacts/live_bench_20261028/full_mcsdk_edges_r1'
PIN=p.ROOT/'artifacts/live_bench_20261028/combined_io_diag_r2'
OUT=OLD.with_name('full_mcsdk_edges_busy_wait_r1');BUILD=2026102805
def transform(s):
 old='''  if(allowed && !bus_clear.attempted && enc.primary_busy && (fault_ready&1U) &&
     release_probe[0].complete && lines(0)==1U){
    bc_begin(&bus_clear,&bus_clear_io,DWT->CYCCNT);return true;
  }'''
 new='''  if(!bus_clear.attempted && enc.primary_busy && (fault_ready&1U) &&
     release_probe[0].complete && enc.configured && !enc.state && !enc.prepare &&
     !enc.recovering && !(I2C1->CR1&I2C_CR1_PE) && lines(0)==1U){
    /* A known occupied bus is one failed preflight, not a new transfer every
       20ms while the application waits to permit recovery. Keep the first
       fault/invalid status; do not send START/STOP/clocks or reset counters. */
    if(allowed)bc_begin(&bus_clear,&bus_clear_io,DWT->CYCCNT);
    return true;
  }'''
 return p.once(s,old,new)
def main():
 OUT.mkdir(parents=True,exist_ok=False);m=json.loads(p.read(OLD/'manifest.json'));assert m['concurrent_real_edges_passed']
 for rel,h in m['sealed_sha256'].items():assert p.sha(OLD/rel)==h,rel
 def cp(src,dst):
  rel=Path(src).relative_to(OLD/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(OLD/'nucleo',OUT/'nucleo',copy_function=cp,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for t in ('build/nucleo','verification','restore','preserved_records'):(OUT/t).mkdir(parents=True,exist_ok=True)
 shutil.copytree(OLD/'preserved_records',OUT/'preserved_records/earlier',copy_function=os.link)
 for t in ('run_r1','install_r1','build/nucleo'):shutil.copytree(OLD/t,OUT/'preserved_records/2804'/t,copy_function=os.link)
 for n in ('assessment.json','runtime_sha256.json','manifest.json'):shutil.copy2(OLD/n,OUT/'preserved_records/2804'/n)
 for n,h in m['tools_sha256'].items():
  assert p.sha(p.ROOT/'tools'/n)==h,n
  dst=OUT/'preserved_records/2804/tools'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p.ROOT/'tools'/n,dst)
 for f in (OLD/'restore').iterdir():shutil.copy2(f,OUT/'restore'/f.name)
 for t in ('Src','Inc'):
  for f in (OUT/'nucleo'/t).iterdir():
   if f.is_file():
    a=p.read(f);b=a.replace('2026102804',str(BUILD))
    if a!=b:p.write(f,b)
 f=OUT/'nucleo/Src/nucleo_encoder.c';p.write(f,transform(p.read(f)))
 m={k:v for k,v in m.items() if k not in ('sealed_sha256','tools_sha256','archived')}
 m.update(build=BUILD,built=False,installed=False,hardware_tested=False,offline_verified=False,readback_verified=False,concurrent_real_edges_passed=False,
  previous_build=2026102804,fix='Wait with frozen invalid BUSY status until existing idle bus-clear permission; preserve first record and original transfer state machine',
  archived={f.relative_to(OUT/'preserved_records').as_posix():p.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()})
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(prepared=True,build=BUILD,hardware_calls=0,archived=len(m['archived']))))
if __name__=='__main__':main()
