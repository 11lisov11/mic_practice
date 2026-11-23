/* Offline sensitivity study. Uses the installed C controller, not board commands.
 * Recorded OFF-state ADC errors are transferred to a simulated motor. This is
 * neither a replay of running-motor currents nor physical FOC qualification. */
#define main original_model_test_main
#include "model_test.cpp"
#undef main
#include "current_core.h"
#include "recorded_noise_data.h"

static ma_motor configured_controller,configured_plant;
static constexpr double amp_per_count=3.3/(4095*.04*2.1);

static int stress(int algo,int capture,int resample,unsigned seed,float mismatch,
                  int spike_step=-1,int trajectory=0) {
  ma_motor m=configured_controller;Plant plant;plant.m=configured_plant;
  plant.m.rs*=mismatch;plant.m.rr*=mismatch;
  ma_observer obs;ma_controller ctl;ma_reset(&obs,&ctl);ma_output out={};
  const ma_geometry g=geometry();const float dt=1.f/16000;
  cm_core zero;cm_init(&zero);
  for(int k=0;k<4;k++)zero.offset[k]=2068;
  std::mt19937 rng(seed);std::uniform_int_distribution<unsigned> choose(0,127);
  unsigned count=0,valid=0,errcount=0,fail=0,pairs[3]={},observer_calls=0;
  double imax=0,measuredmax=0,eref=0,track_error=0,va_sum=0,vb_sum=0;
  double sum_error2=0,maxnis=0,minmargin=1e9;
  unsigned maxrejected=0;const char* fault_stage="none";bool spike_applied=false;
  unsigned total_steps=16000U*(trajectory==1?5U:14U);
  for(unsigned step=0;step<total_steps;step++) {
    const double time=step*dt;
    const float ref=trajectory==1?5.f:trajectory==2?(float)std::min(50.,5*time):
      time<1?0:time<3?5:time<5?20:time<7?35:time<9?50:time<11?25:5;
    double ia,ib;plant.current(plant.x,ia,ib);
    float ma=(float)ia,mb=(float)ib;
    unsigned pair=out.valid?out.pair:0;assert(pair<3);pairs[pair]++;
    if(capture>=0) {
      unsigned row=resample?choose(rng):(step+seed)%128;
      // Pair1 has no simultaneous U1/W2 OFF capture: transfer U1/V2 errors.
      // The report explicitly identifies this as a sensitivity assumption.
      const auto& n=noise_data[capture][pair==2?1:0][row];
      const double phase[3]={ia,-.5*ia+.8660254037844386*ib,
                                -.5*ia-.8660254037844386*ib};
      unsigned first=pair==2?1:0,second=pair==0?1:2;
      long a=lround(zero.offset[cm_path1(pair)]-phase[first]/amp_per_count+n.a);
      long b=lround(zero.offset[cm_path2(pair)]-phase[second]/amp_per_count+n.b);
      assert(a>=16&&a<=4079&&b>=16&&b<=4079);
      int16_t current[3];assert(cm_reconstruct(&zero,(uint8_t)pair,
                                             (uint16_t)a,(uint16_t)b,current));
      ma=(float)(current[0]*amp_per_count);
      mb=(float)((current[0]+2*current[1])*amp_per_count*.5773502692);
    }
    // An isolated recorded 0.604A vector is an additive stress, not a claim
    // that the measured physical trip was entirely noise.
    if((int)step==spike_step){ma+=.6043956044f;mb+=.0055388566f;spike_applied=true;}
    sum_error2+=(ma-ia)*(ma-ia)+(mb-ib)*(mb-ib);
    imax=std::max(imax,hypot(ia,ib));
    measuredmax=std::max(measuredmax,(double)hypotf(ma,mb));
    if(step&&step%16==0) {
      int rc=ma_observe(&obs,&m,ma,mb,(float)(va_sum/16),(float)(vb_sum/16),.001f);
      va_sum=vb_sum=0;observer_calls++;
      maxnis=std::max(maxnis,(double)obs.nis);
      maxrejected=std::max(maxrejected,obs.rejected);
      if(rc){fail=rc;fault_stage="observer";break;}
    }
    int rc=ma_control(&ctl,&m,obs.x,&g,algo,ma,mb,ref,320,dt,1,&out);
    if(rc){fail=rc;fault_stage="control";break;}
    minmargin=std::min(minmargin,(double)ma_margin(&g,out.ccr,
                                            {out.trigger,out.pair,out.valid}));
    valid+=mic_current_window_safe(out.pair,out.ccr[0],out.ccr[1],out.ccr[2],
                                   out.trigger,g.settle,g.acquire);
    const double phase_i[3]={ia,-.5*ia+.8660254037844386*ib,
                               -.5*ia-.8660254037844386*ib};
    double vphase[3];for(int k=0;k<3;k++)
      vphase[k]=320.*out.duty[k]-std::clamp(phase_i[k]/.05,-1.,1.)*
        320.*g.deadtime_ticks/(2*g.arr);
    plant.step((2*vphase[0]-vphase[1]-vphase[2])/3,
               (vphase[1]-vphase[2])/sqrt(3.),dt);
    va_sum+=out.va;vb_sum+=out.vb;count++;
    if((trajectory==0&&time>1&&fmod(time-1.,2.)>1.5)||
       (trajectory==1&&time>3.5)||(trajectory==2&&time>12)) {
      double expected=ref*6.283185307179586/m.poles;
      track_error+=fabs(plant.x[4]-expected);
      eref+=fabs(plant.x[4]-obs.x[4]);errcount++;
    }
  }
  double track=errcount?track_error/errcount:999,estimate=errcount?eref/errcount:999;
  bool pass=!fail&&count==total_steps&&valid==count&&imax<m.trip_current&&track<5&&estimate<5;
  printf("{\"algorithm\":%d,\"trajectory\":%d,\"capture\":%d,\"resample_rows\":%s,\"seed\":%u,"
    "\"rs_rr_factor\":%.3f,\"spike_step\":%d,\"samples\":%u,\"fault\":%u,"
    "\"fault_stage\":\"%s\",\"spike_applied\":%s,\"coverage\":%.7f,\"true_peak_A\":%.6f,"
    "\"measured_peak_A\":%.6f,\"mean_tracking_error_rad_s\":%.6f,"
    "\"mean_estimator_error_rad_s\":%.6f,\"vector_measurement_error_rms_A\":%.6f,"
    "\"observer_calls\":%u,\"max_nis\":%.6f,\"max_consecutive_rejected\":%u,"
    "\"pair_counts\":[%u,%u,%u],\"minimum_margin_ticks\":%.1f,\"passed\":%s}\n",
    algo,trajectory,capture,resample?"true":"false",seed,mismatch,spike_step,count,fail,
    fault_stage,spike_applied?"true":"false",count?(double)valid/count:0,imax,measuredmax,track,estimate,
    sqrt(sum_error2/(count+!!fail)),observer_calls,maxnis,maxrejected,
    pairs[0],pairs[1],pairs[2],minmargin,pass?"true":"false");
  return pass?0:1;
}


