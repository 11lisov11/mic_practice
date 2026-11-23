/* Independent double-precision flux-state plant drives the actual firmware C.
 * The estimator receives measured currents and applied voltage ONLY, never speed.
 */
#include "motor_control.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>
#include <random>
#include <vector>
struct Plant {
  double x[5]={};ma_motor m;double load=0;
  void current(const double*z,double&ia,double&ib)const{
    const double det=(double)m.ls*m.lr-(double)m.lm*m.lm;
    ia=(m.lr*z[0]-m.lm*z[2])/det;ib=(m.lr*z[1]-m.lm*z[3])/det;
  }
  void deriv(const double*z,double va,double vb,double*f)const{
    double ia,ib;current(z,ia,ib);
    const double det=(double)m.ls*m.lr-(double)m.lm*m.lm;
    const double ra=(-m.lm*z[0]+m.ls*z[2])/det,rb=(-m.lm*z[1]+m.ls*z[3])/det;
    f[0]=va-m.rs*ia;f[1]=vb-m.rs*ib;
    f[2]=-m.rr*ra-m.poles*z[4]*z[3];f[3]=-m.rr*rb+m.poles*z[4]*z[2];
    const double torque=1.5*m.poles*(z[0]*ib-z[1]*ia);
    f[4]=(torque-load-m.b*z[4])/m.j;
  }
  void step(double va,double vb,double dt){
    double k[4][5],z[5];deriv(x,va,vb,k[0]);
    for(int i=0;i<5;i++)z[i]=x[i]+dt*.5*k[0][i];deriv(z,va,vb,k[1]);
    for(int i=0;i<5;i++)z[i]=x[i]+dt*.5*k[1][i];deriv(z,va,vb,k[2]);
    for(int i=0;i<5;i++)z[i]=x[i]+dt*k[2][i];deriv(z,va,vb,k[3]);
    for(int i=0;i<5;i++)x[i]+=dt*(k[0][i]+2*k[1][i]+2*k[2][i]+k[3][i])/6;
  }
};
static ma_motor prior(){return {12.23f,10.f,.9f,.9f,.84f,.0003f,.00015f,1,
  .35f,1.1f,1.35f,400.f,12.f};}
