#include <array>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <algorithm>
#include "uart_v3_transport.h"
static unsigned checks;
static void check(bool v,const char *s){++checks;if(!v){fprintf(stderr,"FAIL %s\n",s);exit(1);}}
static uint64_t sim_us;
static uint32_t tick_base;
static bool outputs_on;
static bool mic_last_control_reply_safe_off;
static std::vector<uint8_t> wire;
struct Tdr {
  uint32_t value;
  Tdr &operator=(uint32_t v){value=v;wire.push_back((uint8_t)v);return *this;}
};
struct Usart {uint32_t CR1,CR3,ISR,ICR;Tdr TDR;} usart;
struct Channel {uint32_t CCR,CNDTR,CPAR,CMAR;} channel;
struct Dma {uint32_t ISR,IFCR;} dma;
struct DMA_HandleTypeDef {Channel *Instance;struct {unsigned Request,Direction,PeriphInc,MemInc,PeriphDataAlignment,MemDataAlignment,Mode,Priority;} Init;};
struct UART_HandleTypeDef {Usart *Instance;unsigned gState,ErrorCode,TxXferSize,TxXferCount;struct{unsigned WordLength,Parity;} Init;};
static UART_HandleTypeDef huart1;
enum {HAL_OK=0,HAL_ERROR=1,HAL_BUSY=2,HAL_TIMEOUT=3,USART1_IRQn=1,DMA1_Channel1_IRQn=2,
 USART_CR1_TCIE=64,USART_CR3_DMAT=128,UART_FLAG_TC=64,USART_ICR_TCCF=64,
 DMA_CCR_EN=1,DMA_CCR_TEIE=8,DMA_REQUEST_USART1_TX=25,DMA_MEMORY_TO_PERIPH=16,
 DMA_PINC_DISABLE=0,DMA_MINC_ENABLE=128,DMA_PDATAALIGN_BYTE=0,DMA_MDATAALIGN_BYTE=0,
 DMA_NORMAL=0,DMA_PRIORITY_HIGH=8192,UNO_REPLY_TIMEOUT_MS=5,
 HAL_UART_STATE_READY=32,HAL_UART_STATE_BUSY_TX=33,HAL_UART_ERROR_NONE=0,
 UART_WORDLENGTH_9B=9,UART_PARITY_NONE=0,UART_FLAG_TXE=128,RESET=0};
using HAL_StatusTypeDef=int;
#define DMA1 (&dma)
#define DMA1_Channel1 (&channel)
#define TIM1 nullptr
#define __DMB() ((void)0)
#define __HAL_RCC_DMA1_CLK_ENABLE() ((void)0)
#define MIC_UART_TX_DMA_ACK(mask) do {dma.IFCR=(mask);dma.ISR&=~(mask);}while(0)
static void HAL_NVIC_DisableIRQ(int x){check(x==1||x==2,"mask only UART/TX DMA IRQ");}
static void HAL_NVIC_EnableIRQ(int x){check(x==1||x==2,"unmask only UART/TX DMA IRQ");}
static void HAL_NVIC_SetPriority(int x,unsigned p,unsigned sub){check(x==2&&p==3&&sub==0,"TX DMA priority retains RX priority below motor protection");}
static void HAL_NVIC_ClearPendingIRQ(int x){check(x==2,"clear only new TX DMA IRQ");}
static uint32_t HAL_GetTick(){return tick_base+(uint32_t)(sim_us/1000);}
static int HAL_DMA_Init(DMA_HandleTypeDef *h){
 check(h->Instance==&channel&&h->Init.Request==25&&h->Init.Direction==16,"dedicated USART1 TX DMAMUX channel");
 check(h->Init.PeriphDataAlignment==0&&h->Init.MemDataAlignment==0&&h->Init.Mode==0,"normal byte to byte DMA");
 channel.CCR=h->Init.Direction|h->Init.MemInc|h->Init.Priority;return HAL_OK;
}
static void Error_Handler(){check(false,"HAL init must succeed");}
[[maybe_unused]] static void LL_TIM_DisableAllOutputs(decltype(nullptr)){outputs_on=false;}
#include "driver.inc"

