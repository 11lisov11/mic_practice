#pragma once
#include <Arduino.h>
#include <zephyrSerial.h>
#include <zephyr/drivers/uart.h>
#include <stm32_ll_usart.h>
#include "bounded_rx.h"

/* Dedicated owner of USART1 D0/D1. No vendor RX/TX ring, semaphore or yield in
 * IRQ. Hardware FIFO8 absorbs brief IRQ deferral; each RDR word is preceded by
 * an error-status read. Hardware/software loss is fail-closed until next boot,
 * with monotonic counters; it cannot be hidden by a fresh CRC-valid reply.
 */
class NucleoBufferedSerial : public arduino::ZephyrSerial {
 public:
  struct Stats {uint32_t dropped,errors,error_flags,high_water,pending,rescued;
    uint32_t fifo_enabled,max_batch,max_irq_cycles,max_lock_cycles,tx_rejected,tx_pending;};
  explicit NucleoBufferedSerial(const device*dev):ZephyrSerial(dev){}
  void begin(unsigned long baud){begin(baud,SERIAL_8N1);}
  void begin(unsigned long baud,uint16_t conf){
    if(begun)return;begun=true; /* never clear a live fault by reinitializing */
    uart_irq_rx_disable(uart);LL_USART_DisableIT_TXE_TXFNF(regs());uart_irq_err_disable(uart);
    LL_USART_DisableIT_TC(regs()); /* Installed Zephyr TX API controls TC, not TXE. */
    struct uart_config cfg={};cfg.baudrate=baud;cfg.parity=UART_CFG_PARITY_NONE;
    cfg.stop_bits=UART_CFG_STOP_BITS_1;cfg.data_bits=UART_CFG_DATA_BITS_8;cfg.flow_ctrl=UART_CFG_FLOW_CTRL_NONE;
    if(conf!=SERIAL_8N1||zephyr::arduino::init_dev_apply_pinctrl(uart)!=0||uart_configure(uart,&cfg)!=0){fail(0x80000000U);return;}
    unsigned key=irq_lock();
    LL_USART_Disable(regs());
    LL_USART_EnableFIFO(regs());
    LL_USART_SetRXFIFOThreshold(regs(),LL_USART_FIFOTHRESHOLD_1_8);
    LL_USART_SetTXFIFOThreshold(regs(),LL_USART_FIFOTHRESHOLD_1_8);
    LL_USART_Enable(regs());
    fifo=(regs()->CR1&USART_CR1_FIFOEN)!=0;
    if(!fifo){fail(0x80000000U);irq_unlock(key);return;}
    uart_irq_callback_user_data_set(uart,dispatch,this);
    uart_irq_err_enable(uart);uart_irq_rx_enable(uart);ready=true;
    irq_unlock(key);
  }
  int available()override{unsigned k=irq_lock();int n=rxq.count;irq_unlock(k);return n;}
  int read()override{return read_byte(true);}
  int peek()override{return read_byte(false);}
  int availableForWrite(){unsigned k=irq_lock();int n=ready&&!fault?128-txq.count:0;irq_unlock(k);return n;}
  using Print::write;
  size_t write(uint8_t b)override{return write(&b,1);}
  size_t write(const uint8_t*data,size_t size)override{
    /* Whole packet or zero: never transmit a truncated command. Backpressure
     * waits only in foreground, with IRQs ENABLED, and is bounded to2ms.
     * The independent native observer-age2ms guard is untouched. */
    uint32_t wait_begin=micros();
    for(;;){
      unsigned k=irq_lock();uint32_t started=k_cycle_get_32();
      if(!ready||fault||!data||size>128U){
        if(tx_rejected!=UINT32_MAX)++tx_rejected;irq_unlock(k);return 0;
      }
      if(size<=128U-txq.count){
        for(size_t i=0;i<size;++i)txq.put(data[i]);
        if(size)LL_USART_EnableIT_TXE_TXFNF(regs());
        maximum(max_lock_cycles,k_cycle_get_32()-started);irq_unlock(k);return size;
      }
      irq_unlock(k);
      if((uint32_t)(micros()-wait_begin)>=2000U){
        k=irq_lock();if(tx_rejected!=UINT32_MAX)++tx_rejected;fail(0x20000U);
        LL_USART_DisableIT_TXE_TXFNF(regs());irq_unlock(k);return 0;
      }
    }
  }
  void flush(){
    uint32_t start=micros();
    while(txq.count||!LL_USART_IsActiveFlag_TC(regs())){
      if((uint32_t)(micros()-start)>2000U){unsigned k=irq_lock();fail(0x80000U);irq_unlock(k);return;}
    }
  }
  void end(){unsigned k=irq_lock();uart_irq_rx_disable(uart);LL_USART_DisableIT_TXE_TXFNF(regs());uart_irq_err_disable(uart);ready=false;irq_unlock(k);}
  Stats stats(){
    unsigned k=irq_lock();Stats s={rxq.dropped,errors,error_flags,rxq.high_water,rxq.count,0,
      fifo,max_batch,max_irq_cycles,max_lock_cycles,tx_rejected,txq.count};irq_unlock(k);return s;
  }
 private:
  BoundedRx<1024> rxq;BoundedRx<128> txq;
  uint32_t errors=0,error_flags=0,max_batch=0,max_irq_cycles=0,max_lock_cycles=0,tx_rejected=0;
  bool begun=false,ready=false,fault=false,fifo=false;
  static USART_TypeDef*regs(){
    return reinterpret_cast<USART_TypeDef*>(DT_REG_ADDR(DT_PHANDLE_BY_IDX(DT_PATH(zephyr_user),serials,0)));
  }
  static void maximum(uint32_t&x,uint32_t y){if(y>x)x=y;}
  void fail(uint32_t flags){
    if(errors!=UINT32_MAX)++errors;error_flags|=flags;fault=true;
    rxq.head=rxq.tail=rxq.count=0; /* poisoned prefix cannot become a valid reply */
  }
  int read_byte(bool consume){unsigned k=irq_lock();int v=rxq.read(consume);irq_unlock(k);return v;}
  static void dispatch(const device*,void*arg){static_cast<NucleoBufferedSerial*>(arg)->receive_irq();}
  void receive_irq(){
    uint32_t started=k_cycle_get_32();unsigned batch=0;
    /* Bounded IRQ body; 32 words is four FIFO depths. It never waits for a byte. */
    for(unsigned i=0;i<32U;++i){
      uint32_t s=regs()->ISR;
      uint32_t e=s&(USART_ISR_PE|USART_ISR_FE|USART_ISR_NE|USART_ISR_ORE);
      if(e){
        uint32_t flags=((e&USART_ISR_ORE)?UART_ERROR_OVERRUN:0U)|((e&USART_ISR_PE)?UART_ERROR_PARITY:0U)|
          ((e&USART_ISR_FE)?UART_ERROR_FRAMING:0U)|((e&USART_ISR_NE)?0x10000U:0U);
        fail(flags);regs()->ICR=e;
      }
      if(!(s&USART_ISR_RXNE_RXFNE))break;
      uint8_t b=(uint8_t)regs()->RDR;++batch;
      if(!fault&&!rxq.put(b)){fault=true;rxq.head=rxq.tail=rxq.count=0;}
    }
    /* A byte arriving AFTER an empty read just schedules the next IRQ.
     * Only exhausting the32-word budget with data still pending is a fault. */
    if(batch==32U&&(regs()->ISR&USART_ISR_RXNE_RXFNE))fail(0x40000U);
    maximum(max_batch,batch);
    if(fault){uart_irq_rx_disable(uart);uart_irq_err_disable(uart);LL_USART_DisableIT_TXE_TXFNF(regs());}
    else if(regs()->CR1&USART_CR1_TXEIE_TXFNFIE){
      for(unsigned i=0;i<8U&&txq.count&&(regs()->ISR&USART_ISR_TXE_TXFNF);++i)
        regs()->TDR=(uint8_t)txq.read();
      if(!txq.count)LL_USART_DisableIT_TXE_TXFNF(regs());
    }
    maximum(max_irq_cycles,k_cycle_get_32()-started);
  }
};
