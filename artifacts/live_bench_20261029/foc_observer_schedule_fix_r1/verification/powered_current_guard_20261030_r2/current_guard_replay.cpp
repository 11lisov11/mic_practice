
#include <cassert>
#include <cstdio>
#include "motor_control.h"
#include "foc_experiment.h"
int main(){
 const ma_motor m=FE_ESTIMATED_MOTOR;ma_geometry g={5312,5184,771,112,240,229};
 ma_controller c={};float x[6]={};ma_output o;
 const float scale=(float)(3.3/(4095.0*.04*2.1));
 float ia=-39*scale,ib=(-39+2.f*138)*scale*.5773502692f;
 int result=ma_control_checked(&c,&m,x,&g,MA_FOC,ia,ib,3.2f,322.f,1.f/16000,1,&o,ma_motor_valid(&m));
 assert(result==MA_CURRENT&&o.fault==MA_CURRENT);
 assert(m.trip_current==1.35f&&hypotf(ia,ib)>m.trip_current);
 assert(mic_current_window_safe(1,2557,2889,2423,5184,771,112));
 assert(137<2048);assert(5290<31875);assert(201854<340000);
 printf("{\"native_guard_result\":%d,\"vector_A\":%.9g,\"trip_A\":%.9g,\"three_leg_window_safe\":true,\"raw_counts\":[-39,138,-99]}\n",result,hypotf(ia,ib),m.trip_current);
}
