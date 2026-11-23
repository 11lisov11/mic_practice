#include <cassert>
#include "peak_wire.h"
extern "C" __declspec(dllexport) unsigned wire(const uint8_t*raw){
 pc_receiver r={};unsigned checks=0;
 for(unsigned page=0;page<35;++page){
  uint8_t p[UV3_FRAME]={};p[0]=0x55;p[1]=0xaa;p[2]=0xd8;p[3]=1;p[4]=1;p[5]=page;p[6]=35;
  unsigned len=page==34?4:30;p[7]=len;memcpy(p+8,raw+30*page,len);p[38]=1;uv3_seal(p);
  assert(!pc_receive(&r,p,CT_PEER_BUILD,false,1));++checks;
  assert(!pc_receive(&r,p,2026111716U,true,1));++checks;
  assert(pc_receive(&r,p,CT_PEER_BUILD,true,1));++checks;
 }assert(r.complete&&!memcmp(r.data,raw,1024));++checks;return checks;
}