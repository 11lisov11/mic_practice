#include "foc_experiment.h"
extern "C" __declspec(dllexport) void get_model(ma_motor*m){*m=FE_ESTIMATED_MOTOR;}
extern "C" __declspec(dllexport) int observe(ma_observer*o,const ma_motor*m,float ia,float ib,float va,float vb,float dt){return ma_observe(o,m,ia,ib,va,vb,dt);}
extern "C" __declspec(dllexport) void derivative(const ma_motor*m,const float*x,float va,float vb,float*y,float*a){ma_derivative(m,x,va,vb,y,(float(*)[6])a);}
