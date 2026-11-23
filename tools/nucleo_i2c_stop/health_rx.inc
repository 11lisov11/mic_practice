      if(buf[2]==EH_WIRE){
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&(g_bp_status&0x22U)==0U&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)eh_receive(&g_encoder_health,buf,g_bp_fw_build,off,now);continue;
      }
