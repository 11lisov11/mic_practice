#include "motor_control.h"
__attribute__((noinline)) float ordered_bounds(float x){if(x>=.05f)return 1.f;if(x<=-.05f)return -1.f;return ma_clip(x/.05f,-1,1);}
__attribute__((noinline)) float absolute_bound(float x){if(fabsf(x)>=.05f)return x>=0.f?1.f:-1.f;return ma_clip(x/.05f,-1,1);}
__attribute__((noinline)) float copy_sign_bound(float x){if(fabsf(x)>=.05f)return copysignf(1.f,x);return ma_clip(x/.05f,-1,1);}
