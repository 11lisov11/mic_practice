#ifndef MIC_MULTI_MOTOR_CONTROL_H
#define MIC_MULTI_MOTOR_CONTROL_H
/* Portable actuator kernels. No GPIO, START, CLEAR, or protection-register access.
 * Units: star-equivalent SI parameters, phase peak A, mechanical rad/s, rotor Wb.
 * Simulation priors are not identified motor parameters or hardware qualification.
 */
#include <math.h>
#include <float.h>
#include <stdint.h>
#include <string.h>
#include "current_adc_window_plan.h"
#include "observer_pair_noise.h"
#ifdef __cplusplus
extern "C" {
#endif
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
  uint8_t preflux; /* 0 unused, 1 commanded current frame, 2 handed over */
  float start_cos,start_sin;
  float if_last_ia,if_last_ib;
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

static inline float ma_voltage_scale(float d,float q,float limit){
  /* Skip the norm only when rounding cannot change the already-unity scale.
   * Near or above saturation, keep the original norm, divide and clamp. */
  const float mag2=d*d+q*q;
  if(mag2<(limit*limit)*.99f)return 1.f;
  return ma_min2(1.f,limit/ma_max2(ma_control_norm(d,q),1.e-9f));
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
static inline int ma_observe_noise(ma_observer*o,const ma_motor*m,float ia,float ib,
                            float va,float vb,float dt,const ma_noise*noise){
  if(!noise||!isfinite(noise->aa)||!isfinite(noise->ab)||!isfinite(noise->bb)||
     noise->aa<=0||noise->bb<=0||noise->aa*noise->bb<=noise->ab*noise->ab)return MA_INVALID;
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
  /* Preserve the original fixed-R NIS watchdog independently of the corrected
   * measurement coordinates. Exact sequential/Joseph beta expression; no larger
   * noise matrix may hide an event from the existing >50/20-step stop. */
  const float gs0=cov[0][0]+.0004f,ge0=ia-o->x[0];
  if(!isfinite(gs0)||gs0<=0)return MA_OBSERVER;
  const float gk1=cov[1][0]/gs0;
  const float gs1=cov[1][1]-gk1*cov[0][1]-gk1*cov[1][0]+gk1*gk1*gs0+.0004f;
  const float ge1=ib-(o->x[1]+gk1*ge0);
  if(!isfinite(gs1)||gs1<=0)return MA_OBSERVER;
  const float guard_nis=ge0*ge0/gs0+ge1*ge1/gs1;
  if(!isfinite(guard_nis))return MA_OBSERVER;
  o->nis=0;
  o->predicted_i[0]=o->x[0];o->predicted_i[1]=o->x[1];
  const float y[2]={ia,ib};
  const float whiten=noise->ab/noise->aa;
  for(unsigned ch=0;ch<2;ch++){
    /* Whiten correlated measurement noise before sequential updates.
     * The second row is H=[-R_ab/R_aa,1], not a fictitious beta-only sample. */
    float ph[6],gain[6];
    for(unsigned i=0;i<6;++i)ph[i]=ch?cov[i][1]-whiten*cov[i][0]:cov[i][0];
    const float r=ch?noise->bb-whiten*noise->ab:noise->aa;
    const float s=(ch?ph[1]-whiten*ph[0]:ph[0])+r;
    const float e=ch?(y[1]-whiten*y[0])-(o->x[1]-whiten*o->x[0]):y[0]-o->x[0];
    o->innovation[ch]=e;o->innovation_variance[ch]=s;
    if(!isfinite(s)||s<=0)return MA_OBSERVER;
    o->nis+=e*e/s;
    for(unsigned i=0;i<6;i++){gain[i]=ph[i]/s;o->x[i]+=gain[i]*e;}
    for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++)
      tmp[i][j]=cov[i][j]-gain[i]*ph[j]-gain[j]*ph[i]+gain[i]*gain[j]*s;
    memcpy(cov,tmp,sizeof(a));
  }
  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){
    o->p[i][j]=.5f*(cov[i][j]+cov[j][i]);
    if(!isfinite(o->p[i][j])||!isfinite(o->x[i]))return MA_OBSERVER;
  }
  if(fabsf(o->x[4])>900||hypotf(o->x[2],o->x[3])>2.0f)return MA_OBSERVER;
  if(o->steps>300&&(guard_nis>50||o->nis>50))o->rejected++;else o->rejected=0;
  if(o->rejected>=20)return MA_OBSERVER;
  o->steps++;return MA_OK;
}
/* Historic caller/test compatibility: same diagonal observation model.
 * Production uses ma_observe_noise with actual16-frame pair composition. */
