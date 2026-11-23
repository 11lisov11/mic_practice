"""1803/1804 OFF-only readback, actual UART921600 and DWT qualification.

No START/CLEAR/ARM/RESET/flash. Reads UART configuration, no RDR/clear registers.
"""
import sys,types
import prepare_start_history_release as p

def source():
 s=p.read(p.ROOT/'tools/verify_exact_nis_input_idle.py')
 a='import prepare_exact_nis_input_release as p';assert a in s;s=s.replace(a,'import prepare_start_history_release as p')
 a="p.OUT/f'release/nucleo_{p.NEW[1]}_expected_readback.bin'"
 assert a in s;s=s.replace(a,"p.OUT/f'installation_recipe_r1/release/nucleo_{p.NEW[1]}_expected_readback.bin'")
 a="p.OUT/f'release/nucleo_{p.NEW[1]}_exact_source.elf'"
 assert a in s;s=s.replace(a,"p.OUT/f'installation_recipe_r1/release/nucleo_{p.NEW[1]}_start_history.elf'")
 a="            gpio=struct.unpack('<I',read(0x48000010,4,f'GPIOA_IDR_{i}'))[0]"
 assert a in s;s=s.replace(a,a+"\n            uart_brr=struct.unpack('<I',read(0x4001380c,4,f'USART1_BRR_{i}'))[0]\n            uart_baud=struct.unpack('<I',read(symbols['huart1']+4,4,f'UART1_Init_Baud_{i}'))[0]\n            assert uart_brr==184 and uart_baud==921600,'921600 UART not configured'")
 a="                clear_record_empty=val('mic_clear_diag_ready','<B')==0)"
 assert a in s;s=s.replace(a,"                clear_record_empty=val('mic_clear_diag_ready','<B')==0,\n                UART_BRR=uart_brr,UART_configured_baud=uart_baud,\n                start_history_empty=not any(ram[symbols['observer_history']-0x20000000:symbols['observer_history']-0x20000000+sizes['observer_history']]))")
 a="            assert not row['fe_trial_done'] and row['recorder_empty'] and row['clear_record_empty']"
 assert a in s;s=s.replace(a,a+" and row['start_history_empty']")
 a="        r.update(passed=True,samples=len(statuses),RPC_guard=guard.snapshot(),ordinary_telemetry_fresh=fresh,"
 assert a in s;s=s.replace(a,"        r.update(passed=True,UART921600_qualified=True,UART_qualification_scope='BRR184 + Init921600 + independently verified Uno image + fresh bidirectional replies; full-rate journal not exercised',\n            start_history_empty=True,samples=len(statuses),RPC_guard=guard.snapshot(),ordinary_telemetry_fresh=fresh,")
 a='    print(json.dumps(r,ensure_ascii=True))'
 assert a in s;s=s.replace(a,"    print(json.dumps({k:r.get(k) for k in ('passed','error','fast_cycles','CPU_qualified','UART921600_qualified','zero_ready','SD','START','CLEAR','ARM','RESET')},ensure_ascii=True))")
 s=s.replace("if __name__=='__main__':raise SystemExit(main())",'')
 return s

def main():
 s=source();code=compile(s,__file__,'exec')
 if '--verify-only' in sys.argv:
  print('OFF qualification recipe verified; no hardware access');return 0
 module=types.ModuleType('start_history_OFF_verifier');module.__file__=__file__
 exec(code,module.__dict__);return module.main()
if __name__=='__main__':raise SystemExit(main())
