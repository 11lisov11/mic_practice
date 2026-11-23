  if(starts_ci(cmd,"IDENT ")){
    if(g_pwm_enabled||g_start_req||g_state!=STATE_SAFE)return false;
    unsigned index=0;unsigned long raw=0;char extra;
    if(sscanf(cmd+6,"PAGE %u %c",&index,&extra)==1){
      if(index>=13)return false;g_id_view_page=(uint8_t)index;return true;
    }
    if(g_ma_pending)return false;
    if(sscanf(cmd+6,"SET %u %lx %c",&index,&raw,&extra)==2){
      if(index>=15)return false;g_ma_op=4;g_ma_index=(uint8_t)index;g_ma_value=(uint32_t)raw;g_ma_pending=true;return true;
    }
    if(sscanf(cmd+6,"COMMIT %lx %c",&raw,&extra)==1){
      g_ma_op=5;g_ma_index=0;g_ma_value=(uint32_t)raw;g_ma_pending=true;g_id_execute_crc=0;return true;
    }
    if(sscanf(cmd+6,"ACK %lx %c",&raw,&extra)==1){
      g_ma_op=6;g_ma_index=0;g_ma_value=(uint32_t)raw;g_ma_pending=true;g_id_execute_crc=0;return true;
    }
    if(sscanf(cmd+6,"EXECUTE %lx %c",&raw,&extra)==1){
      if(!g_id_meta.seen||!(g_id_meta.flags&1U)||(g_id_meta.flags&14U)||
         (uint32_t)(millis()-g_id_meta.seen_ms)>1500U||raw!=g_id_meta.config_crc)return false;
      g_id_execute_crc=(uint32_t)raw;return true;
    }
    return false;
  }
