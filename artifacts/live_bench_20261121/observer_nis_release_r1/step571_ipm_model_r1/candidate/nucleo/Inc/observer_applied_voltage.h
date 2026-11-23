#ifndef MIC_OBSERVER_APPLIED_VOLTAGE_H
#define MIC_OBSERVER_APPLIED_VOLTAGE_H
#include "motor_control.h"
/* Average-voltage MODEL of the ADC's active PWM epoch. No voltage measurement
 * or motor identification is claimed. Loss parameters are explicit. */
static inline int ma_applied_voltage(const ma_geometry*g,const uint16_t*ccr,
 uint16_t arr,uint16_t bus,float ia,float ib,float*va,float*vb){
 *va=*vb=0;
 if(!arr||arr!=g->arr||bus<30||bus>350||!isfinite(ia)||!isfinite(ib))return MA_BUS;
 for(unsigned i=0;i<3;++i)if(ccr[i]>arr)return MA_WINDOW;
 const float factor=(float)bus/(float)arr;
 const float average=((float)ccr[0]+ccr[1]+ccr[2])/3.f;
 float loss_a,loss_b;
 ma_voltage_loss_ab(g,(float)bus,ia,ib,&loss_a,&loss_b);
 *va=((float)ccr[0]-average)*factor-loss_a;
 *vb=((float)ccr[1]-ccr[2])*factor*.5773502692f-loss_b;
 return MA_OK;
}
#endif