int main(){properties();int bad=0;
configured_controller={12.23f,11.0044222256f,0.528093860574f,0.528093860574f,0.494477598816f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
assert(ma_motor_valid(&configured_controller));
configured_plant={12.23f,11.0044222256f,0.528093860574f,0.528093860574f,0.494477598816f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,11.2776819671f,0.524701454202f,0.524701454202f,0.491282504433f,0.0002f,7.39530698082e-05f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,10.6584297473f,0.532871645036f,0.532871645036f,0.498987926874f,0.0002f,0.000246510232694f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,11.4348563254f,0.525475579204f,0.546099998673f,0.501413756491f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,10.5940160332f,0.530708765638f,0.510882880569f,0.487752681322f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,11.0044222256f,0.528093860574f,0.528093860574f,0.494477598816f,7e-05f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,11.0044222256f,0.528093860574f,0.528093860574f,0.494477598816f,0.0004f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={8.561f,11.0044222256f,0.528093860574f,0.528093860574f,0.494477598816f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={17.122f,11.0044222256f,0.528093860574f,0.528093860574f,0.494477598816f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,6.60265333535f,0.528093860574f,0.528093860574f,0.494477598816f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,15.4061911158f,0.528093860574f,0.528093860574f,0.494477598816f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,11.0044222256f,0.379750580929f,0.379750580929f,0.346134319171f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,11.0044222256f,0.676437140219f,0.676437140219f,0.642820878461f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,11.0044222256f,0.511285729695f,0.511285729695f,0.494477598816f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
configured_plant={12.23f,11.0044222256f,0.544901991453f,0.544901991453f,0.494477598816f,0.0002f,0.000147906139616f,1,0.25f,0.8f,1.35f,400.f,12.f};
bad+=stress(2,0,1,73,1,-1,1);
bad+=stress(2,0,1,73,1,-1,2);
bad+=stress(3,0,1,73,1,-1,1);
bad+=stress(3,0,1,73,1,-1,2);
return bad?1:0;}
