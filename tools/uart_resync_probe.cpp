/* Offline probe of the actual installed command transport. No hardware I/O. */
#include <cstdio>
#include <cstdint>
#include <array>
#include "uart_v3_transport.h"
using Frame=std::array<uint8_t,UV3_FRAME>;
Frame packet(unsigned seq,unsigned hz=15000) {
  Frame f{};f[0]=0xaa;f[1]=0x55;f[2]=3;f[3]=1;f[4]=3;f[5]=(uint8_t)seq;
  for(unsigned j=0;j<4;++j)f[6+j]=hz>>(8*j);
  f[10]=0xf4;f[11]=1;f[12]=0xc2;f[13]=0x5a;uv3_seal(f.data());return f;
}
uv3_result feed(uv3_rx &rx,const Frame& f,uint32_t t) {
  uv3_result last=UV3_WAIT;
  for(unsigned i=0;i<f.size();++i) {
    auto r=uv3_byte(&rx,f[i],0,t+i*87/1000);
    if(r!=UV3_WAIT)last=r;
    if(r==UV3_READY)uv3_commit(&rx,t+i*87/1000,true,false,false);
  }
  return last;
}
int main() {
  unsigned bad=0,total=0,witness_seq=0,witness_pos=0,witness_bit=0;
  for(unsigned seq=0;seq<256;++seq)for(unsigned pos=2;pos<UV3_FRAME;++pos)for(unsigned bit=0;bit<8;++bit) {
    uv3_rx rx;uv3_init(&rx,true);
    for(unsigned i=0;i<4;++i)feed(rx,packet(seq-5+i),10+50*i);
    auto first=packet(seq-1);first[8]^=1;feed(rx,first,210);uv3_tick(&rx,230);
    auto second=packet(seq);second[pos]^=1;feed(rx,second,260);uv3_tick(&rx,280);
    feed(rx,packet(seq+1),310);
    ++total;
    if(rx.fault_latched) {
      if(!bad){witness_seq=seq;witness_pos=pos;witness_bit=bit;}
      ++bad;
    }
  }
  std::printf("{\"cases\":%u,\"unexpected_latches_after_two_damaged_frames\":%u,"
    "\"first_seq\":%u,\"first_byte\":%u,\"first_bit\":%u}\n",total,bad,witness_seq,witness_pos,witness_bit);
  auto f=packet(197);std::printf("sequence197_manual15_crc=%02x%02x%02x%02x\n",f[39],f[40],f[41],f[42]);
}
