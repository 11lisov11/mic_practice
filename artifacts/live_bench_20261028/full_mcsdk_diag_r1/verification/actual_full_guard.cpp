#include <cstdint>
#include <cstdio>
#include <cstdlib>
static bool active;
static bool mic_load_active(){return active;}
enum {UNO_MODE_OFF=0,UNO_FLAG_ENABLE=1,UNO_FLAG_CLEAR_FAULT=8,UNO_LINK_TIMEOUT_MS=300};
static uint32_t tick;static uint32_t HAL_GetTick(){return tick;}
static uint32_t uno_rx_errors,uno_rx_overflow,full_uart_faults;
static struct {uint32_t last_valid_ms,bad_count;bool link_seen;}uno_link;
static struct {uint32_t fault;}uno_transport;
static struct {uint32_t timeouts,dma_errors,full_errors;}mic_uart_tx;
static volatile uint32_t full_tasks[4],full_commands[2];
void mic_full_task(unsigned i){
 if(i<4 && mic_load_active())++full_tasks[i];
}
void mic_full_command(uint8_t flags,uint8_t mode){
 (void)flags;(void)mode;
 ++full_commands[0];if(mic_load_active())++full_commands[1];
}
uint32_t mic_full_guard(void){
 /* Preserve the native transport fault latch; diagnostics never CLEAR it. */
 if(uno_rx_errors || uno_rx_overflow || uno_link.bad_count || uno_transport.fault ||
    mic_uart_tx.timeouts || mic_uart_tx.dma_errors || mic_uart_tx.full_errors)full_uart_faults|=1U;
 const uint32_t now=HAL_GetTick(),stamp=uno_link.last_valid_ms;
 if(!uno_link.link_seen || (uint32_t)(now-stamp)>UNO_LINK_TIMEOUT_MS)full_uart_faults|=2U;
 return full_uart_faults?256U:0U;
}
static unsigned checks;static void test(bool b){++checks;if(!b)std::exit(1);}
int main(){
 uno_link.link_seen=true;uno_link.last_valid_ms=100;tick=399;test(mic_full_guard()==0);
 tick=400;test(mic_full_guard()==0);tick=401;test(mic_full_guard()==256);
 tick=100;test(mic_full_guard()==256);full_uart_faults=0;
 uno_link.last_valid_ms=0xfffffff0U;tick=0x10;test(mic_full_guard()==0);
 for(unsigned k=0;k<7;k++){
  full_uart_faults=0;uno_rx_errors=uno_rx_overflow=uno_link.bad_count=uno_transport.fault=0;
  mic_uart_tx={};uint32_t*fields[]={&uno_rx_errors,&uno_rx_overflow,&uno_link.bad_count,&uno_transport.fault,&mic_uart_tx.timeouts,&mic_uart_tx.dma_errors,&mic_uart_tx.full_errors};
  *fields[k]=1;test(mic_full_guard()==256);
 }
 for(unsigned n=0;n<10000;n++){active=n<5000;for(unsigned i=0;i<4;i++)mic_full_task(i);}
 for(unsigned i=0;i<4;i++){test(full_tasks[i]==5000);}
 active=true;mic_full_command(0,0);mic_full_command(1,1);mic_full_command(8,0);mic_full_command(2,0);
 test(full_commands[0]==4&&full_commands[1]==4);
 printf("{\"passed\":true,\"checks\":%u}\n",checks);
}
