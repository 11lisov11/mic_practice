# Embedded into the HMI only with the exact reviewed retained evidence hashes.
LOCAL_STOP_FIXTURE_SCHEMA = "mic_ai.powered_trial.local_stop_fixture_delta.v1"
LOCAL_STOP_FIXTURE_PAIR = (2026101298, 2026101299)
LOCAL_STOP_FIXTURE_IMAGES = __LOCAL_STOP_FIXTURE_IMAGES__
LOCAL_STOP_RETAINED_EVIDENCE = __LOCAL_STOP_RETAINED_EVIDENCE__


def validate_local_stop_fixture_trial(proof):
    if not isinstance(proof, dict):
        return False, "local STOP fixture trial proof must be an object"
    if (proof.get("schema") != LOCAL_STOP_FIXTURE_SCHEMA
            or proof.get("pair") != list(BOOT_TRIAL_PAIR)
            or any(type(x) is not int for x in proof["pair"])
            or proof.get("images") != BOOT_TRIAL_IMAGES
            or proof.get("fixture_pair") != list(LOCAL_STOP_FIXTURE_PAIR)
            or any(type(x) is not int for x in proof["fixture_pair"])
            or proof.get("fixture_images") != LOCAL_STOP_FIXTURE_IMAGES
            or proof.get("profile") != "short"
            or proof.get("scope") != "local_stop_fixture_equivalence_one_powered_trial"):
        return False, "local STOP fixture trial identity/scope mismatch"
    for key in ("fixture_six_pwm_and_local_stop_pass", "fixture_stop_source_identical",
                "fixture_ten_code_sections_identical", "production_images_restored_verified",
                "production_idle_wifi_pass", "production_calibration_contract_pass",
                "retained_sd_sample_operator_reported", "offline_pass"):
        if proof.get(key) is not True:
            return False, "local STOP fixture trial evidence missing: " + key
    # A fixture capture must never be relabelled as an active production/HV test.
    for key in ("new_pair_active_pwm_measured", "physical_idle_registers_current",
                "exact_button_to_off_latency_measured", "forced_enable_hardware_validated",
                "hv_release_approved", "current_telemetry_qualified"):
        if proof.get(key) is not False:
            return False, "local STOP fixture trial overclaims: " + key
    for key, value in (("max_run_s", 3), ("max_frequency_hz", 5)):
        if type(proof.get(key)) is not int or proof[key] != value:
            return False, "local STOP fixture trial is limited to 5 Hz / 3 s"
    if type(proof.get("offline_suites")) is not int or proof["offline_suites"] < 57:
        return False, "local STOP fixture trial baseline regression missing"
    if proof.get("evidence_sha256") != LOCAL_STOP_RETAINED_EVIDENCE:
        return False, "local STOP fixture trial retained evidence changed"
    sample = proof.get("sd_sample_v")
    if type(sample) not in (int, float) or not math.isfinite(sample) or sample != 2.6:
        return False, "local STOP fixture trial retained SD sample mismatch"
    gap = proof.get("idle_tx_max_gap_us")
    if type(gap) is not int or not 0 < gap < 100000:
        return False, "local STOP fixture trial idle scheduling margin missing"
    issued, expires = proof.get("issued_at"), proof.get("expires_at")
    if (type(issued) not in (int, float) or type(expires) not in (int, float)
            or not math.isfinite(issued) or not math.isfinite(expires)
            or not 0 < expires-issued <= 600 or not issued <= time.time() < expires):
        return False, "local STOP fixture trial proof expired"
    return True, "one 5-Hz / 3-second trial from measured fixture and exact code equivalence"
