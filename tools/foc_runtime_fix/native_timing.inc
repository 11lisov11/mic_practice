/* First-fault and execution timing; never a replacement for original guards. */
ft_irq_meter mic_foc_irq_meter;
static ft_perf ma_perf;
static uint8_t ma_perf_off=1;
static ft_first_fault ma_first_runtime;
static uint32_t ma_observer_begin;
static volatile uint8_t ma_observer_active;
static ft_clock ma_clock_snapshot(void){
 ft_clock out={0};
 for(unsigned retry=0;retry<4;++retry){
  uint32_t seq=mic_foc_irq_meter.seq;__DMB();
  out.now=DWT->CYCCNT;out.irq=mic_foc_irq_meter.cycles;out.roots=mic_foc_irq_meter.roots;
  __DMB();if(!(seq&1U)&&seq==mic_foc_irq_meter.seq){out.valid=1;return out;}
 }
 out.now=DWT->CYCCNT;return out;
}
static void ma_fail_at(unsigned code,unsigned reason,uint32_t at,
 const ma_current_sample*s,uint32_t est,uint32_t bin,uint32_t elapsed){
 ma_fail(code); /* Latch the original stop immediately, even if IRQ preempts. */
 uint32_t expected=0;
 if(!__atomic_compare_exchange_n(&ma_first_runtime.state,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return;
 uint32_t*w=ma_first_runtime.word;
 w[0]=reason;w[1]=code;w[2]=at;w[3]=s?s->cycles:0;w[4]=est;w[5]=bin;w[6]=ma_observer_begin;
 w[7]=ma_perf.wall;w[8]=ma_perf.irq;w[9]=ma_perf.cpu_upper;w[10]=s?s->sequence:0;
 w[11]=(s?((uint32_t)s->valid|((uint32_t)s->zero<<1)):0)|((uint32_t)running<<2)|((uint32_t)ma_observer_active<<3);
 w[12]=elapsed;w[13]=observer.steps;
 __DMB();__atomic_store_n(&ma_first_runtime.state,2,__ATOMIC_RELEASE);
}
void ma_timing_diag(uint8_t*p,uint32_t build,unsigned page){
 uint32_t words[7]={0};page%=4;
 unsigned complete=__atomic_load_n(&ma_first_runtime.state,__ATOMIC_ACQUIRE)==2;
 if(page==0){
  words[0]=ma_perf.wall;words[1]=ma_perf.irq;words[2]=ma_perf.cpu_upper;words[3]=ma_perf.roots;
  words[4]=ma_perf.max_wall;words[5]=ma_perf.max_irq;words[6]=ma_perf.max_cpu;
 }else if(page==1){
  words[0]=ma_perf.queue;words[1]=ma_perf.adc_age;words[2]=ma_perf.result_age;
  words[3]=ma_perf.max_queue;words[4]=ma_perf.max_result;words[5]=ma_perf.steps;words[6]=ma_perf.errors;
 }else if(complete)memcpy(words,ma_first_runtime.word+(page-2)*7,sizeof(words));
 memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xE8;p[3]=1;
 p[4]=(uint8_t)page;p[5]=(uint8_t)(complete|(ma_perf_off?2U:0U));ma_put(p+6,build);
 for(unsigned i=0;i<7;++i)ma_put(p+10+4*i,words[i]);
 uv3_seal(p);
}
