"""Run actual record builders/arm adapter and wire receivers against register stubs."""
import json,subprocess,sys,importlib.util,hashlib
from pathlib import Path
import prepare_repeat_break_capture as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function

def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
 main=p.read(p.OUT/'nucleo/Src/main.c');fixture=p.read(p.SOURCE/'host_fixture.cpp')
 actual='\n'.join(function(main,n) for n in ('mic_bkin_capture_start','mic_bkin_capture_trigger_from_break',
   'mic_bkin_put32','mic_bkin_prepare_record','mic_repeat_capture_arm','mic_repeat_break_irq'))
 code=fixture.replace('// ACTUAL_FUNCTIONS',actual)
 native=json.loads(common.compile_run(out,'repeat_native_wire',code))
 spec=importlib.util.spec_from_file_location('repeat_hmi_test',p.OUT/'web_hmi/server.py')
 h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
 kv=dict(bp_fw_build=str(p.NEW[1]),bp_age_ms='20',repeat_meta_hex=native['meta_hex'],repeat_meta_age_ms='20',
   mc_boot_packet_hex=native['boot_packet'],mc_boot_fresh='1',mc_break_wave_hex=native['first_wave'],
   mc_repeat_wave_hex=native['repeat_wave'],mc_repeat_wave_age_ms='20',mc_break2_hex=native['repeat_snapshot'],mc_break2_age_ms='20')
 checks=0
 good=h.repeat_capture_status(kv)['repeat_break']
 assert good['available'] and good['fresh'] and good['first_wave_preserved'] and good['records_coherent'] and good['complete_window'];checks+=1
 assert good['wave']['event_tick_ms']==2020 and good['snapshot']['raw']['tick_ms']==2020 and good['event_irq_count']==2;checks+=1
 for i in range(344):
  damaged=bytearray.fromhex(native['meta_hex']);damaged[i//8]^=1<<(i%8)
  assert not h.repeat_capture_status(dict(kv,repeat_meta_hex=damaged.hex()))['repeat_break']['available'];checks+=1
 stale=h.repeat_capture_status(dict(kv,repeat_meta_age_ms='2000'))['repeat_break']
 assert not stale['fresh'] and not stale['live_usable'];checks+=1
 assert not h.repeat_capture_status(dict(kv,mc_boot_fresh='0'))['repeat_break']['fresh'];checks+=1
 assert not h.repeat_capture_status(dict(kv,mc_boot_packet_hex='-'))['repeat_break']['fresh'];checks+=1
 assert not h.repeat_capture_status(dict(kv,mc_repeat_wave_hex='-'))['repeat_break']['records_coherent'];checks+=1
 assert not h.repeat_capture_status(dict(kv,mc_repeat_wave_hex=native['first_wave']))['repeat_break']['records_coherent'];checks+=1
 assert not h.repeat_capture_status(dict(kv,mc_break2_hex='-'))['repeat_break']['records_coherent'];checks+=1
 assert not h.repeat_capture_status(dict(kv,mc_break_wave_hex=native['repeat_wave']))['repeat_break']['first_wave_preserved'];checks+=1
 partial=bytearray.fromhex(native['repeat_wave']);partial[20:24]=(17).to_bytes(4,'little')
 incomplete=h.repeat_capture_status(dict(kv,mc_repeat_wave_hex=partial.hex()))['repeat_break']
 assert incomplete['records_coherent'] and not incomplete['complete_window'] and not incomplete['live_usable'];checks+=1
 assert 'неполное' in incomplete['summary_ru'];checks+=1
 # No control/protection/ADC code changed beyond the one diagnostic arm hook.
 oldmain=p.read(p.BASE/'nucleo/Src/main.c').replace('2026103014',str(p.NEW[1]))
 for name in ('MX_TIM1_Init','MX_ADC1_Init','MX_ADC2_Init','uno_handle_valid_frame','uno_clear_frame_is_safe','uno_stop_motor'):
  assert function(main,name)==function(oldmain,name),name;checks+=1
 assert function(main,'uno_rearm_break_irq').replace('  mic_repeat_capture_arm(HAL_GetTick());\n','')==function(oldmain,'uno_rearm_break_irq');checks+=1
 for name in ('multi_native.c','current_shunt.c','stm32g4xx_mc_it.c','pwm_curr_fdbk.c'):
  expected=p.read(p.BASE/'nucleo/Src'/name).replace('2026103014',str(p.NEW[1]))
  assert p.read(p.OUT/'nucleo/Src'/name)==expected,name;checks+=1
 for rel,hsh in json.loads(p.read(p.OUT/'preserved_capture_hashes.json')).items():assert p.sha(p.ROOT/rel)==hsh,rel
 subprocess.run(['node','--check',str(p.OUT/'web_hmi/static/app.js')],check=True,capture_output=True)
 report=dict(passed=True,native_checks=native['checks'],HMI_checks=checks,actual_arm_DMA_and_record_builders=True,
   first_snapshot_and_wave_immutable=True,second_slot_immutable=True,repeat_wave_separate_receiver=True,
   old_event_replay_does_not_become_repeat=True,CRC_bit_corruption_checks=1032,
   partial_and_stale_records_not_qualified=True,control_and_protection_functions_unchanged=True,
   hardware_commands=0,hardware_validated=False,
   limitation='Register stubs and host decoding do not validate electrical pulse timing or the physical TP23 wire.')
 p.write(out/'report.json',json.dumps(report,indent=2));p.write(out/'fixture_vectors.json',json.dumps(native,indent=2))
 print(json.dumps(report))
if __name__=='__main__':main()
