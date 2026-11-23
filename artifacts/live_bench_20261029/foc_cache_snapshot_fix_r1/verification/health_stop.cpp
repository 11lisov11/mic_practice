
#include <cassert>
#include <cstdint>
#define __weak
enum{M1=0,MC_NO_ERROR=0};
struct Timer{};struct PWM{Timer*TIMx;};static Timer timer;static PWM pwm={&timer};static PWM*pwmHandle[]={&pwm};
struct VF{float fFlux_Freq_Hz;};static VF vf={5};static VF*pACIM_VF[]={&vf};
static int enabled,selected,angles,scalar,native_calls,profiles,faults,ret;
static int LL_TIM_IsEnabledAllOutputs(Timer*){return enabled;}
static void ma_native_profile_tick(){++profiles;}
static void ACIM_VF_CalcAngle(VF*){++angles;}
static uint16_t ACIM_VF_Controller(VF*){++scalar;return ret;}
static unsigned ma_native_selected(){return selected;}
static uint16_t ma_native_fast(float f){assert(f==5);++native_calls;return ret;}
static void PWM_SwitchOffPWM(PWM*){enabled=0;}
static int Mci[1];static void MCI_FaultProcessing(int*,int f,int){assert(f==ret||f==128);++faults;}
static unsigned GLOBAL_TIMESTAMP;struct Log{unsigned Mark;};static Log MCPA_UART_A={};
static void MCPA_dataLog(Log*){}

static int health=1;enum{MC_SW_ERROR=128};static int RCM_CurrentEpoch(){return health;}
__weak uint8_t TSK_HighFrequencyTask(void)
{
  /* USER CODE BEGIN HighFrequencyTask 0 */

  /* USER CODE END HighFrequencyTask 0 */
  uint16_t returnValue;
  uint8_t bMotorNbr = 0;

  /* An off output needs no modulation calculation. A pending update at boot
     or after a hardware break must not evaluate an uninitialized normalizer.
     Active outputs still execute all validity guards and fault processing. */
  if (0U == LL_TIM_IsEnabledAllOutputs(pwmHandle[M1]->TIMx))
  {
    ma_native_profile_tick(); /* CPU-only work; never writes PWM. */
    return bMotorNbr;
  }

  /* Scalar angle is computed only in the scalar branch below. */

  /* USER CODE BEGIN HighFrequencyTask SINGLEDRIVE_1 */

  /* USER CODE END HighFrequencyTask SINGLEDRIVE_1 */

  if(ma_native_selected()==1U){
    ACIM_VF_CalcAngle(pACIM_VF[M1]);
    returnValue=ACIM_VF_Controller(pACIM_VF[M1]);
  }else returnValue=ma_native_fast(pACIM_VF[M1]->fFlux_Freq_Hz);

  if(returnValue==MC_NO_ERROR&&!RCM_CurrentEpoch())returnValue=MC_SW_ERROR;
  if(returnValue != MC_NO_ERROR)
  {
    // Induction motor  V/F
    PWM_SwitchOffPWM(pwmHandle[M1]);
    MCI_FaultProcessing(&Mci[M1], returnValue, 0);
  }

  /* USER CODE BEGIN HighFrequencyTask SINGLEDRIVE_2 */

  /* USER CODE END HighFrequencyTask SINGLEDRIVE_2 */

  /* USER CODE BEGIN HighFrequencyTask 1 */

  /* USER CODE END HighFrequencyTask 1 */

  GLOBAL_TIMESTAMP++;
  if (0U == MCPA_UART_A.Mark)
  {
    /* Nothing to do */
  }
  else
  {
    MCPA_dataLog (&MCPA_UART_A);
  }

  return (bMotorNbr);
}
int main(){
 enabled=0;selected=1;TSK_HighFrequencyTask();assert(profiles==1&&!angles&&!scalar&&!native_calls);
 enabled=1;selected=1;TSK_HighFrequencyTask();assert(angles==1&&scalar==1&&!native_calls);
 selected=2;TSK_HighFrequencyTask();assert(angles==1&&scalar==1&&native_calls==1);
 selected=3;TSK_HighFrequencyTask();assert(angles==1&&native_calls==2);
 ret=128;TSK_HighFrequencyTask();assert(!enabled&&faults==1);
ret=0;enabled=1;health=0;TSK_HighFrequencyTask();assert(!enabled&&faults==2);
}
