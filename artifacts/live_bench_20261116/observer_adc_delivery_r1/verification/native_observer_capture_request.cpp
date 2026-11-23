
#include <cassert>
#include <cstdio>
#include "foc_experiment.h"
#include "multi_native.h"
#include "observer_trace_core.h"
static ma_motor model=FE_ESTIMATED_MOTOR;static ma_observer observer;
static od_capture observer_trace;static int running=1,selected=MA_FOC,run_fault;
static struct{unsigned CYCCNT;} timer;static auto DWT=&timer;static int requests;
static bool LL_TIM_IsEnabledAllOutputs(void*){return true;}static void*TIM1;
static int fe_profile_allowed(unsigned){return 1;}
static float ma_amps(int16_t c){return c*(3.3f/(4095*.04f*2.1f));}
void mic_current_request_observer_capture(){++requests;}
static void ma_observer_record(const ma_current_sample*s,uint32_t stamp,uint32_t seq,uint32_t adc,
 float id,float iq,float idref,float iqref,float reference,float va,float vb,float dt,int fault,int published){
 if(observer_trace.frozen||!running||!LL_TIM_IsEnabledAllOutputs(TIM1))return;
 od_sample r;
 r.cycles=DWT->CYCCNT;r.steps=observer.steps;
 r.reasons=od_reasons(running,fe_profile_allowed(selected),observer.steps,run_fault||fault,
   hypotf(observer.x[2],observer.x[3]),model.flux,observer.nis);
 r.control_sequence=seq;r.control_adc_cycles=adc;
 r.observer_sequence=s->sequence;r.observer_adc_cycles=s->cycles;r.bin_cycles=stamp;
 r.rpm=observer.x[4]*9.549296586f;r.flux_alpha=observer.x[2];r.flux_beta=observer.x[3];r.nis=observer.nis;
 r.id=id;r.iq=iq;r.id_ref=idref;r.iq_ref=iqref;r.reference_hz=reference;
 r.ia=ma_amps(s->counts[0]);r.ib=(r.ia+2.f*ma_amps(s->counts[1]))*.5773502692f;
 r.va=va;r.vb=vb;r.dt=dt;
 for(unsigned i=0;i<2;++i){r.predicted_i[i]=observer.predicted_i[i];r.innovation[i]=observer.innovation[i];r.innovation_variance[i]=observer.innovation_variance[i];}
 for(unsigned i=0;i<3;++i)r.active_ccr[i]=s->ccr[i];
 r.bus_arr=(uint32_t)s->bus_v|((uint32_t)s->arr<<16);r.observer_fault=(uint32_t)fault;r.published=(uint32_t)published;
 od_push(&observer_trace,&r);
 /* First validity loss is immutable; request raw ADC around that event.
  * No diagnostic outcome changes observer/control validity or fault gates. */
 if(observer_trace.blob.header.first_loss_present&&
    observer_trace.blob.header.first_loss_step==r.steps&&(r.reasons&OD_NIS))
   mic_current_request_observer_capture();
}
static void push(unsigned step,float nis){observer.steps=step;observer.nis=nis;
 observer.x[2]=.25f;ma_current_sample s={};
 ma_observer_record(&s,1,1,1,0,0,0,0,1,0,0,.001f,0,1);}
int main(){push(499,100);assert(!requests);push(500,1);assert(!requests);
 push(501,38.9578f);assert(requests==1);auto old=observer_trace.blob.first_loss;
 for(unsigned n=502;n<550;++n)push(n,38);
 assert(requests==1&&!memcmp(&old,&observer_trace.blob.first_loss,sizeof(old)));
 assert(observer.nis==38&&observer.steps==549&&!run_fault);
 puts("{\"actual_native_recorder\":true,\"first_loss_only\":true,\"no_state_or_NIS_change\":true}");}
