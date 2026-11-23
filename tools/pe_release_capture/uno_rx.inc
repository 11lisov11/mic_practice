      if(buf[2]==PR_WIRE){
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&!(g_bp_status&0x22U)&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)pr_receive(&g_release_capture,buf,g_bp_fw_build,off);continue;
      }
