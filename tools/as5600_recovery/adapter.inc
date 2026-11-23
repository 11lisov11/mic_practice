struct PollSchedule {
  static void lock(){k_sched_lock();}
  static void unlock(){k_sched_unlock();}
};
struct PollIo {
  static void claim(){
    LL_I2C_Disable(I2C2);
    (void)LL_I2C_IsEnabled(I2C2); // Explicit PE readback, >=3APB cycles.
    k_busy_wait(2);
    CLEAR_BIT(I2C2->CR1,I2C_CR1_TXIE|I2C_CR1_RXIE|I2C_CR1_TCIE|I2C_CR1_STOPIE|
      I2C_CR1_NACKIE|I2C_CR1_ERRIE|I2C_CR1_TXDMAEN|I2C_CR1_RXDMAEN);
    I2C2->CR2=0;
    I2C2->ICR=I2C_ICR_NACKCF|I2C_ICR_STOPCF|I2C_ICR_BERRCF|I2C_ICR_ARLOCF|I2C_ICR_OVRCF;
    LL_I2C_Enable(I2C2);
  }
  uint32_t now_us(){return micros();}
  uint32_t status(){return I2C2->ISR;}
  uint32_t control(){return I2C2->CR2;}
  uint32_t line_bits(){return (GPIOB->IDR>>10)&3U;}
  bool lines_high(){return (GPIOB->IDR&(3U<<10))==(3U<<10);}
  void wait_step(){k_busy_wait(1);}
  void clear(){I2C2->ICR=I2C_ICR_NACKCF|I2C_ICR_STOPCF|I2C_ICR_BERRCF|I2C_ICR_ARLOCF|I2C_ICR_OVRCF;}
  void clear_berr(){I2C2->ICR=I2C_ICR_BERRCF;}
  void quiesce(){I2C2->CR2=0;}
  void begin_write(){LL_I2C_HandleTransfer(I2C2,0x6c,LL_I2C_ADDRSLAVE_7BIT,1,LL_I2C_MODE_SOFTEND,LL_I2C_GENERATE_START_WRITE);}
  void write_data(uint8_t b){LL_I2C_TransmitData8(I2C2,b);}
  void begin_read(){LL_I2C_HandleTransfer(I2C2,0x6c,LL_I2C_ADDRSLAVE_7BIT,3,LL_I2C_MODE_AUTOEND,LL_I2C_GENERATE_START_READ);}
  uint8_t read_data(){return LL_I2C_ReceiveData8(I2C2);}
  void reset(){claim();}
};
static uint32_t as5600_kernel_clock(){
  // This board's single DT clock entry is PCLK1. Do not infer an HSI/SYSCLK
  // selection from that entry: validate the actual RCC mux first.
  if(READ_BIT(RCC->CCIPR1,RCC_CCIPR1_I2C2SEL)!=0U)return 0;
  const uint32_t bus=DT_CLOCKS_CELL_BY_IDX(DT_NODELABEL(i2c2),0,bus);
  const struct stm32_pclken clock={bus&GENMASK(STM32_CLOCK_DIV_SHIFT-1,0),
      bus>>STM32_CLOCK_DIV_SHIFT,DT_CLOCKS_CELL_BY_IDX(DT_NODELABEL(i2c2),0,bits)};
  uint32_t hz=0;
  int rc=clock_control_get_rate(DEVICE_DT_GET(STM32_CLOCK_CONTROL_NODE),
      (clock_control_subsys_t)&clock,&hz);
  return rc?0:hz;
}
