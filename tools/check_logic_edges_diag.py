"""Exercise actual TIM8 adapter with fake registers and unchanged ADC/I2C tests."""
import json,re,shutil
import prepare_logic_edges_diag as prep
p=prep.configure_common()
def prepare_test():
 for name in ('load_diag.c','logic_edges.c'):shutil.copy2(p.OUT/'nucleo/Src'/name,p.RES/name)
 f=p.RES/'platform_test.cpp';s=p.read(prep.OLD/'test_resources/platform_test.cpp')
 s=p.once(s,'CCR4=4928;};','CCR4=4928,PSC=0,RCR=0,SR=0,EGR=0,SMCR=0,AF1=0,CCMR1=0,CCMR2=0,CCER=0;};')
 s=p.once(s,'LCKR=0;};','LCKR=0,AFR[2]={0,0};};')
 s=p.once(s,'static Timer tim;static GPIO pa,pb;', 'static Timer tim,aux;static GPIO pa,pb,pc,pd;')
 s=p.once(s,'#define GPIOA (&pa)','#define TIM8 (&aux)\n#define GPIOC (&pc)\n#define GPIOD (&pd)\n#define GPIOA (&pa)')
 device=p.read(p.OUT/'nucleo/Drivers/CMSIS/Device/ST/STM32G4xx/Include/stm32g431xx.h')
 existing=set(re.findall(r'^#define (\w+)',s,re.M))
 macros='\n'.join(line for line in device.splitlines() if re.match(r'#define (TIM_|TIM1_AF1_)',line) and line.split()[1] not in existing)
 extra='''
#define GPIO_PIN_2 4U
#define GPIO_PIN_6 64U
#define GPIO_MODE_AF_PP 2U
#define GPIO_SPEED_FREQ_VERY_HIGH 3U
#define GPIO_PIN_SET 1U
#define GPIO_AF4_TIM8 4U
#define __HAL_RCC_GPIOC_CLK_ENABLE() do{}while(0)
#define __HAL_RCC_GPIOD_CLK_ENABLE() do{}while(0)
#define __HAL_RCC_TIM8_CLK_ENABLE() do{}while(0)
#define __HAL_RCC_TIM8_FORCE_RESET() do{}while(0)
#define __HAL_RCC_TIM8_RELEASE_RESET() do{}while(0)
'''
 s=p.once(s,'struct GPIO_InitTypeDef {uint32_t Mode,Pull,Speed,Pin;};',macros+'\n'+extra+'\nstruct GPIO_InitTypeDef {uint32_t Mode,Pull,Speed,Pin,Alternate;};')
 a='static void HAL_GPIO_WritePin(GPIO*g,uint16_t pins,unsigned){g->ODR&=~pins;g->IDR&=~pins;}'
 s=p.once(s,a,'static void HAL_GPIO_WritePin(GPIO*g,uint16_t pins,unsigned set){if(set){g->ODR|=pins;g->IDR|=pins;}else{g->ODR&=~pins;g->IDR&=~pins;}}')
 a='static void HAL_GPIO_Init(GPIO*g,GPIO_InitTypeDef*q){for(unsigned i=0;i<16;i++)if((q->Pin&(1U<<i))&&!(g->LCKR&(1U<<i)))g->MODER=(g->MODER&~(3U<<(2*i)))|(1U<<(2*i));}'
 b='''static void HAL_GPIO_Init(GPIO*g,GPIO_InitTypeDef*q){
 for(unsigned i=0;i<16;i++)if((q->Pin&(1U<<i))&&!(g->LCKR&(1U<<i))){
  g->MODER=(g->MODER&~(3U<<(2*i)))|(q->Mode<<(2*i));
  if(q->Mode==GPIO_MODE_AF_PP){unsigned at=(i%8)*4;g->AFR[i/8]=(g->AFR[i/8]&~(15U<<at))|(q->Alternate<<at);}
 }
}''';s=p.once(s,a,b)
 s=p.once(s,'#include "load_diag.c"','void mic_encoder_load_counters(uint32_t*r,uint32_t*e){*r=now_ms/5;*e=0;}\n#include "logic_edges.c"\n#include "load_diag.c"')
 s=p.once(s,' tim=Timer{};pa=GPIO{};pb=GPIO{};',' tim=Timer{};aux=Timer{};pa=GPIO{};pb=GPIO{};pc=GPIO{};pd=GPIO{};pa.IDR=GPIO_PIN_6;pd.IDR=GPIO_PIN_2;')
 s=p.once(s,'  test(!(tim.BDTR&TIM_BDTR_MOE));test(pins_low());','''  test(!(tim.BDTR&TIM_BDTR_MOE));test(pins_low());
  if(n<32000){test(!(aux.BDTR&TIM_BDTR_MOE));test(!(pc.ODR&GPIO_PIN_9));}
  if(n>=32000 && n<80000){test(aux.BDTR&TIM_BDTR_MOE);test(pc.ODR&GPIO_PIN_9);test(aux.CCR1==tim.CCR1);test(aux.CCR2==tim.CCR2);test(aux.CCR3==tim.CCR3);}
''')
 s=p.once(s,' unsigned calls=math_calls;', ''' test(!(aux.BDTR&TIM_BDTR_MOE));test(!(pc.ODR&ALL_PINS));test(!mic_edges_guard());
 uint32_t er[12];for(unsigned i=0;i<12;i++)er[i]=mic_logic_edge_report[i];
 test(er[10]==3);test(ld_crc(er,11)==er[11]);test(er[2]-core.start==340000000U);test(er[3]-er[2]==510000000U);
 test(er[6]-er[4]==400);test(er[8]-er[6]==600);test(er[5]==0&&er[7]==0&&er[9]==0);
 unsigned calls=math_calls;''')
 s=p.once(s,' std::printf(', '''
 // Missing/LOW SD input, unexpected timer/DMA configuration, or changed GPIO mux denies admission.
 reset();pd.IDR=0;request();test(core.state==LD_DENIED);test(!math_calls);test(!(aux.BDTR&TIM_BDTR_MOE));
 reset();pa.IDR&=~GPIO_PIN_6;request();test(core.state==LD_DENIED);
 reset();aux.DIER=256;request();test(core.state==LD_DENIED);
 reset();aux.BDTR|=TIM_BDTR_AOE;request();test(core.state==LD_DENIED);
 reset();aux.AF1|=TIM1_AF1_BKINP;request();test(core.state==LD_DENIED);
 reset();aux.CCER|=4;request();test(core.state==LD_DENIED);
 reset();aux.SMCR=1;request();test(core.state==LD_DENIED);
 reset();pc.MODER^=1U<<12;request();test(core.state==LD_DENIED);
 // Model a physical Break: hardware clears MOE with no CPU cooperation.
 reset();request();dwt.CYCCNT=core.start+340000000;cached_at=adc_at=dwt.CYCCNT;mic_load_tim_update();
 test(aux.BDTR&TIM_BDTR_MOE);test(!(aux.BDTR&TIM_BDTR_AOE));test(aux.BDTR&TIM_BDTR_BKE);
 aux.BDTR&=~TIM_BDTR_MOE;aux.SR|=TIM_SR_BIF;mic_load_tim_update();
 test(core.state==LD_ABORTED&&(core.reason&256U));test(!(aux.BDTR&TIM_BDTR_MOE));test(!(pc.ODR&ALL_PINS));
 aux.SR=0;request();test(core.state==LD_ABORTED);test(!(aux.BDTR&TIM_BDTR_MOE));
 // Every other early exit also turns real auxiliary edges off immediately.
 for(unsigned cause=0;cause<5;cause++){
  reset();request();dwt.CYCCNT=core.start+340000000;cached_at=adc_at=dwt.CYCCNT;mic_load_tim_update();test(aux.BDTR&TIM_BDTR_MOE);
  if(cause==0)fail_math=1;
  if(cause==1)mic_local_stop_latched=1;
  if(cause==2)adc_at-=850001;
  if(cause==3){mic_load_request=LD_CANCEL;mic_load_poll();}
  if(cause==4){bus=20;mic_load_poll();}
  mic_load_tim_update();test(core.state==LD_ABORTED);test(!(aux.BDTR&TIM_BDTR_MOE));test(!(pc.ODR&ALL_PINS));
 }
 std::printf(''')
 p.write(f,s)
def main():
 prepare_test()
 import check_no_switch_diag as check
 check.main()
 # Source comparison also protects existing UART pin assignment and AS5600 GPIO.
 from audit_production_pwm_filters import function
 a=p.read(p.OLD/'nucleo/Src/main.c') if hasattr(p,'OLD') else p.read(prep.OLD/'nucleo/Src/main.c')
 b=p.read(p.OUT/'nucleo/Src/main.c')
 assert function(a,'MX_USART1_UART_Init')==function(b,'MX_USART1_UART_Init')
 assert p.read(prep.OLD/'nucleo/Src/nucleo_encoder.c').replace('2026102792','2026102793') in p.read(p.OUT/'nucleo/Src/nucleo_encoder.c')
 print(json.dumps(dict(passed=True,auxiliary_edges_only=True,old_protections_and_I2C_unchanged=True,hardware_calls=0)))
if __name__=='__main__':main()
