"""Seal verified OFFLINE1805/1806; no programmer, ports, reset or bench RPC."""
import json,py_compile,shutil
from elftools.elf.elffile import ELFFile
import prepare_uart_921600_rx as p
from probe_native_programming_state import programmed_hex_image

def main():
 assert not (p.OUT/'release_manifest.json').exists()
 tests=['verification/native_RX_r4/report.json','verification/Uno_RX_r3/report.json',
  'verification/guards_r3/report.json','verification/negative_controls/report.json',
  'verification/history_link_r2/report.json','verification/final_build_identity.json','nucleo_build_report.json']
 for path in tests:assert json.loads(p.read(p.OUT/path))['passed'],path
 preserved=json.loads(p.read(p.OUT/'preserved_inputs_sha256.json'))
 for relative,h in preserved.items():assert p.sha(p.ROOT/relative)==h,relative
 previous=json.loads(p.read(p.BASE/'preserved_inputs_sha256.json'))
 for relative,h in previous.items():assert p.sha(p.ROOT/relative)==h,relative
 oldest=json.loads(p.read(p.ROOT/'artifacts/live_bench_20261118/nis_exact_source_analysis_r1/protected_inputs_sha256.json'))
 for relative,h in oldest.items():assert p.sha(p.ROOT/relative)==h,relative
 elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 with elf.open('rb') as f:
  e=ELFFile(f);syms={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
  assert syms['DMA1_Channel2_IRQHandler']['st_info']['bind']=='STB_GLOBAL'
  assert int(syms['mic_uart_rx_dma']['st_size'])==128
  assert int(syms['mic_uart_rx_dma_diag']['st_size'])==24
 py_compile.compile(str(p.OUT/'web_hmi/server.py'),doraise=True)
 uno=p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json';m=json.loads(p.read(uno))
 assert m['firmware_build_id']==p.NEW[0] and '921600' in m['transport']
 assert json.loads(p.read(uno.parent/'llext-check.json'))['pass']
 for a in m['artifacts']:assert p.sha(uno.parent/a['file']).lower()==a['sha256'].lower()
 release=p.OUT/'release';release.mkdir()
 for ext in ('elf','hex','bin'):shutil.copy2(elf.with_suffix('.'+ext),release/f'nucleo_{p.NEW[1]}_uart_rx_dma.{ext}')
 expected,holes=programmed_hex_image(elf.with_suffix('.hex'),elf.with_suffix('.bin').read_bytes())
 (release/f'nucleo_{p.NEW[1]}_expected_readback.bin').write_bytes(expected)
 shutil.copy2(uno.parent/'UNOQ_MOTOR.ino.elf-zsk.bin',release/f'uno_{p.NEW[0]}_fifo_uart.elf-zsk.bin')
 replay=dict(schema='mic_ai.observer_start_history_replay.v1',firmware=p.NEW[1],
  elf=f'release/nucleo_{p.NEW[1]}_uart_rx_dma.elf',elf_sha256=p.sha(elf),
  capture_schema=1,input_row_bytes=22,capacity=5120,checkpoint_stride=16,
  record_files=['meta.bin','rows.bin','checkpoints.bin'],initial_and_terminal_state_words=51,
  exact_replay_requires_all_rows_and_checkpoints=True,
  ABI='observer: R0=o,R1=model,R2=input,R3=noise; noise: R0=counts,R1=out')
 p.write(p.OUT/'replay_manifest.json',json.dumps(replay,indent=2)+'\n')
 report=dict(schema='mic_ai.uart_921600_rx_release.v1',pair=p.NEW,built=True,installed=False,
  offline_acceptance_passed=True,tests=tests,hardware_commands=0,bench_GET=0,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,
  OFF_fast_limit_cycles=4000,estimate_age_ms=2,raw_current_trip_A=1.35,ADC_UPDATE_ticks=2048,
  native_RX_DMA_channel='DMA1 channel2 / DMAMUX1 channel1, USART1_RX',native_DMA_ring_bytes=128,
  native_RX_IRQ_priority=3,motor_IRQ_priorities_unchanged=True,native_RX_FIFO=True,Uno_RX_FIFO=True,
  Uno_vendor_ISR_not_called=True,Uno_KERNEL_ASYNC_DMA_API_not_enabled=True,
  native_TX_DMA_and_UART_TC_completion_guard_unchanged=True,
  RX_error_policy='DMA cannot attribute NE per byte, so all hardware NE/PE/FE/ORE are fatal; Uno loss latches until boot',
  native_DMA_wrap_and_copy_overlap_fail_closed=True,
  Nucleo_RAM_free_after_original_heap_stack_reserve_bytes=240,
  Nucleo_heap_reserve_bytes=512,Nucleo_stack_reserve_bytes=1024,
  Uno_RAM_static_bytes=219174,Uno_RAM_remaining_bytes=42970,Uno_compiler_low_memory_warning=True,
  ARM_fast_and_EKF_byte_identical=True,target_timing_measured=False,UART_hardware_qualified=False,
  physical_NIS_root_cause_fixed=False,prior_file_hashes_verified=[len(preserved),len(previous),len(oldest)],
  native_HEX_erased_padding_offsets=holes,
  artifacts={f.relative_to(p.OUT).as_posix():p.sha(f) for f in release.iterdir() if f.is_file()},
  actual_installed_pair_still=[2026111803,2026111804],
  next_validation='After separately authorized programming: independent readback, FIFO/DMA register proof, quiet and loaded UART OFF, OFF DWT CPU; no automatic motor run')
 p.write(p.OUT/'release_manifest.json',json.dumps(report,indent=2)+'\n')
 files={f.relative_to(p.OUT).as_posix():p.sha(f) for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi') for f in (p.OUT/folder).rglob('*') if f.is_file() and '__pycache__' not in f.parts}
 p.write(p.OUT/'source_hashes.json',json.dumps(files,indent=2)+'\n')
 print(json.dumps(dict(prepared=True,pair=p.NEW,built=True,installed=False,hardware_commands=0,prior_hashes_verified=report['prior_file_hashes_verified'],UART_hardware_qualified=False)))
if __name__=='__main__':main()
