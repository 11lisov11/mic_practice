/* Same finite/NaN selection as newlib fminf/fmaxf, without two fpclassify
 * calls and library stack saves per clamp. Raw overcurrent hypotf is unchanged.
 * No fast-math compiler flag or finite-math assumption is enabled. */
static inline float ma_min2(float a,float b){
 if(isnan(a))return b;
 if(isnan(b))return a;
 return a<b?a:b;
}
static inline float ma_max2(float a,float b){
 if(isnan(a))return b;
 if(isnan(b))return a;
 return a>b?a:b;
}
