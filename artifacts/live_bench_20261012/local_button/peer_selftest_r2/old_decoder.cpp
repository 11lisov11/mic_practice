#include "nucleo_fault_diagnostics.h"
int main(){uint8_t p[39]={};p[11]=0x94;return decode_nucleo_fault_diagnostics(p,true,2026101204).valid?1:0;}
