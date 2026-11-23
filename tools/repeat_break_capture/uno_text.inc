  s += " repeat_meta_hex=";
  if(g_repeat_meta_valid){for(unsigned i=0;i<UV3_FRAME;++i){
    s+=break_hex[g_repeat_meta[i]>>4];s+=break_hex[g_repeat_meta[i]&15];}}
  else s+="-";
  s+=" repeat_meta_age_ms=";s+=String((unsigned long)(g_repeat_meta_valid?(uint32_t)(millis()-g_repeat_meta_ms):999999U));
  s+=" mc_repeat_wave_hex=";
  if(g_repeat_wave.complete){for(unsigned i=0;i<RPW_RECORD_BYTES;++i){
    s+=break_hex[g_repeat_wave.data[i]>>4];s+=break_hex[g_repeat_wave.data[i]&15];}}
  else s+="-";
  s+=" mc_repeat_wave_age_ms=";s+=String((unsigned long)(g_repeat_wave.complete?(uint32_t)(millis()-g_repeat_wave.received_ms):999999U));
  s+=" mc_repeat_wave_good=";s+=String((unsigned long)g_repeat_wave.good_pages);
  s+=" mc_repeat_wave_bad=";s+=String((unsigned long)g_repeat_wave.bad_pages);
