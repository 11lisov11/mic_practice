#include "adapter.h"
#include "uart_v3_transport.h"
#include <cassert>
#include <cstdio>
int main(){
 unsigned exact=0,erased=0,overflow=0;
 for(unsigned gap=0;gap<UV3_FRAME;++gap){
  NucleoBufferedSerial serial(&dev);serial.begin(115200);
  unsigned char frame[UV3_FRAME]={0x55,0xaa,0xda};
  for(unsigned i=3;i<UV3_PAYLOAD;++i)frame[i]=static_cast<unsigned char>(i*7+gap);
  uv3_seal(frame);
  for(unsigned i=0;i<UV3_FRAME;++i){
   if(i==gap)late_byte=frame[i];else fifo.push_back(frame[i]);
   callback(&dev,callback_arg);
  }
  unsigned char got[UV3_FRAME]={};unsigned count=0;
  while(serial.available()&&count<UV3_FRAME)got[count++]=static_cast<unsigned char>(serial.read());
  bool same=count==UV3_FRAME;
  for(unsigned i=0;i<count&&same;++i)same=got[i]==frame[i];
  assert(serial.stats().rescued==1);if(same&&uv3_crc_ok(got))++exact;
  if(count==UV3_FRAME-1)++erased;
 }
 {
  NucleoBufferedSerial serial(&dev);serial.begin(115200);
  for(unsigned i=0;i<1025;++i){fifo.push_back(static_cast<unsigned char>(i));callback(&dev,callback_arg);}
  assert(serial.stats().dropped==1&&serial.available()==1024);++overflow;
 }
 std::printf("{\"frame_cases\":43,\"exact_crc_valid\":%u,\"one_byte_erased\":%u,\"overflow_checks\":%u}\n",exact,erased,overflow);
}
