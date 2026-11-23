"""Actual native adapter and unchanged ARM sections; no hardware access."""
import json,subprocess
from elftools.elf.elffile import ELFFile
import prepare_start_history_release as p
from test_foc_estimate_publish_fix import native_source
from test_observer_current_window import compile_case

def section(path,name):
 with path.open('rb') as f:return ELFFile(f).get_section_by_name(name).data()
def main():
 out=p.OUT/'native_verification_r2';out.mkdir(exist_ok=False)
 fixture=p.read(p.BASE/'verification/adapter/exact_native_adapter.cpp')
 pre='#include "observer_start_history.h"\n'+fixture.split('#define MIC_NATIVE_BUILD',1)[0]
 native=native_source(p.OUT).replace('sample=bin_current;ow_bin window=bin_window;',
  'sample=bin_current;ow_bin window=bin_window;if(inject_torn){++telemetry_seq;inject_torn=false;}')
 tail=fixture[fixture.index('static void NVIC_SetPendingIRQ(int irq){'):]
 tail=tail[:tail.index(' // Exact saved prior/input')]
 tail+=r'''
 assert(observer_history.meta.count==1&&observer_history.meta.initial.steps==0);++checks;
 assert(observer_history.meta.initial.p[4][4]==900.f);++checks;
 const nh_row&row=observer_history.queue[0];float captured[5];memcpy(captured,row.bytes,20);
 assert(captured[0]==w.ia&&captured[1]==w.ib&&captured[2]==w.va&&captured[3]==w.vb);++checks;
 assert(row.hash==nh_hash(&observer));++checks;
 timer.BDTR=0;ma_native_service();assert(observer_history.frozen);++checks;
 auto preserved=observer_history.meta;assert(ma_native_prepare());
 assert(!memcmp(&preserved,&observer_history.meta,sizeof(preserved)));++checks;
 // Original raw current and stale estimate trips still stop. Synthetic inputs.
 timer.BDTR=1;fake_bus=323;running=1;run_fault=0;
 sample.valid=sample.zero=1;sample.cycles=cycle.CYCCNT;
 sample.counts[0]=150;sample.counts[1]=-75;sample.counts[2]=-75;
 ma_estimate_reset(cycle.CYCCNT);assert(ma_native_fast(1.f)!=MC_NO_ERROR&&run_fault==MA_CURRENT);++checks;
 run_fault=0;sample.counts[0]=sample.counts[1]=sample.counts[2]=0;
 start_cycles=fe_trial_begin=cycle.CYCCNT-1700000U; // beyond the unchanged <=1ms neutral prime
 ma_estimate_reset(cycle.CYCCNT-340001U);
 assert(ma_native_fast(1.f)!=MC_NO_ERROR&&run_fault==MA_STALE);++checks;
 printf("{\"passed\":true,\"checks\":%u,\"OFF_cases\":%u,\"fake_clock_not_target_timing\":true}\n",checks,fe_case);
}
'''
 exe=compile_case(out,'native_adapter',pre+native+'\n'+tail,p.OUT)
 result=subprocess.run([str(exe)],capture_output=True,text=True)
 p.write(out/'native_run.log',result.stdout+result.stderr);result.check_returncode();adapter=json.loads(result.stdout)
 obj='nucleo/STM32CubeIDE/Debug/Application/User/multi_native.o'
 same={name:section(p.BASE/obj,'.text.'+name)==section(p.OUT/obj,'.text.'+name)
  for name in ('ma_native_fast','mic_observer_step','mic_observer_noise')}
 assert all(same.values()),same
 report=dict(passed=True,adapter=adapter,ARM_byte_identical_sections=same,
  fast_budget_cycles=4000,estimate_age_ms=2,hardware_commands=0,target_timing_measured=False,
  full_firmware_linked=True,new_foreground_history_cost_NOT_measured_on_target=True)
 p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
