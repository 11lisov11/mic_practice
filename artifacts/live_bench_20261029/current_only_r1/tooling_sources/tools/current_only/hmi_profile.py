# Inserted in the frozen HMI server; historical decoders remain available.
def with_current_only_profile(data):
    if (data.get('fw_build'), data.get('mc_fw_build')) != (2026102901, 2026102902):
        return data
    data.update(research_profile='air56b2_current_only', configured_load_condition='unloaded',
                enc_source='disabled', enc_enabled=0, enc_ok=0, enc_speed_ok=0,
                enc_bus_ok=0, enc_rpm=None, enc_deg=None, enc_raw=None,
                speed_measured_rpm=None, speed_estimated_rpm=None,
                speed_estimate_valid=0, speed_source='unavailable',
                ai_control_enabled=False, rotation_labels_available=False)
    # Frequency is the electrical field reference, never a measured rotor speed.
    data['field_frequency_hz'] = (data.get('mc_frequency_reference_hz')
                                 if data.get('mc_frequency_reference_valid') == 1 else None)
    return data
