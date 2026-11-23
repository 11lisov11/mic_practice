"""Compile actual candidate ADC IRQ, epoch guards and original archived raw frames."""
import shutil
import current_adc_apex_fix_selftest as test
from collect_current_peak import decoder
from prepare_multi_algorithm import OUT
def main():
    test.p.OUT=OUT
    test.irq_test.PREAMBLE='#include "multi_native.h"\nstatic void __DMB(){}\n'+test.irq_test.PREAMBLE
    def new_decoder(candidate):
        m=decoder(candidate);original=m.decode_adc_peak_hex
        m.decode_adc_peak_hex=lambda value,expected_build=2026102922:original(value,expected_build)
        return m
    test.decoder=new_decoder
    log=OUT/'apex_selftest_r1/build.log'
    if log.exists() and 'error:' in log.read_text():shutil.copy2(log,log.with_name('compile_failed_attempt1.log'))
    test.main()
if __name__=='__main__':main()
