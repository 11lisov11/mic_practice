
#include <cassert>
#include <cstdio>
#include <cmath>
#include <cstring>
#include <cstdint>
#include <cfloat>
#include <cfenv>
#include <cerrno>
#include <initializer_list>
#include "current_adc_window_plan.h"
using std::isfinite;using std::isnan;
static uint64_t core_calls;
static uint32_t word(float x){uint32_t v;memcpy(&v,&x,4);return v;}
static float value(uint32_t v){float x;memcpy(&x,&v,4);return x;}
static float host_hypot_core(float a,float b){
 assert((word(a)&0x7fffffffU)<=0x58800000U&&(word(b)&0x7fffffffU)<=0x58800000U);
 ++core_calls;float r=std::hypot(a,b);assert(std::isfinite(r));return r;
}
#define MIC_CONTROL_HYPOT_CORE(a,b) ::host_hypot_core(a,b)
namespace baseline{
/* Portable actuator kernels. No GPIO, START, CLEAR, or protection-register access.
 * Units: star-equivalent SI parameters, phase peak A, mechanical rad/s, rotor Wb.
 * Simulation priors are not identified motor parameters or hardware qualification.
 */

enum { MA_VF=1, MA_FOC=2, MA_ADAPTIVE=3 };
enum { MA_OK=0, MA_INVALID=1, MA_CURRENT=2, MA_STALE=3,
       MA_BUS=4, MA_OBSERVER=5, MA_WINDOW=6, MA_NOT_QUALIFIED=7 };
typedef struct {
  float rs,rr,ls,lr,lm,j,b; uint32_t poles;
  float flux,current_limit,trip_current,current_bw,speed_bw;
} ma_motor;
typedef struct { float x[6],p[6][6],nis; float predicted_i[2],innovation[2],innovation_variance[2]; uint32_t steps,rejected; } ma_observer;
typedef struct {
  float integral[2],speed_integral,time_s,shift,last_va,last_vb;
  uint32_t faults,adaptive_steps;
} ma_controller;
typedef struct {
  uint32_t arr,latest,settle,acquire,min_pulse,deadtime_ticks;
} ma_geometry;
typedef struct {
  float va,vb,duty[3],id_ref,iq_ref,omega_est,flux,shift;
  uint32_t ccr[3],trigger; uint8_t pair,valid,fault;
  float id_measured,iq_measured; /* Observational taps of already computed values. */
} ma_output;
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

static inline float ma_clip(float x,float a,float b){return ma_min2(b,ma_max2(a,x));}
/* Exact saturated branch of clip(current/.05f,-1,1).
 * No reciprocal approximation or fast-math: unsaturated values and NaNs retain
 * the original divide/clip expression. The bounds also make its finite clamps
 * redundant to the compiler without changing the result. */
static inline float ma_current_polarity(float current){
 if(current>=.05f)return 1.f;
 if(current<=-.05f)return -1.f;
 return ma_clip(current/.05f,-1,1);
}

static inline int ma_motor_valid(const ma_motor*m){
  const float a[]={m->rs,m->rr,m->ls,m->lr,m->lm,m->j,m->flux,
    m->current_limit,m->trip_current,m->current_bw,m->speed_bw};
  for(unsigned i=0;i<sizeof(a)/sizeof(a[0]);i++)if(!isfinite(a[i])||a[i]<=0)return 0;
  return isfinite(m->b)&&m->b>=0&&m->poles>0&&m->poles<=8&&
    m->ls*m->lr>1.0001f*m->lm*m->lm&&m->trip_current>m->current_limit&&
    m->flux/m->lm<0.95f*m->current_limit&&m->current_bw<2000&&m->speed_bw<100;
}
static inline void ma_reset(ma_observer*o,ma_controller*c){
  memset(o,0,sizeof(*o));memset(c,0,sizeof(*c));
  const float d[6]={.0025f,.0025f,.0025f,.0025f,900,.0025f};
  for(unsigned i=0;i<6;i++)o->p[i][i]=d[i];
}
static inline void ma_derivative(const ma_motor*m,const float*x,float va,float vb,
                                 float*f,float a[6][6]){
  const float ar=m->rr/m->lr,kr=m->lm/m->lr,l=m->ls-m->lm*kr;
  const float p=(float)m->poles,t=1.5f*p*kr;
  f[2]=ar*(m->lm*x[0]-x[2])-p*x[4]*x[3];
  f[3]=ar*(m->lm*x[1]-x[3])+p*x[4]*x[2];
  f[0]=(va-m->rs*x[0]-kr*f[2])/l;f[1]=(vb-m->rs*x[1]-kr*f[3])/l;
  f[4]=(t*(x[2]*x[1]-x[3]*x[0])-x[5]-m->b*x[4])/m->j;f[5]=0;
  if(!a)return;
  memset(a,0,36*sizeof(float));
  a[2][0]=ar*m->lm;a[2][2]=-ar;a[2][3]=-p*x[4];a[2][4]=-p*x[3];
  a[3][1]=ar*m->lm;a[3][2]=p*x[4];a[3][3]=-ar;a[3][4]=p*x[2];
  for(unsigned k=0;k<6;k++){a[0][k]=-kr*a[2][k]/l;a[1][k]=-kr*a[3][k]/l;}
  a[0][0]-=m->rs/l;a[1][1]-=m->rs/l;
  a[4][0]=-t*x[3]/m->j;a[4][1]=t*x[2]/m->j;
  a[4][2]=t*x[1]/m->j;a[4][3]=-t*x[0]/m->j;
  a[4][4]=-m->b/m->j;a[4][5]=-1/m->j;
}
/* Lower-priority observer, independently scheduled from the PWM current loop.
 * RK4 state integration and second-order covariance transition; Joseph correction
 * keeps covariance symmetric/positive under float roundoff. No plant speed input.
 */
static inline int ma_observe(ma_observer*o,const ma_motor*m,float ia,float ib,
                            float va,float vb,float dt){
  if(!ma_motor_valid(m)||!isfinite(dt)||dt<.0001f||dt>.002f||
     !isfinite(ia)||!isfinite(ib)||!isfinite(va)||!isfinite(vb))return MA_INVALID;
  float a[6][6],f[6][6],tmp[6][6];
  /* The Jacobian is dead after F is built. Reuse its144-byte workspace for
     covariance; no arithmetic order changes and no shared/static scratch. */
  float (*cov)[6]=a;
  float k[4][6],z[6];
  ma_derivative(m,o->x,va,vb,k[0],a);
  for(unsigned i=0;i<6;i++)z[i]=o->x[i]+dt*.5f*k[0][i];
  ma_derivative(m,z,va,vb,k[1],0);
  for(unsigned i=0;i<6;i++)z[i]=o->x[i]+dt*.5f*k[1][i];
  ma_derivative(m,z,va,vb,k[2],0);
  for(unsigned i=0;i<6;i++)z[i]=o->x[i]+dt*k[2][i];
  ma_derivative(m,z,va,vb,k[3],0);
  for(unsigned i=0;i<6;i++)o->x[i]+=dt*(k[0][i]+2*k[1][i]+2*k[2][i]+k[3][i])/6;
  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){
    float aa=0;
#pragma GCC unroll 6
    for(unsigned k0=0;k0<6;k0++)aa+=a[i][k0]*a[k0][j];
    f[i][j]=(i==j?1.f:0.f)+dt*a[i][j]+.5f*dt*dt*aa;
  }
  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){
    float v=0;
#pragma GCC unroll 6
    for(unsigned k0=0;k0<6;k0++)v+=f[i][k0]*o->p[k0][j];
    tmp[i][j]=v;
  }
  const float q[6]={.02f,.02f,.00001f,.00001f,4.f,.0001f};
  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){
    float v=0;
#pragma GCC unroll 6
    for(unsigned k0=0;k0<6;k0++)v+=tmp[i][k0]*f[j][k0];
    cov[i][j]=v+(i==j?q[i]*dt:0);
  }
  o->nis=0;
  o->predicted_i[0]=o->x[0];o->predicted_i[1]=o->x[1];
  const float y[2]={ia,ib};
  for(unsigned ch=0;ch<2;ch++){
    const float r=.0004f,s=cov[ch][ch]+r,e=y[ch]-o->x[ch];float gain[6];
    o->innovation[ch]=e;o->innovation_variance[ch]=s;
    if(!isfinite(s)||s<=0)return MA_OBSERVER;
    o->nis+=e*e/s;
    for(unsigned i=0;i<6;i++){gain[i]=cov[i][ch]/s;o->x[i]+=gain[i]*e;}
    for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++)
      tmp[i][j]=cov[i][j]-gain[i]*cov[ch][j]-gain[j]*cov[i][ch]+gain[i]*gain[j]*s;
    memcpy(cov,tmp,sizeof(a));
  }
  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){
    o->p[i][j]=.5f*(cov[i][j]+cov[j][i]);
    if(!isfinite(o->p[i][j])||!isfinite(o->x[i]))return MA_OBSERVER;
  }
  if(fabsf(o->x[4])>900||hypotf(o->x[2],o->x[3])>2.0f)return MA_OBSERVER;
  if(o->steps>300&&o->nis>50)o->rejected++;else o->rejected=0;
  if(o->rejected>=20)return MA_OBSERVER;
  o->steps++;return MA_OK;
}
static inline float ma_margin(const ma_geometry*g,const uint32_t*c,
                             mic_current_window_plan p){
  if(!p.valid)return -1;
  float margin=(float)(g->latest-p.trigger);
  for(unsigned i=0;i<3;i++){
    const float v=c[i]<p.trigger?(float)(p.trigger-c[i]-g->settle):
                                          (float)(c[i]-p.trigger-g->acquire);
    if(v<margin)margin=v;
  }
  return margin;
}
/* Adaptive common-mode placement at FIXED 16 kHz. All three compare values move
 * together, preserving line voltage before timer quantisation. The same genuine
 * three-leg aperture planner is used by the ADC ISR. Never relax its guards.
 */
