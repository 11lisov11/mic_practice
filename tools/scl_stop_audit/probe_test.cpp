#include "pe_release_probe.h"
#include <cassert>
#include <cstdio>
static unsigned checks;
static sr_sample sample(unsigned us,unsigned gpio,uint32_t base=0){return {base+us*170U,1,0x200,0,gpio};}
int main(){
 static_assert(sizeof(sr_probe)*2<=160,"Two frozen slots must fit160B");
 for(unsigned pins=0;pins<4;pins++){
  sr_probe p{};sr_arm(&p,0,0x250);sr_after_park(&p,sample(1,pins<<8));
  sr_poll(&p,sample(4,pins<<8),170000000);assert(p.count==1);checks++;
  sr_poll(&p,sample(6,pins<<8),170000000);assert(p.count==2&&!p.complete);checks++;
  sr_poll(&p,sample(21,pins<<8),170000000);assert(p.complete&&p.count==3);checks++;
  assert(sr_result(&p)==((pins&1)?SR_SCL_HIGH_AFTER_DISABLE:SR_SCL_LOW_AFTER_DISABLE));checks++;
  sr_probe frozen=p;sr_arm(&p,99,99);assert(!memcmp(&p,&frozen,sizeof(p)));checks++;
 }
 {sr_probe p{};sr_arm(&p,0,0);sr_after_park(&p,sample(0,0x200));sr_poll(&p,sample(5,0x300),170000000);sr_poll(&p,sample(20,0x300),170000000);assert(sr_result(&p)==SR_MIXED);checks++;}
 {sr_probe p{};sr_arm(&p,0,0);sr_after_park(&p,sample(0,0x300));sr_poll(&p,sample(538,0x300),170000000);assert(p.flags&SR_LATE);assert(p.after[1].cycles==538*170&&p.count==2);checks+=2;}
 {sr_probe p{};sr_arm(&p,0,0);sr_after_park(&p,sample(0,0x300));auto s=sample(5,0x300);s.cr1|=1;sr_poll(&p,s,170000000);assert(sr_result(&p)==SR_UNKNOWN&&!p.active);checks++;}
 {sr_probe p{};sr_arm(&p,0,0);sr_after_park(&p,sample(0,0x300));sr_poll(&p,sample(1001,0x300),170000000);assert(sr_result(&p)==SR_UNKNOWN&&(p.flags&SR_TIMEOUT));checks++;}
 {sr_probe p{};uint32_t base=UINT32_MAX-100;sr_arm(&p,base,0);sr_after_park(&p,sample(0,0x300,base));sr_poll(&p,sample(5,0x300,base),170000000);sr_poll(&p,sample(20,0x300,base),170000000);assert(sr_result(&p)==SR_SCL_HIGH_AFTER_DISABLE);checks++;}
 std::printf("{\"passed\":true,\"checks\":%u,\"two_slots_bytes\":%u,\"hardware_commands\":0,\"source_attribution_proven\":false}\n",checks,(unsigned)sizeof(sr_probe)*2);
}
