# Embedded only in the reviewed HMI for the installed 1108/1102 pair.
BOOT_TRIAL_PAIR = (2026101108, 2026101102)
BOOT_TRIAL_IMAGES = __BOOT_TRIAL_IMAGES__
BOOT_TRIAL_SCHEMA = "mic_ai.powered_trial.unoq1108.v1"
BOOT_TRIAL_EVIDENCE = {
    "pwm", "source_audit", "uno_install", "nucleo_install", "offline",
    "idle_wifi", "autonomous", "sd_sample", "calibration",
}


def validate_boot_trial(proof):
    if not isinstance(proof, dict):
        return False, "boot trial proof must be an object"
    if (proof.get("schema") != BOOT_TRIAL_SCHEMA
            or proof.get("pair") != list(BOOT_TRIAL_PAIR)
            or any(type(x) is not int for x in proof["pair"])
            or proof.get("images") != BOOT_TRIAL_IMAGES
            or proof.get("profile") != "short"
            or proof.get("scope") != "unchanged_nucleo_pwm_with_supervisory_boot_fix"):
        return False, "boot trial identity/scope mismatch"
    for key in ("nucleo_pwm_equivalence_pass", "calibration_contract_pass",
                "images_verified", "offline_pass", "idle_wifi_pass",
                "autonomous_boot_pass", "prestart_break_context_pass",
                "sd_sample_operator_reported"):
        if proof.get(key) is not True:
            return False, "boot trial evidence missing: " + key
    for key in ("new_pair_active_pwm_measured", "physical_idle_registers_current",
                "hv_release_approved", "current_telemetry_qualified"):
        if proof.get(key) is not False:
            return False, "boot trial must retain its unmeasured limits: " + key
    for key, expected in (("max_run_s", 3), ("max_frequency_hz", 5)):
        if type(proof.get(key)) is not int or proof[key] != expected:
            return False, "boot trial is limited to 5 Hz / 3 seconds"
    if type(proof.get("offline_suites")) is not int or proof["offline_suites"] < 57:
        return False, "boot trial regression missing"
    sample = proof.get("sd_sample_v")
    # Static operator sample, not a claim of pulse-free SD or live GPIO readback.
    # DS12589 Table 53: VIH=0.7*VDD; use maximum normal VDD=3.6 V.
    if type(sample) not in (int, float) or not math.isfinite(sample) or not 2.52 < sample <= 3.6:
        return False, "static SD sample does not meet the bounded HIGH assumption"
    gap = proof.get("idle_tx_max_gap_us")
    if type(gap) is not int or not 0 < gap < 100000:
        return False, "idle supervisory scheduling margin not demonstrated"
    evidence = proof.get("evidence_sha256")
    if (not isinstance(evidence, dict) or set(evidence) != BOOT_TRIAL_EVIDENCE
            or any(not isinstance(x, str) or len(x) != 64 or any(c not in "0123456789abcdef" for c in x)
                   for x in evidence.values())):
        return False, "boot trial evidence fingerprints missing"
    issued, expires = proof.get("issued_at"), proof.get("expires_at")
    if (type(issued) not in (int, float) or type(expires) not in (int, float)
            or not math.isfinite(issued) or not math.isfinite(expires)
            or not 0 < expires-issued <= 600 or not issued <= time.time() < expires):
        return False, "boot trial qualification expired"
    return True, "one conditional 5-Hz / 3-second trial; not general powered release"
