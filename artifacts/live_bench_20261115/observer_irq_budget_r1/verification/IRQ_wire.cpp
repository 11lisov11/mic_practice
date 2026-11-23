
#include <cassert>
#include <cstdio>
#include "irq_breakdown.h"
#include "foc_timing_wire.h"
int main(){
 ib_meter m={};ib_snapshot a;ib_read(&m,&a,0xfffffff0U);uint32_t w[21];
 ib_leave(&m,4,100);ib_leave(&m,3,50);ib_leave(&m,2,12);ib_delta(&m,&a,0x50,w);
 assert(w[8]==1&&w[9]==100&&w[6]==1&&w[7]==50&&w[20]==511);
 // The frozen timing packet uses the same CRC/peer/version checks, now9 pages.
 ft_receiver r={};uint8_t f[43];
 for(unsigned page=0;page<9;++page){memset(f,0,sizeof(f));f[0]=0x55;f[1]=0xaa;f[2]=FT_WIRE;f[3]=3;f[4]=page;
  uint32_t fw=2026111502;memcpy(f+6,&fw,4);for(unsigned i=0;i<7;++i){uint32_t v=page*7+i;memcpy(f+10+4*i,&v,4);}uv3_seal(f);
  assert(ft_receive(&r,f,fw,true,10));if(page<8)assert(!ft_fresh(&r,true,10));}
 assert(ft_fresh(&r,true,10)&&r.words[62]==62);
 f[3]=2;uv3_seal(f);assert(!ft_receive(&r,f,2026111502,true,10));
 f[3]=3;uv3_seal(f);f[12]^=1;assert(!ft_receive(&r,f,2026111502,true,10));
 // A preempted writer never spins, and it is marked invalid rather than invented.
 m.irq[3].seq=1;ib_delta(&m,&a,0x60,w);assert(!(w[20]&(1U<<3))&&w[6]==0&&w[7]==0);
 printf("{\"nine_IRQ_slots\":true,\"wire9_pages\":true,\"CRC_peer_format_guarded\":true,\"bounded_torn_snapshot\":true}\n");
}
