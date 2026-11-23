"""Offline exact fixed-profile predicate and bounded hypot core dispatch."""
import json,os,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
from prepare_cin_sd_diag import sha
BASE=ROOT/'artifacts/live_bench_20261115/observer_irq_budget_r1'
OUT=ROOT/'artifacts/live_bench_20261115/exact_profile_budget_r1'
NEW=(2026111503,2026111504)


HELPER='''/* Same installed newlib hypot core, without its errno/finite-result
 * wrapper when BOTH finite inputs are bounded by2^50. Their norm is at most
 * sqrt(2)*2^50, far below FLT_MAX, so the wrapper would return it unchanged.
 * All other bit patterns use the original hypotf entry point. The raw-current
 * trip expression deliberately continues to call original hypotf as before. */
#ifndef MIC_CONTROL_HYPOT_CORE
#if defined(__arm__) || defined(__thumb__)
extern float __ieee754_hypotf(float,float);
#define MIC_CONTROL_HYPOT_CORE(a,b) __ieee754_hypotf(a,b)
#else
#define MIC_CONTROL_HYPOT_CORE(a,b) hypotf(a,b)
#endif
#endif
static inline float ma_control_norm(float a,float b){
 uint32_t x,y;memcpy(&x,&a,4);memcpy(&y,&b,4);
 if((x&0x7fffffffU)<=0x58800000U&&(y&0x7fffffffU)<=0x58800000U)
  return MIC_CONTROL_HYPOT_CORE(a,b);
 return hypotf(a,b);
}

'''


def main():
 assert not OUT.exists(),'Never replace prepared firmware or measurements'
 for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=os.path.relpath(src,BASE/folder).split(os.sep)
   if folder=='libraries' or folder=='nucleo' and rel[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026111501',str(NEW[0])).replace('2026111502',str(NEW[1]))
    if n!=s:write(f,n)
 f=OUT/'nucleo/Inc/foc_experiment.h';s=read(f)
 s=once(s,' return ma_motor_valid(m)&&memcmp(m,&expected,sizeof(expected))==0;',
 ''' /* expected is validated by release tests. Bit identity with that SAME
  * valid52-byte model implies the original ma_motor_valid predicate. Compare
  * every byte via memcpy words: no aliasing cast, rounding, CRC shortcut,
  * or cached result; a changed bit still rejects in the SAME invocation. */
 uint32_t difference=0;
#pragma GCC unroll 13
 for(unsigned i=0;i<13;++i){
  uint32_t a,b;memcpy(&a,(const uint8_t*)m+4*i,4);
  memcpy(&b,(const uint8_t*)&expected+4*i,4);difference|=a^b;
 }
 return difference==0;''')
 write(f,s)
 f=OUT/'nucleo/Inc/motor_control.h';s=read(f)
 s=once(s,'static inline int ma_motor_valid(',HELPER+'static inline int ma_motor_valid(')
 # Only the controller's two non-trip norms. Observer bounds and raw1.35A
 # current-trip hypot, including its boundary rounding, are left verbatim.
 s=once(s,'  const float flux=hypotf(x[2],x[3]);','  const float flux=ma_control_norm(x[2],x[3]);')
 s=once(s,'mag=hypotf(dq[0],dq[1]);','mag=ma_control_norm(dq[0],dq[1]);')
 write(f,s)
 preserved=json.loads(read(BASE/'preserved_capture_hashes.json'))
 for f in BASE.rglob('*'):
  if f.is_file() and f.suffix in ('.json','.jsonl','.bin','.log','.txt','.png','.md'):
   preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2)+'\n')
 old=json.loads(read(BASE/'manifest.json'))
 keep=('trip_A','ADC_guard_ticks','estimate_limit_ms','fast_budget_cycles','frequency_max_hz',
       'runlimit_ms','peer_reply_timeout_ms','send_cadence_us','reply_guard_us','CPU_probe_budget_cycles',
       'applied_voltage_source_corrected','accepted_reply_lifecycle_corrected',
       'exact_saturated_polarity_fast_path','profiling_work_removed')
 m={k:old[k] for k in keep}
 m.update(pair=list(NEW),base_pair=old['pair'],built=False,installed=False,hardware_commands=0,
          START=0,CLEAR=0,ARM=0,RESET=0,thresholds_changed=False,observer_tuning_changed=False,
          controller_equations_changed=False,OFF_CPU_qualified=False,FOC_start_ready=False,
          target_timing_measured=False,target_timing_measured_OFF=False,
          target_timing_requalification_required=True,hardware_validated=False,
          full_adapter_under_PWM_measured=False,CPU_baseline_cycles=4229,
          FT_wire_schema=3,FT_pages=9,UART_TC_IRQ_order_fixed=True,
          exact_profile_all52_bytes_each_call=True,raw_current_trip_norm_unchanged=True,
          no_global_math_override=True)
 write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print('Prepared offline exact predicate/hypot dispatch',NEW)


if __name__=='__main__':main()
