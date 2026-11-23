
#include <cassert>
#include <cstdint>
struct Timer{uint32_t CNT,CR1,ARR;};static Timer tim;static Timer*TIM1=&tim;
#define TIM_CR1_DIR 16
uint8_t mic_current_regular_window(void){
 uint32_t cnt=TIM1->CNT,down=TIM1->CR1&TIM_CR1_DIR;
 uint32_t arr=TIM1->ARR;
 return (uint8_t)(down&&arr>1536U&&cnt>1024U&&cnt<arr-512U);
}
int main(){tim.ARR=5312;
 for(unsigned down=0;down<2;++down)for(unsigned cnt=0;cnt<=5312;++cnt){
  tim.CR1=down?16:0;tim.CNT=cnt;int yes=mic_current_regular_window();
  assert(yes==(down&&cnt>1024&&cnt<4800));
  if(yes){assert(cnt>240+128);assert(5312-cnt>148+128);}
 }
}
