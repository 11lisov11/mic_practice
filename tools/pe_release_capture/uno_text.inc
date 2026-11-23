    s += " enc_release_good=";s += String((unsigned long)g_release_capture.good);
    s += " enc_release_bad=";s += String((unsigned long)g_release_capture.bad);
    for(unsigned slot=0;slot<2;slot++){
      s += slot==0?" enc_release_first_hex=":" enc_release_pwm_hex=";
      const pr_slot*rec=&g_release_capture.slot[slot];const fc_slot*parent=&g_i2c_fault.slot[slot];
      if(!pr_linked(rec,parent->bytes,parent->crc,parent->valid))s += "-";
      else for(unsigned i=0;i<PR_BYTES;i++){const char*hex="0123456789abcdef";uint8_t v=rec->bytes[i];s += hex[v>>4];s += hex[v&15];}
    }
