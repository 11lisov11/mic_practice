"""1809/1810 GET-only powerbank readiness. No START/CLEAR/reset/SWD."""
import inspect,json
import prepare_boot_stack_integrity as p
import verify_telemetry_deadline_autonomous as prior

def capture_config_valid(m):
 r=json.loads(p.read(p.OUT/'installation_acceptance.json'))
 assert r['installed'] and r['native_readback_verified'] and r['uno_readback_verified']
 assert r['runtime_idle_verified'] and r['OFF_timing_qualified']
 assert (m['pair'],r['pair'])==(list(p.NEW),list(p.NEW))
 assert (m['OFF_fast_limit_cycles'],m['estimate_age_ms'],m['raw_current_trip_A'],m['ADC_UPDATE_ticks'])==(4000,2,1.35,2048)
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
 assert m['capture_capacities_unchanged'] and m['scheduler_unchanged_and_tested']
 return m['built'] and m['offline_acceptance_passed']

def main():
 src=inspect.getsource(prior.main)
 a="manifest['installed'] and manifest['pair'] == list(p.NEW) and manifest['diagnostic_ADC_first_NIS_loss_trigger'] and manifest['OFF_bulk_round_robin'] and manifest['CPU_probe_budget_cycles'] == 4000 and manifest['estimate_limit_ms'] == 2"
 assert a in src;src=src.replace(a,'capture_config_valid(manifest)')
 src=src.replace("p.OUT/'manifest.json'","p.OUT/'release_manifest.json'")
 src=src.replace("p.OUT/'preserved_capture_hashes.json'","p.OUT/'preserved_inputs_sha256.json'")
 src=src.replace("rows[-1]['mc_good_cnt'] > rows[0]['mc_good_cnt']","rows[-1]['uno_rx_count'] > rows[0]['uno_rx_count']")
 src=src.replace("good_frame_increase=rows[-1]['mc_good_cnt']-rows[0]['mc_good_cnt']","good_frame_increase=rows[-1]['uno_rx_count']-rows[0]['uno_rx_count']")
 a="check('boot_records_fresh', all(s['native_boot'].get('fresh') and s['repeat_break'].get('fresh') for s in rows))"
 assert a in src;src=src.replace(a,a+"\n        check('boot_Break_epoch_matches', all(s['repeat_break'].get('epoch_matches') for s in rows))")
 scope=dict(prior.__dict__,p=p,capture_config_valid=capture_config_valid)
 exec(compile(src,__file__,'exec'),scope);return scope['main']()

if __name__=='__main__':raise SystemExit(main())