static void settle(){if(usart.ICR&USART_ICR_TCCF)usart.ISR&=~UART_FLAG_TC;usart.ICR=0;}
static void reset(){
 memset((void*)&mic_uart_tx,0,sizeof(mic_uart_tx));
 memset(&usart,0,sizeof(usart));memset(&channel,0,sizeof(channel));memset(&dma,0,sizeof(dma));
 huart1={};huart1.Instance=&usart;huart1.gState=HAL_UART_STATE_READY;
 sim_us=0;tick_base=0;wire.clear();outputs_on=false;mic_last_control_reply_safe_off=false;
 uno_tx_init();
}
using Frame=std::array<uint8_t,UV3_FRAME>;
static Frame frame(unsigned seq,unsigned kind=3){
 Frame f{};f[0]=0x55;f[1]=0xaa;f[2]=(uint8_t)kind;f[3]=9;f[4]=(uint8_t)seq;
 for(unsigned i=5;i<UV3_PAYLOAD;++i){f[i]=(uint8_t)(i*17+seq);}
 uv3_seal(f.data());return f;
}
static void dma_byte(bool tc_irq=true){
 settle();check(mic_uart_tx.active&&channel.CNDTR>0,"DMA active remaining bytes");
 check((channel.CCR&DMA_CCR_EN)&&(usart.CR3&USART_CR3_DMAT),"DMA still enabled");
 unsigned slot=mic_uart_tx.tail&3,index=UV3_FRAME-channel.CNDTR;
 check(channel.CMAR==(uint32_t)(uintptr_t)&mic_uart_tx.bytes[slot][0],"DMA points to immutable owned frame");
 wire.push_back((uint8_t)mic_uart_tx.bytes[slot][index]);--channel.CNDTR;sim_us+=87;
 if(channel.CNDTR==0){usart.ISR|=UART_FLAG_TC;if(tc_irq)uno_tx_tc_isr();settle();}
}
static void drain(){unsigned limit=0;while(mic_uart_tx.active){dma_byte();check(++limit<10000,"bounded drain");}}
static void equals(const std::vector<Frame>&f){
 check(wire.size()==f.size()*UV3_FRAME,"exact full-frame length");
 for(unsigned i=0;i<f.size();++i){check(!memcmp(wire.data()+i*UV3_FRAME,f[i].data(),UV3_FRAME),"ordered full bytes including CRC");check(uv3_crc_ok(wire.data()+i*UV3_FRAME),"wire CRC32C intact");}
}

/* The unchanged ST HAL transmitter is extracted verbatim for reproduction.
   Only hardware/timing are mocked; one main-thread preemption is injected. */
static bool old_pause;
static HAL_StatusTypeDef UART_WaitOnFlagUntilTimeout(UART_HandleTypeDef *h,unsigned flag,unsigned,uint32_t start,unsigned timeout){
 if(old_pause&&h->TxXferCount==4){sim_us+=3000;old_pause=false;}
 if(flag==UART_FLAG_TXE&&h->TxXferCount<43)sim_us+=87;
 if(flag==UART_FLAG_TC)sim_us+=87;
 return (uint32_t)(HAL_GetTick()-start)>timeout?HAL_TIMEOUT:HAL_OK;
}
#include "old_hal_transmit.inc"

