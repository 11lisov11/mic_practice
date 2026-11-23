
#pragma once
#include <Arduino.h>
#include <cstdlib>
namespace zephyr {namespace arduino {int init_dev_apply_pinctrl(const device*);}}
namespace arduino {
class ZephyrSerial:public Print {protected:const device*uart;public:
 explicit ZephyrSerial(const device*d):uart(d){}
 virtual void begin(unsigned long){std::abort();}virtual void begin(unsigned long,uint16_t){std::abort();}
 virtual int available(){std::abort();}virtual int read(){std::abort();}virtual int peek(){std::abort();}
 virtual size_t write(uint8_t){std::abort();}virtual size_t write(const uint8_t*,size_t){std::abort();}
 void IrqHandler(){std::abort();}
};}
