#include <cassert>
#include "C:/mic_practice/artifacts/live_bench_20261014/pwm_filter_pair_r5/fixture/UNOQ_MOTOR/nucleo_fault_diagnostics.h"

int main() {
 uint8_t reply[42]={}; reply[11]=0x98; reply[15]=4;
 assert(decode_nucleo_fault_diagnostics(reply,true,2026101495).valid);
 assert(decode_nucleo_fault_diagnostics(reply,true,2026101495).current_faults==4);
 assert(decode_nucleo_fault_diagnostics(reply,true,2026101408).valid);
 assert(!decode_nucleo_fault_diagnostics(reply,true,2026101297).valid);
 assert(!decode_nucleo_fault_diagnostics(reply,false,2026101495).valid);
}
