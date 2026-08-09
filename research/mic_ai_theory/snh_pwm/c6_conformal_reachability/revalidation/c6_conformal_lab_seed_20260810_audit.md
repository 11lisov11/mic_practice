# Independent C6 conformal reachability audit

- Defensible scientific novelty candidate: `true`
- World novelty established: `false`
- Hardware ready: `false`
- Repetitions: `24`
- Held-out coverage: `0.949740` (target `0.950000`)
- Undercoverage p-value: `0.438859`
- OOD coverage: `0.547917`
- Median C6/raw 5D hypervolume ratio: `0.707827`
- Paired sign-test p-value: `1.7941e-05`

## Checks

- [x] `raw_rows_well_formed`
- [x] `protocol_has_at_least_24_repetitions`
- [x] `protocol_has_independent_training_split`
- [x] `protocol_has_at_least_400_calibration_blocks`
- [x] `protocol_has_at_least_800_test_blocks`
- [x] `protocol_scores_at_least_40_switching_steps`
- [x] `all_split_seeds_are_globally_unique`
- [x] `finite_sample_rank_recomputed`
- [x] `c6_equivariance_recomputed`
- [x] `pooled_coverage_not_significantly_below_target_1pct`
- [x] `median_hypervolume_reduction_at_least_10pct`
- [x] `paired_sharpness_sign_test_below_5pct`
- [x] `ood_exchangeability_limit_exposed`
- [x] `world_novelty_not_overclaimed`
- [x] `hardware_safety_not_claimed`

## Claim boundary

candidate method and finite-sample marginal block-coverage result in a host mathematical model; not an exhaustive priority search, recursive guarantee, OOD guarantee, or hardware validation
