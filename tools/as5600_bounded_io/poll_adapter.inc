struct PollIo {
  uint32_t waits=0;
  static void claim() {
    LL_I2C_Disable(I2C2);
    CLEAR_BIT(I2C2->CR1,I2C_CR1_TXIE|I2C_CR1_RXIE|I2C_CR1_TCIE|I2C_CR1_STOPIE|
      I2C_CR1_NACKIE|I2C_CR1_ERRIE|I2C_CR1_TXDMAEN|I2C_CR1_RXDMAEN);
    I2C2->CR2=0;
    I2C2->ICR=I2C_ICR_NACKCF|I2C_ICR_STOPCF|I2C_ICR_BERRCF|I2C_ICR_ARLOCF|I2C_ICR_OVRCF;
    LL_I2C_Enable(I2C2);
  }
  uint32_t now_us() {return micros();}
  uint32_t status() {return I2C2->ISR;}
  bool lines_high() {return (GPIOB->IDR & (3U<<10))==(3U<<10);}
  void wait_step() {k_busy_wait(1);if((++waits&31U)==0)k_yield();}
  void clear() {I2C2->ICR=I2C_ICR_NACKCF|I2C_ICR_STOPCF|I2C_ICR_BERRCF|I2C_ICR_ARLOCF|I2C_ICR_OVRCF;}
  void begin_write() {LL_I2C_HandleTransfer(I2C2,0x6c,LL_I2C_ADDRSLAVE_7BIT,1,LL_I2C_MODE_SOFTEND,LL_I2C_GENERATE_START_WRITE);}
  void write_data(uint8_t x) {LL_I2C_TransmitData8(I2C2,x);}
  void begin_read() {LL_I2C_HandleTransfer(I2C2,0x6c,LL_I2C_ADDRSLAVE_7BIT,3,LL_I2C_MODE_AUTOEND,LL_I2C_GENERATE_START_READ);}
  uint8_t read_data() {return LL_I2C_ReceiveData8(I2C2);}
  void reset() {claim();} // PE reset only; no recovery pulses on external wires.
};
