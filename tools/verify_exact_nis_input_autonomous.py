"""GET-only autonomous qualification1801/1802; no CLEAR/START/reset/SWD."""
import inspect,json
import prepare_exact_nis_input_release as p
import verify_telemetry_deadline_autonomous as prior


def capture_config_valid(manifest):
    receipt=json.loads(p.read(p.OUT/'installation_acceptance.json'))
    return (receipt['installed'] and receipt['pair']==list(p.NEW)
        and receipt['native_readback_verified'] and receipt['uno_readback_verified']
        and manifest['built'] and manifest['pair']==list(p.NEW)
        and manifest['capture_schema']==3 and manifest['observer_schema']==5
        and manifest['source_window_rows']==16 and manifest['voltage_history_rows']==25
        and manifest['raw_ring_rows']==60 and manifest['OFF_fast_limit_cycles']==4000
        and manifest['estimate_age_ms']==2 and manifest['protections_and_limits_unchanged'])


def main():
    src=inspect.getsource(prior.main)
    old="manifest['installed'] and manifest['pair'] == list(p.NEW) and manifest['diagnostic_ADC_first_NIS_loss_trigger'] and manifest['OFF_bulk_round_robin'] and manifest['CPU_probe_budget_cycles'] == 4000 and manifest['estimate_limit_ms'] == 2"
    assert old in src;src=src.replace(old,'capture_config_valid(manifest)')
    old="p.OUT/'preserved_capture_hashes.json'"
    assert old in src;src=src.replace(old,"p.OUT/'preserved_inputs_sha256.json'")
    scope=dict(prior.__dict__,p=p,capture_config_valid=capture_config_valid)
    exec(compile(src,__file__,'exec'),scope)
    return scope['main']()


if __name__=='__main__':raise SystemExit(main())