static inline int ma_observe(ma_observer*o,const ma_motor*m,float ia,float ib,
 float va,float vb,float dt){
 const ma_noise legacy={.0004f,0,.0004f};
 return ma_observe_noise(o,m,ia,ib,va,vb,dt,&legacy);
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
  /* The unsigned truncation fits 16 bits. Its conversion back to float is
   * exact, as is subtraction of the integer part. This avoids the double
   * rounding of adding 0.5f, and uses the M4's fixed-point conversion. */
  const uint32_t whole=(uint32_t)value;
  return whole+(uint32_t)(value-(float)whole>=.5f);
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
  /* The timer counts and ADC aperture are already fixed. Reuse the
   * scale solely for float duty telemetry and anti-windup feedback. */
  const float inv_arr=1.f/(float)g->arr;
  for(unsigned i=0;i<3;i++){out->ccr[i]=cc[i];out->duty[i]=(float)cc[i]*inv_arr;}
  /* Actual quantised average phase voltage, used by observer instead of request. */
  const float mean=(out->duty[0]+out->duty[1]+out->duty[2])/3;
  out->va=(out->duty[0]-mean)*bus;
  out->vb=(out->duty[1]-out->duty[2])*bus*.5773502692f;
  return MA_OK;
}
static inline __attribute__((always_inline)) int ma_control_with_speed_admission(ma_controller*c,const ma_motor*m,const float*x,
    const ma_geometry*g,int algorithm,float ia,float ib,float reference_hz,
    float bus,float dt,int fresh,ma_output*out,int model_ok,int speed_ready){
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
  if(!speed_ready&&c->preflux==0U){
    c->start_cos=1.f;c->start_sin=0.f;c->preflux=1U;
    c->if_last_ia=ia;c->if_last_ib=ib;
  }
  float c0=1.f,s=0.f,start_omega=0.f;
  int handover=0;
  if(c->preflux==1U){
    const float start_hz=c->time_s<.10f?0.f:ma_min2(reference_hz,5.f);
    start_omega=6.2831853072f*start_hz;
    c0=c->start_cos;s=c->start_sin;
    const float projection=c0*x[2]+s*x[3];
    if(speed_ready&&start_hz>=1.f&&flux>.0001f&&projection>=.92f*flux&&
       fabsf(m->poles*x[4]-start_omega)<=6.2831853072f){
      const float inv_flux=1.f/flux;
      c0=x[2]*inv_flux;s=x[3]*inv_flux;
      c->preflux=2U;
      handover=1;
    }else{
      const float delta=start_omega*dt;
      const float next_c=c0-delta*s,next_s=s+delta*c0;
      const float norm=1.5f-.5f*(next_c*next_c+next_s*next_s);
      c0=c->start_cos=next_c*norm;s=c->start_sin=next_s*norm;
      speed_ready=0;
    }
  }else if(flux>.0001f){c0=x[2]/flux;s=x[3]/flux;}
  /* During I/f only, attenuate alternating ADC-frame feedback before the
   * current PI. Raw ia/ib have already passed the original current trip.
   * Keep the dead-time polarity and the 16-frame observer input raw. */
  float feedback_ia=ia,feedback_ib=ib;
  if(c->preflux==1U){
    feedback_ia=.5f*(ia+c->if_last_ia);feedback_ib=.5f*(ib+c->if_last_ib);
    c->if_last_ia=ia;c->if_last_ib=ib;
  }
  const float id=c0*feedback_ia+s*feedback_ib,iq=-s*feedback_ia+c0*feedback_ib;
  const float idref=ma_min2(m->flux/m->lm,.9f*m->current_limit)*ma_min2(1,c->time_s/.10f);
  /* A provisional flux can establish magnetization, but an unqualified
   * speed must not command torque or enter speed feed-forward. */
  const float omega = speed_ready ? x[4] : 0.f;
  float iqref=0;
  if(c->time_s<.35f||!speed_ready)c->speed_integral=0;
  else {
  const float iqmax=sqrtf(ma_max2(0,m->current_limit*m->current_limit-idref*idref));
  const float omega_ref=reference_hz*6.2831853072f/m->poles;
  const float speederr=omega_ref-omega,kp=2*m->j*m->speed_bw,ki=m->j*m->speed_bw*m->speed_bw;
  const float tqgain=1.5f*m->poles*m->lm/m->lr*ma_max2(flux,.025f);
  const float raw=kp*speederr+c->speed_integral;
  iqref=ma_clip(raw/tqgain,-iqmax,iqmax);
  /* No regenerative torque request without a commissioned brake path. */
  if(omega>0&&iqref<0)iqref=0;
  if(c->time_s>=.35f){
    c->speed_integral+=dt*(ki*speederr+m->speed_bw*(tqgain*iqref-raw));
    c->speed_integral=ma_clip(c->speed_integral,-2*tqgain*m->current_limit,2*tqgain*m->current_limit);
  }
  }
  const float err[2]={idref-id,iqref-iq};
  const float kr=m->lm/m->lr,ar=m->rr/m->lr,l=m->ls-kr*m->lm;
  const float sync=c->preflux==1U?start_omega:ma_clip(m->poles*omega+ar*m->lm*iq/ma_max2(flux,.025f),-600,600);
  const float res=m->rs+kr*ar*m->lm;
  /* I/f is a current loop. Its feed-forward uses Rs and the commanded
   * rotation only, leaving flux and back-EMF compensation to closed-loop. */
  const float ff[2]={c->preflux==1U?m->rs*id-sync*l*iq:res*id-kr*ar*flux-sync*l*iq,
    c->preflux==1U?m->rs*iq+sync*l*id:res*iq+kr*m->poles*omega*flux+sync*l*id};
  const float kp_current=l*m->current_bw;
  const float vd=ff[0]+kp_current*err[0],vq=ff[1]+kp_current*err[1];
  if(handover){
    /* Track the last realizable stator voltage in the new frame. Rotating
     * the integral alone leaves the feed-forward and proportional steps. */
    c->integral[0]=c0*c->last_va+s*c->last_vb-vd;
    c->integral[1]=-s*c->last_va+c0*c->last_vb-vq;
  }
  float dq[2]={vd+c->integral[0],vq+c->integral[1]};
  const float limit=.90f*bus*.5773502692f;
  const float scale=ma_voltage_scale(dq[0],dq[1],limit);
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
static inline __attribute__((always_inline)) int ma_control_checked(ma_controller*c,
    const ma_motor*m,const float*x,const ma_geometry*g,int algorithm,float ia,float ib,
    float reference_hz,float bus,float dt,int fresh,ma_output*out,int model_ok){
  return ma_control_with_speed_admission(c,m,x,g,algorithm,ia,ib,reference_hz,bus,dt,
    fresh,out,model_ok,1);
}
/* General callers validate the model here. The native IRQ uses the result
 * of the identical validation already performed in that SAME IRQ invocation;
 * no result is cached between frames and no foreground mutation can intervene. */
static inline int ma_control(ma_controller*c,const ma_motor*m,const float*x,
    const ma_geometry*g,int algorithm,float ia,float ib,float reference_hz,
    float bus,float dt,int fresh,ma_output*out){
  return ma_control_checked(c,m,x,g,algorithm,ia,ib,reference_hz,bus,dt,fresh,out,ma_motor_valid(m));
}
#ifdef __cplusplus
}
#endif
#endif
