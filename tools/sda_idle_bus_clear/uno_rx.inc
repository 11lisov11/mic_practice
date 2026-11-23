      if(buf[2]==0xde){
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&!(g_bp_status&0x22U)&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        if(bc_packet_valid(buf,g_bp_fw_build,off)){memcpy(g_bus_clear,buf,UV3_FRAME);g_bus_clear_seen=true;}
        continue;
      }
