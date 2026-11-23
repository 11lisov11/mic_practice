    const bool id_fresh=g_id_meta.seen&&(uint32_t)(millis()-g_id_meta.seen_ms)<1500U;
    s += " id_valid=";s += String(id_fresh?1:0);
    s += " id_flags=";s += String((unsigned)g_id_meta.flags);
    s += " id_config_crc=";s += String((unsigned long)g_id_meta.config_crc);
    s += " id_result_crc=";s += String((unsigned long)g_id_meta.result_crc);
    s += " id_run_id=";s += String((unsigned long)g_id_meta.run_id);
    s += " id_kind=";s += String((unsigned long)g_id_meta.kind);
    s += " id_frequency=";s += String(g_id_meta.frequency,3);
    s += " id_duration_ms=";s += String((unsigned long)g_id_meta.duration_ms);
    s += " id_fault=";s += String((unsigned)g_id_meta.fault);
    s += " id_wire_good=";s += String((unsigned long)g_id_blob.good);
    s += " id_wire_bad=";s += String((unsigned long)g_id_blob.bad);
    const bool id_complete=id_fresh&&(g_id_meta.flags&4U)&&g_id_blob.complete&&g_id_blob.crc==g_id_meta.result_crc;
    s += " id_complete=";s += String(id_complete?1:0);
    s += " id_view_page=";s += String((unsigned)g_id_view_page);
    s += " id_page_hex=";
    if(id_complete){
      const char digits[]="0123456789abcdef";
      for(unsigned j=0;j<128;j++){uint8_t value=g_id_blob.bytes[128U*g_id_view_page+j];s+=digits[value>>4];s+=digits[value&15];}
    }else s += "-";
