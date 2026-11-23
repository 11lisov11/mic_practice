"""Seal offline-checked1501/1502, preserving evidence and timing limitations."""
import inspect,json,re,subprocess
from elftools.elf.elffile import ELFFile
import seal_observer_input_epoch as old
import prepare_observer_irq_budget as p
from build_multi_native import BIN


def main():
 tests=json.loads(p.read(p.OUT/'verification/report.json'))
 model=json.loads(p.read(p.OUT/'model_verification/model_report.json'))
 assert tests['passed'] and model['passed'] and model['baseline_candidate_model_trajectories_identical']
 # Remove inherited measurements which belong to the installed predecessor.
 m=json.loads(p.read(p.OUT/'manifest.json'))
 for key in ('target_timing_measured_OFF','measured_OFF_fast_cycles','measured_CPU_profile_cases',
             'idle_report_SHA256','numeric_tests','unchanged_source_files'):
  m.pop(key,None)
 m.update(target_timing_measured_OFF=False,controller_equations_changed=False,
          numeric_tests=tests['numeric'],FT_wire_schema=3,FT_pages=9,
          baseline_OFF_fast_cycles=3953,baseline_runtime_fast_cycles=5263,
          baseline_runtime_stop_ms=155,baseline_estimate_age_us=2028.4411764705883,
          UART_TC_IRQ_order_fixed=True,recorded_UART_storm_proven=False,
          per_IRQ_breakdown_available_after_install=True,
          observer_workspace_reused_without_math_change=True)
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 source=inspect.getsource(old.main)
 source=source.replace('_observer_input.hex','_observer_irq.hex').replace('_observer_trace.elf-zsk.bin','_observer_irq.elf-zsk.bin')
 scope=dict(old.__dict__,p=p);exec(compile(source,__file__,'exec'),scope);scope['main']()
 m=json.loads(p.read(p.OUT/'manifest.json'))
 elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 asm=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d',str(elf)],text=True)
 p.write(p.OUT/'verification/ARM_candidate_final.txt',asm)
 native_su=p.read(p.OUT/'nucleo/STM32CubeIDE/Debug/Application/User/multi_native.su')
 stack={}
 for line in native_su.splitlines():
  fields=line.split('\t')
  if len(fields)>=3:stack[fields[0].split(':')[-1]]=int(fields[1])
 arm=dict(passed=True,compiler='GNU Arm14.3 CortexM4F hard float',
          fast_math_not_enabled_for_native_control=True,
          control_always_inlined=not bool(re.search(r' <ma_control_checked[^>]*>:',asm)),
          fixed_model_folded=not bool(re.search(r' <fe_control_model>:',asm)),
          stack_usage=stack,SRAM_sections=m['RAM_sections'],RAM_unallocated=m['RAM_unallocated'],
          target_cycle_claim=False,full_nested_stack_high_water_measured=False)
 assert arm['control_always_inlined']
 assert stack['ma_observe.part.0.constprop']<880
 p.write(p.OUT/'verification/ARM_scope.json',json.dumps(arm,indent=2)+'\n')
 m.update(installed=False,hardware_commands=0,OFF_CPU_qualified=False,FOC_start_ready=False,
          target_timing_measured=False,target_timing_measured_OFF=False,
          full_adapter_under_PWM_measured=False,physical5s_run_proven=False,
          verification_reports={rel:p.sha(p.OUT/rel) for rel in (
              'verification/report.json','verification/ARM_scope.json','model_verification/model_report.json')})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 diagnosis=dict(recorded_fault='MA_STALE/FT_ESTIMATE_AGE while observer is in compute',
    age_us=2028.4411764705883,unchanged_limit_us=2000,
    previous_observer_wall_us=874.8588235294118,previous_IRQ_lower_us=769.3176470588236,
    previous_CPU_upper_us=105.54117647058824,
    exact_IRQ_dominance_identified=False,
    reason='Old recording contains only aggregate IRQ time, not per-vector counters.',
    frequent_vectors_from_code={'TIM1_UPDATE':16000,'ADC1_2':16000},
    software_defect_reproduced='UART TCIE enabled while DMA still has bytes; an inter-byte TC can reenter the old IRQ indefinitely until progress.',
    fix='DMA TC now enables UART TCIE after CNDTR reaches0; completion still requires the final UART stop bit. A spurious early TC disables TCIE without clearing a possibly final TC.',
    controller_optimization='Same exact FE model after unchanged per-frame exact-model guard; always-inline permits constant propagation; startup speed-loop work whose result was overwritten is skipped.',
    observer_optimization='Jacobian workspace reused only after transition matrix is complete; same operation order, smaller stack.',
    evidence_preserved=m['preserved_files_verified'],thresholds_changed=False,
    hardware_commands=0,full5s_hardware_success_proven=False)
 p.write(p.OUT/'recorded_fault_analysis.json',json.dumps(diagnosis,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(dict(passed=True,pair=list(p.NEW),built=True,installed=False,
                      preserved_files_verified=m['preserved_files_verified'],RAM_unallocated=m['RAM_unallocated'])))


if __name__=='__main__':main()
