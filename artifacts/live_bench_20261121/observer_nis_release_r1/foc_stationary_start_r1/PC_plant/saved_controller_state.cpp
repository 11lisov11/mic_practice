#include "C:/mic_practice/artifacts/live_bench_20261121/observer_nis_release_r1/foc_stationary_start_r1/candidate/nucleo/Inc/motor_control.h"

#include <cassert>
#include <cstdio>
#include "foc_experiment.h"
int main(){
  const ma_motor motor=FE_ESTIMATED_MOTOR;
  const ma_geometry geometry={5312,5184,771,112,240,229};
  const float x[6]={-.1684476f,-.6725104f,-.199377f,-.08908632f,-14.100735f,.13949648f};
  const float reversed[6]={x[0],x[1],-x[2],-x[3],90.f,x[5]};
  const float ia=-.2596263f,ib=-.7377065f,ref=.9f,bus=322.f,dt=1.f/16000.f;
  ma_controller feedback={},startup={},altered={};
  feedback.time_s=startup.time_s=altered.time_s=.4f;
  ma_output a,b,c;
  assert(ma_control_checked(&feedback,&motor,x,&geometry,MA_FOC,ia,ib,ref,bus,dt,1,&a,1)==MA_OK);
  assert(ma_control_with_speed_admission(&startup,&motor,x,&geometry,MA_FOC,ia,ib,ref,bus,dt,1,&b,1,0)==MA_OK);
  assert(ma_control_with_speed_admission(&altered,&motor,reversed,&geometry,MA_FOC,ia,ib,ref,bus,dt,1,&c,1,0)==MA_OK);
  assert(a.iq_ref>.25f && b.iq_ref==0.f && c.iq_ref==0.f);
  assert(startup.speed_integral==0.f && startup.preflux==1U && b.id_measured==ia && b.iq_measured==ib);
  assert(!memcmp(&startup,&altered,sizeof(startup)) && !memcmp(b.ccr,c.ccr,sizeof(b.ccr)));

  const float other_axis[6]={.3f,.1f,.12f,.16f,3.f,0.f};
  ma_controller handover=startup,equivalent=startup;
  handover.integral[0]=2.f;handover.integral[1]=-3.f;
  equivalent=handover;equivalent.preflux=2U;
  const float mag=ma_control_norm(other_axis[2],other_axis[3]);
  const float d=other_axis[2]/mag,q=other_axis[3]/mag;
  equivalent.integral[0]=2.f*d-3.f*q;equivalent.integral[1]=-2.f*q-3.f*d;
  assert(ma_control_with_speed_admission(&handover,&motor,other_axis,&geometry,MA_FOC,.3f,.1f,ref,bus,dt,1,&b,1,1)==MA_OK);
  assert(ma_control_with_speed_admission(&equivalent,&motor,other_axis,&geometry,MA_FOC,.3f,.1f,ref,bus,dt,1,&c,1,1)==MA_OK);
  assert(handover.preflux==2U && !memcmp(&handover,&equivalent,sizeof(handover)) && !memcmp(b.ccr,c.ccr,sizeof(b.ccr)));
  assert(ma_control_with_speed_admission(&handover,&motor,other_axis,&geometry,MA_FOC,.3f,.1f,ref,bus,dt,1,&b,1,0)==MA_OK);
  assert(handover.preflux==2U && b.iq_ref==0.f && handover.speed_integral==0.f);
  printf("{\"recorded_state_Iq_with_old_speed_feedback_A\":%.9g,\"recorded_state_Iq_before_admission_A\":0,\"coordinate_handover\":true}\n",a.iq_ref);
}
