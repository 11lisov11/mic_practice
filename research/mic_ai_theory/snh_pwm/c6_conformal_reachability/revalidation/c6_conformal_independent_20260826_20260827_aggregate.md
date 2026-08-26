# C6-BCR confirmatory replication audit

- Replication pass: `false`
- Scientific novelty auto-claimed: `false`
- World novelty established: `false`
- Hardware ready: `false`
- Root seeds: `[20260826, 20260827]`
- Total repetitions: `48`
- Descriptive aggregate held-out coverage: `0.950495`
- Target coverage: `0.950000`
- Aggregate independent coverage probes: `759/800`
- Aggregate independent-probe coverage: `0.948750`
- Aggregate independent-probe undercoverage p-value: `0.458068`
- Aggregate independent-probe exact 99% lower bound: `0.927645`
- Coverage non-inferiority threshold: `0.920000`
- Aggregate OOD coverage: `0.522917`
- Median C6/raw 5D hypervolume ratio: `0.784784`
- C6 >=10% sharpness wins: `40/48`
- Paired 10% sign-test p-value: `1.65263e-06`

## Checks

- [x] `at_least_two_confirmatory_series`
- [ ] `all_individual_host_method_audits_pass`
- [x] `root_seeds_are_unique`
- [x] `root_seeds_are_disjoint_from_all_generation_streams`
- [x] `all_split_seeds_are_unique_across_series`
- [x] `all_independent_probe_seeds_are_unique_across_series`
- [x] `protocol_is_identical_across_series`
- [x] `protocol_source_hash_is_identical_across_series`
- [x] `at_least_48_total_repetitions`
- [x] `at_least_800_total_independent_coverage_probes`
- [x] `aggregate_independent_probe_coverage_noninferiority_lcb99`
- [x] `aggregate_median_hypervolume_reduction_at_least_10pct`
- [x] `aggregate_paired_10pct_sharpness_sign_test_below_5pct`

## Claim boundary

exact lower-tail coverage inference uses only independent calibration/test probes; pooled bulk held-out and OOD trajectories remain descriptive; this host replay does not establish preregistration, scientific novelty, estimator-fed validity, recursive coverage, or hardware safety
