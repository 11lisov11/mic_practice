
#include <cassert>
#include <cstdio>
#include <cstring>
#include "boot_wire.h"
static uint32_t rng=0x17382945U;
static uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
int main(){
 const uint32_t fw=2026103014U;unsigned checks=0;
 mb_record empty={},r=mb_next(&empty,fw,MB_BOR|(1U<<26));
 assert(mb_valid(&r,fw)&&r.sequence==1&&r.flags==0&&r.previous_csr==0);++checks;
 mb_confirm_clear(&r,0U);assert(r.flags==MB_CURRENT_CLEARED);++checks;
 auto warm=mb_next(&r,fw,1U<<26);
 assert(warm.sequence==2&&warm.flags==(MB_PREVIOUS_VALID|MB_PREVIOUS_CLEARED));++checks;
 assert(warm.previous_csr==r.csr&&warm.software_tag==0);++checks;
 mb_confirm_clear(&warm,0U);mb_note_software(&warm,MB_MCP_RESET);
 auto sw=mb_next(&warm,fw,MB_SOFTWARE|(1U<<26));
 assert(sw.sequence==3&&sw.software_tag==MB_MCP_RESET&&!(sw.flags&MB_PENDING_SOFTWARE));++checks;
 mb_confirm_clear(&sw,0U);auto pin=mb_next(&sw,fw,1U<<26);
 assert(pin.software_tag==0);++checks;
 auto bor=mb_next(&sw,fw,MB_BOR);assert(bor.sequence==1&&bor.previous_csr==0&&bor.flags==0);++checks;
 auto upgrade=mb_next(&sw,fw+1U,MB_SOFTWARE);assert(upgrade.sequence==1&&upgrade.flags==0);++checks;
 auto uncleared=mb_next(&empty,fw,MB_SOFTWARE);mb_confirm_clear(&uncleared,MB_SOFTWARE);
 assert(!(uncleared.flags&MB_CURRENT_CLEARED));
 auto following=mb_next(&uncleared,fw,1U<<26);assert(!(following.flags&MB_PREVIOUS_CLEARED));++checks;
 auto saturated=sw;saturated.sequence=0xffffffffU;saturated.crc=mb_crc(&saturated);
 assert(mb_next(&saturated,fw,1U<<26).sequence==1);++checks;
 for(unsigned n=0;n<10000;++n){
   mb_record garbage;auto words=reinterpret_cast<uint32_t*>(&garbage);
   for(unsigned i=0;i<8U;++i)words[i]=next();
   auto first=mb_next(&garbage,fw,1U<<26);
   assert(first.sequence==1&&first.flags==0);++checks;
 }
 // Every retained-record bit corruption must invalidate the old chain.
 for(unsigned i=0;i<sizeof(sw)*8U;++i){
   auto damaged=sw;reinterpret_cast<uint8_t*>(&damaged)[i/8]^=1U<<(i%8);
   assert(!mb_valid(&damaged,fw));assert(mb_next(&damaged,fw,1U<<26).sequence==1);++checks;
 }
 uint8_t wire[UV3_FRAME];mb_packet(wire,&sw,2000);mb_record decoded;
 assert(mb_decode(wire,fw,&decoded)&&memcmp(&sw,&decoded,sizeof(sw))==0);++checks;
 assert(!mb_decode(wire,fw+1,&decoded));++checks;
 for(unsigned i=0;i<UV3_FRAME*8U;++i){
   uint8_t damaged[UV3_FRAME];memcpy(damaged,wire,UV3_FRAME);damaged[i/8]^=1U<<(i%8);
   assert(!mb_decode(damaged,fw,&decoded));++checks;
 }
 uint8_t altered[UV3_FRAME];memcpy(altered,wire,UV3_FRAME);altered[14]^=1U;uv3_seal(altered);
 assert(!mb_decode(altered,fw,&decoded));++checks;
 mb_receiver rx={};assert(!mb_receive(&rx,wire,fw,false,100));assert(!rx.received);++checks;
 assert(mb_receive(&rx,wire,fw,true,0xfffffff0U));assert(mb_fresh(&rx,fw,true,0x20));++checks;
 assert(!mb_fresh(&rx,fw,false,0x20)&&!mb_fresh(&rx,fw,true,0x600));++checks;
 // Persist the actual generated frame for the independent Python decoder.
 printf("{\"checks\":%u,\"packet_hex\":\"",checks);
 for(unsigned i=0;i<UV3_FRAME;++i)printf("%02x",wire[i]);printf("\"}\n");
}
