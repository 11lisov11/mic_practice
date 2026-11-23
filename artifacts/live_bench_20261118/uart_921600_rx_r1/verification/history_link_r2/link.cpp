
#include <cassert>
#include <cstdio>
#include <cstring>
#include <deque>
#include <vector>
#include <Arduino.h>
#include <zephyr/drivers/uart.h>
static unsigned locked;static uint32_t cycles,time_us;static bool auto_tx,refill_rx,late_rx;
static void step_tx();
unsigned irq_lock(){unsigned old=locked;locked=1;return old;}
void irq_unlock(unsigned k){locked=k;}
uint32_t micros(){if(auto_tx&&!locked)step_tx();time_us+=11;return time_us;}
uint32_t k_cycle_get_32(){return ++cycles;}
enum{USART_ISR_PE=1U,USART_ISR_FE=2U,USART_ISR_NE=4U,USART_ISR_ORE=8U,
 USART_ISR_RXNE_RXFNE=32U,USART_ISR_TXE_TXFNF=128U,USART_CR1_FIFOEN=1U<<29,
 USART_CR1_TXEIE_TXFNFIE=128U,LL_USART_FIFOTHRESHOLD_1_8=0U};
struct Byte{uint8_t value;uint32_t errors;};static std::deque<Byte> rx;static std::deque<uint8_t> hwtx;
static std::vector<uint8_t> wire;static uint32_t sticky;static int configure_error;
struct Status{operator uint32_t(){++cycles;uint32_t value=sticky|(rx.empty()?0U:(32U|rx.front().errors))|(hwtx.size()<8?128U:0U)|(hwtx.empty()?64U:0U);if(late_rx&&rx.empty()){late_rx=false;rx.push_back({77,0});}return value;}};
struct Rdr{operator uint32_t(){assert(!rx.empty());auto b=rx.front();rx.pop_front();if(refill_rx)rx.push_back({99,0});++cycles;return b.value;}};
struct Tdr{void operator=(uint8_t b){assert(hwtx.size()<8);hwtx.push_back(b);++cycles;}};
struct Icr{void operator=(uint32_t v){sticky&=~v;if(!rx.empty())rx.front().errors&=~v;++cycles;}};
struct USART_TypeDef{uint32_t CR1=1,CR3=0;Status ISR;Rdr RDR;Tdr TDR;Icr ICR;}fake_registers;
static auto&regs=fake_registers;
#define DT_REG_ADDR(...) ((uintptr_t)&fake_registers)
static void LL_USART_Disable(USART_TypeDef*r){r->CR1&=~1U;}
static void LL_USART_Enable(USART_TypeDef*r){r->CR1|=1U;}
static void LL_USART_EnableFIFO(USART_TypeDef*r){assert(!(r->CR1&1));r->CR1|=USART_CR1_FIFOEN;}
static void LL_USART_SetRXFIFOThreshold(USART_TypeDef*,unsigned v){assert(v==0);}
static void LL_USART_SetTXFIFOThreshold(USART_TypeDef*,unsigned v){assert(v==0);}
static bool LL_USART_IsActiveFlag_TC(USART_TypeDef*){return hwtx.empty();}
namespace zephyr {namespace arduino {int init_dev_apply_pinctrl(const device*){return 0;}}}
static uart_irq_callback_user_data_t callback;static void*context;static device dev;
int uart_configure(const device*,const uart_config*c){assert(c->baudrate==921600&&c->data_bits==8&&c->stop_bits==1);return configure_error;}
void uart_irq_rx_disable(const device*){regs.CR1&=~32U;}void uart_irq_rx_enable(const device*){regs.CR1|=32U;}
void uart_irq_tx_disable(const device*){regs.CR1&=~128U;}void uart_irq_tx_enable(const device*){regs.CR1|=128U;}
void uart_irq_err_disable(const device*){regs.CR3&=~1U;}void uart_irq_err_enable(const device*){regs.CR3|=1U;}
int uart_irq_callback_user_data_set(const device*,uart_irq_callback_user_data_t f,void*arg){callback=f;context=arg;return 0;}
#include "nucleo_buffered_serial.h"
static void fire(){assert(!locked&&callback);callback(&dev,context);}
static void step_tx(){if(!hwtx.empty()){wire.push_back(hwtx.front());hwtx.pop_front();}if(regs.CR1&128U)fire();}
static void init(){regs.CR1=1;regs.CR3=0;rx.clear();hwtx.clear();wire.clear();sticky=0;locked=0;callback=nullptr;context=nullptr;cycles=time_us=0;auto_tx=false;refill_rx=false;late_rx=false;configure_error=0;}
static void arrive(uint8_t b,uint32_t flags=0){unsigned capacity=(regs.CR1&USART_CR1_FIFOEN)?8:1;
 if(rx.size()==capacity)sticky|=USART_ISR_ORE;else rx.push_back({b,flags});}