/* CCR inputs are nonnegative binary32 values bounded by the16-bit timer.
 * Exact halfway-away-from-zero rounding, including the float below0.5:
 * adding0.5 before conversion would double-round that boundary. Invalid input
 * fails closed; every caller rejects the sentinel before aperture planning. */
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || FLT_MAX_EXP != 128
#error "CCR rounding requires IEEE binary32"
#endif
typedef char ma_float_is_32_bits[(sizeof(float)==4)?1:-1];
static inline uint32_t ma_round_ccr(float value){
  uint32_t bits;memcpy(&bits,&value,sizeof(bits));
  if(bits==0x80000000U)return 0; /* negative zero */
  if(bits>0x477fff00U)return UINT32_MAX; /* negative, NaN, Inf, or >65535 */
  unsigned exponent=bits>>23;
  if(exponent<126U)return 0;
  unsigned shift=150U-exponent;
  uint32_t mantissa=(bits&0x7fffffU)|0x800000U;
  return (mantissa+(1U<<(shift-1U)))>>shift;
}
static inline int ma_modulate(ma_controller*c,const ma_geometry*g,int algorithm,
                              float va,float vb,float bus,ma_output*out){
  if(!g->arr||g->arr>65535||g->latest>=g->arr||g->settle>=g->arr||g->acquire>=g->arr||
    g->min_pulse*2>=g->arr||!isfinite(va)||!isfinite(vb)||!isfinite(bus)||bus<30||bus>350)return MA_BUS;
  const float phase[3]={va,-.5f*va+.8660254038f*vb,-.5f*va-.8660254038f*vb};
  const float hi=ma_max2(phase[0],ma_max2(phase[1],phase[2]));
  const float lo=ma_min2(phase[0],ma_min2(phase[1],phase[2]));
  float base[3];const float z=-.5f*(hi+lo),pulse=(float)g->min_pulse/g->arr;
  float lower=-1,upper=1;
  for(unsigned i=0;i<3;i++){
    base[i]=.5f+(phase[i]+z)/bus;
    lower=ma_max2(lower,pulse-base[i]);upper=ma_min2(upper,1-pulse-base[i]);
  }
  if(lower>upper)return MA_WINDOW;
  float target=0,best=-INFINITY;uint32_t cc[3];
  if(algorithm==MA_ADAPTIVE){
    /* Bounded three-candidate search, no variable-frequency carrier jitter. */
    const float candidates[3]={ma_clip(0,lower,upper),lower,upper};
    for(unsigned n=0;n<3;n++){
      for(unsigned i=0;i<3;i++){cc[i]=ma_round_ccr((base[i]+candidates[n])*g->arr);if(cc[i]>g->arr)return MA_WINDOW;}
      mic_current_window_plan p=mic_plan_current_window(cc[0],cc[1],cc[2],g->latest,g->settle,g->acquire);
      float score=p.valid?ma_margin(g,cc,p)-.02f*g->arr*fabsf(candidates[n]):-INFINITY;
      if(score>best){best=score;target=candidates[n];}
    }
    c->adaptive_steps++;
  }
  /* Limit shift slew, but never publish an unsafe intermediate aperture. */
  float shift=ma_clip(c->shift+ma_clip(target-c->shift,-.002f,.002f),lower,upper);
  mic_current_window_plan p;
  for(unsigned attempt=0;attempt<2;attempt++){
    for(unsigned i=0;i<3;i++){cc[i]=ma_round_ccr((base[i]+shift)*g->arr);if(cc[i]>g->arr)return MA_WINDOW;}
    p=mic_plan_current_window(cc[0],cc[1],cc[2],g->latest,g->settle,g->acquire);
    if(p.valid)break;
    shift=target;
  }
  if(!p.valid)return MA_WINDOW;
  c->shift=shift;out->shift=shift;out->trigger=p.trigger;out->pair=p.pair;
  for(unsigned i=0;i<3;i++){out->ccr[i]=cc[i];out->duty[i]=(float)cc[i]/g->arr;}
  /* Actual quantised average phase voltage, used by observer instead of request. */
  const float mean=(out->duty[0]+out->duty[1]+out->duty[2])/3;
  out->va=(out->duty[0]-mean)*bus;
  out->vb=(out->duty[1]-out->duty[2])*bus*.5773502692f;
  return MA_OK;
}
static inline __attribute__((always_inline)) int ma_control_checked(ma_controller*c,const ma_motor*m,const float*x,
    const ma_geometry*g,int algorithm,float ia,float ib,float reference_hz,
    float bus,float dt,int fresh,ma_output*out,int model_ok){
  memset(out,0,sizeof(*out));
  int fault=MA_OK;
  if(!model_ok||!isfinite(ia)||!isfinite(ib)||!isfinite(reference_hz)||
    reference_hz<0||reference_hz>50||!isfinite(dt)||dt<=0||dt>.0002f||
    (algorithm!=MA_FOC&&algorithm!=MA_ADAPTIVE))fault=MA_INVALID;
  else if(!fresh)fault=MA_STALE;
  else if(!isfinite(bus)||bus<30||bus>350)fault=MA_BUS;
  else if(hypotf(ia,ib)>m->trip_current)fault=MA_CURRENT;
  for(unsigned i=0;i<6;i++)if(!isfinite(x[i]))fault=MA_OBSERVER;
  if(fault){c->faults++;out->fault=(uint8_t)fault;return fault;}
  c->time_s+=dt;
  const float flux=hypotf(x[2],x[3]);
  const float c0=flux>.0001f?x[2]/flux:1.f,s=flux>.0001f?x[3]/flux:0.f;
  const float id=c0*ia+s*ib,iq=-s*ia+c0*ib;
  const float idref=ma_min2(m->flux/m->lm,.9f*m->current_limit)*ma_min2(1,c->time_s/.10f);
  float iqref=0;
  if(c->time_s<.35f)c->speed_integral=0;
  else {
  const float iqmax=sqrtf(ma_max2(0,m->current_limit*m->current_limit-idref*idref));
  const float omega_ref=reference_hz*6.2831853072f/m->poles;
  const float speederr=omega_ref-x[4],kp=2*m->j*m->speed_bw,ki=m->j*m->speed_bw*m->speed_bw;
  const float tqgain=1.5f*m->poles*m->lm/m->lr*ma_max2(flux,.025f);
  const float raw=kp*speederr+c->speed_integral;
  iqref=ma_clip(raw/tqgain,-iqmax,iqmax);
  /* No regenerative torque request without a commissioned brake path. */
  if(x[4]>0&&iqref<0)iqref=0;
  if(c->time_s>=.35f){
    c->speed_integral+=dt*(ki*speederr+m->speed_bw*(tqgain*iqref-raw));
    c->speed_integral=ma_clip(c->speed_integral,-2*tqgain*m->current_limit,2*tqgain*m->current_limit);
  }
  }
  const float err[2]={idref-id,iqref-iq};
  const float kr=m->lm/m->lr,ar=m->rr/m->lr,l=m->ls-kr*m->lm;
  const float sync=ma_clip(m->poles*x[4]+ar*m->lm*iq/ma_max2(flux,.025f),-600,600);
  const float res=m->rs+kr*ar*m->lm;
  const float ff[2]={res*id-kr*ar*flux-sync*l*iq,
    res*iq+kr*m->poles*x[4]*flux+sync*l*id};
  float dq[2]={ff[0]+l*m->current_bw*err[0]+c->integral[0],
               ff[1]+l*m->current_bw*err[1]+c->integral[1]};
  const float limit=.90f*bus*.5773502692f,mag=hypotf(dq[0],dq[1]);
  const float scale=ma_min2(1,limit/ma_max2(mag,1.e-9f));
  for(unsigned i=0;i<2;i++){
    const float limited=dq[i]*scale;
    c->integral[i]+=dt*(m->rs*m->current_bw*err[i]+m->current_bw*(limited-dq[i]));
    c->integral[i]=ma_clip(c->integral[i],-limit,limit);dq[i]=limited;
  }
  out->id_ref=idref;out->iq_ref=iqref;out->omega_est=x[4];out->flux=flux;
  out->id_measured=id;out->iq_measured=iq;
  const float requested_a=c0*dq[0]-s*dq[1],requested_b=s*dq[0]+c0*dq[1];
  const float loss=bus*g->deadtime_ticks/(2.f*g->arr);
  const float loss_phase[3]={loss*ma_current_polarity(ia),
    loss*ma_current_polarity((-.5f*ia+.8660254038f*ib)),
    loss*ma_current_polarity((-.5f*ia-.8660254038f*ib))};
  const float loss_a=(2*loss_phase[0]-loss_phase[1]-loss_phase[2])/3;
  const float loss_b=(loss_phase[1]-loss_phase[2])*.5773502692f;
  float aperture_scale=1;
  /* Project voltage into the measurable set, rather than counting edge samples
   * as current. Search is bounded, and failure still stops the actuator. */
  for(unsigned attempt=0;attempt<5;attempt++){
    fault=ma_modulate(c,g,algorithm,(requested_a+loss_a)*aperture_scale,(requested_b+loss_b)*aperture_scale,bus,out);
    if(fault!=MA_WINDOW)break;
    aperture_scale*=.85f;
  }
  if(fault){c->faults++;out->fault=(uint8_t)fault;return fault;}
  out->va-=loss_a;out->vb-=loss_b;
  /* Anti-windup must also see timer quantisation and aperture projection. */
  c->integral[0]+=dt*m->current_bw*(c0*(out->va-requested_a)+s*(out->vb-requested_b));
  c->integral[1]+=dt*m->current_bw*(-s*(out->va-requested_a)+c0*(out->vb-requested_b));
  c->last_va=out->va;c->last_vb=out->vb;out->valid=1;return MA_OK;
}
/* General callers validate the model here. The native IRQ uses the result
 * of the identical validation already performed in that SAME IRQ invocation;
 * no result is cached between frames and no foreground mutation can intervene. */
