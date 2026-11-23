void mic_encoder_health_snapshot(uint32_t*v){
  v[0]=enc.primary_nack;v[1]=enc.timeouts;v[2]=enc.primary_busy;v[3]=enc.primary_arlo;
  v[4]=enc.primary_ovr;v[5]=enc.primary_short;v[6]=enc.primary_setup;v[7]=enc.berr_clears;
  v[8]=enc.clean_stops;v[9]=enc.forced_resets;v[10]=enc.stop_requests;
  v[11]=enc.cleanup_expired;v[12]=enc.parks;v[13]=enc.cleanup_flags;
}
