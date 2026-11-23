#include <initializer_list>
#include "C:/mic_practice/artifacts/live_bench_20261121/observer_nis_release_r1/step571_model_audit_r1/candidate/nucleo/Inc/motor_control.h"

#include <cassert>
#include <cstdio>
#include "foc_experiment.h"
int main(){
  const ma_motor motor=FE_ESTIMATED_MOTOR;
  const ma_geometry g={5312,5184,771,112,240,229};
  const float ia=-.2596263f,ib=-.7377065f,reference=.9f,dt=1.f/16000.f;
  const float x[6]={-.1684476f,-.6725104f,-.199377f,-.08908632f,-14.100735f,.13949648f};
  float alternative[6];memcpy(alternative,x,sizeof(alternative));alternative[4]=90.f;
  ma_controller before={};before.time_s=.4f;before.speed_integral=.02f;
  ma_controller ready=before,warm=before,changed=before;
  ma_output original,qualification,provisional,alternate;
  assert(ma_control_checked(&before,&motor,x,&g,MA_FOC,ia,ib,reference,322.f,dt,1,&original,1)==MA_OK);
  assert(fabsf(original.iq_ref)>.1f);
  assert(ma_control_with_speed_admission(&ready,&motor,x,&g,MA_FOC,ia,ib,reference,322.f,dt,1,&qualification,1,1)==MA_OK);
  assert(!memcmp(&ready,&before,sizeof(ready))&&!memcmp(&qualification,&original,sizeof(qualification)));
  assert(ma_control_with_speed_admission(&warm,&motor,x,&g,MA_FOC,ia,ib,reference,322.f,dt,1,&provisional,1,0)==MA_OK);
  assert(ma_control_with_speed_admission(&changed,&motor,alternative,&g,MA_FOC,ia,ib,reference,322.f,dt,1,&alternate,1,0)==MA_OK);
  assert(provisional.iq_ref==0.f&&warm.speed_integral==0.f);
  assert(!memcmp(&warm,&changed,sizeof(warm))&&!memcmp(provisional.ccr,alternate.ccr,sizeof(provisional.ccr)));
  assert(provisional.id_ref==original.id_ref);
  for(int flag:{0,1}){
    assert(ma_control_with_speed_admission(&warm,&motor,x,&g,MA_FOC,1.36f,0,reference,322.f,dt,1,&provisional,1,flag)==MA_CURRENT);
    assert(ma_control_with_speed_admission(&warm,&motor,x,&g,MA_FOC,ia,ib,reference,322.f,dt,0,&provisional,1,flag)==MA_STALE);
    assert(ma_control_with_speed_admission(&warm,&motor,x,&g,MA_FOC,ia,ib,reference,0.f,dt,1,&provisional,1,flag)==MA_BUS);
  }
  printf("{\"unqualified_speed_torque_A_before\":%.9g,\"unqualified_speed_torque_A_candidate\":0,"
         "\"qualified_path_bit_identical\":true,\"raw_current_age_and_bus_guards_preserved\":true}\n",original.iq_ref);
}
