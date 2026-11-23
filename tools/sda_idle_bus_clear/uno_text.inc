    s += " enc_bus_clear_hex=";
    if(g_bus_clear_seen && g_bp_fw_build==EW_PEER){for(unsigned i=0;i<UV3_FRAME;i++){char h[3];snprintf(h,sizeof(h),"%02x",g_bus_clear[i]);s+=h;}}
    else s+='-';
