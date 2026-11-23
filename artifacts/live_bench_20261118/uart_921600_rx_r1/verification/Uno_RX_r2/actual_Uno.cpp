
#include <cassert>
#include <cstdio>
#include <cstring>
#include <deque>
#include <vector>
#include <Arduino.h>
#include <zephyr/drivers/uart.h>
static unsigned locked;static uint32_t cycles,time_us;static bool auto_tx,refill_rx;
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
struct Status{operator uint32_t(){++cycles;return sticky|(rx.empty()?0U:(32U|rx.front().errors))|(hwtx.size()<8?128U:0U)|(hwtx.empty()?64U:0U);}};
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
static void init(){regs.CR1=1;regs.CR3=0;rx.clear();hwtx.clear();wire.clear();sticky=0;locked=0;callback=nullptr;context=nullptr;cycles=time_us=0;auto_tx=false;refill_rx=false;configure_error=0;}
static void arrive(uint8_t b,uint32_t flags=0){unsigned capacity=(regs.CR1&USART_CR1_FIFOEN)?8:1;
 if(rx.size()==capacity)sticky|=USART_ISR_ORE;else rx.push_back({b,flags});}
int main(){unsigned cases=0;uint8_t packet[43];for(unsigned i=0;i<43;++i)packet[i]=(uint8_t)(i*17U);
 for(unsigned delay=1;delay<=8;++delay){init();NucleoBufferedSerial port(&dev);port.begin(921600);std::vector<uint8_t> got,expected;
  for(unsigned n=0;n<50000;++n){uint8_t b=(uint8_t)(n*73U+delay);arrive(b);expected.push_back(b);
   if((n+1)%delay==0)fire();if(n%31==0)while(port.available())got.push_back((uint8_t)port.read());}
  fire();while(port.available())got.push_back((uint8_t)port.read());auto s=port.stats();
  assert(got==expected&&!s.errors&&!s.dropped&&s.fifo_enabled&&s.max_batch<=8);++cases;
 }
 // Same IRQ delay without FIFO overflows, FIFO8 survives8 characters.
 init();for(unsigned n=0;n<8;++n)arrive(n);assert(sticky&8);++cases;
 // Real hardware-overrun condition remains fail-closed, not hidden by CRC.
 init();NucleoBufferedSerial bad(&dev);bad.begin(921600);for(unsigned n=0;n<9;++n)arrive(n);fire();
 assert(!bad.available()&&bad.stats().error_flags&UART_ERROR_OVERRUN&&bad.write(packet,43)==0);
 auto before=bad.stats();bad.begin(921600);assert(bad.stats().errors==before.errors&&bad.write(packet,43)==0);++cases;
 // All byte-error masks at every FIFO position; no poisoned prefix survives.
 for(unsigned at=0;at<8;++at)for(unsigned mask=1;mask<16;++mask){init();NucleoBufferedSerial port(&dev);port.begin(921600);
  for(unsigned i=0;i<8;++i)arrive(i,i==at?mask:0);fire();assert(!port.available()&&port.stats().errors&&port.write(packet,43)==0);++cases;}
 // Full software RX buffer is also fatal, separately counted as a dropped byte.
 init();NucleoBufferedSerial full(&dev);full.begin(921600);for(unsigned n=0;n<1025;++n){arrive(n);fire();}
 assert(full.stats().dropped==1&&!full.available()&&full.write(packet,43)==0);++cases;
 // Handler never spins forever under an impossible continuous RX source.
 init();NucleoBufferedSerial bounded(&dev);bounded.begin(921600);arrive(1);refill_rx=true;fire();refill_rx=false;
 assert(bounded.stats().max_batch==32&&bounded.stats().error_flags&0x40000U&&!bounded.available());++cases;
 // Whole packet ordering through the actual TX FIFO, all eight slots used.
 init();NucleoBufferedSerial tx(&dev);tx.begin(921600);assert(tx.write(packet,43)==43);fire();assert(hwtx.size()==8);
 for(unsigned i=0;i<100&&(!hwtx.empty()||(regs.CR1&128));++i)step_tx();assert(wire==std::vector<uint8_t>(packet,packet+43));++cases;
 // Backpressure with live IRQs:128 bytes queued, next43 waits for room and sends intact.
 init();NucleoBufferedSerial pressure(&dev);pressure.begin(921600);uint8_t bulk[128]={};assert(pressure.write(bulk,128)==128);
 auto_tx=true;assert(pressure.write(packet,43)==43);auto_tx=false;
 for(unsigned i=0;i<300&&(!hwtx.empty()||(regs.CR1&128));++i)step_tx();
 assert(wire.size()==171&&!memcmp(wire.data()+128,packet,43)&&!pressure.stats().tx_rejected);++cases;
 // No IRQ progress: bounded write timeout, zero partial second packet.
 init();NucleoBufferedSerial stalled(&dev);stalled.begin(921600);assert(stalled.write(bulk,128)==128);
 assert(stalled.write(packet,43)==0&&stalled.stats().tx_rejected==1&&stalled.stats().error_flags&0x20000U);++cases;
 // Initialization failure is visible, never proceeds with an unknown baud/FIFO.
 init();configure_error=-1;NucleoBufferedSerial cfg(&dev);cfg.begin(921600);assert(cfg.write(packet,43)==0&&cfg.stats().errors);++cases;
 printf("{\"passed\":true,\"cases\":%u,\"RX_streams\":8,\"bytes_per_stream\":50000,\"FIFO_char_capacity\":8,\"delay_model_us\":%.3f,\"actual_production_adapter\":true,\"vendor_ISR_calls\":0,\"hardware_commands\":0}\n",cases,8*10./921600*1e6);
}
