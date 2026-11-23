#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
#include "C:/mic_practice/artifacts/live_bench_20261014/pwm_filter_pair_r4/fixture/UNOQ_MOTOR/break_wire.h"

int main(){
 bw_receiver rx{};uint8_t record[BW_BYTES]={},packet[UV3_FRAME];
 bw_packet(packet,record,0,0);
 assert(uv3_crc_ok(packet));
 assert(!bw_receive(&rx,packet,BW_NUCLEO_BUILD,false,100));
 assert(rx.bad_pages==1 && rx.good_pages==0 && !rx.complete[0]);
 assert(bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,150));
 assert(rx.bad_pages==1 && rx.good_pages==1);
 for(unsigned page=1;page<BW_PAGES;++page){
  bw_packet(packet,record,0,page);assert(bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,150+page));
 }
 assert(rx.complete[0] && rx.bad_pages==1);
 std::puts("CRC-valid page rejected while fresh-off predicate false; later accepted without changing policy");
}