static ma_geometry geometry(){return {5312,5184,771,112,240,229};}
static int run(int algo,float mismatch,float noise,float dt_error=0){
  ma_motor m=prior();Plant plant;plant.m=m;plant.m.rs*=mismatch;plant.m.rr*=mismatch;
  ma_observer obs;ma_controller ctl;ma_reset(&obs,&ctl);ma_output out={};
  const ma_geometry g=geometry();const float dt=1.f/16000;
  double vmax=0,imax=0,eref=0,speed_error=0,va_sum=0,vb_sum=0,minmargin=1e9;
  unsigned count=0,valid=0,errcount=0,fail=0;std::mt19937 rng(73);
  std::normal_distribution<float> n(0,noise);
  for(unsigned step=0;step<16000*14;step++){
    double time=step*dt;
    float ref=time<1?0:time<3?5:time<5?20:time<7?35:time<9?50:time<11?25:5;
    double ia,ib;plant.current(plant.x,ia,ib);float ma=(float)ia+n(rng),mb=(float)ib+n(rng);
    if(step&&step%16==0){
      int rc=ma_observe(&obs,&m,ma,mb,(float)(va_sum/16),(float)(vb_sum/16),.001f);
      va_sum=vb_sum=0;if(rc){fail=rc;break;}
    }
    int rc=ma_control(&ctl,&m,obs.x,&g,algo,ma,mb,ref,320,dt,1,&out);
    if(rc){fail=rc;break;}
    imax=std::max(imax,hypot(ia,ib));vmax=std::max(vmax,(double)hypotf(out.va,out.vb));
    minmargin=std::min(minmargin,(double)ma_margin(&g,out.ccr,{out.trigger,out.pair,out.valid}));
    valid+=mic_current_window_safe(out.pair,out.ccr[0],out.ccr[1],out.ccr[2],out.trigger,g.settle,g.acquire);
    // Independent inverter: generate physical phase voltage from quantised duty
    // then subtract current-polarity deadtime loss, rather than applying out.va.
    const double phase_i[3]={ia,-.5*ia+.8660254037844386*ib,-.5*ia-.8660254037844386*ib};
    double vphase[3];for(int i=0;i<3;i++)vphase[i]=320.*out.duty[i]-
      std::clamp(phase_i[i]/.05,-1.,1.)*320.*g.deadtime_ticks/(2*g.arr)*(1+dt_error);
    double applied_a=(2*vphase[0]-vphase[1]-vphase[2])/3,applied_b=(vphase[1]-vphase[2])/sqrt(3.);
    plant.step(applied_a,applied_b,dt);va_sum+=out.va;vb_sum+=out.vb;count++;
    if(time>1&&fmod(time-1.,2.)>1.5){
      double expected=ref*6.283185307179586/m.poles;
      speed_error+=fabs(plant.x[4]-expected);eref+=fabs(plant.x[4]-obs.x[4]);errcount++;
    }
  }
  const double track=errcount?speed_error/errcount:999,estimate=errcount?eref/errcount:999;
  bool pass=!fail&&count==16000*14&&valid==count&&imax<m.trip_current&&track<5&&estimate<5;
  printf("{\"algorithm\":%d,\"rs_rr_factor\":%.3f,\"noise_A\":%.4f,\"deadtime_error_fraction\":%.3f,\"samples\":%u,\"fault\":%u,\"coverage\":%.7f,\"peak_A\":%.6f,\"mean_tracking_error_rad_s\":%.6f,\"mean_estimator_error_rad_s\":%.6f,\"max_voltage\":%.5f,\"minimum_margin_ticks\":%.1f,\"adaptive_steps\":%u,\"passed\":%s}\n",
    algo,mismatch,noise,dt_error,count,fail,count?(double)valid/count:0,imax,track,estimate,vmax,minmargin,ctl.adaptive_steps,pass?"true":"false");
  return pass?0:1;
}
static void properties(){
  ma_motor m=prior();ma_observer o;ma_controller c;ma_reset(&o,&c);ma_output out;
  auto g=geometry();assert(ma_motor_valid(&m));
  assert(ma_control(&c,&m,o.x,&g,MA_FOC,0,0,5,320,1.f/16000,0,&out)==MA_STALE&&!out.valid);
  assert(ma_control(&c,&m,o.x,&g,MA_FOC,2,0,5,320,1.f/16000,1,&out)==MA_CURRENT&&!out.valid);
  assert(ma_control(&c,&m,o.x,&g,MA_FOC,0,0,5,351,1.f/16000,1,&out)==MA_BUS&&!out.valid);
  ma_motor bad=m;bad.lm=2;assert(!ma_motor_valid(&bad));
  o.x[0]=NAN;assert(ma_control(&c,&m,o.x,&g,MA_FOC,0,0,5,320,1.f/16000,1,&out)==MA_OBSERVER&&!out.valid);
  /* Exhaust phase angle and amplitude: compare accepted duty line voltage and
   * all three edge guards for both modulations. Invalid windows never actuate. */
  for(int angle=0;angle<720;angle++)for(int amp=0;amp<=165;amp++){
    float va=amp*cosf(angle*.00872664626f),vb=amp*sinf(angle*.00872664626f);
    for(int algo=MA_FOC;algo<=MA_ADAPTIVE;algo++){
      ma_output q={};int rc=ma_modulate(&c,&g,algo,va,vb,320,&q);
      if(!rc){
        assert(mic_current_window_safe(q.pair,q.ccr[0],q.ccr[1],q.ccr[2],q.trigger,g.settle,g.acquire));
        assert(hypotf(q.va-va,q.vb-vb)<.1f);
        for(int i=0;i<3;i++)assert(q.ccr[i]>=g.min_pulse&&q.ccr[i]<=g.arr-g.min_pulse);
      }
    }
  }
}
int main(){properties();int bad=0;
  for(int algo=MA_FOC;algo<=MA_ADAPTIVE;algo++){
    bad+=run(algo,1,0);bad+=run(algo,1,.002f);bad+=run(algo,1.1f,.002f);
    bad+=run(algo,1,.002f,.1f);
  }return bad?1:0;
}
