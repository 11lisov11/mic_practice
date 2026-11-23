#include <cstdio>
#include "foc_experiment.h"
#define ADC_REFERENCE_VOLTAGE 3.30
#define RSHUNT 0.04
#define AMPLIFICATION_GAIN 2.1
static float ma_amps(int16_t counts){
  const float amp_per_count=(float)(ADC_REFERENCE_VOLTAGE/(4095.0*RSHUNT*AMPLIFICATION_GAIN));
  return (float)counts*amp_per_count;
}
int main(){
 const ma_motor model=FE_ESTIMATED_MOTOR;
 const float ia=ma_amps(-91),ib=(ma_amps(-91)+2.f*ma_amps(140))*.5773502692f;
 ma_controller c={};ma_output out={};float x[6]={};
 ma_geometry g={5312,5184,771,112,240,229};
 int rc=ma_control(&c,&model,x,&g,MA_FOC,ia,ib,.2f,325.f,1.f/16000,1,&out);
 printf("%d %.9g %.9g %.9g %.9g\n",rc,ia,ib,hypotf(ia,ib),model.trip_current);
 return rc==MA_CURRENT?0:1;
}
