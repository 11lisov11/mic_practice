
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <fstream>
#include "observer_start_history.h"
namespace peer {
#include "observer_start_history_wire.h"
}
static unsigned tests;
#define CHECK(x) do{assert(x);++tests;}while(0)
static bool drain(nh_capture&c,peer::nh_receiver&r){
 uint8_t packet[UV3_FRAME];if(!nh_packet(&c,packet,1))return false;
 CHECK(uv3_crc_ok(packet));CHECK(peer::nhr_receive(&r,packet,2026111804U,2026111804U));nh_sent(&c);return true;
}
static void save(const char*path,const void*data,size_t n){FILE*f=fopen(path,"wb");assert(f);assert(fwrite(data,1,n,f)==n);fclose(f);}
int main(int argc,char**argv){
 assert(argc==3);std::ifstream file(argv[1],std::ios::binary);
 std::vector<uint8_t>b((std::istreambuf_iterator<char>(file)),{});assert(b.size()>264);
 ma_observer initial;ma_motor m;memcpy(&initial,b.data(),204);memcpy(&m,b.data()+204,52);
 uint32_t count=nh_u32(b.data()+260);CHECK(count==659U);
 for(unsigned code=0;code<153;++code)CHECK(nh_pair_code(nh_pair_counts(code))==code);
 CHECK(nh_pair_code(0)==255);CHECK(nh_pair_counts(153)==0);
 static nh_capture c;static peer::nh_receiver r;
 nh_begin(&c,&initial,&m,2026111804U,0x12345678U,0);
 const uint8_t*ptr=b.data()+264;ma_observer post=initial;
 for(unsigned index=0;index<count;++index,ptr+=236){
  float input[5];memcpy(input,ptr,20);memcpy(&post,ptr+32,204);
  int event=nh_step(&c,&post,input,nh_u32(ptr+20),nh_u32(ptr+24),(int)nh_u32(ptr+28),
   0xff000000U+index*170000U,0xff000000U+index*170000U+80000U);
  CHECK(event==(index==658U));CHECK(c.frozen==(index==658U));
  CHECK(drain(c,r)); // deterministic transport, not target UART timing
 }
 CHECK(c.frozen&&c.meta.count==659&&c.meta.event_count==659&&c.meta.flags==NH_EVENT);
 CHECK(!r.complete);for(unsigned page=0;page<NH_META_PAGES;++page)CHECK(drain(c,r));
 CHECK(peer::nhr_exact(&r));CHECK(r.count==count);CHECK(!memcmp(&c.meta,r.meta,NH_META_BYTES));
 CHECK(!memcmp(&post,r.meta+320,204));
 nh_meta before=c.meta;nh_begin(&c,&initial,&m,2026111804U,7,0);nh_freeze(&c,&post,NH_STOP);
 CHECK(!memcmp(&before,&c.meta,sizeof(before))); // STOP/CLEAR/next prepare never overwrites first history
 float zero[5]={0,0,0,0,.001f};CHECK(!nh_step(&c,&post,zero,16U,0,0,1,2));
 std::string dest=argv[2];save((dest+"/meta.bin").c_str(),r.meta,NH_META_BYTES);
 save((dest+"/rows.bin").c_str(),r.rows,r.count*NH_ROW);
 save((dest+"/checkpoints.bin").c_str(),r.checkpoints,r.count/16U*4U);
 // Corrupt wire CRC, foreign firmware, changed epoch and missing/reordered row.
 static nh_capture f;static peer::nh_receiver bad;
 ma_observer step=initial;step.steps=1;nh_begin(&f,&initial,&m,2026111804U,2,0);
 CHECK(!nh_step(&f,&step,zero,16U,0,0,100,200));uint8_t packet[UV3_FRAME];CHECK(nh_packet(&f,packet,0));
 packet[12]^=1;CHECK(!peer::nhr_receive(&bad,packet,2026111804U,2026111804U));CHECK(bad.gap);
 packet[12]^=1;memset(&bad,0,sizeof(bad));CHECK(!peer::nhr_receive(&bad,packet,1,2026111804U));
 memset(&bad,0,sizeof(bad));packet[5]=1;uv3_seal(packet);
 CHECK(!peer::nhr_receive(&bad,packet,2026111804U,2026111804U));CHECK(bad.gap);
 // Queue pressure is nonblocking and reports a GAP, never wraps old rows.
 memset(&f,0,sizeof(f));nh_begin(&f,&initial,&m,2026111804U,3,0);
 for(unsigned i=0;i<NH_QUEUE+1U;++i){step.steps=i+1;nh_step(&f,&step,zero,16U,0,0,i,i);}
 CHECK(f.head-f.tail==NH_QUEUE);CHECK(f.meta.flags&NH_GAP);CHECK(f.meta.count==5);
 // First event during warmup is captured, with no qualification shortcut.
 memset(&f,0,sizeof(f));nh_begin(&f,&initial,&m,2026111804U,4,0);step.steps=1;step.nis=25;
 CHECK(nh_step(&f,&step,zero,16U,0,0,1,2));CHECK(f.meta.event_count==1&&f.frozen);
 // No NIS event -> STOP seals complete prefix. Capacity exhaustion explicit.
 memset(&f,0,sizeof(f));nh_begin(&f,&initial,&m,2026111804U,5,0);step.nis=0;
 nh_step(&f,&step,zero,16U,0,0,1,2);nh_freeze(&f,&step,NH_STOP);CHECK(f.frozen&&f.meta.flags==NH_STOP);
 memset(&f,0,sizeof(f));nh_begin(&f,&initial,&m,2026111804U,6,0);
 for(unsigned i=0;i<NH_CAPACITY+1U;++i){step.steps=i+1;nh_step(&f,&step,zero,16U,0,0,i,i);f.tail=f.head;}
 CHECK(f.frozen&&f.meta.count==NH_CAPACITY&&f.meta.flags==NH_OVERFLOW);
 printf("{\"passed\":true,\"checks\":%u,\"rows\":%u,\"nucleo_capture_bytes\":%u,\"uno_capture_bytes\":%u,\"synthetic_fixture\":true,\"target_timing_measured\":false}\n",
  tests,count,(unsigned)sizeof(nh_capture),(unsigned)sizeof(peer::nh_receiver));
}
