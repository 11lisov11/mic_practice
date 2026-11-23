#include "main.h"
#include "nucleo_i2c_wire.h"
#include "wire_capture.h"
#include "nucleo_encoder.h"
/* No IRQ, GPIO output, I2C register write or callback. GPIO is read as a WORD
   and the low halfword stored, as with the existing SD sampler. TIM4/DMAMUX
   request71 and DMA2ch4 are independent of TIM1, TIM2 and USART DMA channels. */
static volatile uint16_t wire_ring[WC_SAMPLES];
static struct {
  uint32_t header[12];
  const uint32_t *parent;
  uint32_t crc;
  uint16_t end;
  uint8_t state;
} wire;
volatile uint32_t mic_i2c_wire_request;

void mic_i2c_wire_init(void){
  if(wire.state!=WC_UNINITIALIZED)return;
  __HAL_RCC_TIM4_CLK_ENABLE();__HAL_RCC_DMA2_CLK_ENABLE();
  wire.state=WC_ERROR;
  if((TIM4->CR1&TIM_CR1_CEN)||(DMA2_Channel4->CCR&DMA_CCR_EN))return;
  RCC_ClkInitTypeDef clocks={0};uint32_t latency=0;
  HAL_RCC_GetClockConfig(&clocks,&latency);
  uint32_t hz=HAL_RCC_GetPCLK1Freq();if(clocks.APB1CLKDivider!=RCC_HCLK_DIV1)hz*=2;
  if(hz!=170000000U)return;
  /* HAL handle is used only during initialization. No HAL DMA IRQ, abort,
     deinit or callback will ever reference it after this function returns. */
  DMA_HandleTypeDef dma={0};dma.Instance=DMA2_Channel4;
  dma.Init.Request=DMA_REQUEST_TIM4_UP;dma.Init.Direction=DMA_PERIPH_TO_MEMORY;
  dma.Init.PeriphInc=DMA_PINC_DISABLE;dma.Init.MemInc=DMA_MINC_ENABLE;
  dma.Init.PeriphDataAlignment=DMA_PDATAALIGN_WORD;
  dma.Init.MemDataAlignment=DMA_MDATAALIGN_HALFWORD;
  dma.Init.Mode=DMA_CIRCULAR;dma.Init.Priority=DMA_PRIORITY_LOW;
  if(HAL_DMA_Init(&dma)!=HAL_OK)return;
  TIM4->CR1=0;TIM4->CR2=0;TIM4->DIER=0;TIM4->PSC=0;TIM4->ARR=WC_PERIOD-1;
  TIM4->CNT=0;TIM4->EGR=TIM_EGR_UG;TIM4->SR=0;
  DMA2->IFCR=0xf000U;
  if(HAL_DMA_Start(&dma,(uint32_t)(uintptr_t)&GPIOB->IDR,
     (uint32_t)(uintptr_t)wire_ring,WC_SAMPLES)!=HAL_OK)return;
  DMA2_Channel4->CCR&=~(DMA_CCR_HTIE|DMA_CCR_TCIE|DMA_CCR_TEIE);
  wire.header[5]=hz;wire.header[6]=WC_PERIOD;wire.state=WC_ARMED;
  TIM4->DIER=TIM_DIER_UDE;TIM4->CR1=TIM_CR1_CEN;
}
void mic_i2c_wire_freeze(const uint32_t*parent,uint32_t requested_cycles){
  if(wire.state!=WC_ARMED)return;
  const bool moe=(TIM1->BDTR&TIM_BDTR_MOE)!=0;
  if(parent&&!moe)return; /* Startup error keeps the ring armed for PWM. */
  if(!parent&&moe)return;
  TIM4->DIER&=~TIM_DIER_UDE;TIM4->CR1&=~TIM_CR1_CEN;
  DMA2_Channel4->CCR&=~DMA_CCR_EN;__DSB();
  const uint32_t cycles=DWT->CYCCNT,remaining=DMA2_Channel4->CNDTR,flags=DMA2->ISR;
  const unsigned end=(WC_SAMPLES-remaining)&(WC_SAMPLES-1);
  const bool full=(flags&0x2000U)!=0;
  wire.header[0]=WC_MAGIC;wire.header[1]=WC_FORMAT;wire.header[2]=WC_BYTES;
  wire.header[3]=WC_PEER;wire.header[4]=0;wire.header[7]=full?(unsigned)WC_SAMPLES:end;
  wire.header[8]=cycles;wire.header[9]=requested_cycles;wire.header[10]=GPIOB->IDR;
  wire.header[11]=(full?(unsigned)WC_FULL:0U)|((flags&0x8000U)?(unsigned)WC_DMA_ERROR:0U)|
    (parent?WC_MOE:WC_MANUAL);
  wire.parent=parent;wire.end=(uint16_t)end;__DMB();wire.state=WC_FROZEN;
}
static uint8_t wire_byte(unsigned i){
  return i<WC_HEADER?(uint8_t)(wire.header[i/4]>>((i%4)*8)):
    wc_data_byte(wire_ring,wire.end,wire.header[7],i-WC_HEADER);
}
void mic_i2c_wire_service(bool off_low_bus){
  /* All frozen captures are immutable until MCU reset. Manual qualification
     is allowed only with the same native OFF and <20V gate. */
  uint32_t request=mic_i2c_wire_request;
  if(request){
    mic_i2c_wire_request=0;
    if(off_low_bus&&!(TIM1->BDTR&TIM_BDTR_MOE)){
      if(request==0x57495245U)mic_i2c_wire_freeze(0,DWT->CYCCNT);
    }
  }
  if(wire.state!=WC_FROZEN||(TIM1->BDTR&TIM_BDTR_MOE))return;
  if(wire.parent&&!mic_encoder_pwm_fault_ready())return;
  /* The parent becomes terminal before this OFF-only service. CRC work is
     deliberately outside the error path and outside active motor operation. */
  if(wire.parent)wire.header[4]=uv3_crc32c((const uint8_t*)wire.parent,160);
  uint32_t crc=0xffffffffU;
  for(unsigned i=0;i<WC_BYTES;i++){
    crc^=wire_byte(i);
    for(unsigned b=0;b<8;b++)crc=(crc>>1)^((crc&1U)?0x82f63b78U:0U);
  }
  wire.crc=crc^0xffffffffU;wire.state=WC_READY;
}
bool mic_i2c_wire_packet(uint8_t*p,unsigned page){
  if(TIM1->BDTR&TIM_BDTR_MOE)return false;
  if(wire.state!=WC_READY){
    memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=WC_WIRE;p[3]=2;p[4]=wire.state;
    wc_put(p+6,WC_PEER);p[38]=WC_FORMAT;uv3_seal(p);return true;
  }
  if(page>=WC_PAGES)return false;
  wc_frame(p,page,wire.crc);
  for(unsigned i=0;i<24&&page*24+i<WC_BYTES;i++)p[14+i]=wire_byte(page*24+i);
  uv3_seal(p);return true;
}
