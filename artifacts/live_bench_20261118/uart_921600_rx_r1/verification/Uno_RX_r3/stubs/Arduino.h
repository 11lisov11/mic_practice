
#pragma once
#include <cstddef>
#include <cstdint>
using std::size_t;
struct device{};
#define SERIAL_8N1 0
unsigned irq_lock();void irq_unlock(unsigned);uint32_t micros();uint32_t k_cycle_get_32();
class Print {public:virtual ~Print(){};virtual size_t write(uint8_t)=0;virtual size_t write(const uint8_t*,size_t)=0;};
