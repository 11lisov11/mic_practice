"""Actual DMA/IDLE ISR host harness: latency, wrap, flags races, hard errors."""
import json,shutil,subprocess
import prepare_uart_921600_rx as p
from test_foc_update_latency_fix import function
def main():
 out=p.OUT/'verification/native_RX_r4';out.mkdir(parents=True,exist_ok=False)
 source=p.read(p.OUT/'nucleo/Src/main.c')
 code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include "uart_v3_transport.h"
enum {UNO_RX_SIZE=128,UNO_RX_MASK=127};
static volatile uint8_t uno_rx_bytes[128],uno_rx_marks[128],uno_rx_errors,uno_rx_overflow;
static volatile uint16_t uno_rx_head,uno_rx_tail;
static bool outputs;static unsigned checks,tx_calls,rdr_reads,ack_late;
static uint32_t dma_flags;
static void snapshot_race();
struct Remaining {uint32_t value=128;operator uint32_t(){snapshot_race();return value;}void operator=(uint32_t v){value=v;}};
struct Ack {void operator=(uint32_t v){if(ack_late){dma_flags|=0x20;ack_late=0;}if(v&0x10)dma_flags=0;else dma_flags&=~v;}};
struct Flags {operator uint32_t(){return dma_flags;}};
struct Dma {Flags ISR;Ack IFCR;} dma;
static Dma*DMA1=&dma;
struct Channel{uint32_t CCR=0,CPAR=0,CMAR=0;Remaining CNDTR;} ch;
static Channel*DMA1_Channel2=&ch;
struct Mux{uint32_t CCR;}mux;static Mux*DMAMUX1_Channel1=&mux;
struct RxRegister{operator uint32_t(){++rdr_reads;return 0;}};
struct Clear{void operator=(uint32_t);};
struct Uart {uint32_t ISR=0,CR3=0;RxRegister RDR;Clear ICR;}uart;
void Clear::operator=(uint32_t v){uart.ISR&=~v;}
struct Handle{Uart*Instance=&uart;}huart1;
static int timer;static int*TIM1=&timer;
static void LL_TIM_DisableAllOutputs(int*){outputs=false;}
#define __HAL_RCC_DMA1_CLK_ENABLE() ((void)0)
#define MIC_FOC_IRQ_SCOPE_NAMED(a,b) ((void)0)
#define DMA_CCR_MINC 128U
#define DMA_CCR_CIRC 32U
#define DMA_CCR_PL_1 8192U
#define DMA_CCR_HTIE 4U
#define DMA_CCR_TCIE 2U
#define DMA_CCR_TEIE 8U
#define DMA_CCR_EN 1U
#define DMA_REQUEST_USART1_RX 24U
#define USART_CR3_DMAR 64U
#define UART_FLAG_PE 1U
#define UART_FLAG_FE 2U
#define UART_FLAG_NE 4U
#define UART_FLAG_ORE 8U
#define UART_FLAG_IDLE 16U
#define UART_CLEAR_IDLEF 16U
enum{DMA1_Channel2_IRQn=12};
static void HAL_NVIC_SetPriority(int,unsigned a,unsigned b){assert(a==3&&!b);}
static void HAL_NVIC_ClearPendingIRQ(int){}
static void HAL_NVIC_EnableIRQ(int){}
static void __DMB(){}
static void uno_tx_tc_isr(){++tx_calls;}
static void during_copy();
PUSH
POP
#include "uart_rx_dma_native.inc"
static bool inject_race;
static void snapshot_race(){if(inject_race){inject_race=false;dma_flags|=0x20;ch.CNDTR.value=128;}}
static unsigned producer,overwrite_during_copy;
static std::vector<uint8_t> delivered;
static void reset(){
 dma_flags=0;producer=0;uno_rx_head=uno_rx_tail=0;uno_rx_errors=uno_rx_overflow=0;
 uart.ISR=uart.CR3=0;outputs=true;rdr_reads=0;delivered.clear();inject_race=false;ack_late=0;overwrite_during_copy=0;
 uno_rx_dma_init();assert(ch.CNDTR.value==128&&uart.CR3&64);
}
static void arrival(uint8_t b){
 mic_uart_rx_dma[producer&127U]=b;++producer;
 unsigned pos=producer&127U;ch.CNDTR.value=pos?128-pos:128;
 if(pos==64)dma_flags|=0x40;if(pos==0)dma_flags|=0x20;
}
static void during_copy(){if(overwrite_during_copy){unsigned n=overwrite_during_copy;overwrite_during_copy=0;for(unsigned i=0;i<n;++i)arrival(0xee);}}
static void consume(){
 uint8_t b,m;while(uno_rx_pop(&b,&m)){assert(!m);delivered.push_back(b);}
}
static void irq(bool idle){if(idle){uart.ISR|=UART_FLAG_IDLE;USART1_IRQHandler();}else DMA1_Channel2_IRQHandler();}
int main(){
 unsigned streams=0;
 // 1..63character delays, 0..127 ring phases; entire byte sequence preserved.
 for(unsigned gap=1;gap<=63;++gap){
  reset();std::vector<uint8_t> expected;
  for(unsigned n=0;n<20000;++n){uint8_t b=(uint8_t)((n*73U)^gap);arrival(b);expected.push_back(b);
   if((n+1)%gap==0){irq((n/gap)&1U);consume();}}
  irq(true);consume();assert(delivered==expected&&!uno_rx_errors&&!uno_rx_overflow&&!rdr_reads);++streams;
 }
 // All short frame prefixes: no padding/phantom bytes, one ready frame only.
 uint8_t frame[UV3_FRAME]={0xaa,0x55,3};uv3_seal(frame);
 for(unsigned prefix=1;prefix<UV3_FRAME;++prefix){reset();uv3_rx parser;uv3_init(&parser,true);
  for(unsigned i=0;i<prefix;++i)arrival(frame[i]);irq(true);consume();assert(delivered.size()==prefix);
  for(auto b:delivered)assert(uv3_byte(&parser,b,0,1)==UV3_WAIT);
  for(unsigned i=prefix;i<UV3_FRAME;++i)arrival(frame[i]);irq(true);consume();
  unsigned ready=0;for(unsigned i=prefix;i<delivered.size();++i)if(uv3_byte(&parser,delivered[i],0,2)==UV3_READY)++ready;
  assert(ready==1);++checks;
 }
 // Any PE/FE/NE/ORE, including ambiguous DMA noise, poisons the whole batch.
 for(unsigned mask=1;mask<16;++mask){reset();for(auto b:frame)arrival(b);uart.ISR=mask|16;USART1_IRQHandler();consume();
  assert(uno_rx_errors==mask&&delivered.empty()&&mic_uart_rx_dma_diag.cursor==43);++checks;}
 // A full missed wrap must be explicit, never appear as an empty clean ring.
 for(unsigned n=128;n<=384;++n){reset();for(unsigned i=0;i<n;++i)arrival((uint8_t)i);irq(true);consume();
  assert(uno_rx_overflow&&delivered.empty()&&mic_uart_rx_dma_diag.gaps==1);++checks;}
 // DMA TE -> old immediate output-disable policy; RX data cannot enter parser.
 reset();arrival(1);dma_flags|=0x80;irq(false);consume();assert(!outputs&&uno_rx_errors==UV3_ORE&&delivered.empty());++checks;
 // Software ring at127: next byte is reported, not overwritten.
 reset();for(unsigned n=0;n<127;++n){arrival((uint8_t)n);irq(true);}arrival(255);irq(true);
 assert(uno_rx_overflow&&uno_rx_head!=uno_rx_tail);++checks;
 // CNDTR0/reload defers while keeping flags, then drains the actual8 bytes.
 reset();for(unsigned n=0;n<120;++n){arrival(n);irq(true);consume();}
 for(unsigned n=0;n<8;++n)arrival(200+n);ch.CNDTR.value=0;irq(false);
 assert(dma_flags&0x20);ch.CNDTR.value=128;irq(false);consume();assert(delivered.size()==128);++checks;
 // Snapshot boundary race: retry before acknowledging a newly arrived TC.
 reset();for(unsigned n=0;n<120;++n){arrival(n);irq(true);consume();}
 for(unsigned n=0;n<8;++n)arrival(200+n);dma_flags=0;ch.CNDTR.value=1;inject_race=true;irq(false);consume();
 assert(delivered.size()==128&&!uno_rx_errors&&!uno_rx_overflow);++checks;
 // An IRQ flag raised AFTER the snapshot is NOT cleared via GIF.
 reset();for(unsigned n=0;n<64;++n)arrival(n);ack_late=1;irq(false);assert(dma_flags&0x20);++checks;
 // New bytes overwrite an unread DMA prefix while CPU copy is preempted.
 reset();for(unsigned n=0;n<127;++n)arrival(n);overwrite_during_copy=12;irq(false);
 assert(uno_rx_overflow&&mic_uart_rx_dma_diag.gaps==1);++checks;
 printf("{\"passed\":true,\"latency_streams\":%u,\"bytes_per_stream\":20000,\"max_masked_model_us\":%.3f,\"fault_and_race_cases\":%u,\"actual_production_ISR\":true,\"hardware_commands\":0}\n",streams,63*10./921600*1e6,checks);
}
'''
 push=function(source,'uno_rx_push').replace('  uno_rx_head = next;','  uno_rx_head = next;during_copy();')
 code=code.replace('PUSH',push).replace('POP',function(source,'uno_rx_pop'))
 cpp=out/'actual_dma.cpp';p.write(cpp,code);exe=cpp.with_suffix('.exe')
 r=subprocess.run([shutil.which('g++'),'-O2','-std=c++17','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-Wno-unused-function',
  '-I',str(p.OUT/'nucleo/Inc'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'build.log',r.stdout+r.stderr);r.check_returncode()
 r=subprocess.run([str(exe)],capture_output=True,text=True);p.write(out/'run.log',r.stdout+r.stderr);r.check_returncode()
 report=json.loads(r.stdout);p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(r.stdout)
if __name__=='__main__':main()