static inline int ma_control(ma_controller*c,const ma_motor*m,const float*x,
    const ma_geometry*g,int algorithm,float ia,float ib,float reference_hz,
    float bus,float dt,int fresh,ma_output*out){
  return ma_control_checked(c,m,x,g,algorithm,ia,ib,reference_hz,bus,dt,fresh,out,ma_motor_valid(m));
}


/* Calculated AIR56B2 candidate, explicitly NOT physical identification. */
#define FE_ESTIMATED_MOTOR {12.23f,11.00442222558575f,0.528093860573909f,0.528093860573909f,0.4944775988161633f,0.0002f,0.00014790613961630187f,1,0.25f,0.8f,1.35f,400.f,12.f}
enum {FE_ESTIMATED=128,FE_READY=1,FE_BUSY=2,FE_DONE=4,
      FE_FAST_BUDGET=4000,FE_OBSERVER_BUDGET=85000,FE_CASES=64};
static inline int fe_model_exact(const ma_motor*m){
 static const ma_motor expected=FE_ESTIMATED_MOTOR;
 return ma_motor_valid(m)&&memcmp(m,&expected,sizeof(expected))==0;
}
static inline int fe_start_policy(unsigned kind,unsigned flags,unsigned algorithm,
                                 int manual,uint32_t limit_ms,float frequency){
 if(kind==7)return 1;
 return kind==FE_ESTIMATED&&(flags&FE_READY)&&!(flags&(FE_BUSY|FE_DONE))&&
  algorithm==MA_FOC&&!manual&&limit_ms==5000&&isfinite(frequency)&&frequency>0&&frequency<=5;
}
static inline int fe_time_up(uint32_t now,uint32_t begin,uint32_t clock){
 return (uint32_t)(now-begin)>=5U*clock;
}

}
namespace candidate{
/* Portable actuator kernels. No GPIO, START, CLEAR, or protection-register access.
 * Units: star-equivalent SI parameters, phase peak A, mechanical rad/s, rotor Wb.
 * Simulation priors are not identified motor parameters or hardware qualification.
 */

enum { MA_VF=1, MA_FOC=2, MA_ADAPTIVE=3 };
enum { MA_OK=0, MA_INVALID=1, MA_CURRENT=2, MA_STALE=3,
       MA_BUS=4, MA_OBSERVER=5, MA_WINDOW=6, MA_NOT_QUALIFIED=7 };
typedef struct {
  float rs,rr,ls,lr,lm,j,b; uint32_t poles;
  float flux,current_limit,trip_current,current_bw,speed_bw;
} ma_motor;
typedef struct { float x[6],p[6][6],nis; float predicted_i[2],innovation[2],innovation_variance[2]; uint32_t steps,rejected; } ma_observer;
typedef struct {
  float integral[2],speed_integral,time_s,shift,last_va,last_vb;
  uint32_t faults,adaptive_steps;
} ma_controller;
typedef struct {
  uint32_t arr,latest,settle,acquire,min_pulse,deadtime_ticks;
} ma_geometry;
typedef struct {
  float va,vb,duty[3],id_ref,iq_ref,omega_est,flux,shift;
  uint32_t ccr[3],trigger; uint8_t pair,valid,fault;
  float id_measured,iq_measured; /* Observational taps of already computed values. */
} ma_output;
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

static inline float ma_clip(float x,float a,float b){return ma_min2(b,ma_max2(a,x));}
/* Exact saturated branch of clip(current/.05f,-1,1).
 * No reciprocal approximation or fast-math: unsaturated values and NaNs retain
 * the original divide/clip expression. The bounds also make its finite clamps
 * redundant to the compiler without changing the result. */
static inline float ma_current_polarity(float current){
 if(current>=.05f)return 1.f;
 if(current<=-.05f)return -1.f;
 return ma_clip(current/.05f,-1,1);
}

/* Same installed newlib hypot core, without its errno/finite-result
 * wrapper when BOTH finite inputs are bounded by2^50. Their norm is at most
 * sqrt(2)*2^50, far below FLT_MAX, so the wrapper would return it unchanged.
 * All other bit patterns use the original hypotf entry point. The raw-current
 * trip expression deliberately continues to call original hypotf as before. */
#ifndef MIC_CONTROL_HYPOT_CORE
#if defined(__arm__) || defined(__thumb__)
extern float __ieee754_hypotf(float,float);
#define MIC_CONTROL_HYPOT_CORE(a,b) __ieee754_hypotf(a,b)
#else
#define MIC_CONTROL_HYPOT_CORE(a,b) hypotf(a,b)
#endif
#endif
static inline float ma_control_norm(float a,float b){
 uint32_t x,y;memcpy(&x,&a,4);memcpy(&y,&b,4);
 if((x&0x7fffffffU)<=0x58800000U&&(y&0x7fffffffU)<=0x58800000U)
  return MIC_CONTROL_HYPOT_CORE(a,b);
 return hypotf(a,b);
}

static inline int ma_motor_valid(const ma_motor*m){
  const float a[]={m->rs,m->rr,m->ls,m->lr,m->lm,m->j,m->flux,
    m->current_limit,m->trip_current,m->current_bw,m->speed_bw};
  for(unsigned i=0;i<sizeof(a)/sizeof(a[0]);i++)if(!isfinite(a[i])||a[i]<=0)return 0;
  return isfinite(m->b)&&m->b>=0&&m->poles>0&&m->poles<=8&&
    m->ls*m->lr>1.0001f*m->lm*m->lm&&m->trip_current>m->current_limit&&
    m->flux/m->lm<0.95f*m->current_limit&&m->current_bw<2000&&m->speed_bw<100;
}
static inline void ma_reset(ma_observer*o,ma_controller*c){
  memset(o,0,sizeof(*o));memset(c,0,sizeof(*c));
  const float d[6]={.0025f,.0025f,.0025f,.0025f,900,.0025f};
  for(unsigned i=0;i<6;i++)o->p[i][i]=d[i];
}
static inline void ma_derivative(const ma_motor*m,const float*x,float va,float vb,
                                 float*f,float a[6][6]){
  const float ar=m->rr/m->lr,kr=m->lm/m->lr,l=m->ls-m->lm*kr;
  const float p=(float)m->poles,t=1.5f*p*kr;
  f[2]=ar*(m->lm*x[0]-x[2])-p*x[4]*x[3];
  f[3]=ar*(m->lm*x[1]-x[3])+p*x[4]*x[2];
  f[0]=(va-m->rs*x[0]-kr*f[2])/l;f[1]=(vb-m->rs*x[1]-kr*f[3])/l;
  f[4]=(t*(x[2]*x[1]-x[3]*x[0])-x[5]-m->b*x[4])/m->j;f[5]=0;
  if(!a)return;
  memset(a,0,36*sizeof(float));
  a[2][0]=ar*m->lm;a[2][2]=-ar;a[2][3]=-p*x[4];a[2][4]=-p*x[3];
  a[3][1]=ar*m->lm;a[3][2]=p*x[4];a[3][3]=-ar;a[3][4]=p*x[2];
  for(unsigned k=0;k<6;k++){a[0][k]=-kr*a[2][k]/l;a[1][k]=-kr*a[3][k]/l;}
  a[0][0]-=m->rs/l;a[1][1]-=m->rs/l;
  a[4][0]=-t*x[3]/m->j;a[4][1]=t*x[2]/m->j;
  a[4][2]=t*x[1]/m->j;a[4][3]=-t*x[0]/m->j;
  a[4][4]=-m->b/m->j;a[4][5]=-1/m->j;
}
/* Lower-priority observer, independently scheduled from the PWM current loop.
 * RK4 state integration and second-order covariance transition; Joseph correction
 * keeps covariance symmetric/positive under float roundoff. No plant speed input.
 */
static inline int ma_observe(ma_observer*o,const ma_motor*m,float ia,float ib,
                            float va,float vb,float dt){
  if(!ma_motor_valid(m)||!isfinite(dt)||dt<.0001f||dt>.002f||
     !isfinite(ia)||!isfinite(ib)||!isfinite(va)||!isfinite(vb))return MA_INVALID;
  float a[6][6],f[6][6],tmp[6][6];
  /* The Jacobian is dead after F is built. Reuse its144-byte workspace for
     covariance; no arithmetic order changes and no shared/static scratch. */
  float (*cov)[6]=a;
  float k[4][6],z[6];
  ma_derivative(m,o->x,va,vb,k[0],a);
  for(unsigned i=0;i<6;i++)z[i]=o->x[i]+dt*.5f*k[0][i];
  ma_derivative(m,z,va,vb,k[1],0);
  for(unsigned i=0;i<6;i++)z[i]=o->x[i]+dt*.5f*k[1][i];
  ma_derivative(m,z,va,vb,k[2],0);
  for(unsigned i=0;i<6;i++)z[i]=o->x[i]+dt*k[2][i];
  ma_derivative(m,z,va,vb,k[3],0);
  for(unsigned i=0;i<6;i++)o->x[i]+=dt*(k[0][i]+2*k[1][i]+2*k[2][i]+k[3][i])/6;
  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){
    float aa=0;
#pragma GCC unroll 6
    for(unsigned k0=0;k0<6;k0++)aa+=a[i][k0]*a[k0][j];
    f[i][j]=(i==j?1.f:0.f)+dt*a[i][j]+.5f*dt*dt*aa;
  }
  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){
    float v=0;
#pragma GCC unroll 6
    for(unsigned k0=0;k0<6;k0++)v+=f[i][k0]*o->p[k0][j];
    tmp[i][j]=v;
  }
  const float q[6]={.02f,.02f,.00001f,.00001f,4.f,.0001f};
  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){
    float v=0;
#pragma GCC unroll 6
    for(unsigned k0=0;k0<6;k0++)v+=tmp[i][k0]*f[j][k0];
    cov[i][j]=v+(i==j?q[i]*dt:0);
  }
  o->nis=0;
  o->predicted_i[0]=o->x[0];o->predicted_i[1]=o->x[1];
  const float y[2]={ia,ib};
  for(unsigned ch=0;ch<2;ch++){
    const float r=.0004f,s=cov[ch][ch]+r,e=y[ch]-o->x[ch];float gain[6];
    o->innovation[ch]=e;o->innovation_variance[ch]=s;
    if(!isfinite(s)||s<=0)return MA_OBSERVER;
    o->nis+=e*e/s;
    for(unsigned i=0;i<6;i++){gain[i]=cov[i][ch]/s;o->x[i]+=gain[i]*e;}
    for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++)
      tmp[i][j]=cov[i][j]-gain[i]*cov[ch][j]-gain[j]*cov[i][ch]+gain[i]*gain[j]*s;
    memcpy(cov,tmp,sizeof(a));
  }
  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){
    o->p[i][j]=.5f*(cov[i][j]+cov[j][i]);
    if(!isfinite(o->p[i][j])||!isfinite(o->x[i]))return MA_OBSERVER;
  }
  if(fabsf(o->x[4])>900||hypotf(o->x[2],o->x[3])>2.0f)return MA_OBSERVER;
  if(o->steps>300&&o->nis>50)o->rejected++;else o->rejected=0;
  if(o->rejected>=20)return MA_OBSERVER;
  o->steps++;return MA_OK;
}
static inline float ma_margin(const ma_geometry*g,const uint32_t*c,
                             mic_current_window_plan p){
  if(!p.valid)return -1;
  float margin=(float)(g->latest-p.trigger);
  for(unsigned i=0;i<3;i++){
    const float v=c[i]<p.trigger?(float)(p.trigger-c[i]-g->settle):
                                          (float)(c[i]-p.trigger-g->acquire);
    if(v<margin)margin=v;
  }
  return margin;
}
/* Adaptive common-mode placement at FIXED 16 kHz. All three compare values move
 * together, preserving line voltage before timer quantisation. The same genuine
 * three-leg aperture planner is used by the ADC ISR. Never relax its guards.
 */
