
#include <cassert>
#include <cstdint>
enum{UV3_FRAME=43};static unsigned available=100,consumed;static bool abort_rx;
static bool uno_rx_pop(uint8_t*b,uint8_t*f){if(!available)return false;--available;*b=0;*f=0;return true;}
static bool uno_abort_pending_rx_fault(){return abort_rx;}
static void uno_consume_sample(uint8_t,uint8_t){++consumed;}
void run_slice(){
  uint8_t byte, flags;
  unsigned serviced=0;
  while (serviced<UV3_FRAME && uno_rx_pop(&byte, &flags)) {
    ++serviced;
    if (uno_abort_pending_rx_fault()) return;
    uno_consume_sample(byte, flags);
  }
}
int main(){run_slice();assert(consumed==43&&available==57);run_slice();assert(consumed==86&&available==14);run_slice();assert(consumed==100&&!available);available=20;abort_rx=true;run_slice();assert(consumed==100);}