// Candidate for AT32F403RCT6 BSMCE04U only. Not flashed or physically qualified.
// PC6 -> existing OUT1 optocoupler; PC11 low -> existing USB pull-up switch.
// GPIO map comes from the BSMCE04U grblHAL board map; verify this actual revision.
#include "at32f403.h"
#include "usbd_core.h"
#include "usbd_int.h"
#include "cdc_class.h"
#include "cdc_desc.h"
#include "permit_protocol.h"
#include <stdio.h>

static PermitProtocol protocol;
static usbd_core_type usb_device;
static volatile uint32_t ticks=0;
static char input[65],tx[64];
static uint8_t packet[64];
static unsigned used=0;
static bool discard=false;
extern "C" void _init(){}
extern "C" void _fini(){}

static void output(bool on){gpio_bits_write(GPIOC,GPIO_PINS_6,on?TRUE:FALSE);}
static void output_pin(gpio_type *port,uint16_t pins,bool high){
  gpio_init_type cfg;gpio_default_para_init(&cfg);
  gpio_bits_write(port,pins,high?TRUE:FALSE);
  cfg.gpio_mode=GPIO_MODE_OUTPUT;cfg.gpio_out_type=GPIO_OUTPUT_PUSH_PULL;
  cfg.gpio_drive_strength=GPIO_DRIVE_STRENGTH_MODERATE;
  cfg.gpio_pins=pins;cfg.gpio_pull=GPIO_PULL_NONE;gpio_init(port,&cfg);
}
static void safe_gpio(){
  crm_periph_clock_enable(CRM_GPIOA_PERIPH_CLOCK,TRUE);
  crm_periph_clock_enable(CRM_GPIOB_PERIPH_CLOCK,TRUE);
  crm_periph_clock_enable(CRM_GPIOC_PERIPH_CLOCK,TRUE);
  output_pin(GPIOC,GPIO_PINS_6|GPIO_PINS_7|GPIO_PINS_8|GPIO_PINS_9,false);
  output_pin(GPIOA,GPIO_PINS_8,false);       // no AVI/PWM
  output_pin(GPIOB,GPIO_PINS_10,true);       // disable the STEP/DIR buffer
}
static void fail_stop(){protocol.stop();output(false);}

extern "C" void SysTick_Handler(){++ticks;}
extern "C" void HardFault_Handler(){fail_stop();for(;;){}}
extern "C" void MemManage_Handler(){fail_stop();for(;;){}}
extern "C" void BusFault_Handler(){fail_stop();for(;;){}}
extern "C" void UsageFault_Handler(){fail_stop();for(;;){}}
extern "C" void USBFS_L_CAN1_RX0_IRQHandler(){usbd_irq_handler(&usb_device);}
extern "C" void usb_delay_ms(uint32_t ms){
  uint32_t start=ticks;while(uint32_t(ticks-start)<ms){} // startup only, permit remains low
}
extern "C" void usb_delay_us(uint32_t us){
  for(uint32_t n=0;n<us;++n)for(volatile unsigned k=0;k<12;++k)__NOP();
}

static void clock72(){
  crm_clock_source_enable(CRM_CLOCK_SOURCE_HEXT,TRUE);
  if(crm_hext_stable_wait()!=SUCCESS)for(;;){} // IWDG resets; no permit
  crm_ahb_div_set(CRM_AHB_DIV_1);crm_apb1_div_set(CRM_APB1_DIV_2);
  crm_apb2_div_set(CRM_APB2_DIV_1);
  crm_pll_config(CRM_PLL_SOURCE_HEXT,CRM_PLL_MULT_9,CRM_PLL_OUTPUT_RANGE_LE72MHZ);
  crm_clock_source_enable(CRM_CLOCK_SOURCE_PLL,TRUE);
  while(crm_flag_get(CRM_PLL_STABLE_FLAG)==RESET){}
  crm_sysclk_switch(CRM_SCLK_PLL);
  while(crm_sysclk_switch_status_get()!=CRM_SCLK_PLL){}
  system_core_clock_update();
  if(system_core_clock!=72000000)for(;;){}
  if(SysTick_Config(system_core_clock/1000))for(;;){}
}

static void send_body(const char *body){
  if(usb_device.conn_state!=USB_CONN_STATE_CONFIGURED)return;
  auto *cdc=static_cast<cdc_struct_type *>(usb_device.class_handler->pdata);
  if(!cdc||!cdc->g_tx_completed)return; // never block the lease/output update
  unsigned len=unsigned(snprintf(tx,sizeof(tx),"%s %04X\n",body,lease_crc(body)));
  if(len>=sizeof(tx))return;
  usb_vcp_send_data(&usb_device,reinterpret_cast<uint8_t *>(tx),uint16_t(len));
}
static void send_value(const char *kind,uint32_t value){
  char body[24];snprintf(body,sizeof(body),"%s %08lX",kind,(unsigned long)value);send_body(body);
}
static void consume(uint8_t byte){
  if(byte=='\r')return;
  if(byte!='\n'){
    if(discard)return;
    if(used<64)input[used++]=char(byte);else{used=0;discard=true;fail_stop();}
    return;
  }
  if(discard){used=0;discard=false;return;}
  input[used]=0;used=0;uint32_t value=0;
  int reply=protocol.receive(input,ticks,value);
  output(protocol.permit(ticks)); // LOW before OFF; set GPIO before acknowledging OK
  if(reply==1)send_body("ID " RNR_IMAGE_ID);
  else if(reply==2)send_value("OFF",0);
  else if(reply==3)send_value("OK",value);
}

extern "C" int main(){
  safe_gpio();
  wdt_register_write_enable(TRUE);wdt_divider_set(WDT_CLK_DIV_64);
  wdt_reload_value_set(312);wdt_counter_reload();wdt_enable(); // ~501 ms at nominal 40kHz LICK
  clock72();nvic_priority_group_config(NVIC_PRIORITY_GROUP_4);
  crm_usb_clock_div_set(CRM_USB_DIV_1_5);
  crm_periph_clock_enable(CRM_USB_PERIPH_CLOCK,TRUE);
  nvic_irq_enable(USBFS_L_CAN1_RX0_IRQn,1,0);
  usbd_core_init(&usb_device,USB,&cdc_class_handler,&cdc_desc_handler,0);
  output_pin(GPIOC,GPIO_PINS_11,false); // active-low D+ connection on the red-board map
  usbd_connect(&usb_device);
  uint32_t next_question=ticks,last_feed=ticks;
  for(;;){
    uint32_t now=ticks;output(protocol.permit(now));
    // Feed only on a changing tick. A stopped SysTick must also cause IWDG reset.
    if(now!=last_feed){wdt_counter_reload();last_feed=now;}
    if(usb_device.conn_state!=USB_CONN_STATE_CONFIGURED){
      fail_stop();used=0;discard=false;continue;
    }
    uint16_t count=usb_vcp_get_rxdata(&usb_device,packet);
    if(count>sizeof(packet)){fail_stop();continue;}
    for(unsigned i=0;i<count;++i)consume(packet[i]);
    now=ticks;
    if(int32_t(now-next_question)>=0){
      if(protocol.issue(now))send_value("Q",protocol.lease.nonce);
      next_question=now+125;
    }
    output(protocol.permit(now));
  }
}
