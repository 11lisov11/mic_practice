
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
static void __DMB(){__asm__ volatile("":::"memory");}
struct Timer{};static Timer timer;static auto TIM1=&timer;
static bool enabled=1,run_fault;static int LL_TIM_IsEnabledAllOutputs(Timer*){return enabled;}
static struct{uint32_t CYCCNT=1000;}clock_;static auto DWT=&clock_;
typedef struct{float x[6];uint32_t stamp;}ma_estimate_slot;
static ma_estimate_slot estimate_slot[2];static uint32_t estimate_index,estimate_cycles;
enum {EP_COPY=2,EP_COMMITTED=3};static uint32_t ma_observer_stage,ma_commit_mark_cycles;
static void read_irq();static uint32_t reads,old_stamp,new_stamp;static float old_x[6],new_x[6];
static uint32_t ma_estimate_read(float*x){
 unsigned index=__atomic_load_n(&estimate_index,__ATOMIC_ACQUIRE);
 for(unsigned i=0;i<6;++i)x[i]=estimate_slot[index].x[i];
 return estimate_slot[index].stamp;
}static int ma_estimate_publish(const float*x,uint32_t stamp){
 if(run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return 0;
 unsigned next=__atomic_load_n(&estimate_index,__ATOMIC_RELAXED)^1U;
 ma_observer_stage=EP_COPY;
 for(unsigned i=0;i<6;++i){estimate_slot[next].x[i]=x[i];read_irq();}
 estimate_slot[next].stamp=stamp;read_irq();
 __DMB();if(run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return 0;
 ma_commit_mark_cycles=DWT->CYCCNT;
 __atomic_store_n(&estimate_index,next,__ATOMIC_RELEASE);read_irq();
 estimate_cycles=stamp;ma_observer_stage=EP_COMMITTED;return 1;
}
static void read_irq(){
 float x[6];auto stamp=ma_estimate_read(x);++reads;
 bool old=stamp==old_stamp;assert(old||stamp==new_stamp);
 for(unsigned i=0;i<6;++i)assert(x[i]==(old?old_x[i]:new_x[i]));
}
int main(){
 for(unsigned epoch=1;epoch<=10000;++epoch){
  old_stamp=estimate_slot[estimate_index].stamp;memcpy(old_x,estimate_slot[estimate_index].x,sizeof(old_x));
  new_stamp=epoch*169984U;for(unsigned i=0;i<6;++i)new_x[i]=(float)(epoch*10+i);
  assert(ma_estimate_publish(new_x,new_stamp));read_irq();
 }
 assert(reads==90000);printf("whole snapshots checked:%u\n",reads);
}
