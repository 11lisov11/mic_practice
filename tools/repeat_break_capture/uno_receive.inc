      if(buf[2]==RPW_VERSION || buf[2]==RPM_VERSION){
        const uint32_t observed_ms=millis();
        const bool fresh_off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&
          !(g_bp_status&0x22U)&&(uint32_t)(observed_ms-g_bp_last_rsp_ms)<300U;
        if(buf[2]==RPW_VERSION){
          (void)rpw_receive(&g_repeat_wave,buf,g_bp_fw_build,fresh_off,observed_ms);
        }else if(rpm_valid(buf,g_bp_fw_build,fresh_off)){
          memcpy(g_repeat_meta,buf,UV3_FRAME);g_repeat_meta_ms=observed_ms;g_repeat_meta_valid=true;
        }
        continue;
      }
