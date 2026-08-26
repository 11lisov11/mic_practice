# Independent C6 conformal reachability audit

- Host method evidence pass: `false`
- Scientific novelty auto-claimed: `false`
- World novelty established: `false`
- Hardware ready: `false`
- Repetitions: `24`
- Descriptive bulk held-out coverage: `0.949844`
- Independent coverage probes: `380/400`
- Independent-probe coverage: `0.950000` (target `0.950000`)
- Independent-probe undercoverage p-value: `0.53203`
- Independent-probe exact 99% lower bound: `0.918599`
- Coverage non-inferiority threshold: `0.920000`
- OOD coverage: `0.524167`
- Median C6/raw 5D hypervolume ratio: `0.793302`
- Paired 10% sharpness sign-test p-value: `0.00077194`

## Checks

- [x] `raw_rows_well_formed`
- [x] `protocol_alpha_is_finite_and_in_open_unit_interval`
- [x] `protocol_has_at_least_24_repetitions`
- [x] `protocol_has_independent_training_split`
- [x] `protocol_has_at_least_400_calibration_blocks`
- [x] `protocol_has_at_least_800_test_blocks`
- [x] `protocol_has_at_least_400_independent_coverage_probes`
- [x] `protocol_has_valid_coverage_noninferiority_margin`
- [x] `protocol_has_valid_coverage_error_probability`
- [x] `protocol_has_10pct_sharpness_threshold`
- [x] `protocol_scores_at_least_40_switching_steps`
- [x] `bulk_split_seeds_are_globally_unique`
- [x] `independent_probe_rows_well_formed`
- [x] `independent_probe_seed_streams_are_globally_unique`
- [x] `finite_sample_rank_recomputed`
- [x] `independent_probe_finite_sample_rank_recomputed`
- [x] `protocol_manifest_and_source_hash_recomputed`
- [x] `deterministic_experiment_replay_pass`
- [x] `c6_equivariance_reported_pass`
- [ ] `independent_probe_coverage_noninferiority_lcb99`
- [x] `median_hypervolume_reduction_at_least_10pct`
- [x] `paired_10pct_sharpness_sign_test_below_5pct`
- [x] `world_novelty_not_overclaimed`
- [x] `scientific_novelty_not_auto_claimed`
- [x] `preregistration_not_auto_claimed`
- [x] `oracle_state_assumption_explicit`
- [x] `hardware_safety_not_claimed`

## Claim boundary

candidate method and finite-sample marginal block-coverage result from independent calibration/test pairs in a one-step oracle-state host model; bulk held-out and OOD coverage are descriptive; the software audit does not establish preregistration, scientific novelty, recursive coverage, estimator-fed validity, or hardware validation
