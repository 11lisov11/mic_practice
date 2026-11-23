  s += " mc_break_rx_good="; s += String((unsigned long)g_break_wire.good_pages);
  s += " mc_break_rx_bad="; s += String((unsigned long)g_break_wire.bad_pages);
  static const char break_hex[] = "0123456789abcdef";
  for (unsigned kind=0;kind<2;++kind) {
    s += kind == 0 ? " mc_break0_hex=" : " mc_break1_hex=";
    if (g_break_wire.complete[kind]) {
      for (unsigned i=0;i<BW_BYTES;++i) {
        const uint8_t byte=g_break_wire.data[kind][i];
        s += break_hex[byte>>4]; s += break_hex[byte&15];
      }
    } else s += "-";
    s += kind == 0 ? " mc_break0_age_ms=" : " mc_break1_age_ms=";
    s += String((unsigned long)(g_break_wire.complete[kind] ?
        (uint32_t)(millis()-g_break_wire.received_ms[kind]) : 999999U));
  }
