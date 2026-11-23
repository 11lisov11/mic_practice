#include <assert.h>
#include <stdio.h>
#include "include/lease.h"
int main(){
  Lease l; assert(!l.permit(0)); l.issue(100);
  assert(!l.reply(0,101)); assert(!l.permit(101));
  assert(l.reply(1,101)); assert(l.permit(850)); assert(!l.permit(851));
  assert(!l.reply(1,852));
  l.issue(900); assert(!l.reply(2,1051)); assert(!l.permit(1051));
  l.issue(1100); assert(l.reply(3,1101)); l.stop(); assert(!l.permit(1102));
  l.issue(0xfffffff0); assert(l.reply(4,0xfffffff1));
  assert(l.permit(0x000002dd)); assert(!l.permit(0x000002df));
  assert(lease_crc("123456789")==0x4b37);
  puts("lease: boot, nonce, replay, age, timeout, STOP, millis wrap, CRC PASS");
}