/* CCR inputs are nonnegative binary32 values bounded by the16-bit timer.
 * Exact halfway-away-from-zero rounding, including the float below0.5:
 * adding0.5 before conversion would double-round that boundary. Invalid input
 * fails closed; every caller rejects the sentinel before aperture planning. */
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || FLT_MAX_EXP != 128
#error "CCR rounding requires IEEE binary32"
#endif
typedef char ma_float_is_32_bits[(sizeof(float)==4)?1:-1];
static inline uint32_t ma_round_ccr(float value){
  uint32_t bits;memcpy(&bits,&value,sizeof(bits));
  if(bits==0x80000000U)return 0; /* negative zero */
  if(bits>0x477fff00U)return UINT32_MAX; /* negative, NaN, Inf, or >65535 */
  unsigned exponent=bits>>23;
  if(exponent<126U)return 0;
  unsigned shift=150U-exponent;
  uint32_t mantissa=(bits&0x7fffffU)|0x800000U;
  return (mantissa+(1U<<(shift-1U)))>>shift;
}
static inline int ma_modulate(ma_controller*c,const ma_geometry*g,int algorithm,
                              float va,float vb,float bus,ma_output*out){
  if(!g->arr||g->arr>65535||g->latest>=g->arr||g->settle>=g->arr||g->acquire>=g->arr||
    g->min_pulse*2>=g->arr||!isfinite(va)||!isfinite(vb)||!isfinite(bus)||bus<30||bus>350)return MA_BUS;
  const float phase[3]={va,-.5f*va+.8660254038f*vb,-.5f*va-.8660254038f*vb};
  const float hi=ma_max2(phase[0],ma_max2(phase[1],phase[2]));
  const float lo=ma_min2(phase[0],ma_min2(phase[1],phase[2]));
  float base[3];const float z=-.5f*(hi+lo),pulse=(float)g->min_pulse/g->arr;
  float lower=-1,upper=1;
  for(unsigned i=0;i<3;i++){
    base[i]=.5f+(phase[i]+z)/bus;
    lower=ma_max2(lower,pulse-base[i]);upper=ma_min2(upper,1-pulse-base[i]);
  }
  if(lower>upper)return MA_WINDOW;
  float target=0,best=-INFINITY;uint32_t cc[3];
  if(algorithm==MA_ADAPTIVE){
    /* Bounded three-candidate search, no variable-frequency carrier jitter. */
    const float candidates[3]={ma_clip(0,lower,upper),lower,upper};
    for(unsigned n=0;n<3;n++){
      for(unsigned i=0;i<3;i++){cc[i]=ma_round_ccr((base[i]+candidates[n])*g->arr);if(cc[i]>g->arr)return MA_WINDOW;}
      mic_current_window_plan p=mic_plan_current_window(cc[0],cc[1],cc[2],g->latest,g->settle,g->acquire);
      float score=p.valid?ma_margin(g,cc,p)-.02f*g->arr*fabsf(candidates[n]):-INFINITY;
      if(score>best){best=score;target=candidates[n];}
    }
    c->adaptive_steps++;
  }
  /* Limit shift slew, but never publish an unsafe intermediate aperture. */
  float shift=ma_clip(c->shift+ma_clip(target-c->shift,-.002f,.002f),lower,upper);
  mic_current_window_plan p;
  for(unsigned attempt=0;attempt<2;attempt++){
    for(unsigned i=0;i<3;i++){cc[i]=ma_round_ccr((base[i]+shift)*g->arr);if(cc[i]>g->arr)return MA_WINDOW;}
    p=mic_plan_current_window(cc[0],cc[1],cc[2],g->latest,g->settle,g->acquire);
    if(p.valid)break;
    shift=target;
  }
  if(!p.valid)return MA_WINDOW;
  c->shift=shift;out->shift=shift;out->trigger=p.trigger;out->pair=p.pair;
  for(unsigned i=0;i<3;i++){out->ccr[i]=cc[i];out->duty[i]=(float)cc[i]/g->arr;}
  /* Actual quantised average phase voltage, used by observer instead of request. */
  const float mean=(out->duty[0]+out->duty[1]+out->duty[2])/3;
  out->va=(out->duty[0]-mean)*bus;
  out->vb=(out->duty[1]-out->duty[2])*bus*.5773502692f;
  return MA_OK;
}
static inline __attribute__((always_inline)) int ma_control_checked(ma_controller*c,const ma_motor*m,const float*x,
    const ma_geometry*g,int algorithm,float ia,float ib,float reference_hz,
    float bus,float dt,int fresh,ma_output*out,int model_ok){
  memset(out,0,sizeof(*out));
  int fault=MA_OK;
  if(!model_ok||!isfinite(ia)||!isfinite(ib)||!isfinite(reference_hz)||
    reference_hz<0||reference_hz>50||!isfinite(dt)||dt<=0||dt>.0002f||
    (algorithm!=MA_FOC&&algorithm!=MA_ADAPTIVE))fault=MA_INVALID;
  else if(!fresh)fault=MA_STALE;
  else if(!isfinite(bus)||bus<30||bus>350)fault=MA_BUS;
  else if(hypotf(ia,ib)>m->trip_current)fault=MA_CURRENT;
  for(unsigned i=0;i<6;i++)if(!isfinite(x[i]))fault=MA_OBSERVER;
  if(fault){c->faults++;out->fault=(uint8_t)fault;return fault;}
  c->time_s+=dt;
  const float flux=ma_control_norm(x[2],x[3]);
  const float c0=flux>.0001f?x[2]/flux:1.f,s=flux>.0001f?x[3]/flux:0.f;
  const float id=c0*ia+s*ib,iq=-s*ia+c0*ib;
  const float idref=ma_min2(m->flux/m->lm,.9f*m->current_limit)*ma_min2(1,c->time_s/.10f);
  float iqref=0;
  if(c->time_s<.35f)c->speed_integral=0;
  else {
  const float iqmax=sqrtf(ma_max2(0,m->current_limit*m->current_limit-idref*idref));
  const float omega_ref=reference_hz*6.2831853072f/m->poles;
  const float speederr=omega_ref-x[4],kp=2*m->j*m->speed_bw,ki=m->j*m->speed_bw*m->speed_bw;
  const float tqgain=1.5f*m->poles*m->lm/m->lr*ma_max2(flux,.025f);
  const float raw=kp*speederr+c->speed_integral;
  iqref=ma_clip(raw/tqgain,-iqmax,iqmax);
  /* No regenerative torque request without a commissioned brake path. */
  if(x[4]>0&&iqref<0)iqref=0;
  if(c->time_s>=.35f){
    c->speed_integral+=dt*(ki*speederr+m->speed_bw*(tqgain*iqref-raw));
    c->speed_integral=ma_clip(c->speed_integral,-2*tqgain*m->current_limit,2*tqgain*m->current_limit);
  }
  }
  const float err[2]={idref-id,iqref-iq};
  const float kr=m->lm/m->lr,ar=m->rr/m->lr,l=m->ls-kr*m->lm;
  const float sync=ma_clip(m->poles*x[4]+ar*m->lm*iq/ma_max2(flux,.025f),-600,600);
  const float res=m->rs+kr*ar*m->lm;
  const float ff[2]={res*id-kr*ar*flux-sync*l*iq,
    res*iq+kr*m->poles*x[4]*flux+sync*l*id};
  float dq[2]={ff[0]+l*m->current_bw*err[0]+c->integral[0],
               ff[1]+l*m->current_bw*err[1]+c->integral[1]};
  const float limit=.90f*bus*.5773502692f,mag=ma_control_norm(dq[0],dq[1]);
  const float scale=ma_min2(1,limit/ma_max2(mag,1.e-9f));
  for(unsigned i=0;i<2;i++){
    const float limited=dq[i]*scale;
    c->integral[i]+=dt*(m->rs*m->current_bw*err[i]+m->current_bw*(limited-dq[i]));
    c->integral[i]=ma_clip(c->integral[i],-limit,limit);dq[i]=limited;
  }
  out->id_ref=idref;out->iq_ref=iqref;out->omega_est=x[4];out->flux=flux;
  out->id_measured=id;out->iq_measured=iq;
  const float requested_a=c0*dq[0]-s*dq[1],requested_b=s*dq[0]+c0*dq[1];
  const float loss=bus*g->deadtime_ticks/(2.f*g->arr);
  const float loss_phase[3]={loss*ma_current_polarity(ia),
    loss*ma_current_polarity((-.5f*ia+.8660254038f*ib)),
    loss*ma_current_polarity((-.5f*ia-.8660254038f*ib))};
  const float loss_a=(2*loss_phase[0]-loss_phase[1]-loss_phase[2])/3;
  const float loss_b=(loss_phase[1]-loss_phase[2])*.5773502692f;
  float aperture_scale=1;
  /* Project voltage into the measurable set, rather than counting edge samples
   * as current. Search is bounded, and failure still stops the actuator. */
  for(unsigned attempt=0;attempt<5;attempt++){
    fault=ma_modulate(c,g,algorithm,(requested_a+loss_a)*aperture_scale,(requested_b+loss_b)*aperture_scale,bus,out);
    if(fault!=MA_WINDOW)break;
    aperture_scale*=.85f;
  }
  if(fault){c->faults++;out->fault=(uint8_t)fault;return fault;}
  out->va-=loss_a;out->vb-=loss_b;
  /* Anti-windup must also see timer quantisation and aperture projection. */
  c->integral[0]+=dt*m->current_bw*(c0*(out->va-requested_a)+s*(out->vb-requested_b));
  c->integral[1]+=dt*m->current_bw*(-s*(out->va-requested_a)+c0*(out->vb-requested_b));
  c->last_va=out->va;c->last_vb=out->vb;out->valid=1;return MA_OK;
}
/* General callers validate the model here. The native IRQ uses the result
 * of the identical validation already performed in that SAME IRQ invocation;
 * no result is cached between frames and no foreground mutation can intervene. */