int main(){
 // Reproduce the observed 39-byte prefix, then next header in the CRC slot.
 reset();auto first=frame(246),second=frame(247);old_pause=true;
 check(HAL_UART_Transmit(&huart1,first.data(),43,5)==HAL_TIMEOUT,"old 5-ms blocking HAL abort reproduced");
 check(wire.size()==39,"old HAL leaves four CRC bytes unsent");
 check(HAL_UART_Transmit(&huart1,second.data(),43,5)==HAL_OK,"old next reply starts after incomplete frame");
 check(!memcmp(wire.data()+39,second.data(),4)&&!uv3_crc_ok(wire.data()),"next header lands in rejected reply CRC slot");

 // With DMA, main may be absent for 18 ms while all bytes still leave UART.
 reset();check(uno_tx_submit(first.data(),UNO_TX_TAG_OFF)==HAL_OK,"enqueue full reply");
 settle();check(!mic_last_control_reply_safe_off,"not OFF-confirmed before physical TC");
 drain();sim_us=18000;check(uno_tx_watchdog(HAL_GetTick())==HAL_OK,"main pause cannot abort completed DMA frame");
 check(mic_last_control_reply_safe_off&&mic_uart_tx.completed==1,"OFF published after last stop bit");equals({first});

 // Queue ownership, ordering, full rejection and source lifetime.
 reset();std::vector<Frame> expected;
 for(unsigned i=0;i<4;++i){auto f=frame(i,i%2?0xd2:3);expected.push_back(f);check(uno_tx_submit(f.data(),i?UNO_TX_TAG_DIAG:UNO_TX_TAG_ON)==HAL_OK,"four bounded frame slots");f.fill(0);}
 auto rejected=frame(99);unsigned head=mic_uart_tx.head,remaining=channel.CNDTR;
 check(uno_tx_submit(rejected.data(),0)==HAL_BUSY,"queue full rejects whole packet");
 check(mic_uart_tx.head==head&&channel.CNDTR==remaining,"queue overflow never changes active frame");drain();equals(expected);
 check(!mic_last_control_reply_safe_off,"diagnostics do not manufacture OFF confirmation");

 // Retain 5-ms failure deadline; do not cancel DMA or splice next packet.
 reset();uno_tx_submit(first.data(),2);settle();for(unsigned i=0;i<39;++i)dma_byte();
 sim_us=5000;check(uno_tx_watchdog(HAL_GetTick())==HAL_OK,"five-ms boundary unchanged");
 sim_us=6000;unsigned saved_remaining=channel.CNDTR;
 check(uno_tx_watchdog(HAL_GetTick())==HAL_TIMEOUT,"six-ms real TX stall still trips");
 check(channel.CNDTR==saved_remaining&&(channel.CCR&1)&&(usart.CR3&128),"timeout does not abort active DMA or CRC tail");
 check(uno_tx_watchdog(HAL_GetTick())==HAL_OK&&mic_uart_tx.timeouts==1,"stall reported once per frame");
 check(!uno_tx_clear_ready(),"CLEAR cannot release TX while frame still pending");
 uno_tx_submit(second.data(),2);drain();equals({first,second});check(uno_tx_clear_ready(),"CLEAR only after complete idle transport");

 // Early TC between bytes cannot advance the frame queue.
 reset();uno_tx_submit(first.data(),2);settle();for(unsigned i=0;i<13;++i)dma_byte();
 usart.ISR|=64;uno_tx_tc_isr();settle();
 check(mic_uart_tx.tail==0&&mic_uart_tx.active&&channel.CNDTR==30&&mic_uart_tx.early_tc==1,"early TC retains unfinished packet");drain();equals({first});

 // DMA hardware error, including competing TC, immediately disables outputs.
 for(unsigned mode=0;mode<2;++mode){
  reset();outputs_on=true;uno_tx_submit(first.data(),1);settle();for(unsigned i=0;i<7;++i)dma_byte();
  dma.ISR=8;if(mode){usart.ISR|=64;uno_tx_tc_isr();}else DMA1_Channel1_IRQHandler();
  check(!outputs_on&&mic_uart_tx.hard_error&&mic_uart_tx.tail==0,"DMA error stops PWM without false completion");
  check(uno_tx_watchdog(HAL_GetTick())==HAL_ERROR,"DMA error reported to main safety latch");
  check(uno_tx_submit(second.data(),2)==HAL_ERROR&&!uno_tx_clear_ready(),"no retry or CLEAR through hard DMA fault");
 }

 // Counter and millisecond wraparound.
 reset();mic_uart_tx.head=mic_uart_tx.tail=UINT32_MAX-1;tick_base=UINT32_MAX-2;
 uno_tx_submit(first.data(),2);drain();uno_tx_submit(second.data(),2);drain();equals({first,second});
 check(mic_uart_tx.tail==0&&uno_tx_watchdog(HAL_GetTick())==HAL_OK,"head/tail/tick rollover");

 // Vary main scheduling and TC latency while retaining exact complete bytes.
 for(unsigned seed=0;seed<256;++seed){
  reset();std::vector<Frame> sent;
  for(unsigned n=0;n<8;++n){auto f=frame(seed+n,n%3?3:0xd3);sent.push_back(f);check(uno_tx_submit(f.data(),n%2?0:2)==HAL_OK,"stress enqueue");
   unsigned count=0;while(channel.CNDTR){dma_byte(false);if(++count==39)sim_us+=(seed%7)*10;}
   sim_us+=seed%100;uno_tx_tc_isr();settle();
   sim_us+=(seed%5)*1000;check(uno_tx_watchdog(HAL_GetTick())==HAL_OK,"main scheduling after DMA completion");
  }equals(sent);
 }
 printf("{\"pass\":true,\"checks\":%u,\"old_prefix_bytes\":39,\"dma_stress_frames\":2048}\n",checks);
}
