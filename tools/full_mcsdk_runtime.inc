/* Included after the real UART/command implementation: counters only, no MMIO writes. */
#include "load_core.h"
volatile uint32_t mic_full_report[24];
volatile uint32_t mic_full_fixture_denials;
static volatile uint32_t full_tasks[4],full_commands[2];
static uint32_t full_publish_at,full_sequence,full_uart_faults;
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
void mic_full_init(void){full_publish_at=HAL_GetTick()-50U;}
void mic_full_publish(void){
 const uint32_t now=HAL_GetTick();
 if((uint32_t)(now-full_publish_at)<50U)return;
 full_publish_at=now;
 uint32_t r[24]={0};
 r[0]=0x31444d46U;r[1]=MIC_NUCLEO_FW_BUILD_ID;r[2]=1;r[3]=24;
 r[5]=bMCBootCompleted;r[6]=MC_GetSTMStateMotor1();r[7]=MC_GetCurrentFaultsMotor1();
 r[8]=MC_GetOccurredFaultsMotor1();r[9]=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
 r[10]=TIM1->BDTR;
 for(unsigned i=0;i<4;i++)r[11+i]=full_tasks[i];
 r[15]=full_commands[0];r[16]=full_commands[1];
 r[17]=uno_link.good_count;r[18]=uno_link.bad_count;
 r[19]=mic_full_fixture_denials;r[20]=full_uart_faults;
 full_sequence+=2;r[4]=full_sequence;r[21]=full_sequence;r[22]=ld_crc(r+5,16);r[23]=0x464d4445U;
 mic_full_report[4]=full_sequence|1U;__DMB();
 for(unsigned i=0;i<24;i++)if(i!=4)mic_full_report[i]=r[i];
 __DMB();mic_full_report[4]=full_sequence;
}
