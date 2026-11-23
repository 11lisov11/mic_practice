#include "motor_control.h"
__attribute__((noinline)) float baseline_saturation(float current){return ma_clip(current/.05f,-1,1);}
__attribute__((noinline)) float candidate_saturation(float current){return ma_current_polarity(current);}
