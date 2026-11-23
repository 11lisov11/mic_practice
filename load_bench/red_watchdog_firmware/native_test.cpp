#include <assert.h>
#include <stdio.h>
#include "include/permit_protocol.h"
static void ack(char *s,uint32_t nonce){
  char body[24];snprintf(body,sizeof(body),"ACK %08lX",(unsigned long)nonce);
  snprintf(s,64,"%s %04X",body,lease_crc(body));
}
int main(){
  PermitProtocol p;uint32_t value=0;char line[64];
  assert(!p.permit(0)&&!p.issue(0));
  assert(p.receive("HELLO",0,value)==1&&!p.permit(0));
  assert(p.issue(100));ack(line,p.lease.nonce);
  assert(p.receive(line,101,value)==3&&p.permit(101));
  assert(p.permit(850)&&!p.permit(851)&&p.latched&&!p.issue(852));
  assert(p.receive("HELLO",900,value)==1&&p.issue(901));
  ack(line,p.lease.nonce);assert(p.receive(line,902,value)==3);
  assert(p.receive(line,903,value)==0&&p.latched&&!p.permit(903)); // replay
  assert(p.receive("HELLO",1000,value)==1&&p.issue(1001));ack(line,p.lease.nonce);
  assert(p.receive(line,1152,value)==0&&p.latched); // stale challenge
  assert(p.receive("HELLO",1200,value)==1&&p.issue(1201));
  assert(p.receive("ACK 00000000 0000",1202,value)==0&&p.latched); // CRC
  assert(p.receive("HELLO",1300,value)==1&&p.issue(1301));ack(line,p.lease.nonce);
  assert(p.receive(line,1302,value)==3&&p.permit(1302));
  assert(p.receive("STOP",1303,value)==2&&!p.permit(1303)&&p.latched&&!p.issue(1304));
  assert(p.receive("HELLO",0xfffffff0,value)==1&&p.issue(0xfffffff0));ack(line,p.lease.nonce);
  assert(p.receive(line,0xfffffff1,value)==3);
  assert(p.permit(0x2dd)&&!p.permit(0x2df));
  assert(lease_crc("123456789")==0x4b37);
  puts("RNR permit: identity gate, zero boot, nonce, CRC, replay, stale, timeout latch, STOP, restart, millis wrap PASS");
}
