#ifndef MIC_OBSERVER_FORECAST_H
#define MIC_OBSERVER_FORECAST_H
#include "motor_control.h"
/* Advance a COPY from the explicitly stamped measurement-window center to its
 * endpoint. No covariance/measurement update, no change to the age limit.
 * The foreground observer itself remains at the center for the next window. */
static inline int ow_forecast(const ma_motor*m,const float*from,float va,float vb,
 float dt,float*out){
 if(!isfinite(dt)||dt<0.f||dt>.001f)return MA_INVALID;
 float k[4][6],z[6];
 ma_derivative(m,from,va,vb,k[0],0);
 for(unsigned i=0;i<6;++i)z[i]=from[i]+dt*.5f*k[0][i];
 ma_derivative(m,z,va,vb,k[1],0);
 for(unsigned i=0;i<6;++i)z[i]=from[i]+dt*.5f*k[1][i];
 ma_derivative(m,z,va,vb,k[2],0);
 for(unsigned i=0;i<6;++i)z[i]=from[i]+dt*k[2][i];
 ma_derivative(m,z,va,vb,k[3],0);
 for(unsigned i=0;i<6;++i){
  out[i]=from[i]+dt*(k[0][i]+2*k[1][i]+2*k[2][i]+k[3][i])/6.f;
  if(!isfinite(out[i]))return MA_OBSERVER;
 }
 if(fabsf(out[4])>900.f||hypotf(out[2],out[3])>2.f)return MA_OBSERVER;
 return MA_OK;
}
#endif
