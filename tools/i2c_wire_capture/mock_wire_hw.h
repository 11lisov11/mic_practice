#include <cstring>
#define __DMB() ((void)0)
typedef struct {uint32_t CR1,CR2,DIER,PSC,ARR,CNT,EGR,SR;} WireTimer;
typedef struct {uint32_t CCR,CNDTR,CPAR,CMAR;} WireDmaChannel;
typedef struct {uint32_t ISR,IFCR;} WireDma;
[[maybe_unused]] static WireTimer mock_tim4;
[[maybe_unused]] static WireDmaChannel mock_ch4;
[[maybe_unused]] static WireDma mock_dma2;
#define TIM4 (&mock_tim4)
#define DMA2_Channel4 (&mock_ch4)
#define DMA2 (&mock_dma2)
#define TIM_CR1_CEN 1U
#define TIM_DIER_UDE 256U
#define TIM_EGR_UG 1U
#define DMA_CCR_EN 1U
#define DMA_CCR_HTIE 4U
#define DMA_CCR_TCIE 2U
#define DMA_CCR_TEIE 8U
#define DMA_REQUEST_TIM4_UP 71U
#define DMA_PERIPH_TO_MEMORY 0U
#define DMA_PINC_DISABLE 0U
#define DMA_MINC_ENABLE 128U
#define DMA_PDATAALIGN_WORD 512U
#define DMA_MDATAALIGN_HALFWORD 1024U
#define DMA_CIRCULAR 32U
#define DMA_PRIORITY_LOW 0U
#define __HAL_RCC_TIM4_CLK_ENABLE() ((void)0)
#define __HAL_RCC_DMA2_CLK_ENABLE() ((void)0)
#define RCC_HCLK_DIV1 0U
#define HAL_OK 0U
typedef struct {uint32_t APB1CLKDivider;} RCC_ClkInitTypeDef;
typedef struct {uint32_t Request,Direction,PeriphInc,MemInc,PeriphDataAlignment,MemDataAlignment,Mode,Priority;} WireDmaInit;
typedef struct {WireDmaChannel*Instance;WireDmaInit Init;} DMA_HandleTypeDef;
static uint32_t mock_wire_hz=170000000U;static bool mock_dma_fail;
static DMA_HandleTypeDef mock_dma_init;
static inline void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef*c,uint32_t*l){c->APB1CLKDivider=RCC_HCLK_DIV1;*l=0;}
static inline uint32_t HAL_RCC_GetPCLK1Freq(){return mock_wire_hz;}
static inline unsigned HAL_DMA_Init(DMA_HandleTypeDef*d){mock_dma_init=*d;return mock_dma_fail?1U:0U;}
static inline unsigned HAL_DMA_Start(DMA_HandleTypeDef*d,uint32_t p,uint32_t m,uint32_t n){
  if(mock_dma_fail)return 1;
  d->Instance->CNDTR=n;d->Instance->CPAR=p;d->Instance->CMAR=m;
  d->Instance->CCR=DMA_CCR_EN|DMA_CIRCULAR|DMA_MINC_ENABLE|DMA_PDATAALIGN_WORD|DMA_MDATAALIGN_HALFWORD;
  return 0;
}
