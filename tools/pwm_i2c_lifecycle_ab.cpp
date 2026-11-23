#include "encoder_core.h"
#include <cassert>
#include <cstdio>
struct Bus {ec_state e{};bool pe=false,noise=false;unsigned enables=0,parks=0,starts=0;uint32_t isr=1;};
static uint32_t status(void*x){return ((Bus*)x)->isr;}
static void begin(void*x){auto&b=*(Bus*)x;assert(b.pe&&!(b.isr&EC_BUSYF));++b.starts;b.isr=EC_BUSYF;}
static void noop(void*){}
static void write(void*,uint8_t){}
static uint8_t read(void*){return 0;}
static void clear(void*x){((Bus*)x)->isr&=~(EC_NACKF|EC_STOPF|EC_BERR|EC_ARLOF|EC_OVRF);}
static void park(void*x){auto&b=*(Bus*)x;++b.parks;b.pe=false;b.isr=1;}
static uint8_t lines(void*){return 3;}
static void enable(void*x){auto&b=*(Bus*)x;assert(!b.pe);b.pe=true;++b.enables;if(b.noise)b.isr=EC_BUSYF;}
static bool ready(void*){return true;}
static void fault(void*,uint8_t,uint32_t,uint32_t,uint32_t){}
static void terminal(void*,uint8_t){}
static void completed(void*x){assert(((Bus*)x)->pe);}
static ec_io io(Bus&b){return {&b,status,begin,write,noop,read,clear,park,fault,lines,enable,park,noop,noop,ready,noop,noop,terminal
#if MIC_PERSISTENT_PE
,completed
#endif
};}
static void step(Bus&b,unsigned us){auto i=io(b);ec_poll(&b.e,&i,us/1000,us*170,170000000);}
static void normal(Bus&b,unsigned us){
 for(unsigned n=0;b.e.state!=1&&n<500;n++)step(b,us+n*10);
 assert(b.e.state==1);auto i=io(b);b.e.state=4;b.e.n=3;b.e.bytes[0]=0x20;b.isr=EC_STOPF;
 ec_poll(&b.e,&i,us/1000,(us+100)*170,170000000);assert(b.e.reads);
}
int main(){
 (void)completed;Bus healthy;ec_init(&healthy.e,170000000,true);
 for(unsigned n=1;n<=200;n++)normal(healthy,n*5000);
 assert(healthy.e.reads==200&&healthy.e.errors==0);
 Bus noisy;ec_init(&noisy.e,170000000,true);normal(noisy,5000);noisy.noise=true;
 for(unsigned us=10000;us<=13500;us+=10)step(noisy,us);
 unsigned false_busy=noisy.e.primary_busy;
 // Both versions preserve/reject the same NACK; neither calls it a valid angle.
 Bus nack;ec_init(&nack.e,170000000,true);for(unsigned us=5000;nack.e.state!=1;us+=10)step(nack,us);
 nack.e.state=2;nack.e.stage=5;nack.isr=EC_NACKF|EC_STOPF;step(nack,5200);
 assert(nack.e.primary_nack==1&&nack.e.reads==0&&!nack.e.angle_ok);
 printf("{\"healthy_reads\":%u,\"healthy_enables\":%u,\"healthy_pe_disables\":%u,\"false_busy_errors\":%u,\"nack_errors\":%u}\n",healthy.e.reads,healthy.enables,healthy.parks,false_busy,nack.e.primary_nack);
}
