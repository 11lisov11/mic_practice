#include "load_core.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
static unsigned checks;
static void test(bool x){++checks;if(!x){std::fprintf(stderr,"check%u\n",checks);std::exit(1);}}
int main(){
 for(uint32_t start: {0U,170000000U,0xfffffff0U}){
  ld_core q;ld_init(&q);test(q.state==LD_IDLE&&!q.attempted);
  test(ld_request(&q,start,170000000U,0));
  for(unsigned n=0;n<5000;n++)test(ld_tick(&q,start+n*170000U,0));
  test(!ld_tick(&q,start+850000000U,0));test(q.state==LD_DONE&&q.elapsed==850000000U);
  test(!ld_request(&q,start+1000000000U,170000000U,0));
  test(!ld_tick(&q,start+1000000001U,0));test(q.state==LD_DONE);
 }
 for(unsigned bit=0;bit<8;bit++){
  ld_core q;ld_init(&q);test(!ld_request(&q,0,170000000U,1U<<bit));
  test(q.state==LD_DENIED&&q.attempted&&q.reason==(1U<<bit));
  test(!ld_request(&q,1,170000000U,0));
  ld_init(&q);test(ld_request(&q,0,170000000U,0));
  test(!ld_tick(&q,170000U,1U<<bit));test(q.state==LD_ABORTED&&q.reason==(1U<<bit));
  test(!ld_tick(&q,850000000U,0));test(q.state==LD_ABORTED);
 }
 for(uint32_t hz: {0U,16000000U,850000000U,0xffffffffU}){
  ld_core q;ld_init(&q);test(!ld_request(&q,0,hz,0));test(q.reason&LD_CLOCK);
 }
 uint32_t words[56];for(unsigned i=0;i<56;i++)words[i]=i*0x1020304U;
 uint32_t crc=ld_crc(words,56);
 for(unsigned i=0;i<56;i++){words[i]^=0x100U;test(ld_crc(words,56)!=crc);words[i]^=0x100U;}
 std::printf("{\"passed\":true,\"checks\":%u,\"hardware_calls\":0}\n",checks);
}
