#include "encoder_core.h"
#include "fault_wire.h"
#include <cassert>
#include <cstdio>
#include <cstring>
struct I2c {uint32_t ISR=0,CR1=0x201,CR2=0x0203046c,TIMINGR=0x30521317;};
struct Gpio {uint32_t IDR=0x300,MODER=10U<<16,OTYPER=0x300,AFR[2]={0,0x44};};
struct Timer {uint32_t BDTR=0,CNT=123,CR1=32,ARR=4250,CCR1=100,CCR2=200,CCR3=300;};
struct Clock {uint32_t CCIPR=2U<<12,CFGR=123;};
struct Cycles {uint32_t CYCCNT=17000;};
static I2c i2c;static Gpio gpio;static Timer timer;static Clock clockreg;static Cycles dwt;
static I2c*I2C1=&i2c;static Gpio*GPIOB=&gpio;static Timer*TIM1=&timer;
static Clock*RCC=&clockreg;static Cycles*DWT=&dwt;
static uint32_t SystemCoreClock=170000000;
static ec_state enc;
#include "capture.inc"
static unsigned resets;
static uint32_t status(void*){return i2c.ISR;}
static void nothing(void*){}
static void write(void*,uint8_t){}
static uint8_t read(void*){return 0;}
static void reset(void*){assert(fault_pending);++resets;i2c.CR1=0x201;i2c.CR2=0;i2c.ISR=1;gpio.IDR=0x300;capture_after_reset();}
static void seal(uint8_t*p){uv3_seal(p);}
int main(){
 poll_seen=true;poll_previous_cycles=100;poll_gap=200;poll_max_gap=400;
 assert(poll_seen&&poll_previous_cycles==100);
 ec_io io={nullptr,status,nothing,write,nothing,read,nothing,reset,capture_before_reset};
 ec_init(&enc,SystemCoreClock,true);enc.state=2;enc.stage=5;enc.errors=8;enc.reads=123;enc.begin_cycles=1000;
 i2c.ISR=EC_BERR|EC_BUSYF;i2c.CR2=0x0203046c;gpio.IDR=0x100;
 ec_finish(&enc,&io,10,17000,SystemCoreClock,EC_BUS,i2c.ISR);
 assert(resets==1&&fault_ready==1&&fault_record[0][26]==8&&enc.errors==9);
 assert(fault_record[0][4]==(EC_BUS|(5U<<8)|(2U<<16)));
 assert(fault_record[0][5]==(EC_BERR|EC_BUSYF)&&fault_record[0][7]==0x100);
 assert(fault_record[0][10]==0x0203046c&&fault_record[0][35]==1&&fault_record[0][37]==0);
 uint32_t first[FC_WORDS];memcpy(first,fault_record[0],FC_BYTES);
 timer.BDTR=32768;i2c.ISR=EC_BUSYF|1;enc.state=0;enc.stage=4;
 ec_finish(&enc,&io,20,34000,SystemCoreClock,EC_BUSY,i2c.ISR);
 assert(fault_ready==3&&fault_record[1][5]==(EC_BUSYF|1));
 assert(fault_record[1][7]==0x300&&fault_record[1][16]==32768);
 uint32_t pwm[FC_WORDS];memcpy(pwm,fault_record[1],FC_BYTES);
 capture_before_reset(nullptr,EC_NACK,EC_NACKF,30,1);
 assert(!fault_pending);capture_after_reset();
 assert(!memcmp(first,fault_record[0],FC_BYTES)&&!memcmp(pwm,fault_record[1],FC_BYTES));
 fc_receiver rx={};uint8_t p[UV3_FRAME];
 for(int page=FC_PAGES-1;page>=0;--page){assert(mic_encoder_fault_packet(p,1,page));assert(fc_receive(&rx,p,FC_PEER,true));}
 assert(rx.slot[1].valid&&!memcmp(rx.slot[1].bytes,fault_record[1],FC_BYTES));
 assert(!mic_encoder_fault_packet(p,2,0)&&!mic_encoder_fault_packet(p,0,FC_PAGES));
 for(unsigned i=0;i<UV3_FRAME;++i){assert(mic_encoder_fault_packet(p,0,0));p[i]^=1;assert(!fc_receive(&rx,p,FC_PEER,true));}
 assert(mic_encoder_fault_packet(p,0,0));assert(!fc_receive(&rx,p,FC_PEER,false));assert(!fc_receive(&rx,p,123,true));
 for(unsigned page=0;page<FC_PAGES;++page){assert(mic_encoder_fault_packet(p,0,page));p[14]^=1;seal(p);fc_receive(&rx,p,FC_PEER,true);}
 assert(!rx.slot[0].valid);
 for(unsigned page=0;page<FC_PAGES;++page){assert(mic_encoder_fault_packet(p,0,page));assert(fc_receive(&rx,p,FC_PEER,true)==(page==FC_PAGES-1));}
 assert(rx.slot[0].valid);
 assert(mic_encoder_fault_packet(p,0,FC_PAGES-1));p[37]=1;seal(p);assert(!fc_receive(&rx,p,FC_PEER,true));
 assert(mic_encoder_fault_packet(p,0,0));p[3]=2;seal(p);assert(!fc_receive(&rx,p,FC_PEER,true));
 /* A pre-existing boot error must not consume the first PWM slot. */
 fault_ready=0;fault_pending=0;timer.BDTR=32768;enc.state=3;enc.n=1;enc.stage=8;i2c.ISR=EC_RXNE;
 ec_finish(&enc,&io,50,50000,SystemCoreClock,EC_DEADLINE,i2c.ISR);
 assert(fault_ready==3&&fault_record[0][4]==fault_record[1][4]&&fault_record[0][26]==10);
 assert(enc.timeouts==1);
 std::printf("{\"passed\":true,\"paging_crc_cases\":43,\"pre_reset_order_verified\":true,\"two_immutable_slots_verified\":true}\n");
}
