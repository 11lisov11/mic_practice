
#include <cassert>
#include <cstdio>
#include <cstring>
#include "nucleo_fault_diagnostics.h"
#include "break_wire.h"
int main() {
 unsigned checks=0;
 auto check=[&](bool v){++checks;assert(v);};
 uint8_t reply[UV3_FRAME]={}; reply[11]=0x94;reply[13]=10;
 reply[15]=4;reply[27]=4;
 auto d=decode_nucleo_fault_diagnostics(reply,true,2026101204);
 check(d.valid && d.reason==4 && d.current_faults==4 && d.occurred_faults==4);
 check(!decode_nucleo_fault_diagnostics(reply,true,2026101205).valid);
 check(!decode_nucleo_fault_diagnostics(reply,false,2026101204).valid);
 reply[11]=0x9f;check(!decode_nucleo_fault_diagnostics(reply,true,2026101204).valid);
 reply[11]=0x98;d=decode_nucleo_fault_diagnostics(reply,true,2026101204);
 check(d.valid && d.reason==8);
 uint8_t record[BW_BYTES]={},packet[UV3_FRAME];bw_receiver rx{};
 check(BW_NUCLEO_BUILD==2026101204);
 for(unsigned p=0;p<BW_PAGES;++p) {
   bw_packet(packet,record,0,p);
   check(bw_u32(packet+6)==2026101204);
   check(bw_receive(&rx,packet,2026101204,true,p));
 }
 check(rx.complete[0] && rx.good_pages==4 && rx.bad_pages==0);
 check(!bw_receive(&rx,packet,2026101102,true,10));
 check(!bw_receive(&rx,packet,2026101204,false,10));
 std::printf("checks=%u\n",checks);
}
