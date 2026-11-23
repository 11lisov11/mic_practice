"""Replay the unchanged actual ADC IRQ in the timing-fix candidate."""
import current_adc_apex_fix_selftest as test
from collect_current_peak import decoder
from prepare_standstill_timing import OUT
def main():
 test.p.OUT=OUT
 test.irq_test.PREAMBLE='#include "multi_native.h"\nstatic void __DMB(){}\n'+test.irq_test.PREAMBLE
 def candidate_decoder(folder):
  m=decoder(folder);old=m.decode_adc_peak_hex
  m.decode_adc_peak_hex=lambda value,expected_build=2026102934:old(value,expected_build)
  return m
 test.decoder=candidate_decoder;test.main()
if __name__=='__main__':main()