static inline int ma_control(ma_controller*c,const ma_motor*m,const float*x,
    const ma_geometry*g,int algorithm,float ia,float ib,float reference_hz,
    float bus,float dt,int fresh,ma_output*out){
  return ma_control_checked(c,m,x,g,algorithm,ia,ib,reference_hz,bus,dt,fresh,out,ma_motor_valid(m));
}


/* Calculated AIR56B2 candidate, explicitly NOT physical identification. */
#define FE_ESTIMATED_MOTOR {12.23f,11.00442222558575f,0.528093860573909f,0.528093860573909f,0.4944775988161633f,0.0002f,0.00014790613961630187f,1,0.25f,0.8f,1.35f,400.f,12.f}
enum {FE_ESTIMATED=128,FE_READY=1,FE_BUSY=2,FE_DONE=4,
      FE_FAST_BUDGET=4000,FE_OBSERVER_BUDGET=85000,FE_CASES=64};
static inline int fe_model_exact(const ma_motor*m){
 static const ma_motor expected=FE_ESTIMATED_MOTOR;
 /* expected is validated by release tests. Bit identity with that SAME
  * valid52-byte model implies the original ma_motor_valid predicate. Compare
  * every byte via memcpy words: no aliasing cast, rounding, CRC shortcut,
  * or cached result; a changed bit still rejects in the SAME invocation. */
 uint32_t difference=0;
#pragma GCC unroll 13
 for(unsigned i=0;i<13;++i){
  uint32_t a,b;memcpy(&a,(const uint8_t*)m+4*i,4);
  memcpy(&b,(const uint8_t*)&expected+4*i,4);difference|=a^b;
 }
 return difference==0;
}
static inline int fe_start_policy(unsigned kind,unsigned flags,unsigned algorithm,
                                 int manual,uint32_t limit_ms,float frequency){
 if(kind==7)return 1;
 return kind==FE_ESTIMATED&&(flags&FE_READY)&&!(flags&(FE_BUSY|FE_DONE))&&
  algorithm==MA_FOC&&!manual&&limit_ms==5000&&isfinite(frequency)&&frequency>0&&frequency<=5;
}
static inline int fe_time_up(uint32_t now,uint32_t begin,uint32_t clock){
 return (uint32_t)(now-begin)>=5U*clock;
}

}

