# Embedded in the prepared HMI; explicit component transfer, not a new PWM capture.
RX_SNAPSHOT_TRIAL_PAIR = (2026101104, 2026101102)
RX_SNAPSHOT_TRIAL_IMAGES = {
    "production_uno": "987a869e146e115ba9f526bf991e50cd461095f0c9448263f5502071b964e15f",
    "production_nucleo": "d17b1ed8313b7e355e66681f90beaf84e7535e22504212f79ef44ce2bad5d37c",
}
RX_SNAPSHOT_SCHEMA = "mic_ai.powered_trial.rx_snapshot_delta.v1"


def validate_rx_snapshot_trial(proof):
    if (proof.get("pair") != list(RX_SNAPSHOT_TRIAL_PAIR)
            or any(type(x) is not int for x in proof["pair"])
            or proof.get("images") != RX_SNAPSHOT_TRIAL_IMAGES
            or proof.get("profile") != "short"
            or proof.get("scope") != "pwm_component_transfer_with_rx_and_snapshot_delta"
            or proof.get("pwm_evidence_pair") != list(UART_V3_TRIAL_PAIR)
            or proof.get("pwm_evidence_images") != UART_V3_TRIAL_IMAGES):
        return False, "RX snapshot component identity/scope mismatch"
    for key in ("pwm_core_equivalence_pass", "break_irq_delta_audited", "calibration_contract_pass",
                "images_verified", "offline_pass", "idle_wifi_pass", "physical_idle_pass"):
        if proof.get(key) is not True:
            return False, "RX snapshot qualification missing: " + key
    if (proof.get("new_pair_active_pwm_measured") is not False
            or proof.get("hv_release_approved") is not False
            or proof.get("current_telemetry_qualified") is not False
            or type(proof.get("max_run_s")) is not int or proof["max_run_s"] != 3
            or type(proof.get("max_frequency_hz")) is not int or proof["max_frequency_hz"] != 5):
        return False, "RX snapshot trial must be explicitly limited to 5 Hz / 3 s"
    cases = proof.get("cases")
    if (not isinstance(cases, dict) or set(cases) != set(UART_V3_TRIAL_CASES)
            or any(x is not True for x in cases.values())):
        return False, "retained baseline PWM scenario evidence missing"
    if type(proof.get("offline_suites")) is not int or proof["offline_suites"] < 51:
        return False, "RX snapshot trial regression missing"
    hashes = proof.get("evidence_sha256")
    required = {"pwm", "physical_idle", "delta_audit", "uno_install", "nucleo_install", "offline", "idle_wifi"}
    if (not isinstance(hashes, dict) or set(hashes) != required
            or any(not isinstance(x, str) or len(x) != 64 or any(c not in "0123456789abcdef" for c in x)
                   for x in hashes.values())):
        return False, "RX snapshot evidence fingerprints missing"
    issued, expires = proof.get("issued_at"), proof.get("expires_at")
    if (type(issued) not in (int, float) or type(expires) not in (int, float)
            or not math.isfinite(issued) or not math.isfinite(expires)
            or not 0 < expires-issued <= 600 or not issued <= time.time() < expires):
        return False, "RX snapshot preparation expired"
    return True, "one 5-Hz / 3-second component-transfer trial only"
