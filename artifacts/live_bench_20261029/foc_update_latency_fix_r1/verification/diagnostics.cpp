
#include <cassert>
#include <cstdint>
enum{HAL_OK=0};static int tx_status;static uint32_t now_ms;static int enabled,service,live,bulk;
static int timer;static int*TIM1=&timer;static int LL_TIM_IsEnabledAllOutputs(int*){return enabled;}
static void ma_native_service(){++service;}
static void mic_send_research_page(uint32_t){++live;}
static void mic_send_current_page(uint32_t){++live;}
static void mic_send_break_page(uint32_t){++bulk;}
static void mic_send_peak_page(uint32_t){++bulk;}
static void mic_send_noise_page(uint32_t){++bulk;}
static void mic_send_identification(uint32_t){++bulk;}
void reply(){
  if (tx_status == HAL_OK) {
    ma_native_service();mic_send_research_page(now_ms);
    ma_native_service();mic_send_current_page(now_ms);
    ma_native_service();
    /* Bulk frozen records wait until OFF; sampling/capture and normal control
     * replies continue during RUN. Do not serialize old traces ahead of FOC. */
    if(!LL_TIM_IsEnabledAllOutputs(TIM1)){
      mic_send_break_page(now_ms);mic_send_peak_page(now_ms);
      mic_send_noise_page(now_ms);mic_send_identification(now_ms);
    }
  }

}
int main(){enabled=1;reply();assert(service==3&&live==2&&!bulk);enabled=0;reply();assert(service==6&&live==4&&bulk==4);tx_status=1;reply();assert(service==6&&live==4&&bulk==4);}