#include <fstream>
#include <string>
#include "observer_start_history.h"
namespace peer {
#include "observer_start_history_wire.h"
}
static peer::nh_receiver receiver;
static uint8_t packet_in[43];static unsigned fill;
static NucleoBufferedSerial*port;
static void collect(){
 while(port->available()){
  packet_in[fill++]=(uint8_t)port->read();
  if(fill==43){assert(peer::nhr_receive(&receiver,packet_in,2026111806U,2026111806U));fill=0;}
 }
}
static unsigned wire_count,commands;
static void transmit(nh_capture&c){
 uint8_t packet[43];assert(nh_packet(&c,packet,1));
 for(unsigned i=0;i<43;++i){arrive(packet[i]);++wire_count;
  if(wire_count%8==0)fire();step_tx();}
 fire();collect();nh_sent(&c);
}
static void save(std::string name,const void*data,size_t n){std::ofstream f(name,std::ios::binary);f.write((const char*)data,n);assert(f.good());}
int main(int argc,char**argv){
 assert(argc==3);std::ifstream f(argv[1],std::ios::binary);std::vector<uint8_t>b((std::istreambuf_iterator<char>(f)),{});
 assert(b.size()==264+659*236);ma_observer initial;ma_motor m;
 memcpy(&initial,b.data(),204);memcpy(&m,b.data()+204,52);
 init();NucleoBufferedSerial serial(&dev);port=&serial;port->begin(921600);
 static nh_capture capture;nh_begin(&capture,&initial,&m,2026111806U,0x12345678U,0);
 uint8_t command[43]={0xaa,0x55,3};uv3_seal(command);
 const uint8_t*at=b.data()+264;
 for(unsigned i=0;i<659;++i,at+=236){
  float input[5];ma_observer post;memcpy(input,at,20);memcpy(&post,at+32,204);
  nh_step(&capture,&post,input,nh_u32(at+20),nh_u32(at+24),nh_u32(at+28),0xff000000U+i*170000U,0xff000000U+i*170000U+80000U);
  if(i%50==0){assert(port->write(command,43)==43);++commands;}
  transmit(capture);
 }
 for(unsigned page=0;page<NH_META_PAGES;++page)transmit(capture);
 for(unsigned i=0;i<100&&(!hwtx.empty()||(regs.CR1&128));++i)step_tx();
 assert(!fill&&peer::nhr_exact(&receiver)&&receiver.count==659);
 assert(!port->stats().errors&&!port->stats().dropped&&port->stats().max_batch<=8);
 assert(wire.size()==commands*43U);for(unsigned i=0;i<commands;++i)assert(!memcmp(wire.data()+i*43U,command,43));
 std::string dest=argv[2];save(dest+"/meta.bin",receiver.meta,524);save(dest+"/rows.bin",receiver.rows,receiver.count*22);
 save(dest+"/checkpoints.bin",receiver.checkpoints,receiver.count/16*4);
 printf("{\"passed\":true,\"rows\":659,\"received_bytes\":%u,\"full_duplex_OFF_frames\":%u,\"hardware_RX_errors\":0,\"software_RX_drops\":0,\"actual_recorder_and_Uno_adapter\":true,\"simulated_FIFO\":true,\"hardware_commands\":0}\n",wire_count,commands);
}
