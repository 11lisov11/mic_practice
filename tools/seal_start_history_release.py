"""Verify old evidence and seal the OFFLINE candidate. No device access."""
import json,py_compile
from pathlib import Path
import prepare_start_history_release as p
def main():
 assert not (p.OUT/'release_manifest.json').exists(),'Never rewrite a sealed release'
 preserved=json.loads(p.read(p.OUT/'preserved_inputs_sha256.json'))
 older=json.loads(p.read(p.ROOT/'artifacts/live_bench_20261118/nis_exact_source_analysis_r1/protected_inputs_sha256.json'))
 for source in (preserved,older):
  for relative,expected in source.items():assert p.sha(p.ROOT/relative)==expected,'Old evidence changed: '+relative
 tests={}
 for name,relative in (
  ('codec_and_ARM_sequence','verification/report.json'),
  ('native_adapter','native_verification_r2/report.json'),
  ('full_capacity','capacity_verification/report.json'),
  ('RPC_and_throughput','transport_verification/report.json'),
  ('real_saved_step','verification/preserved_real_step_replay.json'),
  ('native_build','nucleo_build_report.json')):
  result=json.loads(p.read(p.OUT/relative));assert result['passed'],name;tests[name]=relative
 py_compile.compile(str(p.OUT/'web_hmi/server.py'),doraise=True)
 uno=p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json';m=json.loads(p.read(uno))
 assert m['firmware_build_id']==p.NEW[0] and '921600' in m['transport']
 llext=json.loads(p.read(p.OUT/'build/uno/llext-check.json'));assert llext['pass'] and not llext['issues']
 for item in m['artifacts']:
  assert p.sha(uno.parent/item['file']).lower()==item['sha256'].lower()
 elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 replay=dict(schema='mic_ai.observer_start_history_replay.v1',firmware=p.NEW[1],
  elf=elf.relative_to(p.OUT).as_posix(),elf_sha256=p.sha(elf),
  ABI='observer: R0=o,R1=model,R2=input,R3=noise; noise: R0=counts,R1=out',
  capture_schema=1,input_row_bytes=22,capacity=5120,checkpoint_stride=16,
  record_files=['meta.bin','rows.bin','checkpoints.bin'],
  FPSCR_control_bits='22..26: rounding, FZ, DN, AHP; sticky exception flags do not alter this non-trapping kernel',
  initial_and_terminal_state_words=51,exact_replay_requires_all_rows_and_checkpoints=True)
 p.write(p.OUT/'replay_manifest.json',json.dumps(replay,indent=2)+'\n')
 # Capture/model/guard headers are unchanged from the installed package.
 guards={}
 for name in ('motor_control.h','observer_pair_noise.h','foc_experiment.h','current_adc_window_plan.h',
  'current_adc_deadline.h','local_stop.h','first_break_snapshot.h','observer_trace_core.h','peak_core.h'):
  assert p.sha(p.BASE/'nucleo/Inc'/name)==p.sha(p.OUT/'nucleo/Inc'/name),name
  guards[name]=p.sha(p.OUT/'nucleo/Inc'/name)
 files=[elf,elf.with_suffix('.bin'),elf.with_suffix('.hex'),uno,
  uno.parent/'UNOQ_MOTOR.ino.elf',uno.parent/'UNOQ_MOTOR.ino.elf-zsk.bin']
 result=dict(schema='mic_ai.observer_start_history_release.v1',pair=p.NEW,installed=False,
  offline_acceptance_passed=True,tests=tests,hardware_commands=0,live_status_GET=0,
  START=0,CLEAR=0,RESET=0,flash=0,
  OFF_fast_limit_cycles=4000,estimate_age_ms=2,raw_current_trip_A=1.35,ADC_UPDATE_ticks=2048,
  control_and_observer_math_unchanged=True,publication_policy_candidate_NOT_included=True,
  UART_baud=921600,both_images_must_be_installed_as_a_pair=True,
  UART_rate_hardware_qualified=False,new_foreground_cost_measured_on_target=False,
  new_target_4000_cycles_qualification=False,power_test_qualified=False,
  physical_NIS_root_cause_fixed=False,
  Nucleo_RAM_free_after_original_heap_stack_reserve_bytes=392,
  Nucleo_heap_reserve_bytes=512,Nucleo_stack_reserve_bytes=1024,
  Uno_RAM_static_bytes=217850,Uno_RAM_remaining_bytes=44294,
  Uno_compiler_low_memory_warning=True,
  prior_input_hashes_verified=len(preserved),older_input_hashes_verified=len(older),
  identical_guard_headers=guards,artifacts={f.relative_to(p.OUT).as_posix():p.sha(f) for f in files})
 p.write(p.OUT/'release_manifest.json',json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(offline_acceptance=True,pair=p.NEW,hardware_commands=0,
  preserved_hashes_verified=[len(preserved),len(older)],target_timing_measured=False)))
if __name__=='__main__':main()
