    const bool health_off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&(g_bp_status&0x22U)==0U&&(uint32_t)(millis()-g_bp_last_rsp_ms)<300U;
    const bool health_valid=eh_fresh(&g_encoder_health,health_off,millis());
    s += " enc_diag_category_counts_available=";s += String(health_valid?1:0);
    static const char*health_names[]={"nack","deadline","busy","arlo","ovr","short","setup","berr_clears","clean_stops","forced_resets","stop_requests","cleanup_expired","normal_parks","cleanup_flags"};
    for(unsigned i=0;i<14;i++){s += " enc_health_";s += health_names[i];s += '=';s += String((unsigned long)(health_valid?g_encoder_health.values[i]:0));}
