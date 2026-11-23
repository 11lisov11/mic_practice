
#include "foc_experiment.h"
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C"
#endif
API unsigned control_size(){return sizeof(ma_controller);}
API unsigned output_size(){return sizeof(ma_output);}
API void reset(void*c){memset(c,0,sizeof(ma_controller));}
API int control(void*c,const float*x,const ma_geometry*g,int algorithm,float ia,float ib,
 float hz,float bus,float dt,int fresh,void*out){
 static const ma_motor m=FE_ESTIMATED_MOTOR;
 return ma_control((ma_controller*)c,&m,x,g,algorithm,ia,ib,hz,bus,dt,fresh,(ma_output*)out);
}
API int modulation(void*c,const ma_geometry*g,int algorithm,float va,float vb,float bus,void*out){
 memset(out,0,sizeof(ma_output));
 return ma_modulate((ma_controller*)c,g,algorithm,va,vb,bus,(ma_output*)out);
}
