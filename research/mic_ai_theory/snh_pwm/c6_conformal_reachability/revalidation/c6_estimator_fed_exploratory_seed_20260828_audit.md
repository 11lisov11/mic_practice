# Estimator-fed C6-BCR exploratory replay audit

- Exploratory audit pass: `true`
- Host method evidence pass: `false`
- Coverage inference claim: `false`
- Hardware ready: `false`
- Protocol SHA-256: `ef0a7f2d18672860f69aaa3cb7e39dfa1faa11ca98f8589e4456fe783b402adc`
- Median estimated-sector accuracy: `0.973875`
- Median estimator C6 coverage, descriptive: `0.955000`
- Median estimator/oracle volume ratio: `6.73168e+06`
- Median estimator C6/raw volume ratio: `0.824788`
- Test flux clip events: `0`
- Median stator-flux RMSE alpha/beta: `0.00859501` / `0.00828886` Wb
- Median rotor-flux RMSE alpha/beta: `0.00890466` / `0.00857704` Wb
- Median speed RMSE: `0.268117` rad/s

## Checks

- [x] `protocol_manifest_and_source_hash_recomputed`
- [x] `deterministic_full_payload_replay_pass`
- [x] `estimator_inputs_exclude_true_flux`
- [x] `true_state_is_simulation_target_only`
- [x] `estimator_sector_accuracy_is_finite`
- [x] `no_test_flux_clip_events`
- [x] `bulk_coverage_is_not_claimed_as_inference`
- [x] `method_pass_is_not_auto_claimed`
- [x] `scientific_novelty_is_not_claimed`
- [x] `hardware_readiness_is_not_claimed`

Boundary: deterministically replayed estimator-fed host exploration; coverage remains descriptive and no independent-probe, hardware-estimator, recursive-safety, or novelty claim is made
