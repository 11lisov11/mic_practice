#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <algorithm>
#include <stdexcept>
inline uint32_t fake_ms=0;
inline uint32_t millis(){return fake_ms;}
inline void delay(uint32_t n){fake_ms+=n;if(fake_ms>10000)throw std::runtime_error("unbounded wait");}
class Stream {
public:
 virtual ~Stream()=default;
 virtual int available()=0;
 virtual int availableForWrite()=0;
 virtual size_t write(const uint8_t*,size_t)=0;
 size_t write(const char*s){return write(reinterpret_cast<const uint8_t*>(s),std::strlen(s));}
 virtual size_t readBytes(uint8_t*,size_t)=0;
 void setTimeout(unsigned){}
};
class HardwareSerial:public Stream {
public:
 void begin(unsigned long){}
 explicit operator bool()const{return true;}
};
