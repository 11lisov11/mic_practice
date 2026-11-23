#include "encoder_core.h"
#include "record_fixture.h"
#include <cassert>
#include <cstdio>
static uint32_t isr;static bool pe=true;static unsigned resets;
static uint32_t status(void*){return isr;}
static void nothing(void*){}
static void write(void*,uint8_t){}
static uint8_t read(void*){return 0;}
static uint8_t lines(void*){return 3;}
static void reset(void*){assert(pe&&(isr&EC_BUSYF)&&!(isr&EC_STOPF));pe=false;++resets;}
int main(){
 ec_state e;ec_init(&e,170000000,true);e.state=(record[4]>>16)&255;e.n=record[4]>>24;
 e.begin_cycles=record[3]-record[25];e.last_start_ms=record[2];isr=record[5];
 ec_io i={nullptr,status,nothing,write,nothing,read,nothing,reset,nullptr,lines,nothing,nothing,nothing};
 ec_poll(&e,&i,record[2],record[3],170000000);
 assert(e.cause==EC_NACK&&resets==1&&!pe&&e.errors==1);
 std::puts("{\"passed\":true,\"installed_2702_premature_PE_reset_reproduced\":true,\"record_entry_exact\":true}");
}
