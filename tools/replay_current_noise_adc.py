"""Existing full ADC IRQ regression, with the new OFF-only diagnostic included."""
import current_adc_apex_fix_selftest as test
import prepare_standstill_current_noise as package
from collect_current_peak import decoder

def main():
 test.p.OUT=package.OUT
 test.irq_test.PREAMBLE='#include "multi_native.h"\n#include "uart_v3_transport.h"\n#include "noise_core.h"\nstatic void __DMB(){}\n'+test.irq_test.PREAMBLE
 test.previous.CASES=test.previous.CASES.replace('pending_pair==2?7U:1U','pending_pair>=2?7U:1U').replace(
  'pending_pair==0?7U:6U','(pending_pair==0||pending_pair==3)?7U:6U')
 test.previous.CASES=test.previous.CASES.replace('static void reset_test(){','static void reset_test(){nd_init(&idle_noise);')
 def candidate_decoder(folder):
  m=decoder(folder);old=m.decode_adc_peak_hex
  m.decode_adc_peak_hex=lambda value,expected_build=2026102940:old(value,expected_build)
  return m
 test.decoder=candidate_decoder
 test.main()

if __name__=='__main__':main()
