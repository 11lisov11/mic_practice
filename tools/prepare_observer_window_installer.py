"""Prepare stopped-only1611/1612 installer/readback/OFF checks, no device access."""
import ast,json,shutil
import prepare_observer_current_window as p
from probe_native_programming_state import programmed_hex_image
from prepare_telemetry_deadline_installer import function
def main():
    source=p.read(p.ROOT/'tools/install_clear_recovery.py')
    source=source.replace('import prepare_clear_recovery as p','import prepare_observer_current_window as p')
    source=source.replace('Install sealed 2026111605/1606','Install sealed 2026111611/1612')
    source=source.replace('OLD=(2026111603,2026111604)','OLD=(2026111609,2026111606)')
    source=source.replace('_clear_recovery.hex','_observer_mean16.hex')
    source=source.replace('_clear_recovery.elf-zsk.bin','_observer_schema3.elf-zsk.bin')
    source=source.replace('mic_clear1606_','mic_window1612_').replace("'clear_1606_'","'window_1612_'")
    check='''def package_check():
 m=json.loads(p.read(p.OUT/'manifest.json'))
 assert m['built'] and m['pair']==list(NEW) and not m['installed']
 assert m['control_and_observer_Q_R_math_unchanged']
 assert (m['raw_trip_A'],m['ADC_UPDATE_limit_ticks'],m['OFF_fast_budget_cycles'],m['estimate_age_limit_ms'])==(1.35,2048,4000,2)
 assert m['RUN_existing_deadline_cycles']==5312
 for name in ('core','adapter','model'):
  assert json.loads(p.read(p.OUT/f'verification/{name}_report.json'))['passed']
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in json.loads(p.read(p.OUT/'installation_assets.json')).items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in json.loads(p.read(p.OUT/'preserved_all_hashes.json')).items():assert p.sha(p.ROOT/rel)==h,rel
 for rel in ('nucleo/Inc/motor_control.h','nucleo/Inc/foc_experiment.h','nucleo/Src/current_shunt.c','nucleo/Inc/current_adc_deadline.h'):
  assert p.sha(p.OUT/rel)==p.sha(p.BASE/rel),rel
 return m
'''
    source=source.replace(function(source,'package_check'),check)
    # Archive the old HMI-visible records before reprogramming resets MCU RAM.
    anchor="  p.write(out/'before.json',json.dumps(before,ensure_ascii=False,indent=2));r['before_pair']=list(OLD)"
    source=source.replace(anchor,anchor+'''
  for key,filename in (('mc_observer_trace_hex','observer_before.bin'),('mc_adc_peak_hex','ADC_before.bin')):
   value=before.get(key,'-')
   if value and value!='-':
    raw=bytes.fromhex(value);(out/filename).write_bytes(raw)
    r.setdefault('preserved_live_records',{})[filename]=p.sha(out/filename)
''')
    idle=p.read(p.ROOT/'tools/verify_clear_recovery_idle.py').replace('import prepare_clear_recovery as p','import prepare_observer_current_window as p')
    idle=idle.replace("p.OUT/'preserved_capture_hashes.json'","p.OUT/'preserved_all_hashes.json'")
    idle=idle.replace("fresh_link=rows[-1]['mc_good_cnt']>rows[0]['mc_good_cnt']", "fresh_link=rows[-1]['uno_rx_count']>rows[0]['uno_rx_count']")
    idle=idle.replace("        report['predecessor_OFF_cycles']=3618", "        report['predecessor_OFF_cycles']=3618\n        report['observer_mean16_forecast_in_OFF_probe']=True")
    for name,text in [('install_observer_current_window.py',source),('verify_observer_current_window_idle.py',idle)]:
        f=p.ROOT/'tools'/name;assert not f.exists();ast.parse(text);p.write(f,text)
    debug=p.OUT/'nucleo/STM32CubeIDE/Debug'
    assets={}
    for src,dst in [(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex',p.OUT/'release/nucleo_2026111612_observer_mean16.hex')]:
        assert not dst.exists();shutil.copy2(src,dst);assets[dst.relative_to(p.OUT).as_posix()]=p.sha(dst)
    image,holes=programmed_hex_image(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex',
        (p.OUT/'release/nucleo_2026111612_observer_mean16.bin').read_bytes())
    dst=p.OUT/'release/nucleo_2026111612_expected_readback.bin';assert not dst.exists();dst.write_bytes(image)
    assets[dst.relative_to(p.OUT).as_posix()]=p.sha(dst)
    p.write(p.OUT/'installation_assets.json',json.dumps(assets,indent=2)+'\n')
    print('Prepared safe-state/readback/OFF installers; no device access')
if __name__=='__main__':main()
