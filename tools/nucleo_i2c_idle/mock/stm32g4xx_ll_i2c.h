#pragma once
#define LL_I2C_ADDRSLAVE_7BIT 0U
#define LL_I2C_MODE_SOFTEND 0U
#define LL_I2C_MODE_AUTOEND (1U<<25)
#define LL_I2C_GENERATE_START_WRITE (1U<<13)
#define LL_I2C_GENERATE_START_READ ((1U<<13)|(1U<<10))
static inline void LL_I2C_HandleTransfer(I2cRegs*r,uint32_t a,uint32_t m,uint32_t n,uint32_t end,uint32_t start){(void)m;r->CR2=a|(n<<16)|end|start;}
static inline void LL_I2C_TransmitData8(I2cRegs*r,uint8_t b){r->TXDR=b;}
static inline uint8_t LL_I2C_ReceiveData8(I2cRegs*r){return (uint8_t)r->RXDR;}
