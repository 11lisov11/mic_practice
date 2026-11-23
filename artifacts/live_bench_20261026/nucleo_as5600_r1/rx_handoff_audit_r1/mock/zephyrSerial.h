#pragma once
#include <zephyr/drivers/uart.h>
namespace arduino {
class ZephyrSerial {
public:
 explicit ZephyrSerial(const device*d):uart(d){}
 void begin(unsigned long){}
 virtual int available(){return static_cast<int>(rx.size());}
 virtual int read(){if(rx.empty())return -1;int v=rx.front();rx.pop_front();return v;}
 virtual int peek(){return rx.empty()?-1:rx.front();}
protected:
 const device*uart;
 std::deque<unsigned char>rx;
 void IrqHandler(){
  if(late_byte>=0){fifo.push_back(static_cast<unsigned char>(late_byte));late_byte=-1;}
  unsigned char b[8];int n;
  while(uart_irq_rx_ready(uart)&&(n=uart_fifo_read(uart,b,8))>0)
   for(int i=0;i<n;++i)rx.push_back(b[i]);
 }
};
}