static uint32_t rng=0x1503f04;static uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static float random_value(float lo,float hi){return lo+(hi-lo)*(next()>>8)*(1.f/16777216.f);}
static void norm(uint32_t x,uint32_t y){
 float a=value(x),b=value(y);core_calls=0;errno=0;float old=std::hypot(a,b);int old_errno=errno;
 errno=0;float now=candidate::ma_control_norm(a,b);int new_errno=errno;
 assert(word(old)==word(now)&&old_errno==new_errno);
 bool bounded=(x&0x7fffffffU)<=0x58800000U&&(y&0x7fffffffU)<=0x58800000U;
 assert(core_calls==(bounded?1U:0U));
}
int main(){
 static_assert(sizeof(baseline::ma_motor)==52&&sizeof(candidate::ma_motor)==52,"same full model ABI");
 baseline::ma_motor expected=FE_ESTIMATED_MOTOR;
 assert(baseline::ma_motor_valid(&expected));
 unsigned predicates=0;
 auto compare=[&](const baseline::ma_motor&m){candidate::ma_motor n;memcpy(&n,&m,52);
  bool a=baseline::fe_model_exact(&m),b=candidate::fe_model_exact(&n);
  assert(a==b&&b==(memcmp(&m,&expected,52)==0));++predicates;};
 compare(expected);
 for(unsigned bit=0;bit<416;++bit){auto m=expected;((uint8_t*)&m)[bit/8]^=(uint8_t)(1U<<(bit%8));compare(m);}
 for(unsigned n=0;n<250000;++n){
  auto m=expected;
  if(n&1)for(unsigned i=0;i<52;++i)((uint8_t*)&m)[i]=(uint8_t)next();
  else for(unsigned i=0;i<1+n%20;++i)((uint8_t*)&m)[next()%52]^=(uint8_t)next();
  compare(m);
 }
 for(int round:{FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO}){
  assert(std::fesetround(round)==0);assert(baseline::ma_motor_valid(&expected));compare(expected);
 }
 assert(std::fesetround(FE_TONEAREST)==0);
 unsigned norms=0;
 for(unsigned i=0;i<2000000;++i){norm(next(),next());++norms;}
 const uint32_t special[]={0U,0x80000000U,1U,0x80000001U,0x007fffffU,0x00800000U,
  0x3f800000U,0xbf800000U,0x58800000U,0x58800001U,0x7f7fffffU,0xff7fffffU,
  0x7f800000U,0xff800000U,0x7fc12345U,0x7f800001U,0xffc12345U};
 for(uint32_t a:special)for(uint32_t b:special){norm(a,b);++norms;}
 for(uint32_t a=0x58800000U-1024;a<=0x58800000U+1024;++a){norm(a,0x3f800000U);norm(a|0x80000000U,0x3f800000U);norm(0x3f800000U,a);norm(0x3f800000U,a|0x80000000U);norms+=4;}
 candidate::ma_motor cm;memcpy(&cm,&expected,52);
 baseline::ma_geometry g={5312,5184,771,112,240,229};candidate::ma_geometry cg;memcpy(&cg,&g,sizeof(g));
 unsigned controls=0,trips=0;
 for(unsigned i=0;i<200000;++i){
  baseline::ma_controller a={};a.time_s=random_value(0,5);a.integral[0]=random_value(-2,2);a.integral[1]=random_value(-2,2);a.speed_integral=random_value(-.1f,.1f);
  candidate::ma_controller b;memcpy(&b,&a,sizeof(b));
  float x[6]={random_value(-1,1),random_value(-1,1),random_value(.001f,.3f),random_value(-.2f,.2f),random_value(-10,40),0};
  float ia=random_value(-1.5f,1.5f),ib=random_value(-1.5f,1.5f),ref=random_value(0,5),bus=random_value(250,350);
  if(i%1000==0)ia=NAN;if(i%1000==1)ia=INFINITY;if(i%1000==2)ia=-0.f;
  baseline::ma_output oa;candidate::ma_output ob;int algo=i%2?2:3;
  int ra=baseline::ma_control(&a,&expected,x,&g,algo,ia,ib,ref,bus,1.f/16000,1,&oa);
  int rb=candidate::ma_control(&b,&cm,x,&cg,algo,ia,ib,ref,bus,1.f/16000,1,&ob);
  assert(ra==rb&&!memcmp(&a,&b,sizeof(a))&&!memcmp(&oa,&ob,sizeof(oa)));++controls;
 }
 for(float a:{std::nextafter(1.35f,0.f),1.35f,std::nextafter(1.35f,INFINITY)}){
  baseline::ma_controller ac={};candidate::ma_controller bc={};baseline::ma_output ao;candidate::ma_output bo;
  float x[6]={0,0,.25f,0,0,0};
  int r1=baseline::ma_control(&ac,&expected,x,&g,2,a,0,5,320,1.f/16000,1,&ao);
  int r2=candidate::ma_control(&bc,&cm,x,&cg,2,a,0,5,320,1.f/16000,1,&bo);
  assert(r1==r2&&((r1==baseline::MA_CURRENT)==(a>1.35f)));++trips;
 }
 printf("{\"exact_model_predicate_cases\":%u,\"all416_single_bit_mutations\":true,\"normal_rounding_modes\":4,\"hypot_dispatch_bit_exact_cases\":%u,\"controller_bit_exact_cases\":%u,\"raw135A_boundary_cases\":%u}\n",predicates,norms,controls,trips);
}
